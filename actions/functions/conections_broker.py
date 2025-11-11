# actions/models/connection_broker.py
import os
import logging
import time
import requests
from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass
# from dotenv import load_dotenv
from openai import OpenAI, APITimeoutError, APIConnectionError, NotFoundError

logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR,  '..', '.env.local')

# Cargar el .env y capturar el resultado
# loaded_ok = load_dotenv(ENV_PATH)


# ============== CONFIGURACIÓN ==============
# Ollama Local
OLLAMA_GPU_URL = os.getenv('OLLAMA_GPU_URL', "http://host.docker.internal:11435")
OLLAMA_CPU_URL = os.getenv('OLLAMA_CPU_URL', "http://host.docker.internal:11434")
MODEL_GPU = os.getenv("MODEL_SEARCH_GPU", "mistral:7b")
MODEL_CPU = os.getenv("MODEL_SEARCH_CPU", "pompi_search_cpu")

# RunPod
RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID")
RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY")
RUNPOD_POLL_INTERVAL = 2  # segundos entre checks
RUNPOD_MAX_WAIT_TIME = 120  # timeout máximo para RunPod

# Timeouts generales
OLLAMA_TIMEOUT = 120
OLLAMA_CLIENT_TIMEOUT = 90
# ===========================================


class ConnectionType(Enum):
    """Tipos de conexión disponibles"""
    OLLAMA_GPU = "ollama_gpu"
    OLLAMA_CPU = "ollama_cpu"
    RUNPOD = "runpod"


@dataclass
class ConnectionConfig:
    """Configuración de una conexión"""
    conn_type: ConnectionType
    priority: int  # 1 = más alta
    available: bool = False
    last_error: Optional[str] = None
    last_used: Optional[float] = None
    total_requests: int = 0
    total_failures: int = 0


