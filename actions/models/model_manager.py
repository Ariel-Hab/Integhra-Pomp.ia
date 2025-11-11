# actions/models/model_manager.py (REFACTORIZADO)
import logging
import time
from typing import Optional, List, Dict

from actions.functions.conections_broker import get_broker
from actions.functions.search_engine import SearchEngine

logger = logging.getLogger(__name__)

# ============== CONFIGURACIÓN ==============
GENERATION_TIMEOUT = 40
# ===========================================


class ChatModel:
    """
    Modelo conversacional para respuestas generales.
    ✅ AHORA USA EL BROKER para manejo robusto de conexiones.
    """
    
    def __init__(self):
        self.broker = None
        self._is_loaded = False
        
    def load(self):
        """Carga el broker de conexiones."""
        if self._is_loaded:
            logger.info("[ChatModel] Ya está cargado")
            return

        logger.info("[ChatModel] Inicializando broker...")
        self.broker = get_broker()
        self._is_loaded = True
        logger.info("[ChatModel] ✅ Broker listo")
        
    def warmup(self):
        """Precalienta el broker con una request de prueba."""
        if not self._is_loaded:
            self.load()
        
        logger.info("[ChatModel] 🔥 Iniciando warmup...")
        
        test_messages = [
            {"role": "user", "content": "hola"}
        ]
        
        result = self.broker.generate(
            messages=test_messages,
            temperature=0.3,
            max_tokens=10
        )
        
        if result:
            logger.info("[ChatModel] ✅ Warmup exitoso")
            return True
        else:
            logger.warning("[ChatModel] ⚠️ Warmup falló")
            return False
    
    def generate_raw(
        self, 
        messages: List[Dict], 
        temperature: float = 0.3, 
        max_tokens: int = 150
    ) -> Optional[str]:
        """
        Genera respuesta usando el broker.
        
        Args:
            messages: Lista de mensajes en formato OpenAI
            temperature: Temperatura de generación
            max_tokens: Máximo de tokens a generar
            
        Returns:
            Texto generado o None si falla
        """
        if not self._is_loaded:
            try:
                self.load()
            except Exception as e:
                logger.error(f"[ChatModel] No se pudo cargar: {e}")
                return None

        start_time = time.time()
        
        try:
            logger.info("[ChatModel] 🧠 Generando respuesta...")
            
            # ✅ Usar el broker directamente
            response = self.broker.generate(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=GENERATION_TIMEOUT
            )
            
            elapsed = time.time() - start_time
            
            if response:
                logger.info(f"[ChatModel] ✅ Generación exitosa en {elapsed:.2f}s")
                
                # Obtener info de qué conexión se usó
                status = self.broker.get_status()
                conn_used = self._get_last_used_connection(status)
                logger.info(f"[ChatModel] 📡 Conexión usada: {conn_used}")
                
                return response
            else:
                logger.warning("[ChatModel] ⚠️ El broker retornó None")
                return None
                
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"[ChatModel] ❌ Error después de {elapsed:.2f}s: {e}", exc_info=True)
            return None
    
    def _get_last_used_connection(self, broker_status: Dict) -> str:
        """Helper para determinar qué conexión se usó"""
        most_recent = None
        most_recent_time = 0
        
        for conn_name, conn_data in broker_status.items():
            last_used = conn_data.get("last_used")
            if last_used and last_used > most_recent_time:
                most_recent = conn_name
                most_recent_time = last_used
        
        return most_recent or "unknown"
    
    def get_broker_status(self) -> Dict:
        """Obtiene el estado actual del broker (útil para debugging)"""
        if not self._is_loaded:
            return {"error": "Broker no cargado"}
        
        return self.broker.get_status()


class ModelManager:
    """
    Gestor centralizado de modelos.
    ✅ SIMPLIFICADO: Ahora solo maneja ChatModel y SearchEngine.
    """
    
    def __init__(self):
        self.chat_model = ChatModel()
        self.search_engine = SearchEngine()
        self._initialized = False
    
    def initialize(self, warmup: bool = True):
        """Inicializa ambos modelos."""
        if self._initialized:
            logger.info("[ModelManager] Ya inicializado")
            return
        
        total_start = time.time()
        logger.info("=" * 60)
        logger.info("[ModelManager] 🚀 INICIANDO CARGA DE MODELOS")
        logger.info("=" * 60)
        
        try:
            # 1. ChatModel (usa broker internamente)
            logger.info("[ModelManager] [1/2] Cargando ChatModel...")
            start = time.time()
            self.chat_model.load()
            logger.info(f"[ModelManager] ✅ ChatModel listo en {time.time()-start:.2f}s")
            
            # 2. SearchEngine (usa broker internamente)
            logger.info("[ModelManager] [2/2] Cargando SearchEngine...")
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
            
            # Mostrar estado del broker
            self._log_broker_status()
            
        except Exception as e:
            logger.error(f"[ModelManager] ❌ Error crítico: {e}", exc_info=True)
            self._initialized = False
            raise
    
    def _log_broker_status(self):
        """Muestra el estado del broker"""
        try:
            status = self.chat_model.get_broker_status()
            
            logger.info("=" * 60)
            logger.info("📊 [ModelManager] ESTADO DEL BROKER")
            logger.info("=" * 60)
            
            for conn_name, conn_data in status.items():
                available = "✅" if conn_data["available"] else "❌"
                priority = conn_data["priority"]
                logger.info(f"  [{priority}] {conn_name}: {available}")
            
            logger.info("=" * 60)
            
        except Exception as e:
            logger.warning(f"[ModelManager] No se pudo obtener estado del broker: {e}")
    
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
    
    def get_broker_status(self) -> Dict:
        """Obtiene el estado del broker (útil para monitoring)"""
        if not self._initialized:
            return {"error": "ModelManager no inicializado"}
        
        return self.chat_model.get_broker_status()


# ============== INSTANCIAS GLOBALES ==============
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

def get_broker_status() -> Dict:
    """Helper para obtener estado del broker desde cualquier parte"""
    return _model_manager.get_broker_status()