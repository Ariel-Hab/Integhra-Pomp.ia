import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from rasa_sdk import Tracker
from scripts.config_loader import ConfigLoader
from .config import INTENT_CONFIG

logger = logging.getLogger(__name__)

# ===== FUNCIONES ORIGINALES MANTENIDAS =====

def get_intent_info(intent_name: str) -> Dict[str, Any]:
    """Obtiene información de configuración para un intent específico"""
    return INTENT_CONFIG.get("intents", {}).get(intent_name, {})

def is_search_intent(intent_name: str) -> bool:
    """Determina si un intent es de tipo búsqueda"""
    return get_intent_info(intent_name).get("grupo") == "busqueda"

def is_small_talk_intent(intent_name: str) -> bool:
    """Determina si un intent es de small talk"""
    return get_intent_info(intent_name).get("grupo") == "small_talk"

def detect_sentiment_in_message(user_message: str) -> str:
    """Detecta sentimiento en el mensaje del usuario."""
    try:
        text = user_message.lower()
        if any(word in text for word in ["mal", "triste", "enojado", "horrible"]):
            return "negativo"
        elif any(word in text for word in ["bien", "feliz", "genial", "excelente"]):
            return "positivo"
        else:
            return "neutral"
    except Exception as e:
        logger.error(f"[Helpers] Error detectando sentimiento: {e}")
        return "neutral"

def detect_implicit_intentions(user_message: str) -> List[str]:
    """Detecta intenciones implícitas en el mensaje (básico)."""
    try:
        implicit_intents = []
        text = user_message.lower()

        if "comparar" in text or "vs" in text:
            implicit_intents.append("comparacion")
        if "último" in text or "reciente" in text:
            implicit_intents.append("filtro_tiempo")
        if "descuento" in text or "oferta" in text:
            implicit_intents.append("buscar_oferta")

        return implicit_intents
    except Exception as e:
        logger.error(f"[Helpers] Error detectando intenciones implícitas: {e}")
        return []

def get_search_type_from_intent(intent_name: str) -> str:
    """Extrae el tipo de búsqueda desde el nombre del intent"""
    if intent_name == "buscar_producto":
        return "producto"
    elif intent_name == "buscar_oferta":
        return "oferta"
    return "producto"

def normalize_date(date_string: str, default_year: Optional[int] = None) -> Optional[str]:
    """Normaliza fechas a formato YYYY-MM-DD con soporte de múltiples formatos"""
    try:
        if not date_string:
            return None
        
        date_lower = date_string.lower().strip()
        current_year = datetime.now().year
        year_to_use = default_year or current_year
        
        logger.debug(f"[Helpers] Normalizando fecha: '{date_string}'")
        
        # Patrón dd/mm/yyyy o dd-mm-yyyy
        match = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", date_lower)
        if match:
            day, month, year = match.groups()
            result = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            logger.debug(f"[Helpers] Fecha normalizada (dd/mm/yyyy): {result}")
            return result
        
        # Patrón yyyy-mm-dd (ya normalizado)
        match = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", date_lower)
        if match:
            year, month, day = match.groups()
            result = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            logger.debug(f"[Helpers] Fecha ya normalizada: {result}")
            return result
        
        # Patrón "dd de mes de año" o "dd de mes"
        months_es = {
            "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
            "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
            "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12"
        }
        
        match = re.match(r"(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s*(?:de\s+(\d{4}))?", date_lower)
        if match:
            day, month_name, year = match.groups()
            month_num = months_es.get(month_name, "01")
            year = year or str(year_to_use)
            result = f"{year}-{month_num}-{day.zfill(2)}"
            logger.debug(f"[Helpers] Fecha normalizada (texto): {result}")
            return result
        
        logger.warning(f"[Helpers] No se pudo normalizar la fecha: '{date_string}'")
        return None
        
    except Exception as e:
        logger.error(f"[Helpers] Error normalizando fecha '{date_string}': {e}")
        return None

def sanitize_user_input(user_input: str) -> str:
    """Sanitiza entrada del usuario para evitar problemas de seguridad o parsing"""
    try:
        if not user_input:
            return ""
        
        # Limpiar espacios excesivos
        sanitized = re.sub(r'\s+', ' ', user_input.strip())
        
        # Remover caracteres de control
        sanitized = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', sanitized)
        
        # Limitar longitud
        if len(sanitized) > 1000:
            sanitized = sanitized[:1000]
            logger.warning("[Helpers] Entrada del usuario truncada por longitud excesiva")
        
        return sanitized
        
    except Exception as e:
        logger.error(f"[Helpers] Error sanitizando entrada: {e}")
        return str(user_input)[:200] if user_input else ""

