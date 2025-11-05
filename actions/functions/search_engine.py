# actions/actions_busqueda/search_engine.py
import logging
import os
import time
import json
from typing import Dict, Any, Tuple, List, Optional
from openai import OpenAI, APITimeoutError, APIConnectionError, NotFoundError

from actions.api_client import search_products, search_offers

logger = logging.getLogger(__name__)

# ============== CONFIGURACIÓN ==============
# Carga TODAS las variables de entorno necesarias
MODEL_SEARCH_GPU = os.getenv("MODEL_SEARCH_GPU", "pompi_search_gpu")
OLLAMA_GPU_URL = os.getenv('OLLAMA_GPU_URL', "http://host.docker.internal:11435")

MODEL_SEARCH_CPU = os.getenv("MODEL_SEARCH_CPU", "pompi_search_cpu")
OLLAMA_CPU_URL = os.getenv('OLLAMA_CPU_URL', "http://host.docker.internal:11434")

OLLAMA_API_KEY = "ollama"
TEMPERATURE = 0.1
GENERATION_TIMEOUT = 120
# ===========================================

# Mapeo de estados (sin cambios)
ESTADO_MAP = {
    "en_oferta": ["rebajado", "promocion", "oferta", "con_descuento", "en_promocion"],
    "nuevo": ["nuevas", "novedades", "no_vistas", "sin_ver"],
    "vence_pronto": ["proximo_a_vencer", "por_vencer", "vencimiento_cercano"],
    "poco_stock": ["ultimas_unidades", "stock_limitado", "pocas_unidades"],
    "vistas": ["ya_vistas", "visitadas"]
}

