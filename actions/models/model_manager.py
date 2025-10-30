# actions/model_manager.py
import os
import hashlib
import logging
import time
from typing import Optional, Dict, Any

from openai import OpenAI
from dotenv import load_dotenv
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from actions.actions_busqueda.search_engine import SearchEngine


load_dotenv()
logger = logging.getLogger(__name__)

# ============== CONFIGURACIÓN ==============
SYSTEM_PROMPT = """Te llamas Pompi, asistente veterinario.
Respuestas cortas: máximo 2 oraciones.
Siempre preguntá qué necesita."""

RESPONSE_CACHE = {}
MAX_CACHE_SIZE = 50

GENERATION_TIMEOUT = 8
OLLAMA_CLIENT_TIMEOUT = 10

MODEL_NAME = "llama3:8b-instruct-q4_K_M"
MAX_TOKENS_DEFAULT = 150
# ===========================================

FALLBACK_MESSAGES = {
    'timeout': "Estoy procesando tu consulta. ¿En qué más puedo ayudarte?",
    'connection_error': "Tengo un problema técnico temporal. ¿Podrías reformular tu pregunta?",
    'validation_error': "No pude generar una respuesta adecuada. ¿Podrías ser más específico?",
    'default': "¿En qué puedo ayudarte?"
}


# ============== CHAT MODEL ==============
class ChatModel:
    """Modelo conversacional para respuestas generales."""
    failed_attempts = 0
    
    def __init__(self):
        self.client = None
        self._is_loaded = False
        
    def load(self):
        """Carga cliente Ollama para chat."""
        if self._is_loaded:
            return
        
        try:
            ollama_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434/v1')
            self.client = OpenAI(
                base_url=ollama_url,
                api_key='ollama',
                timeout=OLLAMA_CLIENT_TIMEOUT
            )
            self.client.models.list()
            self._is_loaded = True
            logger.info(f"[ChatModel] ✅ Conexión establecida con {ollama_url}")
        except Exception as e:
            logger.error(f"[ChatModel] ❌ Error: {e}")
            self.client = None
            self._is_loaded = False
            raise ConnectionError("Fallo al conectar con Ollama.")
    
    def warmup(self):
        """Warmup del modelo conversacional."""
        if not self._is_loaded:
            self.load()
        
        try:
            logger.info("[ChatModel] Iniciando warmup...")
            start_time = time.time()
            
            _ = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": "hola"}
                ],
                model=MODEL_NAME,
                temperature=0.3,
                max_tokens=50,
                stream=False,
                timeout=GENERATION_TIMEOUT
            )
            
            elapsed = time.time() - start_time
            logger.info(f"[ChatModel] ✅ Warmup completado en {elapsed:.2f}s")
            
        except Exception as e:
            logger.error(f"[ChatModel] ⚠️ Error en warmup: {e}")
    
    def generate(self, user_prompt: str, max_new_tokens: int = 100, 
                 temperature: float = 0.3) -> Dict[str, Any]:
        """
        Genera respuesta usando el cliente Ollama, con caché y fallbacks.
        NUNCA retorna None.
        """
        if not self._is_loaded:
            try:
                self.load()
            except Exception as e:
                logger.error(f"[ChatModel] ❌ Fallo al cargar (lazy load): {e}")
                return {
                    'success': False, 
                    'error_type': 'connection_error', 
                    'fallback_message': FALLBACK_MESSAGES['connection_error']
                }

        # 1. Crear clave de caché
        cache_key = hashlib.md5(
            f"{user_prompt}:{max_new_tokens}:{temperature}:{MODEL_NAME}".encode('utf-8')
        ).hexdigest()

        # 2. Revisar caché
        if cache_key in RESPONSE_CACHE:
            logger.info("[ChatModel] ✅ Respuesta desde caché")
            return RESPONSE_CACHE[cache_key]

        # 3. Preparar mensajes para la API
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]

        try:
            # 4. Llamar a la API de Ollama
            start_time = time.time()
            response = self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=temperature,
                max_tokens=max_new_tokens,
                stream=False,
                timeout=GENERATION_TIMEOUT
            )
            elapsed = time.time() - start_time

            # 5. Procesar respuesta exitosa
            if response.choices and response.choices[0].message.content:
                text_response = response.choices[0].message.content.strip()
                logger.info(f"[ChatModel] ✅ Respuesta generada en {elapsed:.2f}s")
                
                result = {
                    'success': True,
                    'text': text_response,
                    'error_type': None,
                    'fallback_message': None
                }
                
                # Guardar en caché
                if len(RESPONSE_CACHE) > MAX_CACHE_SIZE:
                    RESPONSE_CACHE.pop(next(iter(RESPONSE_CACHE)))
                RESPONSE_CACHE[cache_key] = result
                
                return result
            else:
                raise ValueError("Respuesta de API vacía o inválida")

        # 6. Manejar errores
        except OpenAI.APITimeoutError as e:
            logger.warning(f"[ChatModel] ⚠️ Timeout ({GENERATION_TIMEOUT}s): {e}")
            return {
                'success': False, 
                'error_type': 'timeout', 
                'fallback_message': FALLBACK_MESSAGES['timeout']
            }
        except OpenAI.APIConnectionError as e:
            logger.error(f"[ChatModel] ❌ Error de Conexión: {e}")
            self.failed_attempts += 1
            return {
                'success': False, 
                'error_type': 'connection_error', 
                'fallback_message': FALLBACK_MESSAGES['connection_error']
            }
        except Exception as e:
            logger.error(f"[ChatModel] ❌ Error Inesperado: {e}", exc_info=True)
            return {
                'success': False, 
                'error_type': 'validation_error', 
                'fallback_message': FALLBACK_MESSAGES['validation_error']
            }