# ===============================
# ✅ SISTEMA DE VALIDACIÓN CORREGIDO
# ===============================

# ✅ CORREGIDO: Import con mejor manejo de errores
try:
    from actions.config import validate_entity_value, get_entity_suggestions, get_lookup_tables  # type: ignore
    _HAS_VALIDATE_FN = True
    logger.info("[Helpers] Sistema de lookup tables cargado correctamente")
except ImportError as e:
    logger.warning(f"[Helpers] No se pudieron cargar funciones de config: {e}")
    _HAS_VALIDATE_FN = False
except Exception as e:
    logger.error(f"[Helpers] Error inesperado cargando funciones de config: {e}")
    _HAS_VALIDATE_FN = False

# Mapeo entidad -> nombre de parámetro usado internamente
_ENTITY_TO_PARAM = {
    'producto': 'nombre',
    'producto_name': 'nombre',
    'compuesto': 'ingrediente_activo',
    'ingrediente_activo': 'ingrediente_activo',
    'categoria': 'categoria',
    'empresa': 'empresa',
    'animal': 'animal',
    'dosis': 'dosis',
    'cantidad': 'cantidad',
    'cantidad_stock': 'cantidad_stock',
    'precio': 'precio',
    'descuento': 'cantidad_descuento',
    'bonificacion': 'cantidad_bonificacion',
    'sintoma': 'sintoma',
    'fecha': 'fecha',
    'tiempo': 'tiempo'
}

_NUMERIC_ENTITIES = {
    'cantidad', 'cantidad_stock', 'precio', 'descuento', 'bonificacion',
    'cantidad_descuento', 'cantidad_bonificacion', 'dosis'
}

_WORD_FRAGMENT_PATTERNS = [
    r'^[aeiou]$',  # Solo una vocal
    r'^[bcdfghjklmnpqrstvwxyz]$',  # Solo una consonante
    r'^(pro|prod|cat|ani|ing|des|bon|can|pre|sto)$',  # Fragmentos específicos conocidos
    r'^[a-z]{1}$',  # Solo una letra
]

_VALID_SHORT_WORDS = {
    # Unidades médicas y de medida
    'mg', 'ml', 'kg', 'gr', 'ui', 'cc', 'cm', 'mm', 'lt', 'dl', 'cl',
    'mg/ml', 'mg/kg', 'ui/ml', 'mcg', 'µg',
    # Vías de administración abreviadas
    'iv', 'im', 'po', 'sc', 'id', 'ip', 'ic', 'sl', 'pr',
    # Términos médicos comunes de 2-3 letras
    'ph', 'rx', 'dx', 'sx', 'tx', 'hx',
    # Abreviaciones farmacéuticas
    'gel', 'sol', 'cap', 'tab',
    # Respuestas básicas
    'si', 'sí', 'no', 'ok', 'ya'
}

_DOSE_PATTERNS = [
    r'^\d+\s*mg$', r'^\d+\s*ml$', r'^\d+\s*kg$', r'^\d+\s*gr$',
    r'^\d+\s*ui$', r'^\d+\s*cc$', r'^\d+\s*mcg$', r'^\d+\s*µg$',
    r'^\d+\.?\d*\s*mg$', r'^\d+\.?\d*\s*ml$',  # Con decimales
    r'^\d+\s*mg/kg$', r'^\d+\s*mg/ml$',  # Ratios
    r'^\d+%$', r'^%\d+$',  # Porcentajes
]

def _map_entity_to_param(entity_type: str) -> str:
    """Mapea un tipo de entidad a nombre de parámetro empleado en el sistema"""
    return _ENTITY_TO_PARAM.get(entity_type, entity_type)

def _is_valid_numeric(value: str) -> bool:
    """Valida si un string representa un número válido"""
    try:
        value_clean = value.strip().replace('%', '').replace(',', '.')
        float(value_clean)
        return True
    except (ValueError, AttributeError):
        return False

