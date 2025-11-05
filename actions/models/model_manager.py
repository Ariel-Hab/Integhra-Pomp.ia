# actions/models/model_manager.py
import os
import logging
import time
from typing import Optional

from openai import OpenAI, APITimeoutError, APIConnectionError, NotFoundError
from dotenv import load_dotenv

from actions.functions.search_engine import SearchEngine

load_dotenv()
logger = logging.getLogger(__name__)

# ============== CONFIGURACIÓN ==============
# --- Modelos de Chat ---
MODEL_CHAT_CPU = os.getenv("MODEL_CHAT_CPU", "pompi_chat_cpu")
OLLAMA_CPU_URL = os.getenv('OLLAMA_CPU_URL', "http://host.docker.internal:11434")
MODEL_CHAT_GPU = os.getenv("MODEL_CHAT_GPU", "pompi_chat_gpu")
OLLAMA_GPU_URL = os.getenv('OLLAMA_GPU_URL', "http://host.docker.internal:11435")

# Timeouts
GENERATION_TIMEOUT = 120
OLLAMA_CLIENT_TIMEOUT = 150
# ===========================================


# ============== CHAT MODEL (GPU con Fallback a CPU) ==============
class ChatModel:
    """
    Modelo conversacional para respuestas generales.
    Prioriza GPU y usa CPU como fallback.
    """
    
    def __init__(self):
        self.client_gpu = None
        self.client_cpu = None
        self.url_gpu = OLLAMA_GPU_URL
        self.url_cpu = OLLAMA_CPU_URL
        self.model_gpu = MODEL_CHAT_GPU
        self.model_cpu = MODEL_CHAT_CPU
        self._gpu_available = False
        self._cpu_available = False
        self._is_loaded = False
        
    def load(self):
        """Carga clientes Ollama para GPU y CPU de forma independiente."""
        if self._is_loaded:
            logger.info("[ChatModel] Ya está cargado")
            return

        # --- Cargar GPU ---
        try:
            logger.info(f"[ChatModel] Conectando a GPU en {self.url_gpu} ({self.model_gpu})...")
            self.client_gpu = OpenAI(
                base_url=self.url_gpu,
                api_key='ollama',
                timeout=OLLAMA_CLIENT_TIMEOUT
            )
            self.client_gpu.models.list() # Test connection
            self._gpu_available = True
            logger.info(f"[ChatModel] ✅ Conexión GPU establecida")
        except Exception as e:
            logger.warning(f"[ChatModel] ⚠️ No se pudo conectar a GPU: {e}")
            
            # --- AGREGAR ESTA LÍNEA ---
            logger.debug(f"[ChatModel] Error detallado de conexión GPU", exc_info=True)
            # --- FIN DE LÍNEA AGREGADA ---

            self.client_gpu = None
            self._gpu_available = False
        
        # --- Cargar CPU ---
        try:
            logger.info(f"[ChatModel] Conectando a CPU en {self.url_cpu} ({self.model_cpu})...")
            self.client_cpu = OpenAI(
                base_url=self.url_cpu,
                api_key='ollama',
                timeout=OLLAMA_CLIENT_TIMEOUT
            )
            self.client_cpu.models.list() # Test connection
            self._cpu_available = True
            logger.info(f"[ChatModel] ✅ Conexión CPU establecida")
        except Exception as e:
            logger.warning(f"[ChatModel] ⚠️ No se pudo conectar a CPU: {e}")
            self.client_cpu = None
            self._cpu_available = False
        
        self._is_loaded = True
        
        if not self._gpu_available and not self._cpu_available:
            logger.error("[ChatModel] ❌ FALLA TOTAL: No se pudo conectar a CPU ni a GPU.")
        else:
            logger.info(f"[ChatModel] Carga completada (GPU: {self._gpu_available}, CPU: {self._cpu_available})")

    def _warmup_client(self, client: OpenAI, model: str, client_name: str) -> bool:
        """Helper interno para calentar un cliente."""
        try:
            start = time.time()
            _ = client.chat.completions.create(
                messages=[{"role": "user", "content": "hola"}],
                model=model,
                temperature=0.3,
                max_tokens=10,
                timeout=GENERATION_TIMEOUT
            )
            elapsed = time.time() - start
            logger.info(f"[ChatModel] ✅ Warmup {client_name} completado en {elapsed:.2f}s")
            return True
        except Exception as e:
            logger.error(f"[ChatModel] ⚠️ Error en warmup {client_name}: {e}")
            return False
        
    def warmup(self):
        """Precalienta el modelo (GPU primero, luego CPU)."""
        if not self._is_loaded:
            self.load()
        
        if self._gpu_available:
            logger.info(f"[ChatModel] 🔥 Iniciando warmup GPU ({self.model_gpu})...")
            if self._warmup_client(self.client_gpu, self.model_gpu, "GPU"):
                # Si GPU funciona, no necesitamos calentar CPU
                return True
            # GPU falló warmup, marcar como no disponible
            self._gpu_available = False
            logger.warning("[ChatModel] Warmup GPU falló, marcando como no disponible.")
        
        if self._cpu_available:
            logger.info(f"[ChatModel] 🔥 Iniciando warmup CPU ({self.model_cpu})...")
            if not self._warmup_client(self.client_cpu, self.model_cpu, "CPU"):
                self._cpu_available = False # CPU también falló
        
        logger.warning("[ChatModel] ⚠️ No hay cliente (GPU/CPU) disponible para warmup")
        return False
    
    def generate_raw(self, messages: list, temperature: float = 0.3, 
                    max_tokens: int = 150) -> Optional[str]:
        """
        Genera respuesta usando GPU, con fallback a CPU.
        Retorna el texto generado o None si ambos fallan.
        """
        if not self._is_loaded:
            try:
                self.load()
            except Exception as e:
                logger.error(f"[ChatModel] No se pudo cargar: {e}")
                return None

        if not self._gpu_available and not self._cpu_available:
            logger.error("[ChatModel] ❌ No hay clientes (GPU/CPU) disponibles para generar.")
            return None

        start_time = time.time()
        
        # --- Intento 1: GPU ---
        if self._gpu_available:
            try:
                logger.info(f"[ChatModel] 🧠 Generando con GPU ({self.model_gpu})...")
                response = self.client_gpu.chat.completions.create(
                    model=self.model_gpu,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=False,
                    timeout=GENERATION_TIMEOUT
                )
                elapsed = time.time() - start_time
                
                if response.choices and response.choices[0].message.content:
                    text = response.choices[0].message.content.strip()
                    logger.info(f"[ChatModel] ✅ Generación GPU exitosa en {elapsed:.2f}s")
                    return text
                else:
                    logger.warning("[ChatModel] ⚠️ Respuesta vacía del modelo GPU")
                    # No hacer fallback por respuesta vacía, es un problema del modelo
                    return None 

            except (APITimeoutError, APIConnectionError, NotFoundError) as e:
                logger.warning(f"[ChatModel] ⚠️ Error de conexión GPU: {e}. Fallback a CPU.")
                self._gpu_available = False # Marcar como muerta
            
            except Exception as e:
                logger.error(f"[ChatModel] ❌ Error inesperado en GPU: {e}", exc_info=True)
                self._gpu_available = False # Marcar como muerta por si acaso
                # Continuar para fallback a CPU
        
        # --- Intento 2: CPU (si GPU falló o no estaba disponible) ---
        if self._cpu_available:
            try:
                logger.info(f"[ChatModel] 🧠 Generando con CPU ({self.model_cpu})...")
                start_time_cpu = time.time()
                
                response = self.client_cpu.chat.completions.create(
                    model=self.model_cpu,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=False,
                    timeout=GENERATION_TIMEOUT
                )
                
                elapsed = time.time() - start_time_cpu
                
                if response.choices and response.choices[0].message.content:
                    text = response.choices[0].message.content.strip()
                    logger.info(f"[ChatModel] ✅ Generación CPU exitosa en {elapsed:.2f}s")
                    return text
                else:
                    logger.warning("[ChatModel] ⚠️ Respuesta vacía del modelo CPU")
                    return None
            
            except (APITimeoutError, APIConnectionError, NotFoundError) as e:
                logger.warning(f"[ChatModel] ⚠️ Error de conexión CPU: {e}")
                self._cpu_available = False # Marcar CPU como muerta
                return None
                
            except Exception as e:
                logger.error(f"[ChatModel] ❌ Error inesperado en CPU: {e}", exc_info=True)
                return None
        
        # Si llegamos aquí, es que GPU falló y CPU no estaba disponible (o falló)
        logger.error("[ChatModel] ❌ Fallback a CPU falló o no estaba disponible.")
        return None


