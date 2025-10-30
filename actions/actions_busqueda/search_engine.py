# actions/search_engine.py
import logging
import time
import json
from typing import Dict, Any, Tuple, List, Optional
from openai import OpenAI  # ← Sigue siendo OpenAI

from actions.api_client import search_products, search_offers

logger = logging.getLogger(__name__)

# --- Constantes ---
ESTADO_MAP = {
    "en_oferta": ["rebajado", "promocion", "oferta", "con_descuento", "en_promocion"],
    "nuevo": ["nuevas", "novedades", "no_vistas", "sin_ver"],
    "vence_pronto": ["proximo_a_vencer", "por_vencer", "vencimiento_cercano"],
    "poco_stock": ["ultimas_unidades", "stock_limitado", "pocas_unidades"],
    "vistas": ["ya_vistas", "visitadas"]
}

# ← Cambio: Configuración para Ollama
OLLAMA_MODEL = "pomp-translator"
OLLAMA_BASE_URL = "http://localhost:11434/v1"  # ← API compatible OpenAI
OLLAMA_API_KEY = "ollama"  # ← No se valida, pero es requerido
TEMPERATURE = 0.1


class SearchEngine:
    """Motor de búsqueda inteligente usando Ollama."""
    
    def __init__(self):
        self.client = None
        self._is_loaded = False
        
    def load(self):
        """Carga y calienta el cliente Ollama."""
        if self._is_loaded:
            logger.info("🧠 [SearchEngine] Ya está cargado")
            return
        
        try:
            logger.info(f"🧠 [SearchEngine] Inicializando Ollama ({OLLAMA_MODEL})...")
            
            # ← Cliente OpenAI apuntando a Ollama
            self.client = OpenAI(
                base_url=OLLAMA_BASE_URL,
                api_key=OLLAMA_API_KEY  # No se valida en Ollama
            )
            
            logger.info("🔥 [SearchEngine] Calentando LLM...")
            self._warmup_llm()
            
            self._is_loaded = True
            logger.info("✅ [SearchEngine] Cerebro cargado y listo")
            
        except Exception as e:
            logger.error(f"❌ [SearchEngine] Error crítico al cargar: {e}")
            self._is_loaded = False
            raise

    def _warmup_llm(self) -> bool:
        """Calienta el LLM con una consulta simple."""
        if not self.client:
            logger.warning("⚠️ [SearchEngine] No hay cliente para calentar.")
            return False
        
        try:
            start = time.time()
            
            # Llamada de warmup simple
            _ = self.client.chat.completions.create(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": "Responde con un JSON simple"},
                    {"role": "user", "content": "Dame un JSON con {test: true}"}
                ],
                temperature=0,
                max_tokens=50
            )
            
            warmup_time = time.time() - start
            logger.info(f"✅ [SearchEngine] Modelo calentado en {warmup_time:.2f}s")
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ [SearchEngine] Error en warmup (no crítico): {e}")
            return False

    # --- Punto de Entrada Principal ---
    
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
        - Si is_modification=True → Usa Ollama para reconstruir
        """
        if not self._is_loaded:
            self.load()
        
        if is_modification:
            logger.info("🧠 [SearchEngine] Usando Ollama para MODIFICACIÓN")
            return self._execute_with_llm(
                current_params=search_params,
                previous_params=previous_params or {},
                user_message=user_message,
                search_type=search_type,
                chat_history=chat_history or []
            )
        else:
            logger.info("⚡ [SearchEngine] Búsqueda directa (sin LLM)")
            # return self._execute_with_llm(
            #     current_params=search_params,
            #     previous_params=previous_params or {},
            #     user_message=user_message,
            #     search_type=search_type,
            #     chat_history=chat_history or [])
            return self._execute_direct(search_params, search_type)
    
    # --- Búsqueda Directa (SIN LLM) ---
    
    def _execute_direct(
        self, 
        search_params: Dict[str, Any], 
        search_type: str
    ) -> Dict[str, Any]:
        """Ejecuta búsqueda directa SIN usar LLM."""
        action = "search_offers" if search_type == "ofertas" else "search_products"
        
        try:
            # Los logs de parámetros finales están en _transform_params_for_api (DEBUG)
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
                "total_results": result.get('total_results', 0)
            }
            
        except Exception as e:
            logger.error(f"❌ [SearchEngine] Error en búsqueda directa: {e}")
            return {
                "success": False,
                "error": str(e),
                "total_results": 0
            }
    
    # --- Búsqueda con Ollama (MODIFICACIONES) ---
    def warmup(search_chain):
        """
        Realiza una llamada de warmup al LLM para 'calentar' el modelo.
        Esto reduce la latencia en la primera llamada real.
        """
        logging.info("🔥 Calentando modelo LLM...")
        
        warmup_input = {
            "input": json.dumps({
                "intent": "modificar_busqueda",
                "entities": [{"entity": "proveedor", "value": "test"}],
                "previous_params": {"nombre": "test"},
                "previous_type": "productos",
                "chat_history": []
            }, ensure_ascii=False)
        }
        
        try:
            start = time.time()
            _ = search_chain.invoke(warmup_input)
            warmup_time = time.time() - start
            logging.info(f"✅ Modelo calentado en {warmup_time:.2f}s")
        except Exception as e:
            logging.warning(f"⚠️ Error en warmup (no crítico): {e}")

    def _execute_with_llm(
        self,
        current_params: Dict[str, Any],
        previous_params: Dict[str, Any],
        user_message: str,
        search_type: str,
        chat_history: List[Dict]
    ) -> Dict[str, Any]:
        """Usa Ollama para reconstruir parámetros en modificaciones."""
        llm_start = time.time()
        
        try:
            # 1. Preparar prompt
            system_prompt = """Eres un asistente que MODIFICA búsquedas previas de productos veterinarios.

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

            user_prompt = f"""Parámetros previos:
{json.dumps(previous_params, indent=2, ensure_ascii=False)}

Parámetros actuales detectados:
{json.dumps(current_params, indent=2, ensure_ascii=False)}

Mensaje del usuario: "{user_message}"

Tipo de búsqueda: {search_type}

Combina los parámetros y dame el JSON final."""

            # --- NUEVOS LOGS (INPUT) ---
            logger.info("🧠 [SearchEngine] Enviando a Ollama para reconstrucción...")
            logger.debug(f"    LLM Input - Prev Params: {json.dumps(previous_params)}")
            logger.debug(f"    LLM Input - Curr Params: {json.dumps(current_params)}")
            logger.debug(f"    LLM Input - User Msg: {user_message}")
            # Nota: chat_history se recibe pero no se está usando en el prompt.
            # Si lo agregas, la velocidad puede disminuir.

            # 2. Llamar a Ollama (usando cliente OpenAI)
            response = self.client.chat.completions.create(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=TEMPERATURE,
                max_tokens=500,
                # ⚠️ Ollama NO soporta response_format aún
                # response_format={"type": "json_object"}  
            )
            
            # --- LOG MEJORADO (TIEMPO) ---
            llm_time = time.time() - llm_start
            
            # 3. Parsear respuesta (Ollama puede devolver markdown)
            raw_response = response.choices[0].message.content
            logger.debug(f"[SearchEngine] Respuesta cruda de Ollama: {raw_response}")
            
            # Intentar extraer JSON si viene con markdown
            llm_output = self._extract_json_from_response(raw_response)
            
            # --- LOG MEJORADO (TIEMPO Y SALIDA) ---
            logger.info(f"✅ [SearchEngine] Ollama respondió en {llm_time:.3f}s")
            logger.debug(f"    LLM Output (Parseado): {json.dumps(llm_output)}")
            
            # 4. Extraer params reconstruidos
            action = llm_output.get("action", "search_products")
            rebuilt_params = {k: v for k, v in llm_output.items() 
                            if k != "action" and v is not None}
            
            # --- NUEVO LOG (OUTPUT RECONSTRUIDO) ---
            logger.info(f"🛠️ [SearchEngine] Parámetros reconstruidos por LLM: {json.dumps(rebuilt_params)}")

            # 5. Ejecutar búsqueda
            # Los logs de params FINALES (para API) están en _transform_params_for_api
            direct_result = self._execute_direct(rebuilt_params, search_type)
            direct_result["llm_time"] = llm_time
            direct_result["llm_used"] = True
            
            return direct_result
            
        except Exception as e:
            llm_time = time.time() - llm_start
            logger.error(f"❌ [SearchEngine] Error en LLM: {e}")
            return {
                "success": False,
                "error": str(e),
                "llm_time": llm_time,
                "total_results": 0
            }
    
    def _extract_json_from_response(self, text: str) -> Dict[str, Any]:
        """
        Extrae JSON de la respuesta de Ollama (puede venir con markdown).
        
        Ejemplos que maneja:
        - ```json\n{...}\n```
        - ```\n{...}\n```
        - {...}
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
        
        # Si todo falla, lanzar error con el texto original
        logger.error(f"❌ No se pudo extraer JSON de: {text[:200]}")
        raise json.JSONDecodeError("No se encontró JSON válido", text, 0)

    # --- Métodos de Transformación (sin cambios) ---
    
    def _transform_params_for_api(self, params: Dict[str, Any], action: str) -> Dict[str, Any]:
        """Transforma parámetros al formato de la API."""
        api_params = {}
        
        is_valid, error_msg = self._validate_params(params.copy(), action)
        if not is_valid:
            logger.error(f"❌ [SearchEngine] Validación fallida: {error_msg}")
            raise ValueError(error_msg)
        
        # Transformar 'nombre' a 'producto_1', 'producto_2', etc.
        if "nombre" in params and params["nombre"]:
            nombres = [n.strip() for n in str(params["nombre"]).split(',') if n.strip()]
            for i, nombre in enumerate(nombres, start=1):
                api_params[f"producto_{i}"] = nombre
                
                if i == 1 and action == "search_products":
                    if "dosis_gramaje" in params: 
                        api_params["dosis_gramaje_1"] = params["dosis_gramaje"]
                    if "dosis_volumen" in params: 
                        api_params["dosis_volumen_1"] = params["dosis_volumen"]
                    if "dosis_forma" in params: 
                        api_params["dosis_forma_1"] = params["dosis_forma"]

        # Transformar proveedor, categoria, estado
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
        # --- LOG DE PARÁMETROS FINALES (para la API) ---
        # Asegúrate de tener tu logger en nivel DEBUG para ver esto
        logger.debug(f"    IN (reconstruido):  {params}")
        logger.debug(f"    OUT (para API): {api_params}")
        
        return api_params

    def _validate_params(self, params: Dict[str, Any], action: str) -> Tuple[bool, Optional[str]]:
        """Valida parámetros antes de transformar."""
        if "descuento_min" in params and params["descuento_min"] < 0:
            return False, "Descuento mínimo no puede ser negativo"
        if "descuento_max" in params and params["descuento_max"] > 100:
            return False, "Descuento máximo no puede ser mayor a 100%"
        
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
                if estado_lower in ESTADO_MAP["en_oferta"] or estado_lower == "en_oferta":
                    if "en_oferta" not in estados_normalizados:
                        estados_normalizados.append("en_oferta")
            
            elif search_type == "ofertas":
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


# --- Instancia Global ---
_search_engine = SearchEngine()

def get_search_engine() -> SearchEngine:
    """Función helper para obtener la instancia única del motor."""
    if not _search_engine._is_loaded:
        _search_engine.load()
    return _search_engine