def _is_medical_dose_pattern(value: str) -> bool:
    """Detecta si un valor sigue patrones de dosis médica válida"""
    try:
        if not value:
            return False
            
        value_clean = value.lower().strip()
        
        for pattern in _DOSE_PATTERNS:
            if re.match(pattern, value_clean):
                logger.debug(f"[Medical] '{value}' reconocido como dosis válida")
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"[Medical] Error verificando patrón de dosis '{value}': {e}")
        return False

def _is_in_lookup_tables(value: str, entity_type: str = "") -> Tuple[bool, Optional[str]]:
    """
    ✅ FUNCIÓN CORREGIDA: Verifica exhaustivamente en lookup tables con debugging detallado
    
    Returns:
        Tuple[bool, Optional[str]]: (found, exact_match_or_none)
    """
    try:
        if not value or not _HAS_VALIDATE_FN:
            logger.debug(f"[Lookup] Sin valor o funciones no disponibles: value='{value}', has_fn={_HAS_VALIDATE_FN}")
            return False, None
            
        value_clean = value.lower().strip()
        logger.debug(f"[Lookup] Verificando '{value_clean}' en lookup tables para tipo '{entity_type}'")
        
        # ✅ NUEVA LÓGICA: Verificación directa con logging detallado
        if entity_type:
            try:
                is_valid = validate_entity_value(entity_type, value_clean)  # type: ignore
                logger.debug(f"[Lookup] validate_entity_value('{entity_type}', '{value_clean}') = {is_valid}")
                
                if is_valid:
                    logger.info(f"[Lookup] ✅ '{value}' ENCONTRADO en lookup table para {entity_type}")
                    return True, value_clean
                else:
                    logger.debug(f"[Lookup] ❌ '{value}' NO encontrado en lookup table para {entity_type}")
                    
            except Exception as e:
                logger.error(f"[Lookup] Error en validate_entity_value para {entity_type}: {e}")

        # ✅ NUEVA FUNCIONALIDAD: Verificación cruzada en otros tipos si falla el específico
        if not entity_type or entity_type:  # Siempre hacer verificación cruzada
            common_types = ['producto', 'categoria', 'empresa', 'animal', 'sintoma', 'dosis', 'estado']
            for lookup_type in common_types:
                if lookup_type != entity_type:  # Evitar re-verificar el mismo tipo
                    try:
                        is_valid_cross = validate_entity_value(lookup_type, value_clean)  # type: ignore
                        logger.debug(f"[Lookup] Verificación cruzada: validate_entity_value('{lookup_type}', '{value_clean}') = {is_valid_cross}")
                        
                        if is_valid_cross:
                            logger.warning(f"[Lookup] 🔄 '{value}' encontrado en {lookup_type} pero se buscaba en {entity_type}")
                            return True, f"{lookup_type}:{value_clean}"  # Indicar el tipo real encontrado
                            
                    except Exception as cross_error:
                        logger.debug(f"[Lookup] Error en verificación cruzada {lookup_type}: {cross_error}")
                        continue
        
        # ✅ NUEVA FUNCIONALIDAD: Verificación manual en lookup tables si están disponibles
        try:
            all_lookups = get_lookup_tables()  # type: ignore
            if all_lookups and isinstance(all_lookups, dict):
                logger.debug(f"[Lookup] Lookup tables disponibles: {list(all_lookups.keys())}")
                
                # Verificar en el tipo específico
                if entity_type in all_lookups:
                    lookup_values = all_lookups[entity_type]
                    if isinstance(lookup_values, list):
                        # Búsqueda exacta
                        for lookup_val in lookup_values:
                            if str(lookup_val).lower().strip() == value_clean:
                                logger.info(f"[Lookup] ✅ '{value}' encontrado por búsqueda manual en {entity_type}")
                                return True, value_clean
                        
                        # Búsqueda parcial (contiene)
                        for lookup_val in lookup_values:
                            if value_clean in str(lookup_val).lower() or str(lookup_val).lower() in value_clean:
                                logger.info(f"[Lookup] 🔍 '{value}' coincidencia parcial con '{lookup_val}' en {entity_type}")
                                return True, str(lookup_val).lower()
                
                # Verificación cruzada manual si no se encontró en tipo específico
                for table_type, table_values in all_lookups.items():
                    if table_type != entity_type and isinstance(table_values, list):
                        for lookup_val in table_values:
                            if str(lookup_val).lower().strip() == value_clean:
                                logger.warning(f"[Lookup] 🔄 '{value}' encontrado por búsqueda manual en {table_type} (tipo incorrecto)")
                                return True, f"{table_type}:{str(lookup_val).lower()}"
                                
        except Exception as manual_error:
            logger.error(f"[Lookup] Error en verificación manual de lookup tables: {manual_error}")
        
        logger.debug(f"[Lookup] ❌ '{value}' NO encontrado en ninguna lookup table")
        return False, None
        
    except Exception as e:
        logger.error(f"[Lookup] Error crítico verificando en lookup tables '{value}': {e}")
        return False, None