class SearchEngine:
    """
    Motor de búsqueda inteligente con LLM.
    Prioriza GPU y usa CPU como fallback.
    """
    
    def __init__(self):
        self.client_gpu = None
        self.client_cpu = None
        
        self.url_gpu = OLLAMA_GPU_URL
        self.url_cpu = OLLAMA_CPU_URL
        self.model_gpu = MODEL_SEARCH_GPU
        self.model_cpu = MODEL_SEARCH_CPU
        
        self._is_loaded = False
        self._gpu_available = False
        self._cpu_available = False
        
    def load(self):
            """Carga y calienta clientes Ollama (GPU y CPU) de forma independiente."""
            if self._is_loaded:
                logger.info("🔍 [SearchEngine] Ya está cargado")
                return
            
            # --- Cargar GPU ---
            try:
                logger.info(f"🔍 [SearchEngine] Inicializando Ollama GPU ({self.model_gpu})...")
                logger.info(f"    URL: {self.url_gpu}")
                
                self.client_gpu = OpenAI(base_url=self.url_gpu, api_key=OLLAMA_API_KEY)
                
                models_response = self.client_gpu.models.list()
                # Convertir lista de objetos modelo a lista de IDs (strings)
                available_models = [m.id for m in models_response.data]
                
                # --- INICIO DEL ARREGLO ---
                # Comprueba si algún modelo en la lista COMIENZA con el nombre que buscamos.
                # Esto soluciona el problema de "pompi_search_gpu" vs "pompi_search_gpu:latest"
                found_gpu = any(model_id.startswith(self.model_gpu) for model_id in available_models)
                
                if found_gpu:
                # --- FIN DEL ARREGLO ---
                    logger.info(f"✅ [SearchEngine] Modelo GPU {self.model_gpu} disponible")
                    self._gpu_available = True
                else:
                    logger.warning(
                        f"⚠️ [SearchEngine] Modelo GPU {self.model_gpu} no encontrado. "
                        f"Disponibles: {available_models}"
                    )
                    self._gpu_available = False
                    
            except Exception as e:
                logger.warning(f"⚠️ [SearchEngine] No se pudo conectar a GPU: {e}")
                self._gpu_available = False

            # --- Cargar CPU ---
            try:
                logger.info(f"🔍 [SearchEngine] Inicializando Ollama CPU ({self.model_cpu})...")
                logger.info(f"    URL: {self.url_cpu}")
                
                self.client_cpu = OpenAI(base_url=self.url_cpu, api_key=OLLAMA_API_KEY)
                
                models_response = self.client_cpu.models.list()
                available_models = [m.id for m in models_response.data]
                
                # --- INICIO DEL ARREGLO ---
                # Aplicamos la misma lógica de "startswith" para el CPU
                found_cpu = any(model_id.startswith(self.model_cpu) for model_id in available_models)

                if found_cpu:
                # --- FIN DEL ARREGLO ---
                    logger.info(f"✅ [SearchEngine] Modelo CPU {self.model_cpu} disponible")
                    self._cpu_available = True
                else:
                    logger.warning(
                        f"⚠️ [SearchEngine] Modelo CPU {self.model_cpu} no encontrado. "
                        f"Disponibles: {available_models}"
                    )
                    self._cpu_available = False
                    
            except Exception as e:
                logger.warning(f"⚠️ [SearchEngine] No se pudo conectar a CPU: {e}")
                self._cpu_available = False
                
            self._is_loaded = True
            logger.info(f"✅ [SearchEngine] Carga completada (GPU: {self._gpu_available}, CPU: {self._cpu_available})")

    def _warmup_client(self, client: OpenAI, model: str, client_name: str) -> bool:
        """Función helper para calentar un cliente específico."""
        try:
            start = time.time()
            
            _ = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Responde con un JSON simple"},
                    {"role": "user", "content": "Dame un JSON con {test: true}"}
                ],
                temperature=0,
                max_tokens=50,
                timeout=GENERATION_TIMEOUT
            )
            
            warmup_time = time.time() - start
            logger.info(f"✅ [SearchEngine] Modelo {client_name} ({model}) calentado en {warmup_time:.2f}s")
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ [SearchEngine] Error en warmup {client_name}: {e}")
            return False

    def warmup(self) -> bool:
        """Calienta el LLM (GPU primero, luego CPU como fallback)."""
        if not self._is_loaded:
            self.load()
        
        if self._gpu_available:
            logger.info("🔥 [SearchEngine] Calentando GPU...")
            success = self._warmup_client(self.client_gpu, self.model_gpu, "GPU")
            if not success:
                self._gpu_available = False # Marcar como fallido
                if self._cpu_available:
                    logger.info("🔥 [SearchEngine] GPU falló, calentando CPU...")
                    return self._warmup_client(self.client_cpu, self.model_cpu, "CPU")
            return success
        
        elif self._cpu_available:
            logger.info("🔥 [SearchEngine] GPU no disponible, calentando CPU...")
            return self._warmup_client(self.client_cpu, self.model_cpu, "CPU")
            
        else:
            logger.info("⚠️ [SearchEngine] No hay LLMs (GPU/CPU) disponibles, skip warmup")
            return False

    # ============== PUNTO DE ENTRADA PRINCIPAL ==============
    
    def execute_search(
        self,
        search_params: Dict[str, Any],
        search_type: str,
        user_message: str,
        is_modification: bool = False,
        previous_params: Dict[str, Any] = None,
        chat_history: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        Ejecuta búsqueda con decisión inteligente:
        - Si is_modification=False → Búsqueda directa SIN LLM
        - Si is_modification=True Y (GPU o CPU disponible) → Usa LLM
        - Si LLMs no disponibles → Fallback a búsqueda directa (autocompletar)
        """
        if not self._is_loaded:
            self.load()
        
        # Caso 1: Modificación CON algún LLM disponible
        if is_modification and (self._gpu_available or self._cpu_available):
            logger.info("🧠 [SearchEngine] Usando LLM para MODIFICACIÓN")
            return self._execute_with_llm(
                current_params=search_params,
                previous_params=previous_params or {},
                user_message=user_message,
                search_type=search_type,
                chat_history=chat_history or []
            )
        
        # Caso 2: Búsqueda directa O LLMs no disponibles
        if is_modification and not (self._gpu_available or self._cpu_available):
            logger.warning(
                "⚠️ [SearchEngine] No hay LLM (GPU/CPU) disponible para modificación. "
                "Usando autocompletado de parámetros detectados por Rasa"
            )
        else:
            logger.info("⚡ [SearchEngine] Búsqueda directa (sin LLM)")
        
        return self._execute_direct(search_params, search_type)
    
    # ============== BÚSQUEDA DIRECTA (SIN LLM) ==============
    
    def _execute_direct(
        self, 
        search_params: Dict[str, Any], 
        search_type: str
    ) -> Dict[str, Any]:
        """Ejecuta búsqueda directa SIN usar LLM."""
        action = "search_offers" if search_type == "ofertas" else "search_products"
        
        try:
            api_params = self._transform_params_for_api(search_params, action)
            
            if action == "search_offers":
                result, api_time = search_offers(api_params)
            else:
                result, api_time = search_products(api_params)
            
            return {
                "success": True,
                "results": result,
                "api_time": api_time,
                "llm_time": 0.0,
                "llm_used": False,
                "total_results": result.get('total_results', 0)
            }
            
        except Exception as e:
            logger.error(f"❌ [SearchEngine] Error en búsqueda directa: {e}")
            return {
                "success": False,
                "error": str(e),
                "llm_used": False,
                "total_results": 0
            }
    
    def _fallback_to_direct(
        self, 
        search_params: Dict[str, Any], 
        search_type: str, 
        reason: str, 
        llm_time: float = 0.0
    ) -> Dict[str, Any]:
        """Helper para centralizar el fallback a búsqueda directa."""
        logger.warning(
            f"⚠️ [SearchEngine] Fallback a búsqueda directa (autocompletado). "
            f"Razón: {reason}"
        )
        direct_result = self._execute_direct(search_params, search_type)
        direct_result["llm_time"] = llm_time
        direct_result["llm_used"] = False
        direct_result["fallback_reason"] = reason
        return direct_result

    # ============== BÚSQUEDA CON LLM (MODIFICACIONES) ==============
    
    def _execute_with_llm(
        self,
        current_params: Dict[str, Any],
        previous_params: Dict[str, Any],
        user_message: str,
        search_type: str,
        chat_history: List[Dict]
    ) -> Dict[str, Any]:
        """Usa LLM (GPU con fallback a CPU) para reconstruir parámetros."""
        
        llm_start = time.time()
        
        # 1. Preparar prompts
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            previous_params, current_params, user_message, search_type
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        raw_response = None
        llm_time = 0.0
        
        try:
            # --- Intento 1: GPU ---
            if self._gpu_available:
                try:
                    logger.info(f"🧠 [SearchEngine] Enviando a LLM (GPU: {self.model_gpu})...")
                    response = self.client_gpu.chat.completions.create(
                        model=self.model_gpu,
                        messages=messages,
                        temperature=TEMPERATURE,
                        max_tokens=500,
                        timeout=GENERATION_TIMEOUT
                    )
                    raw_response = response.choices[0].message.content
                    llm_time = time.time() - llm_start
                    logger.info(f"✅ [SearchEngine] LLM (GPU) respondió en {llm_time:.3f}s")
                
                except (APITimeoutError, APIConnectionError, NotFoundError) as e:
                    llm_time = time.time() - llm_start
                    logger.warning(
                        f"⚠️ [SearchEngine] Error de conexión LLM (GPU) ({e.__class__.__name__}). "
                        f"Marcando GPU como no disponible."
                    )
                    self._gpu_available = False # Marcar como muerta
                    raw_response = None # Asegurarse que no hay respuesta
            
            # --- Intento 2: CPU (si GPU falló o no estaba disponible) ---
            if raw_response is None and self._cpu_available:
                try:
                    logger.info(f"🧠 [SearchEngine] Enviando a LLM (CPU: {self.model_cpu})...")
                    # Reiniciar tiempo si es el primer intento
                    if llm_time == 0.0: llm_start = time.time() 

                    response = self.client_cpu.chat.completions.create(
                        model=self.model_cpu,
                        messages=messages,
                        temperature=TEMPERATURE,
                        max_tokens=500,
                        timeout=GENERATION_TIMEOUT # Podrías querer un timeout más largo para CPU
                    )
                    raw_response = response.choices[0].message.content
                    llm_time = time.time() - llm_start
                    logger.info(f"✅ [SearchEngine] LLM (CPU) respondió en {llm_time:.3f}s")
                
                except (APITimeoutError, APIConnectionError, NotFoundError) as e:
                    llm_time = time.time() - llm_start
                    logger.error(
                        f"❌ [SearchEngine] Error de conexión LLM (CPU) ({e.__class__.__name__}). "
                        f"Marcando CPU como no disponible."
                    )
                    self._cpu_available = False # Marcar como muerta
                    return self._fallback_to_direct(
                        current_params, search_type, 
                        f"Error de conexión LLM (CPU): {e}", llm_time
                    )
            
            # --- Si no hay respuesta de ninguno ---
            if raw_response is None:
                return self._fallback_to_direct(
                    current_params, search_type, 
                    "Ningún LLM (GPU/CPU) disponible o ambos fallaron", llm_time
                )

            # --- 3. Parsear respuesta (si tuvimos éxito) ---
            logger.debug(f"[SearchEngine] Respuesta cruda: {raw_response}")
            llm_output = self._extract_json_from_response(raw_response)
            logger.debug(f"    LLM Output: {json.dumps(llm_output)}")
            
            # 4. Extraer params reconstruidos
            rebuilt_params = {
                k: v for k, v in llm_output.items() 
                if k != "action" and v is not None
            }
            
            logger.info(f"🛠️ [SearchEngine] Parámetros reconstruidos: {json.dumps(rebuilt_params)}")
            
            # 5. Ejecutar búsqueda
            direct_result = self._execute_direct(rebuilt_params, search_type)
            direct_result["llm_time"] = llm_time
            direct_result["llm_used"] = True
            
            return direct_result
            
        except json.JSONDecodeError as e:
            llm_time = time.time() - llm_start
            logger.error(f"❌ [SearchEngine] Error parseando JSON de LLM: {e}")
            return self._fallback_to_direct(
                current_params, search_type, 
                f"LLM JSON parsing error: {e}", llm_time
            )
            
        except Exception as e:
            llm_time = time.time() - llm_start
            logger.error(f"❌ [SearchEngine] Error inesperado en LLM: {e}", exc_info=True)
            return self._fallback_to_direct(
                current_params, search_type, 
                f"Error inesperado LLM: {str(e)}", llm_time
            )
    
    # ============== FUNCIONES AUXILIARES (Sin cambios) ==============
    
    def _build_system_prompt(self) -> str:
        """Construye el system prompt para el LLM."""
        return """Eres un asistente que MODIFICA búsquedas previas de productos veterinarios.

CRITICAL: Tu respuesta debe ser ÚNICAMENTE un objeto JSON válido.
NO agregues explicaciones, NO uses markdown, NO escribas texto antes o después del JSON.

FORMATO OBLIGATORIO:
{
    "action": "search_products" o "search_offers",
    "nombre": "...",
    "proveedor": "...",
    "descuento_min": 20,
    ...
}

REGLAS:
1. Preserva parámetros previos que no se modifican
2. Si el usuario reemplaza un valor, usa el nuevo
3. Si el usuario agrega un filtro, inclúyelo
4. Si el usuario remueve algo, omítelo

Responde SOLO el JSON, nada más."""

    def _build_user_prompt(
        self,
        previous_params: Dict[str, Any],
        current_params: Dict[str, Any],
        user_message: str,
        search_type: str
    ) -> str:
        """Construye el user prompt para el LLM."""
        return f"""Parámetros previos:
{json.dumps(previous_params, indent=2, ensure_ascii=False)}

Parámetros actuales detectados:
{json.dumps(current_params, indent=2, ensure_ascii=False)}

Mensaje del usuario: "{user_message}"

Tipo de búsqueda: {search_type}

Combina los parámetros y dame el JSON final."""

    def _extract_json_from_response(self, text: str) -> Dict[str, Any]:
        """
        Extrae JSON de la respuesta del LLM.
        Maneja casos donde viene con markdown (```json...```).
        """
        try:
            # Intentar parsear directo
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Buscar JSON dentro de markdown code blocks
        import re
        
        # Patrón 1: ```json ... ```
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Patrón 2: Buscar { ... } más grande
        brace_match = re.search(r'\{.*\}', text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass
        
        # Si todo falla
        logger.error(f"❌ No se pudo extraer JSON de: {text[:200]}")
        raise json.JSONDecodeError("No se encontró JSON válido", text, 0)

    def _transform_params_for_api(
        self, 
        params: Dict[str, Any], 
        action: str
    ) -> Dict[str, Any]:
        """Transforma parámetros al formato de la API."""
        api_params = {}
        
        # Validar parámetros
        is_valid, error_msg = self._validate_params(params.copy(), action)
        if not is_valid:
            logger.error(f"❌ [SearchEngine] Validación fallida: {error_msg}")
            raise ValueError(error_msg)
        
        # Transformar 'nombre' a 'producto_1', 'producto_2', etc.
        if "nombre" in params and params["nombre"]:
            nombres = [n.strip() for n in str(params["nombre"]).split(',') if n.strip()]
            for i, nombre in enumerate(nombres, start=1):
                api_params[f"producto_{i}"] = nombre
                
                # Dosis solo para el primer producto
                if i == 1 and action == "search_products":
                    for dosis_key in ["dosis_gramaje", "dosis_volumen", "dosis_forma"]:
                        if dosis_key in params:
                            api_params[f"{dosis_key}_1"] = params[dosis_key]

        # Transformar otros parámetros
        for key in ["proveedor", "categoria", "estado"]:
            if key in params and params[key]:
                value = params[key]
                api_params[key] = ','.join(str(v) for v in value) if isinstance(value, list) else str(value)
    
        # Copiar parámetros numéricos
        for key in ["descuento_min", "descuento_max", "bonificacion_min", 
                    "bonificacion_max", "stock_min", "stock_max"]:
            if key in params and params[key] is not None:
                api_params[key] = params[key]
    
        logger.info(f"🔄 [SearchEngine] Transformación completada")
        logger.debug(f"    IN:  {params}")
        logger.debug(f"    OUT: {api_params}")
        
        return api_params

    def _validate_params(
        self, 
        params: Dict[str, Any], 
        action: str
    ) -> Tuple[bool, Optional[str]]:
        """Valida parámetros antes de transformar."""
        # Validar descuentos
        if "descuento_min" in params and params["descuento_min"] < 0:
            return False, "Descuento mínimo no puede ser negativo"
        if "descuento_max" in params and params["descuento_max"] > 100:
            return False, "Descuento máximo no puede ser mayor a 100%"
        
        # Normalizar estados
        if "estado" in params:
            search_type = "productos" if action == "search_products" else "ofertas"
            normalized = self._normalize_estado(params["estado"], search_type)
            if normalized is None:
                return False, f"Estado '{params['estado']}' no es válido para {search_type}"
            params["estado"] = normalized
        
        return True, None

    def _normalize_estado(self, estados_str: str, search_type: str) -> Optional[str]:
        """Normaliza uno o múltiples estados."""
        if not estados_str: 
            return None
        
        estados_individuales = [
            e.strip().lower().replace(" ", "_") 
            for e in estados_str.split(',') 
            if e.strip()
        ]
        estados_normalizados = []
        
        for estado_lower in estados_individuales:
            if search_type == "productos":
                # Solo "en_oferta" válido para productos
                if estado_lower in ESTADO_MAP["en_oferta"] or estado_lower == "en_oferta":
                    if "en_oferta" not in estados_normalizados:
                        estados_normalizados.append("en_oferta")
            
            elif search_type == "ofertas":
                # Todos los estados válidos para ofertas
                found = False
                for canonical, aliases in ESTADO_MAP.items():
                    if estado_lower == canonical or estado_lower in aliases:
                        if canonical not in estados_normalizados:
                            estados_normalizados.append(canonical)
                        found = True
                        break
                
                if not found:
                    logger.warning(f"Estado '{estado_lower}' no reconocido, omitiendo")
        
        if not estados_normalizados: 
            return None
        
        return ",".join(estados_normalizados)
    def classify_intent(
        self,
        user_message: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Clasifica si un mensaje es de BÚSQUEDA o CONVERSACIONAL.
        Usa el modelo de búsqueda (MistralB) con GPU fallback a CPU.
        
        Returns:
            {
                "is_search": bool,
                "confidence": float,
                "reasoning": str,
                "llm_time": float,
                "llm_used": str  # "gpu", "cpu", o "none"
            }
        """
        if not self._is_loaded:
            self.load()
        
        # Si no hay LLMs disponibles, asumir conversacional
        if not (self._gpu_available or self._cpu_available):
            logger.warning("⚠️ [Classify] No hay LLM disponible, asumiendo conversacional")
            return {
                "is_search": False,
                "confidence": 0.0,
                "reasoning": "No LLM available",
                "llm_time": 0.0,
                "llm_used": "none"
            }
        
        llm_start = time.time()
        
        # Construir prompt de clasificación
        system_prompt = self._build_classification_system_prompt()
        user_prompt = self._build_classification_user_prompt(user_message, context)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        raw_response = None
        llm_used = "none"
        
        try:
            # Intento 1: GPU
            if self._gpu_available:
                try:
                    logger.info(f"🧠 [Classify] Clasificando con GPU ({self.model_gpu})...")
                    response = self.client_gpu.chat.completions.create(
                        model=self.model_gpu,
                        messages=messages,
                        temperature=0.1,  # Baja temperatura para clasificación
                        max_tokens=200,
                        timeout=GENERATION_TIMEOUT
                    )
                    raw_response = response.choices[0].message.content
                    llm_used = "gpu"
                    logger.info(f"✅ [Classify] GPU respondió")
                
                except (APITimeoutError, APIConnectionError, NotFoundError) as e:
                    logger.warning(f"⚠️ [Classify] Error GPU: {e}")
                    self._gpu_available = False
                    raw_response = None
            
            # Intento 2: CPU
            if raw_response is None and self._cpu_available:
                try:
                    logger.info(f"🧠 [Classify] Clasificando con CPU ({self.model_cpu})...")
                    response = self.client_cpu.chat.completions.create(
                        model=self.model_cpu,
                        messages=messages,
                        temperature=0.1,
                        max_tokens=200,
                        timeout=GENERATION_TIMEOUT
                    )
                    raw_response = response.choices[0].message.content
                    llm_used = "cpu"
                    logger.info(f"✅ [Classify] CPU respondió")
                
                except (APITimeoutError, APIConnectionError, NotFoundError) as e:
                    logger.error(f"❌ [Classify] Error CPU: {e}")
                    self._cpu_available = False
                    return {
                        "is_search": False,
                        "confidence": 0.0,
                        "reasoning": f"LLM error: {e}",
                        "llm_time": time.time() - llm_start,
                        "llm_used": "none"
                    }
            
            if raw_response is None:
                return {
                    "is_search": False,
                    "confidence": 0.0,
                    "reasoning": "No LLM responded",
                    "llm_time": time.time() - llm_start,
                    "llm_used": "none"
                }
            
            # Parsear respuesta
            llm_time = time.time() - llm_start
            classification = self._parse_classification_response(raw_response)
            classification["llm_time"] = llm_time
            classification["llm_used"] = llm_used
            
            logger.info(
                f"✅ [Classify] Resultado: {'BÚSQUEDA' if classification['is_search'] else 'CONVERSACIONAL'} "
                f"(conf: {classification['confidence']:.2f}, {llm_used.upper()}, {llm_time:.2f}s)"
            )
            
            return classification
            
        except Exception as e:
            logger.error(f"❌ [Classify] Error: {e}", exc_info=True)
            return {
                "is_search": False,
                "confidence": 0.0,
                "reasoning": f"Error: {str(e)}",
                "llm_time": time.time() - llm_start,
                "llm_used": llm_used
            }
    
    def generate_search_from_message(
        self,
        user_message: str,
        context: Dict[str, Any],
        search_type: str = "productos"
    ) -> Dict[str, Any]:
        """
        Genera parámetros de búsqueda desde un mensaje del usuario.
        Usa el modelo de búsqueda (MistralB) con GPU fallback a CPU.
        
        Returns:
            {
                "success": bool,
                "search_params": Dict[str, Any],
                "search_type": str,
                "confidence": float,
                "llm_time": float,
                "llm_used": str
            }
        """
        if not self._is_loaded:
            self.load()
        
        if not (self._gpu_available or self._cpu_available):
            logger.error("❌ [GenerateSearch] No hay LLM disponible")
            return {
                "success": False,
                "error": "No LLM available",
                "search_params": {},
                "search_type": search_type,
                "llm_time": 0.0,
                "llm_used": "none"
            }
        
        llm_start = time.time()
        
        # Construir prompts
        system_prompt = self._build_search_generation_system_prompt()
        user_prompt = self._build_search_generation_user_prompt(
            user_message, context, search_type
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        raw_response = None
        llm_used = "none"
        
        try:
            # Intento 1: GPU
            if self._gpu_available:
                try:
                    logger.info(f"🧠 [GenerateSearch] Generando búsqueda con GPU...")
                    response = self.client_gpu.chat.completions.create(
                        model=self.model_gpu,
                        messages=messages,
                        temperature=TEMPERATURE,
                        max_tokens=500,
                        timeout=GENERATION_TIMEOUT
                    )
                    raw_response = response.choices[0].message.content
                    llm_used = "gpu"
                    logger.info(f"✅ [GenerateSearch] GPU respondió")
                
                except (APITimeoutError, APIConnectionError, NotFoundError) as e:
                    logger.warning(f"⚠️ [GenerateSearch] Error GPU: {e}")
                    self._gpu_available = False
                    raw_response = None
            
            # Intento 2: CPU
            if raw_response is None and self._cpu_available:
                try:
                    logger.info(f"🧠 [GenerateSearch] Generando búsqueda con CPU...")
                    response = self.client_cpu.chat.completions.create(
                        model=self.model_cpu,
                        messages=messages,
                        temperature=TEMPERATURE,
                        max_tokens=500,
                        timeout=GENERATION_TIMEOUT
                    )
                    raw_response = response.choices[0].message.content
                    llm_used = "cpu"
                    logger.info(f"✅ [GenerateSearch] CPU respondió")
                
                except (APITimeoutError, APIConnectionError, NotFoundError) as e:
                    logger.error(f"❌ [GenerateSearch] Error CPU: {e}")
                    self._cpu_available = False
                    return {
                        "success": False,
                        "error": f"LLM error: {e}",
                        "search_params": {},
                        "search_type": search_type,
                        "llm_time": time.time() - llm_start,
                        "llm_used": "none"
                    }
            
            if raw_response is None:
                return {
                    "success": False,
                    "error": "No LLM responded",
                    "search_params": {},
                    "search_type": search_type,
                    "llm_time": time.time() - llm_start,
                    "llm_used": "none"
                }
            
            # Parsear JSON
            llm_time = time.time() - llm_start
            llm_output = self._extract_json_from_response(raw_response)
            
            # Extraer action y parámetros
            action = llm_output.get("action", "search_products")
            inferred_search_type = "ofertas" if action == "search_offers" else "productos"
            
            search_params = {
                k: v for k, v in llm_output.items() 
                if k != "action" and v is not None
            }
            
            logger.info(
                f"✅ [GenerateSearch] Parámetros generados: {json.dumps(search_params)} "
                f"({llm_used.upper()}, {llm_time:.2f}s)"
            )
            
            return {
                "success": True,
                "search_params": search_params,
                "search_type": inferred_search_type,
                "confidence": 0.8,  # Puedes ajustar según necesites
                "llm_time": llm_time,
                "llm_used": llm_used
            }
            
        except json.JSONDecodeError as e:
            llm_time = time.time() - llm_start
            logger.error(f"❌ [GenerateSearch] Error parseando JSON: {e}")
            return {
                "success": False,
                "error": f"JSON parsing error: {str(e)}",
                "search_params": {},
                "search_type": search_type,
                "llm_time": llm_time,
                "llm_used": llm_used
            }
        
        except Exception as e:
            llm_time = time.time() - llm_start
            logger.error(f"❌ [GenerateSearch] Error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "search_params": {},
                "search_type": search_type,
                "llm_time": llm_time,
                "llm_used": llm_used
            }
    
    # ============== PROMPTS PARA CLASIFICACIÓN ==============
    
    def _build_classification_system_prompt(self) -> str:
        """System prompt para clasificar intención."""
        return """Eres un clasificador de intenciones para un chatbot veterinario.

Tu tarea: Determinar si el mensaje del usuario es una BÚSQUEDA de productos/ofertas o es CONVERSACIONAL.

BÚSQUEDA incluye:
- Solicitudes de productos (nombre, categoría, animal, síntoma, dosis)
- Solicitudes de ofertas, descuentos, promociones
- Comparaciones de precios, stock
- Filtros específicos (proveedor, estado, cantidad)
- Ejemplos: "busco antibióticos para perros", "ofertas con más de 20% descuento", "productos nuevos"

CONVERSACIONAL incluye:
- Saludos, despedidas, agradecimientos
- Preguntas sobre el servicio, cómo funciona
- Quejas, feedback negativo
- Conversación casual sin intención de búsqueda
- Ejemplos: "hola", "gracias", "no me sirvió", "¿cómo funciona esto?"

FORMATO OBLIGATORIO (responde SOLO este JSON):
{
    "is_search": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "breve explicación"
}"""

    def _build_classification_user_prompt(
        self,
        user_message: str,
        context: Dict[str, Any]
    ) -> str:
        """User prompt para clasificación."""
        sentiment = context.get('detected_sentiment', 'neutral')
        implicit_intentions = context.get('implicit_intentions', [])
        search_history = context.get('search_history', [])
        
        context_info = []
        
        if search_history:
            last_search = search_history[-1]
            context_info.append(f"Última búsqueda: {last_search.get('type', 'producto')}")
        
        if sentiment not in ['neutral', 'positive']:
            context_info.append(f"Sentimiento: {sentiment}")
        
        if implicit_intentions:
            context_info.append(f"Intenciones implícitas: {', '.join(implicit_intentions)}")
        
        context_str = "\n".join(context_info) if context_info else "Sin contexto previo"
        
        return f"""Mensaje del usuario: "{user_message}"

Contexto:
{context_str}

Clasifica la intención y responde con el JSON."""

    # ============== PROMPTS PARA GENERACIÓN DE BÚSQUEDA ==============
    
    def _build_search_generation_system_prompt(self) -> str:
        """System prompt para generar búsqueda desde mensaje."""
        return """Eres un asistente que EXTRAE parámetros de búsqueda de productos veterinarios desde mensajes del usuario.

CRITICAL: Tu respuesta debe ser ÚNICAMENTE un objeto JSON válido.
NO agregues explicaciones, NO uses markdown, NO escribas texto antes o después del JSON.

FORMATO OBLIGATORIO:
{
    "action": "search_products" o "search_offers",
    "nombre": "nombre del producto (opcional)",
    "proveedor": "nombre del proveedor (opcional)",
    "categoria": "categoría (opcional)",
    "animal": "perro/gato/bovino/etc (opcional)",
    "sintoma": "síntoma (opcional)",
    "estado": "nuevo/poco_stock/vence_pronto/en_oferta (opcional)",
    "descuento_min": 20 (opcional, número),
    "descuento_max": 50 (opcional, número),
    "bonificacion_min": 10 (opcional, número),
    "stock_min": 5 (opcional, número)
}

REGLAS:
1. Usa "search_products" si busca productos, "search_offers" si busca ofertas/descuentos
2. Extrae SOLO los parámetros que menciona el usuario
3. Normaliza valores (ej: "perrito" → "perro")
4. Si menciona comparación (">", "más de"), usa _min; ("<", "menos de"), usa _max
5. Estados válidos: nuevo, poco_stock, vence_pronto, en_oferta

Responde SOLO el JSON, nada más."""

    def _build_search_generation_user_prompt(
        self,
        user_message: str,
        context: Dict[str, Any],
        search_type: str
    ) -> str:
        """User prompt para generación de búsqueda."""
        search_history = context.get('search_history', [])
        
        context_info = ""
        if search_history:
            last_search = search_history[-1]
            last_params = last_search.get('parameters', {})
            if last_params:
                context_info = f"\n\nBúsqueda previa:\n{json.dumps(last_params, indent=2, ensure_ascii=False)}"
        
        return f"""Mensaje del usuario: "{user_message}"

Tipo de búsqueda sugerido: {search_type}{context_info}

Extrae los parámetros de búsqueda y dame el JSON."""

    # ============== PARSEO DE RESPUESTAS ==============
    
    def _parse_classification_response(self, raw_response: str) -> Dict[str, Any]:
        """Parsea respuesta de clasificación."""
        try:
            # Intentar extraer JSON
            classification = self._extract_json_from_response(raw_response)
            
            # Validar campos requeridos
            is_search = classification.get("is_search", False)
            confidence = float(classification.get("confidence", 0.5))
            reasoning = classification.get("reasoning", "")
            
            # Normalizar bool (por si viene como string)
            if isinstance(is_search, str):
                is_search = is_search.lower() in ['true', 'yes', 'sí', '1']
            
            return {
                "is_search": bool(is_search),
                "confidence": min(max(confidence, 0.0), 1.0),  # Clamp 0-1
                "reasoning": reasoning
            }
            
        except Exception as e:
            logger.error(f"❌ [ParseClassification] Error: {e}")
            # Fallback: buscar keywords en texto plano
            text_lower = raw_response.lower()
            
            if any(word in text_lower for word in ["is_search: true", "búsqueda", "search"]):
                return {"is_search": True, "confidence": 0.6, "reasoning": "Keyword match"}
            else:
                return {"is_search": False, "confidence": 0.6, "reasoning": "Keyword match (conversational)"}

# ============== INSTANCIA GLOBAL (Sin cambios) ==============
_search_engine = SearchEngine()

def get_search_engine() -> SearchEngine:
    """Función helper para obtener la instancia única del motor."""
    if not _search_engine._is_loaded:
        _search_engine.load()
    return _search_engine