# ============== MODEL MANAGER ==============
class ModelManager:
    """Gestor centralizado de modelos."""
    
    def __init__(self):
        self.chat_model = ChatModel()
        self.search_engine = SearchEngine()  # ← NUEVO
        self._initialized = False
    
    def initialize(self, warmup: bool = True):
        """Inicializa ambos modelos."""
        if self._initialized:
            logger.info("[ModelManager] Ya inicializado")
            return
        
        total_start = time.time()
        logger.info("="*60)
        logger.info("[ModelManager] 🚀 INICIANDO CARGA DE MODELOS")
        logger.info("="*60)
        
        try:
            # 1. ChatModel
            logger.info("[ModelManager] [1/2] Cargando ChatModel...")
            start = time.time()
            self.chat_model.load()
            logger.info(f"[ModelManager] ✅ ChatModel en {time.time()-start:.2f}s")
            
            # 2. SearchEngine
            logger.info("[ModelManager] [2/2] Cargando SearchEngine...")
            start = time.time()
            self.search_engine.load()
            logger.info(f"[ModelManager] ✅ SearchEngine en {time.time()-start:.2f}s")
            
            # 3. Warmup
            if warmup:
                logger.info("[ModelManager] 🔥 Warmup de modelos...")
                start = time.time()
                self.chat_model.warmup()
                self.search_engine.warmup()
                logger.info(f"[ModelManager] ✅ Warmup en {time.time()-start:.2f}s")
            
            total = time.time() - total_start
            self._initialized = True
            
            logger.info("="*60)
            logger.info(f"[ModelManager] ✅ COMPLETO en {total:.2f}s")
            logger.info("="*60)
            
        except Exception as e:
            logger.error(f"[ModelManager] ❌ Error: {e}", exc_info=True)
            self._initialized = False
            raise
    
    def get_chat_model(self) -> ChatModel:
        if not self._initialized:
            self.initialize()
        return self.chat_model
    
    def get_search_engine(self) -> SearchEngine:
        if not self._initialized:
            self.initialize()
        return self.search_engine


# ============== INSTANCIAS GLOBALES ==============
_model_manager = ModelManager()


def initialize_models(warmup: bool = True):
    """Inicializa modelos al arrancar Rasa."""
    logger.info("[Init] Iniciando carga de modelos...")
    _model_manager.initialize(warmup=warmup)
    logger.info("[Init] ✅ Modelos listos")


def get_chat_model() -> ChatModel:
    return _model_manager.get_chat_model()


def get_search_engine() -> SearchEngine:
    """Obtiene SearchEngine inicializado."""
    return _model_manager.get_search_engine()



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
    start_time = time.time()
    try:
        # Obtener modelo del manager (se inicializa automáticamente si es necesario)
        chat_model = _model_manager.get_chat_model()
        
        # Construir contexto
        context_info = _build_lightweight_context(tracker) if tracker else ""
        full_prompt = (
            f"Contexto de la conversación:\n{context_info}\n\nInstrucción:\n{prompt}"
            if context_info else prompt
        )
        
        # Generar respuesta
        result = chat_model.generate(full_prompt, max_new_tokens, temperature)
        total_duration = time.time() - start_time

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
        logger.warning(
            f"[ModelManager] ⚠️ Generation failed after {total_duration:.2f}s "
            f"(type: {error_type}). Using fallback."
        )
        
        fallback_text = result.get('fallback_message', FALLBACK_MESSAGES['default'])
        
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