def _get_entity_suggestions_enhanced(value: str, entity_type: str) -> List[str]:
    """
    ✅ NUEVA FUNCIÓN: Obtiene sugerencias con múltiples métodos de fallback
    """
    suggestions = []
    
    try:
        # Método 1: Usar función del sistema si está disponible
        if _HAS_VALIDATE_FN:
            try:
                system_suggestions = get_entity_suggestions(entity_type, value)  # type: ignore
                if system_suggestions and isinstance(system_suggestions, list):
                    suggestions.extend(system_suggestions)
                    logger.debug(f"[Suggestions] Sistema devolvió {len(system_suggestions)} sugerencias para '{value}'")
            except Exception as e:
                logger.debug(f"[Suggestions] Error obteniendo sugerencias del sistema: {e}")
        
        # Método 2: Búsqueda manual por similitud si el sistema no devuelve resultados
        if not suggestions:
            try:
                all_lookups = get_lookup_tables()  # type: ignore
                if all_lookups and entity_type in all_lookups:
                    lookup_values = all_lookups[entity_type]
                    if isinstance(lookup_values, list):
                        import difflib
                        # Usar difflib para encontrar similitudes
                        close_matches = difflib.get_close_matches(
                            value.lower(), 
                            [str(v).lower() for v in lookup_values],
                            n=3, 
                            cutoff=0.6
                        )
                        suggestions.extend(close_matches)
                        logger.debug(f"[Suggestions] Difflib encontró {len(close_matches)} sugerencias similares")
            except Exception as e:
                logger.debug(f"[Suggestions] Error en búsqueda manual por similitud: {e}")
        
        # Método 3: Búsqueda cruzada en otros tipos si no hay resultados
        if not suggestions and _HAS_VALIDATE_FN:
            cross_types = ['producto', 'categoria', 'empresa', 'animal', 'sintoma']
            for cross_type in cross_types:
                if cross_type != entity_type:
                    try:
                        cross_suggestions = get_entity_suggestions(cross_type, value)  # type: ignore
                        if cross_suggestions and isinstance(cross_suggestions, list):
                            # Marcar como sugerencias cruzadas
                            for sug in cross_suggestions[:2]:  # Solo las 2 mejores
                                suggestions.append(f"{sug} ({cross_type})")
                            logger.debug(f"[Suggestions] Sugerencias cruzadas de {cross_type}: {len(cross_suggestions)}")
                            break  # Solo usar el primer tipo que devuelva resultados
                    except Exception:
                        continue
        
        logger.info(f"[Suggestions] Total de {len(suggestions)} sugerencias encontradas para '{value}' (tipo: {entity_type})")
        return suggestions[:5]  # Limitar a máximo 5 sugerencias
        
    except Exception as e:
        logger.error(f"[Suggestions] Error crítico obteniendo sugerencias para '{value}': {e}")
        return []

