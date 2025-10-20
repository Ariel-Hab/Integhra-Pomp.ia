# actions/models/model_manager.py

import os
import hashlib
import logging
import time
from typing import Optional, Dict, Any

from openai import OpenAI
from dotenv import load_dotenv
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

load_dotenv()
logger = logging.getLogger(__name__)

# ============== CONFIGURACIÓN SIMPLIFICADA ==============
SYSTEM_PROMPT = """Sos Pompi, asistente veterinario argentino.
Respuestas cortas: máximo 2 oraciones.
Siempre preguntá qué necesita."""

RESPONSE_CACHE = {}
MAX_CACHE_SIZE = 50

# Timeout para la generación de la respuesta completa.
GENERATION_TIMEOUT = 8
OLLAMA_CLIENT_TIMEOUT = 10

# Configuración del modelo
MODEL_NAME = "llama3:8b-instruct-q4_0"
MAX_TOKENS_DEFAULT = 150
# =======================================================

# ✅ NUEVO: Mensajes de fallback por tipo de error
FALLBACK_MESSAGES = {
    'timeout': "Estoy procesando tu consulta. ¿En qué más puedo ayudarte?",
    'connection_error': "Tengo un problema técnico temporal. ¿Podrías reformular tu pregunta?",
    'validation_error': "No pude generar una respuesta adecuada. ¿Podrías ser más específico?",
    'default': "¿En qué puedo ayudarte?"
}


class ChatModel:
    """Modelo Ollama optimizado para generar respuestas completas con timeout."""
    failed_attempts = 0
    
    def __init__(self):
        self.client = None
        
    def load(self):
        """Carga y valida la conexión con el cliente de Ollama."""
        if self.client is not None:
            return
        try:
            self.client = OpenAI(
                base_url='http://localhost:11434/v1',
                api_key='ollama',
                timeout=OLLAMA_CLIENT_TIMEOUT
            )
            self.client.models.list()
            logger.info("✅ Conexión con Ollama (local) establecida")
        except Exception as e:
            logger.error(f"❌ No se pudo conectar a Ollama. Error: {e}")
            self.client = None
            raise ConnectionError("Fallo al conectar con el servidor local de Ollama.")
    
    def generate(self, user_prompt: str, max_new_tokens: int = 100, 
                 temperature: float = 0.3) -> Dict[str, Any]:
        """
        ✅ MODIFICADO: Ahora retorna un dict con resultado y metadata
        
        Returns:
            {
                'success': bool,
                'text': str o None,
                'error_type': str o None,
                'fallback_message': str o None
            }
        """
        cache_key = hashlib.md5(f"{user_prompt}_{max_new_tokens}_{temperature}".encode()).hexdigest()
        
        # Cache hit
        if cache_key in RESPONSE_CACHE:
            logger.info("✅ Respuesta devuelta desde caché.")
            return {
                'success': True,
                'text': RESPONSE_CACHE[cache_key],
                'error_type': None,
                'fallback_message': None
            }
        
        # Intentar cargar cliente
        try:
            self.load()
        except ConnectionError:
            return {
                'success': False,
                'text': None,
                'error_type': 'connection_error',
                'fallback_message': FALLBACK_MESSAGES['connection_error']
            }

        if not self.client:
            return {
                'success': False,
                'text': None,
                'error_type': 'connection_error',
                'fallback_message': FALLBACK_MESSAGES['connection_error']
            }

        try:
            start_time = time.time()
            logger.info(f"[Generate] Iniciando generación (timeout: {GENERATION_TIMEOUT}s)...")
            
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                model=MODEL_NAME,
                temperature=temperature,
                max_tokens=max_new_tokens,
                stream=False,
                timeout=GENERATION_TIMEOUT
            )
            
            elapsed = time.time() - start_time
            result = self._validate_response(response.choices[0].message.content)
            
            if result:
                self._update_cache(cache_key, result)
                self.failed_attempts = 0
                logger.info(f"[Generate] ✓ Respuesta generada en {elapsed:.2f}s")
                return {
                    'success': True,
                    'text': result,
                    'error_type': None,
                    'fallback_message': None
                }
            else:
                logger.warning("[Generate] La respuesta del modelo fue inválida o vacía.")
                return {
                    'success': False,
                    'text': None,
                    'error_type': 'validation_error',
                    'fallback_message': FALLBACK_MESSAGES['validation_error']
                }

        except Exception as e:
            elapsed = time.time() - start_time
            self.failed_attempts += 1
            
            # Detectar tipo de error
            error_str = str(e).lower()
            if 'timeout' in error_str or elapsed >= GENERATION_TIMEOUT:
                error_type = 'timeout'
            elif 'connection' in error_str:
                error_type = 'connection_error'
            else:
                error_type = 'default'
            
            logger.error(f"❌ Intento {self.failed_attempts}/3 falló ({error_type}) tras {elapsed:.2f}s: {e}")
            
            if self.failed_attempts >= 3:
                logger.critical("❌ Se superó el máximo de reintentos. El modelo no responderá.")
            
            return {
                'success': False,
                'text': None,
                'error_type': error_type,
                'fallback_message': FALLBACK_MESSAGES.get(error_type, FALLBACK_MESSAGES['default'])
            }

    def _validate_response(self, result: str) -> Optional[str]:
        """Valida y limpia la respuesta del modelo."""
        if not result or len(result.strip()) < 5:
            return None
        
        clean_result = result.strip()
        for prefix in ["Bot:", "Pompi:", "Respuesta:", "R:"]:
            if clean_result.startswith(prefix):
                clean_result = clean_result[len(prefix):].strip()
        
        return clean_result if clean_result else None
    
    def _update_cache(self, key: str, value: str):
        """Actualiza el caché con límite de tamaño."""
        if len(RESPONSE_CACHE) >= MAX_CACHE_SIZE:
            oldest_key = next(iter(RESPONSE_CACHE))
            del RESPONSE_CACHE[oldest_key]
        RESPONSE_CACHE[key] = value


