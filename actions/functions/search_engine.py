# actions/actions_busqueda/search_engine.py
import logging
import os
import time
import json
from typing import Dict, Any, Tuple, List, Optional

# from dotenv import load_dotenv
from actions.functions.conections_broker import ConnectionBroker, ConnectionType, get_broker
# from openai import OpenAI, APITimeoutError, APIConnectionError, NotFoundError

from actions.api_client import search_products, search_offers

logger = logging.getLogger(__name__)


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
    Ahora el LLM es el responsable principal de generar búsquedas,
    usando el pre-análisis del NLU como guía.
    """
    
    def __init__(self):
        # self.client_gpu = None
        # self.client_cpu = None
        
        # self.url_gpu = OLLAMA_GPU_URL
        # self.url_cpu = OLLAMA_CPU_URL
        # self.model_gpu = MODEL_SEARCH_GPU
        # self.model_cpu = MODEL_SEARCH_CPU
        self.broker: Optional[ConnectionBroker] = None 
        self._is_loaded = False 
        self._gpu_available = False 
        self._cpu_available = False 
        
    def load(self):
        """
        🔄 MODIFICADO: Carga el broker de conexiones.
        """
        if self._is_loaded:
            logger.info("🔒 [SearchEngine] Ya está cargado")
            return
        
        logger.info("🔧 [SearchEngine] Inicializando broker...")
        self.broker = get_broker()
        self._is_loaded = True
        logger.info("✅ [SearchEngine] Broker listo")

    def warmup(self) -> bool:
        """
        🔄 MODIFICADO: Calienta el broker con una request de prueba.
        """
        if not self._is_loaded:
            self.load()
        
        logger.info("🔥 [SearchEngine] Calentando broker (via SearchEngine)...")
        
        try:
            test_messages = [
                {"role": "system", "content": "Responde con un JSON simple"},
                {"role": "user", "content": "Dame un JSON con {test: true}"}
            ]
            
            # ✅ NUEVO: Usa el broker para el warmup
            result = self.broker.generate(
                messages=test_messages,
                temperature=0,
                max_tokens=50,
                timeout=GENERATION_TIMEOUT
            )
            
            if result:
                logger.info("✅ [SearchEngine] Warmup exitoso")
                return True
            else:
                logger.warning("⚠️ [SearchEngine] Warmup falló (broker retornó None)")
                return False
                
        except Exception as e:
            logger.warning(f"⚠️ [SearchEngine] Error en warmup: {e}")
            return False

    def is_gpu_available(self) -> bool:
        """
        ✅ CORREGIDO: Verifica si "GPU" (alias de RunPod) está disponible.
        """
        if not self._is_loaded:
            self.load()
        
        if not self.broker:
            return False
            
        status = self.broker.get_status()
        
        # ✅ SOLUCIÓN: Hacemos que "GPU" sea un alias de "RUNPOD"
        runpod_status = status.get(ConnectionType.RUNPOD.value, {})
        return runpod_status.get("available", False)
    # ============== PUNTO DE ENTRADA PRINCIPAL ==============
    def _is_broker_available(self) -> bool:
        if not self.broker:
            return False
        status = self.broker.get_status()
        # Verifica si alguna conexión está disponible
        return any(conn.get("available", False) for conn in status.values())

    # ✅ NUEVO: Helper para saber qué conexión usó el broker
    def _get_last_used_connection(self, broker_status: Dict) -> str:
        """Helper para determinar qué conexión se usó"""
        most_recent = None
        most_recent_time = 0
        
        for conn_name, conn_data in broker_status.items():
            last_used = conn_data.get("last_used")
            if last_used and last_used > most_recent_time:
                most_recent = conn_name
                most_recent_time = last_used
        
        return most_recent or "none"
    
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
        🔄 MODIFICADO: Usa _is_broker_available() para el fallback.
        """
        if not self._is_loaded:
            self.load()
        
        # ✅ CASO 1: Modificación
        if is_modification and previous_params:
            logger.info("🧠 [SearchEngine] Usando LLM (Broker) para MODIFICACIÓN")
            return self._execute_with_llm_modification(
                current_params=search_params,
                previous_params=previous_params,
                user_message=user_message,
                search_type=search_type,
                chat_history=chat_history or []
            )
        
        # ✅ CASO 2: Búsqueda NUEVA (usa el broker si está disponible)
        elif self._is_broker_available():
            logger.info("🧠 [SearchEngine] Usando LLM (Broker) para BÚSQUEDA NUEVA")
            return self._execute_with_llm_new_search(
                pre_analyzed_params=search_params,
                user_message=user_message,
                search_type=search_type
            )
        
        # ⚠️ CASO 3: Fallback si NO hay broker
        else:
            logger.warning("⚠️ [SearchEngine] No hay LLM (Broker) disponible. Usando pre-análisis directo.")
            return self.execute_direct(search_params, search_type)
    
    # ============== ✅ NUEVO: BÚSQUEDA NUEVA CON LLM ==============
    
    def _execute_with_llm_new_search(
        self,
        pre_analyzed_params: Dict[str, Any],
        user_message: str,
        search_type: str
    ) -> Dict[str, Any]:
        """
        🔄 MODIFICADO: Usa self.broker.generate() en lugar de try/except GPU/CPU
        """
        llm_start = time.time()
        
        # 1. Preparar prompts (sin cambios)
        system_prompt = self._build_new_search_system_prompt(search_type)
        user_prompt = self._build_new_search_user_prompt(
            user_message, pre_analyzed_params 
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        raw_response = None
        llm_time = 0.0
        llm_used = "none"
        
        try:
            # --- ✅ NUEVO: Llamada única al Broker ---
            logger.info(f"🧠 [NewSearch] Enviando a Broker...")
            
            raw_response = self.broker.generate(
                messages=messages,
                temperature=TEMPERATURE,
                max_tokens=500,
                timeout=GENERATION_TIMEOUT
            )
            
            llm_time = time.time() - llm_start
            
            # Obtener qué conexión se usó
            status = self.broker.get_status()
            llm_used = self._get_last_used_connection(status)
            
            # --- ❌ ELIMINADO: Lógica try/except GPU/CPU ---

            # --- Si no hay respuesta ---
            if raw_response is None:
                logger.error("❌ [NewSearch] El Broker retornó None")
                return self._fallback_to_direct(
                    pre_analyzed_params, search_type, 
                    "Broker returned None", llm_time
                )

            logger.info(f"✅ [NewSearch] Broker respondió en {llm_time:.3f}s (usando {llm_used})")
            
            # --- 3. Parsear respuesta (sin cambios) ---
            logger.debug(f"[NewSearch] Respuesta cruda: {raw_response}")
            llm_output = self._extract_json_from_response(raw_response)
            logger.debug(f"    LLM Output: {json.dumps(llm_output, ensure_ascii=False)}")
            
            # 4. Extraer parámetros finales (sin cambios)
            final_params = {
                k: v for k, v in llm_output.items() 
                if k != "action" and v is not None
            }
            action = llm_output.get("action", "search_products")
            final_search_type = "ofertas" if action == "search_offers" else "productos"
            
            logger.info(f"🛠️ [NewSearch] Parámetros finales del LLM: {json.dumps(final_params, ensure_ascii=False)}")
            
            # 5. Ejecutar búsqueda directa (sin cambios)
            direct_result = self.execute_direct(final_params, final_search_type)
            direct_result["llm_time"] = llm_time
            direct_result["llm_used"] = llm_used # Ahora será "ollama_gpu", "ollama_cpu", etc.
            direct_result["final_params"] = final_params
            direct_result["final_search_type"] = final_search_type
            return direct_result

        
        except json.JSONDecodeError as e:
            llm_time = time.time() - llm_start
            logger.error(f"❌ [NewSearch] Error parseando JSON: {e}")
            return self._fallback_to_direct(
                pre_analyzed_params, search_type, 
                f"JSON parsing error: {e}", llm_time
            )
        
        except Exception as e:
            # ✅ NUEVO: Captura errores del broker
            llm_time = time.time() - llm_start
            logger.error(f"❌ [NewSearch] Error en Broker.generate(): {e}", exc_info=True)
            return self._fallback_to_direct(
                pre_analyzed_params, search_type, 
                f"Error Broker: {str(e)}", llm_time
            )
    
    # ============== ✅ MODIFICADO: MODIFICACIÓN CON LLM ==============
    
    def _execute_with_llm_modification(
        self,
        current_params: Dict[str, Any],
        previous_params: Dict[str, Any],
        user_message: str,
        search_type: str,
        chat_history: List[Dict]
    ) -> Dict[str, Any]:
        """
        🔄 MODIFICADO: Usa self.broker.generate() en lugar de try/except GPU/CPU
        """
        
        llm_start = time.time()
        
        # 1. Preparar prompts (sin cambios)
        system_prompt = self._build_modification_system_prompt()
        user_prompt = self._build_modification_user_prompt(
            previous_params, current_params, user_message, search_type
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        raw_response = None
        llm_time = 0.0
        llm_used = "none"
        
        try:
            # --- ✅ NUEVO: Llamada única al Broker ---
            logger.info(f"🧠 [Modification] Enviando a Broker...")
            
            raw_response = self.broker.generate(
                messages=messages,
                temperature=TEMPERATURE,
                max_tokens=500,
                timeout=GENERATION_TIMEOUT
            )
            
            llm_time = time.time() - llm_start
            
            status = self.broker.get_status()
            llm_used = self._get_last_used_connection(status)
            
            # --- ❌ ELIMINADO: Lógica try/except GPU/CPU ---
            
            # --- Si no hay respuesta ---
            if raw_response is None:
                logger.error("❌ [Modification] El Broker retornó None")
                return self._fallback_to_direct(
                    current_params, search_type, 
                    "Broker returned None", llm_time
                )
            
            logger.info(f"✅ [Modification] Broker respondió en {llm_time:.3f}s (usando {llm_used})")

            # --- 3. Parsear respuesta (sin cambios) ---
            logger.debug(f"[Modification] Respuesta cruda: {raw_response}")
            llm_output = self._extract_json_from_response(raw_response)
            logger.debug(f"    LLM Output: {json.dumps(llm_output, ensure_ascii=False)}")
            
            # 4. Extraer parámetros (sin cambios)
            rebuilt_params = {
                k: v for k, v in llm_output.items() 
                if k != "action" and v is not None
            }
            logger.info(f"🛠️ [Modification] Parámetros reconstruidos: {json.dumps(rebuilt_params, ensure_ascii=False)}")
            
            # 5. Ejecutar búsqueda (sin cambios)
            direct_result = self.execute_direct(rebuilt_params, search_type)
            direct_result["llm_time"] = llm_time
            direct_result["llm_used"] = llm_used
            direct_result["final_params"] = rebuilt_params
            direct_result["final_search_type"] = search_type
            return direct_result
        except json.JSONDecodeError as e:
            llm_time = time.time() - llm_start
            logger.error(f"❌ [Modification] Error parseando JSON: {e}")
            return self._fallback_to_direct(
                current_params, search_type, 
                f"JSON parsing error: {e}", llm_time
            )
        
            
        except Exception as e:
            # ✅ NUEVO: Captura errores del broker
            llm_time = time.time() - llm_start
            logger.error(f"❌ [Modification] Error en Broker.generate(): {e}", exc_info=True)
            return self._fallback_to_direct(
                current_params, search_type, 
                f"Error Broker: {str(e)}", llm_time
            )
    
    # ============== BÚSQUEDA DIRECTA (SIN LLM) ==============
    
    def execute_direct(self, search_params: Dict[str, Any], search_type: str) -> Dict[str, Any]:
        """
        Ejecuta búsqueda directa SIN usar LLM.
        
        ✅ AHORA ES PÚBLICO para permitir bypass desde el orquestador.
        
        Args:
            search_params: Parámetros de búsqueda pre-procesados
            search_type: "productos" o "ofertas"
        
        Returns:
            Dict con resultados de la API
        """
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
            f"⚠️ [SearchEngine] Fallback a búsqueda directa. Razón: {reason}"
        )
        direct_result = self.execute_direct(search_params, search_type)
        direct_result["llm_time"] = llm_time
        direct_result["llm_used"] = False
        direct_result["fallback_reason"] = reason
        return direct_result

    # ============== ✅ NUEVOS PROMPTS MEJORADOS ==============
    
    def _build_new_search_system_prompt(self, search_type: str) -> str: # <-- ACEPTA EL ARGUMENTO
            """
            ✅ NUEVO: System prompt para búsquedas nuevas con pre-análisis
            """
            
            # Determinamos la acción OBLIGATORIA basado en la sugerencia del NLU
            action_obligatoria = "search_offers" if search_type == "ofertas" else "search_products"

            # Usamos un f-string para inyectar la acción
            return f"""Eres un asistente experto en generar búsquedas de productos veterinarios.

    REGLA DE ORO: Debes generar un JSON válido. Responde SÓLO con el JSON. NADA MÁS.

    FORMATO OBLIGATORIO (responde SOLO este JSON):
    {{
        "action": "{action_obligatoria}",
        "nombre": ["producto1", "producto2"],
        "proveedor": ["Richmond", "Holliday"],
        "categoria": ["Antiparasitarios"],
        "animal": ["perro", "gato"],
        "sintoma": ["vomitos"],
        "estado": ["nuevo", "poco_stock"],
        "descuento_min": 20,
        "descuento_max": 50,
        "bonificacion_min": 10,
        "bonificacion_max": 30,
        "stock_min": 5,
        "stock_max": 100,
        "dosis_gramaje": "500mg",
        "dosis_volumen": "10ml",
        "dosis_forma": "comprimidos"
    }}

    REGLAS CRÍTICAS:
    1.  **ACCIÓN OBLIGATORIA**: El NLU ha determinado que esto es una búsqueda de '{search_type}'.
        Tu JSON DEBE incluir la clave "action" con el valor "{action_obligatoria}".
        NO USES la clave "búsqueda". USA LA CLAVE "action".

    2.  **FORMATO ARRAY OBLIGATORIO**: Los campos 'nombre', 'proveedor', 'categoria', 'animal', 'sintoma', y 'estado' DEBEN ser arrays `[]`.
        - INCORRECTO: "proveedor": "holliday"
        - CORRECTO: "proveedor": ["holliday"]

    3.  **PRE-ANÁLISIS**: El pre-análisis del NLU (que verás en el prompt del usuario) es una *guía*. Úsalo.
        - Si el pre-análisis dice `"descuento_min": 20`, tu JSON debe tener `"descuento_min": 20`.
        - Si el pre-análisis dice `"estado": "nuevo,poco_stock"`, tu JSON debe tener `"estado": ["nuevo", "poco_stock"]`.

    4.  **MENSAJE DEL USUARIO**: Úsalo para encontrar filtros que el NLU omitió (como 'amoxicilina' en "busco amoxicilina para perros").
        
    5.  **REGLA DE ESTADOS vs ACCIÓN (IMPORTANTE):**
        - Si "action" es "search_products", el ÚNICO estado válido es "en_oferta".
        - Si "action" es "search_offers", puedes usar: "nuevo", "vistas", "poco_stock", "vence_pronto".
        - Si el usuario pide "productos nuevos" (y la action es "search_products"), NO uses el filtro de estado, ignóralo.

    Responde SOLO el JSON, nada más."""

    def _build_new_search_user_prompt(
        self,
        user_message: str,
        pre_analyzed_params: Dict[str, Any]
    ) -> str:
        """
        ✅ CORREGIDO: User prompt para búsquedas nuevas
        """
        # Convertir pre-análisis a JSON legible
        pre_analysis_str = "Sin pre-análisis."
        if pre_analyzed_params:
            pre_analysis_str = json.dumps(pre_analyzed_params, indent=2, ensure_ascii=False)
        
        # ✅ ARREGLO: Se borró la línea "Tipo de búsqueda sugerido: {search_type}"
        return f"""Mensaje del usuario: "{user_message}"

Mi pre-análisis (NLU/Reglas):
{pre_analysis_str}

Genera el JSON final de búsqueda combinando el mensaje del usuario y mi pre-análisis,
siguiendo las reglas y el formato JSON obligatorio del system prompt.

JSON FINAL:"""

    def _build_modification_system_prompt(self) -> str:
            """
            ✅ REFACTORIZADO: System prompt alineado con el de búsqueda nueva.
            """
            return """Eres un asistente que MODIFICA búsquedas previas de productos veterinarios.

    REGLA DE ORO: Debes generar un JSON válido. Responde SÓLO con el JSON. NADA MÁS.

    FORMATO OBLIGATORIO (responde SOLO este JSON):
    {{
        "action": "search_products" o "search_offers",
        "nombre": ["producto1"],
        "proveedor": ["Richmond"],
        "categoria": ["Antiparasitarios"],
        "estado": ["nuevo", "poco_stock"],
        "descuento_min": 20,
        ...
    }}

    REGLAS DE MODIFICACIÓN:

    1.  **AGREGAR**: Si el usuario menciona algo nuevo, agrégalo.
        - "ahora con descuento del 15%" → agregar descuento_min: 15
        - "que sean de Richmond" → agregar proveedor: ["Richmond"]

    2.  **REEMPLAZAR**: Si el usuario cambia un valor, reemplázalo.
        - Anterior: {{"proveedor": ["Holliday"]}}
        - Usuario: "cambia a Richmond"
        - Final: {{"proveedor": ["Richmond"]}}

    3.  **REMOVER**: Si el usuario quita algo, omítelo.
        - Usuario: "sin filtro de proveedor" → NO incluir proveedor en el JSON final.
        - Usuario: "saca el estado" → NO incluir estado.

    4.  **PRESERVAR**: Todo lo que el usuario NO menciona, se mantiene.
        - Anterior: {{"nombre": ["amoxicilina"], "animal": ["perro"]}}
        - Usuario: "ahora con descuento"
        - Final: {{"nombre": ["amoxicilina"], "animal": ["perro"], "descuento_min": ...}}

    5.  **ACCIÓN**: El `action` ("search_products" o "search_offers") PUEDE cambiar.
        - Si la búsqueda anterior era "search_products" y el usuario pide "ver ofertas",
        la nueva `action` debe ser "search_offers".

    6.  **FORMATO ARRAY OBLIGATORIO**: Los campos 'nombre', 'proveedor', 'categoria', 'animal', 'sintoma', y 'estado' DEBEN ser arrays `[]`.

    7.  **REGLA DE ESTADOS vs ACCIÓN (IMPORTANTE):**
        - Si la "action" final es "search_products", el ÚNICO estado válido es "en_oferta".
        - Si la "action" final es "search_offers", puedes usar: "nuevo", "vistas", "poco_stock", "vence_pronto".
        - Si el usuario pide "productos nuevos" (y la action es "search_products"), NO uses el filtro de estado, ignóralo.

    Responde SOLO el JSON, nada más."""

    def _build_modification_user_prompt(
        self,
        previous_params: Dict[str, Any],
        current_params: Dict[str, Any],
        user_message: str,
        search_type: str
    ) -> str:
        """
        ✅ MODIFICADO: User prompt mejorado para modificaciones
        """
        return f"""El usuario quiere MODIFICAR su búsqueda.

Búsqueda Anterior (Historial):
{json.dumps(previous_params, indent=2, ensure_ascii=False)}

Mensaje del usuario: "{user_message}"

Mi pre-análisis de las NUEVAS entidades del mensaje:
{json.dumps(current_params, indent=2, ensure_ascii=False)}

Tipo de búsqueda: {search_type}

Tu trabajo:
1. Toma la "Búsqueda Anterior" como base
2. Usa el "Mensaje del usuario" y mi "pre-análisis" para entender qué cambiar (agregar, quitar, reemplazar)
3. Genera el JSON final que representa la nueva búsqueda combinada

Responde SOLO con el JSON final.

JSON FINAL:"""

    # ============== FUNCIONES AUXILIARES (Mantenidas) ==============
    
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
        """
        ✅ CORREGIDO: Transforma parámetros al formato de la API.
        Acepta arrays del LLM y los convierte a strings con comas para Django.
        """
        api_params = {}
        
        # Validar parámetros
        is_valid, error_msg = self._validate_params(params.copy(), action)
        if not is_valid:
            logger.error(f"❌ [SearchEngine] Validación fallida: {error_msg}")
            raise ValueError(error_msg)
        
        # ✅ Transformar 'nombre' a 'producto_1', 'producto_2', etc.
        if "nombre" in params and params["nombre"]:
            nombres_val = params["nombre"]
            nombres_list = []

            if isinstance(nombres_val, list):
                # El LLM envió una lista (caso ideal)
                nombres_list = [str(n).strip() for n in nombres_val if str(n).strip()]
            elif isinstance(nombres_val, str):
                # Fallback: el LLM envió un string con comas
                nombres_list = [n.strip() for n in nombres_val.split(',') if n.strip()]

            for i, nombre in enumerate(nombres_list, start=1):
                api_params[f"producto_{i}"] = nombre

                # La lógica de dosis se aplica SÓLO al primer producto
                if i == 1 and action == "search_products":
                    for dosis_key in ["dosis_gramaje", "dosis_volumen", "dosis_forma"]:
                        if dosis_key in params and params[dosis_key]:
                            api_params[f"{dosis_key}_1"] = params[dosis_key]

        # ✅ Transformar proveedor, categoria, estado (acepta lista o string)
        for key in ["proveedor", "categoria", "estado"]:
            if key in params and params[key]:
                value = params[key]
                if isinstance(value, list):
                    # Filtra valores vacíos y convierte a string
                    clean_values = [str(v).strip() for v in value if str(v).strip()]
                    if clean_values:
                        api_params[key] = ','.join(clean_values)
                elif isinstance(value, str):
                    # Acepta un string como fallback si el LLM se equivoca
                    clean_value = value.strip()
                    if clean_value:
                        api_params[key] = clean_value
    
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

    def _normalize_estado(self, estados_input: Any, search_type: str) -> Optional[str]:
        """
        ✅ CORREGIDO: Normaliza uno o múltiples estados.
        Acepta lista o string como entrada.
        """
        if not estados_input: 
            return None
        
        estados_individuales = []
        if isinstance(estados_input, list):
            # El LLM envió una lista (caso ideal)
            estados_individuales = [str(e).strip().lower().replace(" ", "_") for e in estados_input if str(e).strip()]
        elif isinstance(estados_input, str):
            # Fallback: el LLM envió un string con comas
            estados_individuales = [e.strip().lower().replace(" ", "_") for e in estados_input.split(',') if e.strip()]
        else:
            logger.warning(f"Tipo de estado no reconocido: {type(estados_input)}")
            return None  # Tipo no soportado
        
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

    # ============== FUNCIONES DE CLASIFICACIÓN (Mantenidas) ==============
    
    def classify_intent(
        self,
        user_message: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        🔄 MODIFICADO: Usa self.broker.generate() 
        """
        if not self._is_loaded:
            self.load()
        
        # 🔄 MODIFICADO: Usa _is_broker_available()
        if not self._is_broker_available():
            logger.warning("⚠️ [Classify] No hay LLM (Broker) disponible, asumiendo conversacional")
            return {
                "is_search": False,
                "confidence": 0.0,
                "reasoning": "No LLM (Broker) available",
                "llm_time": 0.0,
                "llm_used": "none"
            }
        
        llm_start = time.time()
        
        system_prompt = self._build_classification_system_prompt()
        user_prompt = self._build_classification_user_prompt(user_message, context)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        raw_response = None
        llm_used = "none"
        
        try:
            # --- ✅ NUEVO: Llamada única al Broker ---
            logger.info(f"🧠 [Classify] Clasificando con Broker...")
            
            raw_response = self.broker.generate(
                messages=messages,
                temperature=0.1,
                max_tokens=200,
                timeout=GENERATION_TIMEOUT
            )
            
            llm_time = time.time() - llm_start
            
            status = self.broker.get_status()
            llm_used = self._get_last_used_connection(status)
            
            # --- ❌ ELIMINADO: Lógica try/except GPU/CPU ---

            if raw_response is None:
                logger.error("❌ [Classify] El Broker retornó None")
                return {
                    "is_search": False,
                    "confidence": 0.0,
                    "reasoning": "No LLM (Broker) responded",
                    "llm_time": llm_time,
                    "llm_used": "none"
                }

            # Parsear respuesta (sin cambios)
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

    def _parse_classification_response(self, raw_response: str) -> Dict[str, Any]:
        """Parsea respuesta de clasificación."""
        try:
            classification = self._extract_json_from_response(raw_response)
            
            is_search = classification.get("is_search", False)
            confidence = float(classification.get("confidence", 0.5))
            reasoning = classification.get("reasoning", "")
            
            if isinstance(is_search, str):
                is_search = is_search.lower() in ['true', 'yes', 'sí', '1']
            
            return {
                "is_search": bool(is_search),
                "confidence": min(max(confidence, 0.0), 1.0),
                "reasoning": reasoning
            }
            
        except Exception as e:
            logger.error(f"❌ [ParseClassification] Error: {e}")
            text_lower = raw_response.lower()
            
            if any(word in text_lower for word in ["is_search: true", "búsqueda", "search"]):
                return {"is_search": True, "confidence": 0.6, "reasoning": "Keyword match"}
            else:
                return {"is_search": False, "confidence": 0.6, "reasoning": "Keyword match (conversational)"}


# ============== INSTANCIA GLOBAL ==============
_search_engine = SearchEngine()

def get_search_engine() -> SearchEngine:
    """Función helper para obtener la instancia única del motor."""
    # if not _search_engine._is_loaded:
    #     _search_engine.load()
    return _search_engine