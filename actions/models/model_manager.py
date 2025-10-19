# actions/models/model_manager.py

import os
import hashlib
import logging
import time
from typing import Optional

from openai import OpenAI
from dotenv import load_dotenv
from rasa_sdk import Tracker

load_dotenv()
logger = logging.getLogger(__name__)

# ============== CONFIGURACIÓN SIMPLIFICADA ==============
# Se eliminaron todas las variables de streaming.
SYSTEM_PROMPT = """Sos Pompi, asistente veterinario argentino.
Respuestas cortas: máximo 2 oraciones.
Siempre preguntá qué necesita."""

RESPONSE_CACHE = {}
MAX_CACHE_SIZE = 50

# Timeout para la generación de la respuesta completa.
# Si el modelo tarda más que esto, la función devolverá None.
GENERATION_TIMEOUT = 8
OLLAMA_CLIENT_TIMEOUT = 10

# Configuración del modelo
MODEL_NAME = "llama3:8b-instruct-q4_0" # Usamos el modelo que ya tenías para la generación estándar
MAX_TOKENS_DEFAULT = 150 # Aumentamos un poco el default para respuestas completas
# =======================================================


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
            self.client = None # Aseguramos que el cliente quede como None si falla
            raise ConnectionError("Fallo al conectar con el servidor local de Ollama.")

    # ⛔️ ELIMINADO: El método generate_and_stream() fue completamente removido.
    
    def generate(self, user_prompt: str, max_new_tokens: int = 100, 
                 temperature: float = 0.3) -> Optional[str]:
        """
        Genera una respuesta completa con timeout, reintentos y caché.
        Si falla después de 3 intentos o por timeout, devuelve None.
        """
        cache_key = hashlib.md5(f"{user_prompt}_{max_new_tokens}_{temperature}".encode()).hexdigest()
        if cache_key in RESPONSE_CACHE:
            logger.info("✅ Respuesta devuelta desde caché.")
            return RESPONSE_CACHE[cache_key]
        
        try:
            self.load()
        except ConnectionError:
            return None # Si no puede conectar, falla rápido

        if not self.client:
            return None

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
                stream=False, # Aseguramos que el streaming esté deshabilitado
                timeout=GENERATION_TIMEOUT
            )
            
            elapsed = time.time() - start_time
            result = self._validate_response(response.choices[0].message.content)
            
            if result:
                self._update_cache(cache_key, result)
                self.failed_attempts = 0 # Reinicia contador si hay éxito
                logger.info(f"[Generate] ✓ Respuesta generada en {elapsed:.2f}s")
                return result
            else:
                logger.warning("[Generate] La respuesta del modelo fue inválida o vacía.")
                return None

        except Exception as e:
            elapsed = time.time() - start_time
            self.failed_attempts += 1
            logger.error(f"❌ Intento {self.failed_attempts}/3 falló generando respuesta (tras {elapsed:.2f}s): {e}")
            if self.failed_attempts >= 3:
                logger.critical("❌ Se superó el máximo de reintentos. El modelo no responderá.")
                # Opcional: Podrías resetear el contador aquí si querés que vuelva a intentar después de un tiempo
            return None

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

def generate_text_with_context(prompt: str, tracker: Optional[Tracker] = None, 
                               max_new_tokens: int = 150, 
                               temperature: float = 0.3) -> Optional[str]:
    """
    Función principal para generar texto. Construye el contexto y llama al modelo.
    Devuelve el texto generado o None si falla.
    """
    try:
        # La construcción de contexto se mantiene, ya que es útil.
        context_info = _build_lightweight_context(tracker) if tracker else ""
        full_prompt = f"Contexto de la conversación:\n{context_info}\n\nInstrucción:\n{prompt}" if context_info else prompt
        
        return _chat_model.generate(full_prompt, max_new_tokens, temperature)
        
    except Exception as e:
        logger.error(f"[ModelManager] Error inesperado en generate_text_with_context: {e}", exc_info=True)
        return None

def _build_lightweight_context(tracker: Tracker) -> str:
    # Esta función auxiliar no necesita cambios, sigue siendo eficiente.
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