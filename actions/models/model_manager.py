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

# ============== CONFIGURACIÓN ==============
SYSTEM_PROMPT = """Sos Pompi, asistente veterinario argentino.
Respuestas cortas: máximo 2 oraciones.
Siempre preguntá qué necesita."""

RESPONSE_CACHE = {}
MAX_CACHE_SIZE = 50

GENERATION_TIMEOUT = 8
OLLAMA_CLIENT_TIMEOUT = 10

MODEL_NAME = "llama3:8b-instruct-q4_0"
MAX_TOKENS_DEFAULT = 150
# ===========================================

# Mensajes de fallback por tipo de error
FALLBACK_MESSAGES = {
    'timeout': "Estoy procesando tu consulta. ¿En qué más puedo ayudarte?",
    'connection_error': "Tengo un problema técnico temporal. ¿Podrías reformular tu pregunta?",
    'validation_error': "No pude generar una respuesta adecuada. ¿Podrías ser más específico?",
    'default': "¿En qué puedo ayudarte?"
}


class ChatModel:
    """Modelo Ollama optimizado para generar respuestas con timeout."""
    failed_attempts = 0
    
    def __init__(self):
        self.client = None
        
    def load(self):
        """Carga y valida la conexión con Ollama."""
        if self.client is not None:
            return
        try:
            self.client = OpenAI(
                base_url='http://localhost:11434/v1',
                api_key='ollama',
                timeout=OLLAMA_CLIENT_TIMEOUT
            )
            self.client.models.list()
            logger.info("✅ Conexión con Ollama establecida")
        except Exception as e:
            logger.error(f"❌ Error conectando a Ollama: {e}")
            self.client = None
            raise ConnectionError("Fallo al conectar con Ollama.")
    
    def generate(self, user_prompt: str, max_new_tokens: int = 100, 
                 temperature: float = 0.3) -> Dict[str, Any]:
        """
        Genera respuesta con el modelo.
        
        Returns:
            {
                'success': bool,
                'text': str | None,
                'error_type': str | None,
                'fallback_message': str | None
            }
        """
        # NUEVO: Log de parámetros de generación
        generation_params = {
            "model": MODEL_NAME,
            "max_tokens": max_new_tokens,
            "temperature": temperature
        }
        logger.info(f"[Generate] New request. Params: {generation_params}")

        cache_key = hashlib.md5(
            f"{user_prompt}_{max_new_tokens}_{temperature}".encode()
        ).hexdigest()
        
        # Cache hit
        if cache_key in RESPONSE_CACHE:
            logger.info("✅ Respuesta desde caché")
            return {
                'success': True,
                'text': RESPONSE_CACHE[cache_key],
                'error_type': None,
                'fallback_message': None
            }
        
        # Cargar cliente
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

        start_time = time.time()
        try:
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
                logger.info(f"[Generate] ✓ Generado en {elapsed:.2f}s")
                return {
                    'success': True,
                    'text': result,
                    'error_type': None,
                    'fallback_message': None
                }
            else:
                logger.warning(f"[Generate] Respuesta inválida o vacía tras {elapsed:.2f}s")
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
            
            logger.error(
                f"❌ Intento {self.failed_attempts}/3 falló "
                f"({error_type}) tras {elapsed:.2f}s: {e}"
            )
            
            if self.failed_attempts >= 3:
                logger.critical("❌ Máximo de reintentos alcanzado")
            
            return {
                'success': False,
                'text': None,
                'error_type': error_type,
                'fallback_message': FALLBACK_MESSAGES.get(
                    error_type, 
                    FALLBACK_MESSAGES['default']
                )
            }

    def _validate_response(self, result: str) -> Optional[str]:
        """Valida y limpia la respuesta."""
        if not result or len(result.strip()) < 5:
            return None
        
        clean_result = result.strip()
        for prefix in ["Bot:", "Pompi:", "Respuesta:", "R:"]:
            if clean_result.startswith(prefix):
                clean_result = clean_result[len(prefix):].strip()
        
        return clean_result if clean_result else None
    
    def _update_cache(self, key: str, value: str):
        """Actualiza el caché con límite."""
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
    ✅ FUNCIÓN PRINCIPAL - SIEMPRE ENVÍA MENSAJE CUANDO HAY DISPATCHER
    
    COMPORTAMIENTO GARANTIZADO:
    - Si hay dispatcher: SIEMPRE envía mensaje (éxito o fallback) y retorna None
    - Si NO hay dispatcher: retorna el texto generado o mensaje de fallback
    """
    start_time = time.time() # NUEVO: Inicia el cronómetro para toda la operación
    try:
        # Construir contexto
        context_info = _build_lightweight_context(tracker) if tracker else ""
        full_prompt = (
            f"Contexto de la conversación:\n{context_info}\n\nInstrucción:\n{prompt}"
            if context_info else prompt
        )
        
        # Generar respuesta
        result = _chat_model.generate(full_prompt, max_new_tokens, temperature)
        total_duration = time.time() - start_time # NUEVO: Calcula la duración total

        # ✅ CASO 1: Generación exitosa
        if result['success'] and result['text']:
            logger.info(f"[ModelManager] ✅ Generation successful in {total_duration:.2f}s")
            
            if dispatcher:
                dispatcher.utter_message(text=result['text'])
                logger.info("[ModelManager] ✅ Mensaje enviado al usuario")
                return None
            
            return result['text']
        
        # ❌ CASO 2: Generación falló - usar fallback
        error_type = result.get('error_type', 'unknown')
        # NUEVO: Log de fallback mejorado con duración y tipo de error
        logger.warning(
            f"[ModelManager] ⚠️ Generation failed after {total_duration:.2f}s "
            f"(type: {error_type}). Using fallback."
        )
        
        fallback_text = result.get('fallback_message', FALLBACK_MESSAGES['default'])
        
        # NUEVO: Log para saber qué fallback se está utilizando
        log_fallback_source = (f"template '{fallback_template}'" 
                               if fallback_template and dispatcher 
                               else f"text '{fallback_text}'")
        logger.info(f"[ModelManager] Fallback source: {log_fallback_source}")
        
        if dispatcher:
            if fallback_template:
                try:
                    dispatcher.utter_message(template=fallback_template)
                    logger.info(f"[ModelManager] ✅ Template enviado: {fallback_template}")
                    return None
                except Exception as e:
                    logger.error(f"[ModelManager] ❌ Error con template: {e}")
            
            dispatcher.utter_message(text=fallback_text)
            logger.info(f"[ModelManager] ✅ Fallback enviado: '{fallback_text}'")
            return None
        
        return fallback_text
        
    except Exception as e:
        total_duration = time.time() - start_time
        logger.error(f"[ModelManager] ❌ Critical error after {total_duration:.2f}s: {e}", exc_info=True)
        
        fallback_text = FALLBACK_MESSAGES['default']
        
        if dispatcher:
            dispatcher.utter_message(text=fallback_text)
            logger.info("[ModelManager] ✅ Fallback de emergencia enviado")
            return None
        
        return fallback_text


def generate_with_safe_fallback(
    prompt: str,
    dispatcher: CollectingDispatcher,
    tracker: Optional[Tracker] = None,
    fallback_template: str = "utter_default",
    max_new_tokens: int = 150,
    temperature: float = 0.1
) -> None:
    """
    ✅ WRAPPER SIMPLIFICADO - USA generate_text_with_context
    """
    generate_text_with_context(
        prompt=prompt,
        tracker=tracker,
        dispatcher=dispatcher,
        fallback_template=fallback_template,
        max_new_tokens=max_new_tokens,
        temperature=temperature
    )


def _build_lightweight_context(tracker: Tracker) -> str:
    """Construye contexto ligero desde el tracker."""
    try:
        context_parts = []
        search_history = tracker.get_slot('search_history')
        
        if search_history and len(search_history) > 0:
            last_search = search_history[-1]
            params = last_search.get('parameters', {})
            if params:
                params_str = ", ".join([f"{k}='{v}'" for k, v in params.items()])
                context_parts.append(
                    f"El usuario está buscando con: {params_str}"
                )
        
        return "\n".join(context_parts)
    except Exception:
        return ""