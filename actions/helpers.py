import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from .config import INTENT_CONFIG

logger = logging.getLogger(__name__)

# ===== CONFIGURACIÓN DE OPTIMIZACIÓN =====
MAX_LOOKUP_ITERATIONS = 100  # ✅ Limitar iteraciones en lookup tables
MAX_CROSS_TYPE_CHECKS = 3    # ✅ Limitar verificaciones cruzadas
ENABLE_CROSS_CHECK = False   # ✅ DESACTIVAR verificaciones cruzadas por defecto (muy lentas)
ENABLE_MANUAL_SEARCH = False # ✅ DESACTIVAR búsqueda manual (muy lenta)
# =========================================

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
        
        # Patrón dd/mm/yyyy o dd-mm-yyyy
        match = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", date_lower)
        if match:
            day, month, year = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        
        # Patrón yyyy-mm-dd (ya normalizado)
        match = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", date_lower)
        if match:
            year, month, day = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        
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
            return f"{year}-{month_num}-{day.zfill(2)}"
        
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
        
        return sanitized
        
    except Exception as e:
        logger.error(f"[Helpers] Error sanitizando entrada: {e}")
        return str(user_input)[:200] if user_input else ""

# ===============================
# ✅ SISTEMA DE VALIDACIÓN OPTIMIZADO
# ===============================

# ✅ Import con mejor manejo de errores
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
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"[Medical] Error verificando patrón de dosis '{value}': {e}")
        return False

def _is_in_lookup_tables(value: str, entity_type: str = "") -> Tuple[bool, Optional[str]]:
    """
    ✅ OPTIMIZADO: Verificación en lookup tables SIN verificaciones cruzadas lentas
    
    Returns:
        Tuple[bool, Optional[str]]: (found, exact_match_or_none)
    """
    try:
        if not value or not _HAS_VALIDATE_FN:
            return False, None
            
        value_clean = value.lower().strip()
        
        # ✅ ÚNICA VERIFICACIÓN: Tipo específico solamente
        if entity_type:
            try:
                is_valid = validate_entity_value(entity_type, value_clean)  # type: ignore
                
                if is_valid:
                    logger.debug(f"[Lookup] ✅ '{value}' encontrado en {entity_type}")
                    return True, value_clean
                    
            except Exception as e:
                logger.debug(f"[Lookup] Error en validate_entity_value para {entity_type}: {e}")

        # ✅ REMOVIDO: Verificación cruzada (muy lenta)
        # ✅ REMOVIDO: Verificación manual (muy lenta)
        
        return False, None
        
    except Exception as e:
        logger.error(f"[Lookup] Error verificando '{value}': {e}")
        return False, None

def _get_entity_suggestions_enhanced(value: str, entity_type: str) -> List[str]:
    """
    ✅ OPTIMIZADO: Obtiene sugerencias SOLO del sistema, sin búsquedas manuales
    """
    suggestions = []
    
    try:
        # ✅ ÚNICO MÉTODO: Usar función del sistema (más rápido)
        if _HAS_VALIDATE_FN and entity_type:
            try:
                system_suggestions = get_entity_suggestions(entity_type, value)  # type: ignore
                if system_suggestions and isinstance(system_suggestions, list):
                    suggestions.extend(system_suggestions[:3])  # ✅ Limitar a 3 sugerencias
                    logger.debug(f"[Suggestions] {len(suggestions)} sugerencias para '{value}'")
            except Exception as e:
                logger.debug(f"[Suggestions] Error obteniendo sugerencias: {e}")
        
        # ✅ REMOVIDO: Búsqueda manual por similitud (muy lenta)
        # ✅ REMOVIDO: Búsqueda cruzada en otros tipos (muy lenta)
        
        return suggestions[:3]  # ✅ Máximo 3 sugerencias
        
    except Exception as e:
        logger.error(f"[Suggestions] Error obteniendo sugerencias: {e}")
        return []

def _is_likely_word_fragment(value: str, min_length: int = 2, entity_type: str = "") -> bool:
    """✅ OPTIMIZADO: Detecta fragmentos usando solo validaciones rápidas"""
    try:
        if not value or len(value) < 1:
            return True
        
        value_lower = value.lower().strip()
        
        # ✅ VERIFICACIÓN RÁPIDA 1: Palabras cortas válidas
        if value_lower in _VALID_SHORT_WORDS:
            return False
        
        # ✅ VERIFICACIÓN RÁPIDA 2: Patrones de dosis
        if _is_medical_dose_pattern(value_lower):
            return False
        
        # ✅ VERIFICACIÓN RÁPIDA 3: Lookup tables (SOLO si es necesario)
        if entity_type and _HAS_VALIDATE_FN:
            try:
                # ✅ Una sola llamada rápida
                is_valid = validate_entity_value(entity_type, value_lower)  # type: ignore
                if is_valid:
                    return False
            except:
                pass
        
        # ✅ VERIFICACIÓN RÁPIDA 4: Patrones de fragmentos
        for pattern in _WORD_FRAGMENT_PATTERNS:
            if re.match(pattern, value_lower):
                return True
        
        # ✅ VERIFICACIÓN RÁPIDA 5: Longitud mínima
        if len(value_lower) < max(min_length, 2):
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"[Anti-Fragment] Error verificando '{value}': {e}")
        return True