# ============== MODEL MANAGER (Sin cambios) ==============
class ModelManager:
    """
    Gestor centralizado de modelos.
    Responsable de inicializar ChatModel y SearchEngine.
    """
    
    def __init__(self):
        self.chat_model = ChatModel()
        self.search_engine = SearchEngine()
        self._initialized = False
    
    def initialize(self, warmup: bool = True):
        """Inicializa ambos modelos (ChatModel CPU y SearchEngine GPU)."""
        if self._initialized:
            logger.info("[ModelManager] Ya inicializado")
            return
        
        total_start = time.time()
        logger.info("=" * 60)
        logger.info("[ModelManager] 🚀 INICIANDO CARGA DE MODELOS")
        logger.info("=" * 60)
        
        try:
            # 1. ChatModel (Ahora con lógica GPU/CPU)
            logger.info("[ModelManager] [1/2] Cargando ChatModel (GPU/CPU)...")
            start = time.time()
            self.chat_model.load()
            logger.info(f"[ModelManager] ✅ ChatModel listo en {time.time()-start:.2f}s")
            
            # 2. SearchEngine (GPU/CPU)
            logger.info("[ModelManager] [2/2] Cargando SearchEngine (GPU/CPU)...")
            start = time.time()
            self.search_engine.load()
            logger.info(f"[ModelManager] ✅ SearchEngine listo en {time.time()-start:.2f}s")
            
            # 3. Warmup (opcional)
            if warmup:
                logger.info("[ModelManager] 🔥 Precalentando modelos...")
                start = time.time()
                self.chat_model.warmup()
                self.search_engine.warmup()
                logger.info(f"[ModelManager] ✅ Warmup completado en {time.time()-start:.2f}s")
            
            total = time.time() - total_start
            self._initialized = True
            
            logger.info("=" * 60)
            logger.info(f"[ModelManager] ✅ CARGA COMPLETA en {total:.2f}s")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"[ModelManager] ❌ Error crítico: {e}", exc_info=True)
            self._initialized = False
            raise
    
    def get_chat_model(self) -> ChatModel:
        """Obtiene la instancia de ChatModel, inicializando si es necesario."""
        if not self._initialized:
            self.initialize()
        return self.chat_model
    
    def get_search_engine(self) -> SearchEngine:
        """Obtiene la instancia de SearchEngine, inicializando si es necesario."""
        if not self._initialized:
            self.initialize()
        return self.search_engine


# ============== INSTANCIAS GLOBALES (Sin cambios) ==============
_model_manager = ModelManager()

def initialize_models(warmup: bool = True):
    """Inicializa todos los modelos."""
    logger.info("[Init] Iniciando carga de modelos...")
    _model_manager.initialize(warmup=warmup)
    logger.info("[Init] ✅ Modelos listos")

def get_chat_model() -> ChatModel:
    """Obtiene la instancia global de ChatModel."""
    return _model_manager.get_chat_model()

def get_search_engine() -> SearchEngine:
    """Obtiene la instancia global de SearchEngine."""
    return _model_manager.get_search_engine()