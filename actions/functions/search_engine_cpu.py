# actions/actions_busqueda/search_engine_cpu.py
"""
Motor de búsqueda optimizado para CPU con phi3:mini.
Diseñado para queries simples con timeout agresivo y prompts minimalistas.

IMPORTANTE: Este módulo NO reemplaza al GPU, solo actúa cuando GPU no está disponible.
"""

import logging
import json
import time
import re
from typing import Dict, Any, Optional

# from dotenv import load_dotenv
from openai import OpenAI, APITimeoutError, APIConnectionError

logger = logging.getLogger(__name__)
# load_dotenv("../../.env.local")
class SearchEngineCPU:
    """
    Motor de búsqueda CPU-optimizado con bypass para queries simples.
    Usa phi3:mini con prompts ultra-cortos para máxima velocidad.
    """
    
    def __init__(self, ollama_url: str, model: str, api_key: str = "ollama"):
        """
        Inicializa el motor CPU.
        
        Args:
            ollama_url: URL del servidor Ollama CPU
            model: Nombre del modelo (ej: "pompi_search_cpu" o "phi3:mini")
            api_key: API key para Ollama (default: "ollama")
        """
        self.client = OpenAI(base_url=ollama_url, api_key=api_key)
        self.model = model
        self.ollama_url = ollama_url
        self._available = False
        self._last_check = 0
        self._check_interval = 60  # Re-verificar disponibilidad cada 60s
        
        logger.info(f"[CPU Engine] Inicializado con modelo: {model}")
        logger.info(f"[CPU Engine] URL: {ollama_url}")
    
    def is_available(self) -> bool:
        """
        Verifica si el modelo CPU está disponible.
        Cache la respuesta por 60s para no sobrecargar Ollama.
        """
        now = time.time()
        
        # Usar cache si es reciente
        if now - self._last_check < self._check_interval:
            return self._available
        
        # Re-verificar disponibilidad
        try:
            models_response = self.client.models.list()
            available_models = [m.id for m in models_response.data]
            self._available = any(model_id.startswith(self.model) for model_id in available_models)
            self._last_check = now
            
            if self._available:
                logger.debug(f"[CPU Engine] Modelo {self.model} disponible")
            else:
                logger.warning(f"[CPU Engine] Modelo {self.model} NO encontrado. Disponibles: {available_models}")
            
            return self._available
            
        except Exception as e:
            logger.warning(f"[CPU Engine] Error verificando disponibilidad: {e}")
            self._available = False
            self._last_check = now
            return False
    
    def load(self) -> bool:
        """
        Carga y verifica el modelo CPU.
        Retorna True si el modelo está disponible.
        """
        return self.is_available()
    
    def warmup(self) -> bool:
        """
        Calienta el modelo CPU con una query simple.
        Retorna True si el warmup fue exitoso.
        """
        if not self.is_available():
            logger.warning("[CPU Engine] No se puede calentar: modelo no disponible")
            return False
        
        try:
            logger.info("[CPU Engine] 🔥 Calentando modelo CPU...")
            start = time.time()
            
            _ = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "JSON: {\"test\": true}"}],
                temperature=0,
                max_tokens=20,
                timeout=30
            )
            
            warmup_time = time.time() - start
            logger.info(f"[CPU Engine] ✅ Modelo CPU calentado en {warmup_time:.2f}s")
            return True
            
        except Exception as e:
            logger.warning(f"[CPU Engine] ⚠️ Error en warmup: {e}")
            return False
    
    def execute_with_timeout(
        self,
        pre_analyzed_params: Dict[str, Any],
        search_type: str,
        user_message: str,
        timeout: int = 40
    ) -> Optional[Dict[str, Any]]:
        """
        Ejecuta búsqueda con LLM CPU y timeout.
        
        Args:
            pre_analyzed_params: Parámetros del pre-análisis NLU (Cerebro A)
            search_type: "productos" o "ofertas"
            user_message: Mensaje original del usuario
            timeout: Timeout en segundos (default: 40)
        
        Returns:
            Dict con "success", "params", "action" si exitoso
            None si falló (timeout, error, o JSON inválido)
        """
        if not self.is_available():
            logger.warning("[CPU Engine] Modelo no disponible, skip")
            return None
        
        llm_start = time.time()
        
        try:
            # Construir prompt minimalista
            prompt = self._build_lite_prompt(search_type, pre_analyzed_params, user_message)
            
            logger.info(f"[CPU Engine] Enviando a {self.model} (timeout: {timeout}s)...")
            logger.debug(f"[CPU Engine] Prompt: {prompt[:200]}...")
            
            # Llamada al LLM con timeout
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,  # Baja temperatura para mayor consistencia
                max_tokens=300,   # Suficiente para el JSON
                timeout=timeout   # Ollama abortará internamente si se pasa
            )
            
            llm_time = time.time() - llm_start
            raw_response = response.choices[0].message.content
            
            logger.info(f"[CPU Engine] ✅ Respuesta recibida en {llm_time:.2f}s")
            logger.debug(f"[CPU Engine] Respuesta raw: {raw_response[:200]}...")
            
            # Parsear JSON
            parsed = self._extract_json(raw_response)
            
            if not parsed:
                logger.error("[CPU Engine] ❌ No se pudo extraer JSON válido")
                return None
            
            # Extraer parámetros finales
            final_params = {
                k: v for k, v in parsed.items() 
                if k != "action" and v is not None
            }
            
            final_action = parsed.get("action", "search_products")
            
            logger.info(f"[CPU Engine] Parámetros extraídos: {json.dumps(final_params, ensure_ascii=False)}")
            
            return {
                "success": True,
                "params": final_params,
                "action": final_action,
                "llm_time": llm_time,
                "model_used": self.model
            }
        
        except (APITimeoutError, APIConnectionError) as e:
            llm_time = time.time() - llm_start
            logger.warning(f"[CPU Engine] ⏱️ Timeout/Connection error después de {llm_time:.2f}s: {e}")
            return None
        
        except json.JSONDecodeError as e:
            llm_time = time.time() - llm_start
            logger.error(f"[CPU Engine] ❌ JSON inválido después de {llm_time:.2f}s: {e}")
            return None
        
        except Exception as e:
            llm_time = time.time() - llm_start
            logger.error(f"[CPU Engine] ❌ Error inesperado después de {llm_time:.2f}s: {e}", exc_info=True)
            return None
    
    def _build_lite_prompt(
        self, 
        search_type: str, 
        pre_params: Dict[str, Any], 
        user_msg: str
    ) -> str:
        """
        Construye un prompt ultra-minimalista para phi3:mini.
        
        Objetivo: <300 tokens totales para máxima velocidad.
        """
        action = "search_offers" if search_type == "ofertas" else "search_products"
        
        # Formatear pre-análisis de forma compacta
        pre_analysis_str = "vacío"
        if pre_params:
            # Mostrar solo valores no vacíos
            compact_params = {k: v for k, v in pre_params.items() if v}
            if compact_params:
                pre_analysis_str = json.dumps(compact_params, ensure_ascii=False)
        
        # Prompt ultra-corto (inspirado en tus logs exitosos)
        prompt = f"""Usuario busca: "{user_msg}"

Pre-análisis NLU: {pre_analysis_str}

Genera JSON válido con estos campos (usa arrays [] para nombre, proveedor, categoria, animal, estado):

{{
  "action": "{action}",
  "nombre": ["texto1", "texto2"],
  "proveedor": ["texto"],
  "categoria": ["texto"],
  "animal": ["texto"],
  "estado": ["texto"],
  "descuento_min": número,
  "descuento_max": número,
  "stock_min": número,
  "dosis_gramaje": "texto",
  "dosis_volumen": "texto",
  "dosis_forma": "texto"
}}

REGLAS:
1. Si el pre-análisis tiene un valor, úsalo (respeta arrays [])
2. Si el mensaje del usuario menciona algo nuevo, agrégalo
3. Si un campo no aplica, omítelo (no pongas null)
4. NO inventes valores que no están en el mensaje o pre-análisis

Responde SOLO el JSON, sin texto adicional.

JSON:"""
        
        return prompt
    
    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extrae JSON de la respuesta del LLM.
        Maneja casos con markdown (```json...```), texto extra, etc.
        
        Returns:
            Dict con el JSON parseado, o None si falló
        """
        if not text:
            return None
        
        try:
            # Intento 1: Parsear directo (caso ideal)
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass
        
        # Intento 2: Buscar JSON dentro de markdown code blocks
        # Patrón: ```json ... ``` o ``` ... ```
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Intento 3: Buscar el bloque { ... } más grande
        brace_match = re.search(r'\{.*\}', text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass
        
        # Intento 4: Limpiar texto común antes del JSON
        # Ej: "Aquí está el JSON: {..."
        cleaned = re.sub(r'^.*?(?=\{)', '', text, flags=re.DOTALL)
        if cleaned != text:
            try:
                return json.loads(cleaned.strip())
            except json.JSONDecodeError:
                pass
        
        # Si todo falla
        logger.error(f"[CPU Engine] No se pudo extraer JSON de: {text[:300]}")
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Retorna estadísticas del motor CPU.
        Útil para debugging y monitoreo.
        """
        return {
            "model": self.model,
            "ollama_url": self.ollama_url,
            "available": self._available,
            "last_check": self._last_check,
            "check_interval": self._check_interval
        }


# ============== FUNCIONES HELPER GLOBALES ==============

def create_cpu_engine() -> SearchEngineCPU:
    """
    Factory function para crear una instancia del motor CPU.
    Lee configuración de variables de entorno.
    """
    import os
    
    ollama_url = os.getenv('OLLAMA_CPU_URL', 'http://host.docker.internal:11434')
    model = os.getenv('MODEL_SEARCH_CPU', 'pompi_search_cpu')
    
    engine = SearchEngineCPU(ollama_url=ollama_url, model=model)
    
    # Intentar cargar y calentar
    if engine.load():
        engine.warmup()
    
    return engine


# Instancia global (singleton) - similar al patrón del search_engine.py original
_cpu_engine_instance: Optional[SearchEngineCPU] = None

def get_cpu_search_engine() -> SearchEngineCPU:
    """
    Retorna la instancia singleton del motor CPU.
    Crea la instancia si no existe.
    """
    global _cpu_engine_instance
    
    if _cpu_engine_instance is None:
        _cpu_engine_instance = create_cpu_engine()
    
    return _cpu_engine_instance