def _is_likely_word_fragment(value: str, min_length: int = 2, entity_type: str = "") -> bool:
    """Detecta fragmentos usando lookup tables dinámicas"""
    try:
        if not value or len(value) < 1:
            return True
        
        value_lower = value.lower().strip()
        
        # ✅ PRIORIDAD 1: Si está en las lookup tables del sistema, NO es fragmento
        found_in_lookup, exact_match = _is_in_lookup_tables(value_lower, entity_type)
        if found_in_lookup:
            logger.debug(f"[Anti-Fragment] '{value}' NO es fragmento - encontrado en lookup tables")
            return False
        
        # ✅ PRIORIDAD 2: Si sigue patrón de dosis, NO es fragmento
        if _is_medical_dose_pattern(value_lower):
            logger.debug(f"[Anti-Fragment] '{value}' NO es fragmento - patrón de dosis válido")
            return False
        
        # ✅ PRIORIDAD 3: Si está en lista de palabras válidas cortas, NO es fragmento
        if value_lower in _VALID_SHORT_WORDS:
            logger.debug(f"[Anti-Fragment] '{value}' NO es fragmento - palabra corta válida")
            return False
        
        # ✅ VERIFICAR PATRONES RESTRICTIVOS (solo fragmentos reales)
        for pattern in _WORD_FRAGMENT_PATTERNS:
            if re.match(pattern, value_lower):
                logger.debug(f"[Anti-Fragment] '{value}' ES fragmento por patrón: {pattern}")
                return True
        
        # ✅ LONGITUD MÍNIMA AJUSTADA
        if len(value_lower) < max(min_length, 2):
            logger.debug(f"[Anti-Fragment] '{value}' ES fragmento por longitud < {max(min_length, 2)}")
            return True
        
        # ✅ Si llegó hasta aquí, probablemente NO es fragmento
        logger.debug(f"[Anti-Fragment] '{value}' NO es fragmento - pasó todas las validaciones")
        return False
        
    except Exception as e:
        logger.error(f"[Anti-Fragment] Error verificando fragmento para '{value}': {e}")
        return True  # En caso de error, asumir que es fragmento

def validate_entity_detection(entity_type: str,
                              entity_value: Any,
                              intent_name: Optional[str] = None,
                              min_length: int = 2,
                              check_fragments: bool = True) -> Dict[str, Any]:
    """
    ✅ FUNCIÓN CORREGIDA: Validación con flujo mejorado y debugging detallado
    """
    try:
        result = {
            "valid": False,
            "normalized": None,
            "reason": None,
            "suggestions": [],
            "param_name": _map_entity_to_param(entity_type),
            "debug_info": {}
        }

        if entity_value is None:
            result["reason"] = "empty"
            result["debug_info"]["stage"] = "null_check"
            return result

        # Normalizar/sanitizar
        value = sanitize_user_input(str(entity_value)).strip()
        if value == "":
            result["reason"] = "empty_after_sanitize"
            result["debug_info"]["stage"] = "sanitization"
            return result

        logger.info(f"[Validation] Validando {entity_type}='{value}' (longitud: {len(value)})")
        result["debug_info"]["original_value"] = value
        result["debug_info"]["entity_type"] = entity_type

        # ✅ PASO 1: Verificar en lookup tables con debugging detallado
        found_in_lookup, exact_match = _is_in_lookup_tables(value, entity_type)
        result["debug_info"]["lookup_check"] = {"found": found_in_lookup, "match": exact_match}
        
        if found_in_lookup:
            result["valid"] = True
            result["normalized"] = exact_match if exact_match else value
            result["debug_info"]["stage"] = "lookup_validation"
            logger.info(f"[Validation] ✅ {entity_type}='{value}' VÁLIDO por lookup tables")
            return result

        # ✅ PASO 2: Verificar si es patrón médico válido
        if _is_medical_dose_pattern(value):
            result["valid"] = True
            result["normalized"] = value
            result["debug_info"]["stage"] = "medical_pattern"
            logger.info(f"[Validation] ✅ {entity_type}='{value}' VÁLIDO por patrón médico")
            return result

        # ✅ PASO 3: Verificar si es fragmento de palabra
        if check_fragments and _is_likely_word_fragment(value, min_length, entity_type):
            # Obtener sugerencias antes de rechazar por fragmento
            suggestions = _get_entity_suggestions_enhanced(value, entity_type)
            result["suggestions"] = suggestions
            result["reason"] = "word_fragment"
            result["debug_info"]["stage"] = "fragment_check"
            result["debug_info"]["suggestions_found"] = len(suggestions)
            logger.info(f"[Validation] ❌ {entity_type}='{value}' rechazado como fragmento, {len(suggestions)} sugerencias")
            return result

        # ✅ PASO 4: Si la entidad es numérica, validar número
        if entity_type in _NUMERIC_ENTITIES:
            if _is_valid_numeric(value):
                result["valid"] = True
                result["normalized"] = value
                result["debug_info"]["stage"] = "numeric_validation"
                logger.info(f"[Validation] ✅ {entity_type}='{value}' VÁLIDO como número")
                return result
            else:
                result["reason"] = "not_numeric"
                result["debug_info"]["stage"] = "numeric_validation_failed"
                logger.info(f"[Validation] ❌ {entity_type}='{value}' rechazado - no es número válido")
                return result

        # ✅ PASO 5: Verificar longitud mínima
        if len(value) < min_length and value.lower() not in _VALID_SHORT_WORDS:
            suggestions = _get_entity_suggestions_enhanced(value, entity_type)
            result["suggestions"] = suggestions
            result["reason"] = "too_short"
            result["debug_info"]["stage"] = "length_check"
            result["debug_info"]["suggestions_found"] = len(suggestions)
            logger.info(f"[Validation] ❌ {entity_type}='{value}' rechazado por longitud < {min_length}, {len(suggestions)} sugerencias")
            return result

        # ✅ PASO 6: Obtener sugerencias si no fue válido hasta aquí
        suggestions = _get_entity_suggestions_enhanced(value, entity_type)
        if suggestions:
            result["suggestions"] = suggestions
            result["reason"] = "not_in_lookup"
            result["debug_info"]["stage"] = "suggestions_found"
            result["debug_info"]["suggestions_found"] = len(suggestions)
            logger.info(f"[Validation] ❌ {entity_type}='{value}' no válido, {len(suggestions)} sugerencias disponibles")
            return result

        # ✅ PASO 7: Validaciones finales básicas
        # Rechazar si el valor es solo puntuación
        if re.match(r'^[\W_]+$', value):
            result["reason"] = "non_alphanumeric"
            result["debug_info"]["stage"] = "punctuation_check"
            logger.info(f"[Validation] ❌ {entity_type}='{value}' rechazado - solo puntuación")
            return result

        # Rechazar palabras comunes irrelevantes
        irrelevant_common_words = {
            'el', 'la', 'los', 'las', 'un', 'una', 'de', 'del', 'en', 'con', 'para', 'por', 'que'
        }
        
        if value.lower() in irrelevant_common_words:
            result["reason"] = "irrelevant_word"
            result["debug_info"]["stage"] = "irrelevant_word_check"
            logger.info(f"[Validation] ❌ {entity_type}='{value}' rechazado - palabra común irrelevante")
            return result

        # ✅ PASO 8: Si llegó hasta aquí sin ser validado ni rechazado, es inválido
        result["reason"] = "invalid_value"
        result["debug_info"]["stage"] = "final_rejection"
        logger.info(f"[Validation] ❌ {entity_type}='{value}' rechazado - no cumple criterios de validación")
        return result

    except Exception as e:
        logger.error(f"[Validation] Error crítico validando entidad {entity_type}='{entity_value}': {e}")
        return {
            "valid": False, 
            "normalized": None, 
            "reason": "exception", 
            "suggestions": [], 
            "param_name": _map_entity_to_param(entity_type),
            "debug_info": {"error": str(e), "stage": "exception"}
        }