# ============== INSTANCIA GLOBAL ==============
_chat_model = ChatModel()


def generate_text_with_context(
    prompt: str, 
    tracker: Optional[Tracker] = None, 
    dispatcher: Optional[CollectingDispatcher] = None,
    fallback_template: Optional[str] = None,
    max_new_tokens: int = 150, 
    temperature: float = 0.3
) -> Optional[str]:
    """
    ✅ MODIFICADO: Función principal con manejo automático de fallback
    
    Args:
        prompt: El prompt para el modelo
        tracker: Tracker de Rasa para contexto
        dispatcher: Dispatcher para enviar mensajes de fallback
        fallback_template: Template de Rasa a usar como fallback (ej: "utter_default")
        max_new_tokens: Máximo de tokens a generar
        temperature: Temperatura del modelo
    
    Returns:
        str: Texto generado o mensaje de fallback
        None: Solo si no hay dispatcher para enviar fallback
    """
    try:
        # Construir contexto
        context_info = _build_lightweight_context(tracker) if tracker else ""
        full_prompt = f"Contexto de la conversación:\n{context_info}\n\nInstrucción:\n{prompt}" if context_info else prompt
        
        # Generar respuesta
        result = _chat_model.generate(full_prompt, max_new_tokens, temperature)
        
        # ✅ Caso exitoso
        if result['success']:
            return result['text']
        
        # ✅ Caso de error: usar fallback
        logger.warning(f"[ModelManager] Generación falló ({result['error_type']}). Usando fallback.")
        
        fallback_text = None
        
        # Prioridad 1: Template de Rasa
        if dispatcher and fallback_template:
            try:
                dispatcher.utter_message(template=fallback_template)
                logger.info(f"[ModelManager] ✅ Enviado template de fallback: {fallback_template}")
                # Retornar el texto del fallback para mantener compatibilidad
                fallback_text = f"fallback:{fallback_template}"
            except Exception as e:
                logger.error(f"[ModelManager] Error enviando template {fallback_template}: {e}")
        
        # Prioridad 2: Mensaje genérico del model_manager
        if not fallback_text and dispatcher:
            fallback_text = result['fallback_message']
            dispatcher.utter_message(text=fallback_text)
            logger.info(f"[ModelManager] ✅ Enviado mensaje de fallback genérico")
        
        # Prioridad 3: Solo retornar texto (sin dispatcher)
        if not fallback_text:
            fallback_text = result['fallback_message']
        
        return fallback_text
        
    except Exception as e:
        logger.error(f"[ModelManager] Error inesperado en generate_text_with_context: {e}", exc_info=True)
        
        # Último recurso: enviar mensaje genérico
        if dispatcher:
            dispatcher.utter_message(text=FALLBACK_MESSAGES['default'])
            return FALLBACK_MESSAGES['default']
        
        return None


def generate_with_safe_fallback(
    prompt: str,
    dispatcher: CollectingDispatcher,
    tracker: Optional[Tracker] = None,
    fallback_template: str = "utter_default",
    max_new_tokens: int = 150,
    temperature: float = 0.3
) -> str:
    """
    ✅ NUEVA FUNCIÓN: Wrapper seguro que SIEMPRE envía un mensaje
    
    Garantiza que Flutter siempre reciba una respuesta, ya sea del modelo
    o un fallback apropiado.
    
    Returns:
        str: Siempre retorna algún texto (nunca None)
    """
    result = generate_text_with_context(
        prompt=prompt,
        tracker=tracker,
        dispatcher=dispatcher,
        fallback_template=fallback_template,
        max_new_tokens=max_new_tokens,
        temperature=temperature
    )
    
    # Garantizar que siempre hay un mensaje
    if not result:
        fallback = FALLBACK_MESSAGES['default']
        dispatcher.utter_message(text=fallback)
        return fallback
    
    return result


def _build_lightweight_context(tracker: Tracker) -> str:
    """Construye contexto ligero desde el tracker."""
    try:
        context_parts = []
        search_history = tracker.get_slot('search_history')
        if search_history:
            last_search = search_history[-1]
            params = last_search.get('parameters', {})
            if params:
                params_str = ", ".join([f"{k}='{v}'" for k, v in params.items()])
                context_parts.append(f"El usuario está buscando con estos filtros: {params_str}")
        
        return "\n".join(context_parts)
    except Exception:
        return ""