class RunPodClient:
    """Cliente para interactuar con RunPod"""
    
    def __init__(self, endpoint_id: str, api_key: str):
        self.endpoint_id = endpoint_id
        self.api_key = api_key
        self.base_url = "https://api.runpod.ai/v2"
        
    def _get_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def run_job(self, messages: List[Dict], temperature: float = 0.3, 
                max_tokens: int = 500) -> str:
        """
        Envía un job a RunPod y espera el resultado.
        Convierte formato OpenAI messages a prompt simple.
        """
        # Convertir messages a prompt
        prompt = self._messages_to_prompt(messages)
        
        url = f"{self.base_url}/{self.endpoint_id}/run"
        body = {
            "input": {
                "prompt": prompt,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
        }
        
        logger.info(f"📤 [RunPod] Enviando job...")
        
        try:
            # Enviar job
            response = requests.post(url, headers=self._get_headers(), json=body, timeout=30)
            response.raise_for_status()
            job_data = response.json()
            job_id = job_data.get("id")
            
            if not job_id:
                raise ValueError("No se recibió job_id de RunPod")
            
            logger.info(f"✅ [RunPod] Job {job_id} enviado")
            
            # Esperar resultado
            return self._wait_for_result(job_id)
            
        except requests.RequestException as e:
            logger.error(f"❌ [RunPod] Error en request: {e}")
            raise
    
    def _wait_for_result(self, job_id: str) -> str:
        """Espera el resultado de un job"""
        url = f"{self.base_url}/{self.endpoint_id}/status/{job_id}"
        start_time = time.time()
        
        logger.info(f"⏳ [RunPod] Esperando resultado de {job_id}...")
        
        while True:
            elapsed = time.time() - start_time
            
            if elapsed > RUNPOD_MAX_WAIT_TIME:
                raise TimeoutError(f"RunPod timeout después de {elapsed:.1f}s")
            
            try:
                response = requests.get(url, headers=self._get_headers(), timeout=10)
                response.raise_for_status()
                job_status = response.json()
                
                status = job_status.get("status")
                
                if status == "COMPLETED":
                    output = job_status.get("output")
                    logger.info(f"✅ [RunPod] Job completado en {elapsed:.2f}s")
                    return self._extract_text_from_output(output)
                
                elif status == "FAILED":
                    error = job_status.get("error", "Unknown error")
                    raise RuntimeError(f"RunPod job failed: {error}")
                
                elif status in ["IN_QUEUE", "IN_PROGRESS"]:
                    # Continuar esperando
                    time.sleep(RUNPOD_POLL_INTERVAL)
                
                else:
                    logger.warning(f"⚠️ [RunPod] Estado desconocido: {status}")
                    time.sleep(RUNPOD_POLL_INTERVAL)
                    
            except requests.RequestException as e:
                logger.error(f"❌ [RunPod] Error checking status: {e}")
                raise
    
    def _messages_to_prompt(self, messages: List[Dict]) -> str:
        """Convierte formato OpenAI messages a un prompt simple"""
        prompt_parts = []
        
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                prompt_parts.append(f"[SYSTEM]\n{content}\n")
            elif role == "user":
                prompt_parts.append(f"[USER]\n{content}\n")
            elif role == "assistant":
                prompt_parts.append(f"[ASSISTANT]\n{content}\n")
        
        prompt_parts.append("[ASSISTANT]")  # Prompt para que el modelo responda
        return "\n".join(prompt_parts)
    
    def _extract_text_from_output(self, output: Any) -> str:
        """
        ✅ CORREGIDO: Extrae el texto de la respuesta de RunPod
        Maneja formatos /v1/completions y /v1/chat/completions.
        """
        try:
            completion_data = None
            
            # Caso 1: La salida es una lista que contiene el dict de completado
            # Ejemplo: [{'choices': [...]}]
            if isinstance(output, list) and output:
                completion_data = output[0]
            # Caso 2: La salida es el dict de completado directamente
            # Ejemplo: {'choices': [...]}
            elif isinstance(output, dict):
                completion_data = output
            else:
                # Fallback: es un string simple u otro formato
                logger.warning(f"Formato de RunPod no reconocido (no es lista ni dict), devolviendo str.")
                return str(output)

            # Ahora extraemos de 'completion_data'
            if "choices" in completion_data and isinstance(completion_data["choices"], list) and completion_data["choices"]:
                first_choice = completion_data["choices"][0]
                
                if "text" in first_choice:
                    # Para endpoints tipo /v1/completions
                    return first_choice["text"].strip()
                
                if "message" in first_choice and "content" in first_choice["message"]:
                    # Para endpoints tipo /v1/chat/completions
                    return first_choice["message"]["content"].strip()
            
            # Fallback si 'choices' está vacío o no tiene 'text'/'message'
            logger.warning(f"Formato 'choices' de RunPod no reconocido: {completion_data}")
            return str(output)

        except Exception as e:
            logger.error(f"Error crítico parseando RunPod output: {e}. Output: {output}", exc_info=True)
            return str(output) # Fallback final


class ConnectionBroker:
    """
    Broker que maneja múltiples tipos de conexiones con priorización
    y fallback automático.
    """
    
    def __init__(self):
        self.connections: Dict[ConnectionType, ConnectionConfig] = {}
        self.ollama_gpu_client: Optional[OpenAI] = None
        self.ollama_cpu_client: Optional[OpenAI] = None
        self.runpod_client: Optional[RunPodClient] = None
        self._initialized = False
        
    def initialize(self):
        """Inicializa todas las conexiones disponibles"""
        if self._initialized:
            logger.info("🔒 [Broker] Ya inicializado")
            return
        
        logger.info("=" * 60)
        logger.info("🚀 [Broker] INICIALIZANDO CONEXIONES")
        logger.info("=" * 60)
        
        # # 1. Ollama GPU (Prioridad 1)
        # self._init_ollama_gpu()
        
        
        
        # 3. RunPod (Prioridad 3 - Fallback remoto)
        self._init_runpod()

        # 2. Ollama CPU (Prioridad 2)
        self._init_ollama_cpu()
        
        self._initialized = True
        self._log_status()
    
    def _init_ollama_gpu(self):
        """Inicializa conexión Ollama GPU"""
        config = ConnectionConfig(
            conn_type=ConnectionType.OLLAMA_GPU,
            priority=1
        )
        
        try:
            logger.info(f"🔧 [Broker] Conectando Ollama GPU ({OLLAMA_GPU_URL})...")
            
            self.ollama_gpu_client = OpenAI(
                base_url=OLLAMA_GPU_URL,
                api_key='ollama',
                timeout=OLLAMA_CLIENT_TIMEOUT
            )
            
            # Test de conexión
            models = self.ollama_gpu_client.models.list()
            available_models = [m.id for m in models.data]
            
            if any(m.startswith(MODEL_GPU) for m in available_models):
                config.available = True
                logger.info(f"✅ [Broker] Ollama GPU disponible ({MODEL_GPU})")
            else:
                logger.warning(f"⚠️ [Broker] Modelo {MODEL_GPU} no encontrado en GPU")
                config.last_error = f"Model {MODEL_GPU} not found"
                
        except Exception as e:
            logger.warning(f"⚠️ [Broker] Ollama GPU no disponible: {e}")
            config.last_error = str(e)
        
        self.connections[ConnectionType.OLLAMA_GPU] = config
    
    def _init_ollama_cpu(self):
        """Inicializa conexión Ollama CPU"""
        config = ConnectionConfig(
            conn_type=ConnectionType.OLLAMA_CPU,
            priority=3
        )
        
        try:
            logger.info(f"🔧 [Broker] Conectando Ollama CPU ({OLLAMA_CPU_URL})...")
            
            self.ollama_cpu_client = OpenAI(
                base_url=OLLAMA_CPU_URL,
                api_key='ollama',
                timeout=OLLAMA_CLIENT_TIMEOUT
            )
            
            # Test de conexión
            models = self.ollama_cpu_client.models.list()
            available_models = [m.id for m in models.data]
            
            if any(m.startswith(MODEL_CPU) for m in available_models):
                config.available = True
                logger.info(f"✅ [Broker] Ollama CPU disponible ({MODEL_CPU})")
            else:
                logger.warning(f"⚠️ [Broker] Modelo {MODEL_CPU} no encontrado en CPU")
                config.last_error = f"Model {MODEL_CPU} not found"
                
        except Exception as e:
            logger.warning(f"⚠️ [Broker] Ollama CPU no disponible: {e}")
            config.last_error = str(e)
        
        self.connections[ConnectionType.OLLAMA_CPU] = config
    
    def _init_runpod(self):
        """Inicializa conexión RunPod"""
        config = ConnectionConfig(
            conn_type=ConnectionType.RUNPOD,
            priority=2  # Menor prioridad = último fallback
        )
        
        if not RUNPOD_ENDPOINT_ID or not RUNPOD_API_KEY:
            logger.info("ℹ️ [Broker] RunPod no configurado (credenciales faltantes)")
            config.last_error = "Missing credentials"
            self.connections[ConnectionType.RUNPOD] = config
            return
        
        try:
            logger.info(f"🔧 [Broker] Configurando RunPod ({RUNPOD_ENDPOINT_ID})...")
            
            self.runpod_client = RunPodClient(RUNPOD_ENDPOINT_ID, RUNPOD_API_KEY)
            
            # Test de conexión básico (solo verifica credenciales)
            test_url = f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT_ID}"
            headers = {"Authorization": f"Bearer {RUNPOD_API_KEY}"}
            response = requests.get(test_url, headers=headers, timeout=10)
            
            if response.status_code in [200, 404]:  # 404 es OK, significa que el endpoint existe
                config.available = True
                logger.info("✅ [Broker] RunPod disponible")
            else:
                config.last_error = f"HTTP {response.status_code}"
                logger.warning(f"⚠️ [Broker] RunPod respondió con {response.status_code}")
                
        except Exception as e:
            logger.warning(f"⚠️ [Broker] RunPod no disponible: {e}")
            config.last_error = str(e)
        
        self.connections[ConnectionType.RUNPOD] = config
    
    def generate(self, messages: List[Dict], temperature: float = 0.3, 
                 max_tokens: int = 500, timeout: int = OLLAMA_TIMEOUT) -> Optional[str]:
        """
        Genera texto usando la mejor conexión disponible.
        Intenta en orden de prioridad con fallback automático.
        """
        if not self._initialized:
            self.initialize()
        
        # Ordenar conexiones por prioridad
        sorted_conns = sorted(
            self.connections.values(),
            key=lambda c: c.priority
        )
        
        last_error = None
        
        for config in sorted_conns:
            if not config.available:
                continue
            
            try:
                logger.info(f"🧠 [Broker] Intentando con {config.conn_type.value}...")
                start = time.time()
                
                result = self._generate_with_connection(
                    config.conn_type, messages, temperature, max_tokens, timeout
                )
                
                elapsed = time.time() - start
                
                if result:
                    # Actualizar estadísticas
                    config.total_requests += 1
                    config.last_used = time.time()
                    config.last_error = None
                    
                    logger.info(
                        f"✅ [Broker] Éxito con {config.conn_type.value} "
                        f"({elapsed:.2f}s, {config.total_requests} requests)"
                    )
                    return result
                
            except Exception as e:
                elapsed = time.time() - start
                last_error = str(e)
                
                # Actualizar estadísticas de error
                config.total_failures += 1
                config.last_error = last_error
                
                logger.warning(
                    f"⚠️ [Broker] Falló {config.conn_type.value} después de {elapsed:.2f}s: {e}"
                )
                
                # Si es un error grave, marcar como no disponible temporalmente
                if isinstance(e, (APIConnectionError, requests.ConnectionError)):
                    config.available = False
                    logger.warning(f"🚫 [Broker] Deshabilitando {config.conn_type.value} temporalmente")
                
                continue  # Intentar siguiente conexión
        
        # Si llegamos aquí, todas las conexiones fallaron
        logger.error(f"❌ [Broker] TODAS las conexiones fallaron. Último error: {last_error}")
        return None
    
    def _generate_with_connection(
        self, 
        conn_type: ConnectionType,
        messages: List[Dict],
        temperature: float,
        max_tokens: int,
        timeout: int
    ) -> Optional[str]:
        """Genera usando una conexión específica"""
        
        if conn_type == ConnectionType.OLLAMA_GPU:
            response = self.ollama_gpu_client.chat.completions.create(
                model=MODEL_GPU,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout
            )
            return response.choices[0].message.content.strip()
        
        elif conn_type == ConnectionType.OLLAMA_CPU:
            response = self.ollama_cpu_client.chat.completions.create(
                model=MODEL_CPU,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout
            )
            return response.choices[0].message.content.strip()
        
        elif conn_type == ConnectionType.RUNPOD:
            return self.runpod_client.run_job(messages, temperature, max_tokens)
        
        else:
            raise ValueError(f"Tipo de conexión desconocido: {conn_type}")
    
    def get_status(self) -> Dict[str, Any]:
        """Retorna el estado actual de todas las conexiones"""
        status = {}
        
        for conn_type, config in self.connections.items():
            status[conn_type.value] = {
                "available": config.available,
                "priority": config.priority,
                "total_requests": config.total_requests,
                "total_failures": config.total_failures,
                "last_error": config.last_error,
                "last_used": config.last_used
            }
        
        return status
    
    def _log_status(self):
        """Muestra un resumen del estado de las conexiones"""
        logger.info("=" * 60)
        logger.info("📊 [Broker] ESTADO DE CONEXIONES")
        logger.info("=" * 60)
        
        for conn_type, config in sorted(self.connections.items(), key=lambda x: x[1].priority):
            status = "✅ Disponible" if config.available else "❌ No disponible"
            error = f" ({config.last_error})" if config.last_error else ""
            
            logger.info(f"  [{config.priority}] {conn_type.value}: {status}{error}")
        
        logger.info("=" * 60)
    
    def reset_connection(self, conn_type: ConnectionType):
        """Reinicia una conexión específica (útil para recovery)"""
        logger.info(f"🔄 [Broker] Reiniciando {conn_type.value}...")
        
        if conn_type == ConnectionType.OLLAMA_GPU:
            self._init_ollama_gpu()
        elif conn_type == ConnectionType.OLLAMA_CPU:
            self._init_ollama_cpu()
        elif conn_type == ConnectionType.RUNPOD:
            self._init_runpod()


# ============== INSTANCIA GLOBAL ==============
_broker = ConnectionBroker()

def get_broker() -> ConnectionBroker:
    """Obtiene la instancia global del broker"""
    if not _broker._initialized:
        _broker.initialize()
    return _broker