def validate_entities_for_intent(
    entities: List[Dict[str, Any]],
    intent_name: Optional[str] = None,
    min_length: int = 2,
    check_fragments: bool = True
) -> Dict[str, Any]:
    """
    ✅ FUNCIÓN CORREGIDA: Validación con debugging detallado y mejor manejo de sugerencias
    """
    try:
        valid_params: Dict[str, Any] = {}
        errors: List[str] = []
        suggestions: List[Dict[str, Any]] = []
        debug_info: List[Dict[str, Any]] = []

        if not entities:
            logger.info("[Validation] No hay entidades para validar")
            return {
                "valid_params": {},
                "errors": [],
                "suggestions": [],
                "has_suggestions": False,
                "has_errors": False,
                "debug_info": []
            }

        logger.info(f"[Validation] === INICIANDO VALIDACIÓN DE {len(entities)} ENTIDADES ===")

        for i, ent in enumerate(entities):
            try:
                etype = ent.get("entity")
                raw_value = ent.get("value")
                confidence = ent.get("confidence", 0.0)

                if etype is None or raw_value is None:
                    continue

                logger.info(f"[Validation] [{i+1}/{len(entities)}] Procesando {etype}='{raw_value}' (conf: {confidence:.2f})")

                # Validación individual
                validation_result = validate_entity_detection(
                    etype, raw_value,
                    intent_name=intent_name,
                    min_length=min_length,
                    check_fragments=check_fragments
                )

                # Agregar información de debugging
                entity_debug = {
                    "index": i,
                    "entity_type": etype,
                    "raw_value": raw_value,
                    "confidence": confidence,
                    "validation_result": validation_result.get("debug_info", {}),
                    "final_status": "valid" if validation_result.get("valid") else "invalid"
                }
                debug_info.append(entity_debug)

                param_name = validation_result.get("param_name") or _map_entity_to_param(etype)

                if validation_result.get("valid"):
                    # Manejar múltiples valores para un mismo parámetro
                    existing = valid_params.get(param_name)
                    normalized_value = validation_result["normalized"]
                    
                    if existing:
                        if isinstance(existing, list):
                            if normalized_value not in existing:
                                existing.append(normalized_value)
                        else:
                            if existing != normalized_value:
                                valid_params[param_name] = [existing, normalized_value]
                    else:
                        valid_params[param_name] = normalized_value

                    logger.info(f"[Validation] ✅ [{i+1}] {etype}='{raw_value}' -> {param_name}='{normalized_value}' VÁLIDO")

                else:
                    reason = validation_result.get("reason", "invalid")
                    entity_suggestions = validation_result.get("suggestions", [])
                    
                    if entity_suggestions:
                        suggestion_item = {
                            "entity_type": etype,
                            "raw_value": raw_value,
                            "suggestions": entity_suggestions,
                            "confidence": confidence,
                            "reason": reason
                        }
                        suggestions.append(suggestion_item)
                        logger.info(f"[Validation] 💡 [{i+1}] {etype}='{raw_value}' INVÁLIDO ({reason}) -> {len(entity_suggestions)} sugerencias")
                    else:
                        # Solo mostrar errores para casos significativos
                        if reason not in ["too_short", "irrelevant_word", "word_fragment"]:
                            error_msg = f"'{raw_value}' no parece un {etype} válido"
                            errors.append(error_msg)
                            logger.info(f"[Validation] ❌ [{i+1}] {etype}='{raw_value}' ERROR ({reason})")
                        else:
                            logger.info(f"[Validation] 🟡 [{i+1}] {etype}='{raw_value}' IGNORADO ({reason})")

            except Exception as entity_error:
                logger.error(f"[Validation] Error procesando entidad {i+1} {ent}: {entity_error}")
                continue

        # Ordenar sugerencias por confianza de entidad original (descendente)
        suggestions.sort(key=lambda x: x.get("confidence", 0.0), reverse=True)

        result = {
            "valid_params": valid_params,
            "errors": errors,
            "suggestions": suggestions,
            "has_suggestions": len(suggestions) > 0,
            "has_errors": len(errors) > 0,
            "debug_info": debug_info
        }

        logger.info(f"[Validation] === RESULTADO FINAL ===")
        logger.info(f"[Validation] ✅ Parámetros válidos: {len(valid_params)} -> {list(valid_params.keys())}")
        logger.info(f"[Validation] 💡 Sugerencias: {len(suggestions)}")
        logger.info(f"[Validation] ❌ Errores: {len(errors)}")
        
        if suggestions:
            for i, sug in enumerate(suggestions[:3]):  # Mostrar las 3 primeras
                logger.info(f"[Validation]   Sugerencia {i+1}: {sug['entity_type']}='{sug['raw_value']}' -> {sug['suggestions'][:2]}")
        
        return result

    except Exception as e:
        logger.error(f"[Validation] Error crítico en validate_entities_for_intent: {e}")
        return {
            "valid_params": {},
            "errors": [f"Error interno validando entidades: {str(e)}"],
            "suggestions": [],
            "has_suggestions": False,
            "has_errors": True,
            "debug_info": []
        }

def calculate_confidence_score(factors: Dict[str, float]) -> float:
    """Calcula puntuación de confianza basada en múltiples factores"""
    try:
        if not factors:
            return 0.0
        
        default_weights = {
            "entity_match": 0.3,
            "intent_confidence": 0.25,
            "comparison_detected": 0.2,
            "temporal_filters": 0.15,
            "parameter_completeness": 0.1
        }
        
        weighted_sum = 0.0
        total_weight = 0.0
        
        for factor_name, factor_value in factors.items():
            if factor_value is not None and 0 <= factor_value <= 1:
                weight = default_weights.get(factor_name, 0.1)
                weighted_sum += factor_value * weight
                total_weight += weight
        
        if total_weight == 0:
            return 0.0
        
        confidence = min(weighted_sum / total_weight, 1.0)
        logger.debug(f"[Helpers] Confianza calculada: {confidence:.2f} basada en {len(factors)} factores")
        
        return confidence
        
    except Exception as e:
        logger.error(f"[Helpers] Error calculando confianza: {e}")
        return 0.0