def validate_entity_detection(entity_type: str,
                              entity_value: Any,
                              intent_name: Optional[str] = None,
                              min_length: int = 2,
                              check_fragments: bool = True) -> Dict[str, Any]:
    """
    ✅ OPTIMIZADO: Validación rápida sin búsquedas exhaustivas
    """
    try:
        result = {
            "valid": False,
            "normalized": None,
            "reason": None,
            "suggestions": [],
            "param_name": _map_entity_to_param(entity_type)
        }

        if entity_value is None:
            result["reason"] = "empty"
            return result

        # Normalizar/sanitizar
        value = sanitize_user_input(str(entity_value)).strip()
        if value == "":
            result["reason"] = "empty_after_sanitize"
            return result

        # ✅ PASO 1: Verificar en lookup tables (UNA SOLA VEZ)
        found_in_lookup, exact_match = _is_in_lookup_tables(value, entity_type)
        
        if found_in_lookup:
            result["valid"] = True
            result["normalized"] = exact_match if exact_match else value
            return result

        # ✅ PASO 2: Verificar si es patrón médico válido
        if _is_medical_dose_pattern(value):
            result["valid"] = True
            result["normalized"] = value
            return result

        # ✅ PASO 3: Si es numérico y debe serlo, validar
        if entity_type in _NUMERIC_ENTITIES:
            if _is_valid_numeric(value):
                result["valid"] = True
                result["normalized"] = value
                return result
            else:
                result["reason"] = "not_numeric"
                return result

        # ✅ PASO 4: Verificar fragmento (RÁPIDO)
        if check_fragments and _is_likely_word_fragment(value, min_length, entity_type):
            # ✅ OBTENER SUGERENCIAS SOLO SI ES FRAGMENTO
            suggestions = _get_entity_suggestions_enhanced(value, entity_type)
            result["suggestions"] = suggestions
            result["reason"] = "word_fragment"
            return result

        # ✅ PASO 5: Verificar longitud mínima
        if len(value) < min_length and value.lower() not in _VALID_SHORT_WORDS:
            suggestions = _get_entity_suggestions_enhanced(value, entity_type)
            result["suggestions"] = suggestions
            result["reason"] = "too_short"
            return result

        # ✅ PASO 6: Rechazar solo puntuación
        if re.match(r'^[\W_]+$', value):
            result["reason"] = "non_alphanumeric"
            return result

        # ✅ PASO 7: Rechazar palabras comunes irrelevantes
        irrelevant_common_words = {
            'el', 'la', 'los', 'las', 'un', 'una', 'de', 'del', 'en', 'con', 'para', 'por', 'que'
        }
        
        if value.lower() in irrelevant_common_words:
            result["reason"] = "irrelevant_word"
            return result

        # ✅ PASO 8: Obtener sugerencias como último recurso
        suggestions = _get_entity_suggestions_enhanced(value, entity_type)
        if suggestions:
            result["suggestions"] = suggestions
            result["reason"] = "not_in_lookup"
            return result

        # ✅ PASO 9: Rechazar si no cumple ningún criterio
        result["reason"] = "invalid_value"
        return result

    except Exception as e:
        logger.error(f"[Validation] Error validando {entity_type}='{entity_value}': {e}")
        return {
            "valid": False, 
            "normalized": None, 
            "reason": "exception", 
            "suggestions": [], 
            "param_name": _map_entity_to_param(entity_type)
        }

def validate_entities_for_intent(
    entities: List[Dict[str, Any]],
    intent_name: Optional[str] = None,
    min_length: int = 2,
    check_fragments: bool = True
) -> Dict[str, Any]:
    """
    ✅ OPTIMIZADO: Validación sin logging excesivo
    """
    try:
        valid_params: Dict[str, Any] = {}
        errors: List[str] = []
        suggestions: List[Dict[str, Any]] = []

        if not entities:
            logger.debug("[Validation] No hay entidades para validar")
            return {
                "valid_params": {},
                "errors": [],
                "suggestions": [],
                "has_suggestions": False,
                "has_errors": False
            }

        logger.debug(f"[Validation] Validando {len(entities)} entidades")

        for i, ent in enumerate(entities):
            try:
                etype = ent.get("entity")
                raw_value = ent.get("value")

                if etype is None or raw_value is None:
                    continue

                # Validación individual (RÁPIDA)
                validation_result = validate_entity_detection(
                    etype, raw_value,
                    intent_name=intent_name,
                    min_length=min_length,
                    check_fragments=check_fragments
                )

                param_name = validation_result.get("param_name") or _map_entity_to_param(etype)

                if validation_result.get("valid"):
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

                    logger.debug(f"[Validation] ✅ {etype}='{raw_value}' válido")

                else:
                    reason = validation_result.get("reason", "invalid")
                    entity_suggestions = validation_result.get("suggestions", [])
                    
                    if entity_suggestions:
                        suggestion_item = {
                            "entity_type": etype,
                            "raw_value": raw_value,
                            "suggestions": entity_suggestions
                        }
                        suggestions.append(suggestion_item)
                        logger.debug(f"[Validation] 💡 {etype}='{raw_value}' -> sugerencias")
                    elif reason not in ["too_short", "irrelevant_word", "word_fragment"]:
                        logger.debug(f"[Validation] ❌ {etype}='{raw_value}' inválido ({reason})")

            except Exception as entity_error:
                logger.error(f"[Validation] Error procesando entidad {i+1}: {entity_error}")
                continue

        result = {
            "valid_params": valid_params,
            "errors": errors,
            "suggestions": suggestions,
            "has_suggestions": len(suggestions) > 0,
            "has_errors": len(errors) > 0
        }

        logger.info(f"[Validation] Resultado: {len(valid_params)} válidos, {len(suggestions)} sugerencias")
        
        return result

    except Exception as e:
        logger.error(f"[Validation] Error crítico: {e}")
        return {
            "valid_params": {},
            "errors": [f"Error validando entidades: {str(e)}"],
            "suggestions": [],
            "has_suggestions": False,
            "has_errors": True
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
        
        return confidence
        
    except Exception as e:
        logger.error(f"[Helpers] Error calculando confianza: {e}")
        return 0.0