import logging
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class ComparisonType(Enum):
    """Tipos de comparación detectables"""
    NUMERIC = "numeric"          # más de 20%, menos de 100
    PRICE = "price"             # más barato que, más caro que
    QUALITY = "quality"         # mejor que, peor que
    QUANTITY = "quantity"       # más cantidad, menos stock
    TEMPORAL = "temporal"       # más reciente, más antiguo, esta semana
    SIZE = "size"              # más grande, más pequeño

class ComparisonOperator(Enum):
    """Operadores de comparación"""
    GREATER_THAN = "greater_than"     # más que, mayor que, superior a
    LESS_THAN = "less_than"          # menos que, menor que, inferior a
    EQUAL_TO = "equal_to"            # igual que, mismo que
    DIFFERENT_FROM = "different_from" # diferente de, distinto a

@dataclass
class ComparisonEntity:
    """Entidad involucrada en la comparación"""
    entity_type: str      # producto, proveedor, categoria, etc.
    entity_value: str     # nombre específico
    role: Optional[str]   # "reference", "target", "group"

@dataclass
class ComparisonResult:
    """Resultado del análisis de comparación"""
    detected: bool
    comparison_type: Optional[ComparisonType]
    operator: Optional[ComparisonOperator]
    entities: List[ComparisonEntity]
    quantity: Optional[str]
    groups_detected: List[str]
    roles_detected: List[str]
    confidence: float
    raw_expression: str
    # Nuevos campos para soporte temporal
    temporal_filters: Optional[Dict[str, Any]] = None
    normalized_dates: Optional[Dict[str, str]] = None

# actions/actions_busqueda/comparison_detector.py

import re
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

class ComparisonDetector:
    """Detecta y procesa comparaciones en el texto del usuario"""
    
    def __init__(self):
        """✅ INICIALIZAR TODOS LOS PATRONES"""
        
        # ========== PATRONES NUMÉRICOS (descuento/bonificación) ==========
        self.numeric_patterns = {
            'greater_than': [
                r'(?:mayor|mas|más|superior|arriba)\s+(?:de|del|a|al?)\s+(\d+)',
                r'(\d+)\s*%?\s+(?:o|ó)\s+(?:mas|más|mayor)',
                r'(?:supera|excede)\s+(?:el?\s+)?(\d+)'
            ],
            'less_than': [
                r'(?:menor|menos)\s+(?:de|del|a|al?)\s+(\d+)',
                r'(?:hasta|máximo|como\s+máximo)\s+(\d+)',
                r'(?:no\s+(?:mas|más)\s+de|debajo\s+de)\s+(\d+)'
            ],
            'equal_to': [
                r'(?:igual\s+a|exactamente|justo)\s+(\d+)',
                r'(?:de|del)\s+(\d+)\s*%',
                r'^(\d+)\s*%?\s*$'
            ],
            'between': [
                r'entre\s+(\d+)\s+y\s+(\d+)',
                r'de\s+(\d+)\s+a\s+(\d+)',
                r'desde\s+(\d+)\s+hasta\s+(\d+)'
            ]
        }
        
        # ========== PATRONES DE PRECIO ==========
        self.price_patterns = {
            'less_than': [
                r'(?:menos|menor|más\s+barato|hasta)\s+(?:de\s+)?(?:\$|pesos?)?\s*(\d+(?:\.\d+)?)',
                r'(?:no\s+(?:más|mas)\s+de|máximo)\s+(?:\$|pesos?)?\s*(\d+(?:\.\d+)?)',
                r'(?:que\s+cueste\s+menos\s+de)\s+(?:\$|pesos?)?\s*(\d+(?:\.\d+)?)'
            ],
            'greater_than': [
                r'(?:más|mas|mayor)\s+(?:de|a)\s+(?:\$|pesos?)?\s*(\d+(?:\.\d+)?)',
                r'(?:arriba\s+de|superior\s+a)\s+(?:\$|pesos?)?\s*(\d+(?:\.\d+)?)'
            ],
            'equal_to': [
                r'(?:a|de|por)\s+(?:\$|pesos?)?\s*(\d+(?:\.\d+)?)\s*(?:pesos?)?',
                r'(?:precio|cuesta|vale)\s+(?:\$|pesos?)?\s*(\d+(?:\.\d+)?)'
            ],
            'between': [
                r'entre\s+(?:\$|pesos?)?\s*(\d+(?:\.\d+)?)\s+y\s+(?:\$|pesos?)?\s*(\d+(?:\.\d+)?)',
                r'de\s+(?:\$|pesos?)?\s*(\d+(?:\.\d+)?)\s+a\s+(?:\$|pesos?)?\s*(\d+(?:\.\d+)?)'
            ]
        }
        
        # ========== PATRONES DE CALIDAD ==========
        self.quality_patterns = {
            'greater_than': [
                r'(?:mejor|superior|más\s+(?:bueno|buena))\s+(?:que|a)',
                r'(?:de\s+)?(?:mayor|mejor)\s+calidad'
            ],
            'less_than': [
                r'(?:peor|inferior|más\s+(?:malo|mala))\s+(?:que|a)',
                r'(?:de\s+)?(?:menor|peor)\s+calidad'
            ],
            'equal_to': [
                r'(?:igual|misma|mismo)\s+(?:que|a|de)',
                r'(?:tan\s+(?:bueno|buena)\s+como)'
            ]
        }
        
        # ========== PATRONES TEMPORALES ==========
        self.temporal_patterns = {
            'vigente': [
                r'vigente', r'válid[oa]', r'activ[oa]', r'disponible',
                r'en\s+curso', r'actual'
            ],
            'vencimiento': [
                r'venc[ie]', r'expira', r'caduc', r'hasta\s+(?:el\s+)?(\d{1,2}[/-]\d{1,2})',
                r'antes\s+de', r'por\s+vencer'
            ],
            'periodo': [
                r'(?:este|del)\s+(mes|año|semana|trimestre)',
                r'(?:en|de|del)\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)',
                r'(?:en|de)\s+(\d{4})'
            ]
        }
        
        # ========== PATRONES DE CANTIDAD ==========
        self.quantity_patterns = {
            'greater_than': [
                r'(?:más|mas)\s+de\s+(\d+)\s*(?:unidades?|productos?|items?)?',
                r'(?:mayor|superior)\s+a\s+(\d+)',
                r'(?:arriba\s+de|por\s+encima\s+de)\s+(\d+)'
            ],
            'less_than': [
                r'(?:menos|menor)\s+(?:de|que|a)\s+(\d+)',
                r'(?:hasta|máximo)\s+(\d+)',
                r'(?:no\s+más\s+de)\s+(\d+)'
            ],
            'equal_to': [
                r'(?:exactamente|justo)\s+(\d+)',
                r'^(\d+)\s*(?:unidades?|productos?)?$'
            ],
            'between': [
                r'entre\s+(\d+)\s+y\s+(\d+)',
                r'de\s+(\d+)\s+a\s+(\d+)'
            ]
        }
        
        # ========== PATRONES DE TAMAÑO ==========
        self.size_patterns = {
            'greater_than': [
                r'(?:mayor|más\s+grande)\s+(?:que|de|a)\s+(\d+(?:\.\d+)?)\s*(ml|l|kg|g|mg|cm|m)?',
                r'(?:superior|arriba)\s+(?:de|a)\s+(\d+(?:\.\d+)?)\s*(ml|l|kg|g|mg|cm|m)?'
            ],
            'less_than': [
                r'(?:menor|más\s+chico|más\s+pequeño)\s+(?:que|de|a)\s+(\d+(?:\.\d+)?)\s*(ml|l|kg|g|mg|cm|m)?',
                r'(?:hasta|máximo)\s+(\d+(?:\.\d+)?)\s*(ml|l|kg|g|mg|cm|m)?'
            ],
            'equal_to': [
                r'(?:de|del?)\s+(\d+(?:\.\d+)?)\s*(ml|l|kg|g|mg|cm|m)',
                r'^(\d+(?:\.\d+)?)\s*(ml|l|kg|g|mg|cm|m)$'
            ]
        }
        
        logger.info("[ComparisonDetector] ✅ Inicializado con todos los patrones")
    
    def detect_comparison(self, text: str, entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Detecta comparaciones en el texto
        
        Args:
            text: Texto del usuario
            entities: Entidades detectadas por NLU
            
        Returns:
            Dict con información de comparación detectada
        """
        try:
            logger.info(f"[ComparisonDetector] Analizando texto: '{text[:50]}...'")
            
            results = {
                'numeric': self._detect_numeric_comparison(text, entities),
                'price': self._detect_price_comparison(text),
                'quality': self._detect_quality_comparison(text),
                'temporal': self._detect_temporal_comparison(text),
                'quantity': self._detect_quantity_comparison(text),
                'size': self._detect_size_comparison(text)
            }
            
            # Encontrar la comparación con mayor confianza
            best_comparison = self._select_best_comparison(results)
            
            if best_comparison:
                logger.info(
                    f"[ComparisonDetector] Comparación detectada - "
                    f"Tipo: {best_comparison['type']}, "
                    f"Confianza: {best_comparison.get('confidence', 0):.2f}"
                )
            else:
                logger.debug("[ComparisonDetector] No se detectó comparación")
            
            return best_comparison or {'detected': False}
            
        except Exception as e:
            logger.error(f"[ComparisonDetector] Error general: {e}", exc_info=True)
            return {'detected': False}
    
    def _detect_numeric_comparison(self, text: str, entities: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Detecta comparaciones numéricas (descuento/bonificación)"""
        try:
            # Buscar entidades numéricas relacionadas
            numeric_entities = [
                e for e in entities 
                if e.get('entity') in ['cantidad_descuento', 'cantidad_bonificacion', 'descuento', 'bonificacion']
            ]
            
            if not numeric_entities:
                return None
            
            # Intentar detectar operador
            for operator, patterns in self.numeric_patterns.items():
                for pattern in patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        value = match.group(1)
                        return {
                            'detected': True,
                            'type': 'numeric',
                            'operator': operator,
                            'value': value,
                            'confidence': 0.9
                        }
            
            # Si hay entidad pero no operador, asumir equal_to
            return {
                'detected': True,
                'type': 'numeric',
                'operator': 'equal_to',
                'value': numeric_entities[0].get('value'),
                'confidence': 0.7
            }
            
        except Exception as e:
            logger.error(f"[ComparisonDetector] Error en detección numérica: {e}")
            return None
    
    def _detect_price_comparison(self, text: str) -> Optional[Dict[str, Any]]:
        """Detecta comparaciones de precio"""
        try:
            for operator, patterns in self.price_patterns.items():
                for pattern in patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        return {
                            'detected': True,
                            'type': 'price',
                            'operator': operator,
                            'value': match.group(1),
                            'confidence': 0.85
                        }
            return None
            
        except Exception as e:
            logger.error(f"[ComparisonDetector] Error en detección de precio: {e}")
            return None
    
    def _detect_quality_comparison(self, text: str) -> Optional[Dict[str, Any]]:
        """Detecta comparaciones de calidad"""
        try:
            for operator, patterns in self.quality_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, text, re.IGNORECASE):
                        return {
                            'detected': True,
                            'type': 'quality',
                            'operator': operator,
                            'confidence': 0.8
                        }
            return None
            
        except Exception as e:
            logger.error(f"[ComparisonDetector] Error en detección de calidad: {e}")
            return None
    
    def _detect_temporal_comparison(self, text: str) -> Optional[Dict[str, Any]]:
        """Detecta comparaciones temporales"""
        try:
            # Validar palabras clave temporales primero
            temporal_keywords = [
                'mes', 'semana', 'día', 'año', 'fecha', 'periodo',
                'vigente', 'vence', 'expira', 'válido', 'actual'
            ]
            
            if not any(keyword in text.lower() for keyword in temporal_keywords):
                return None
            
            # Evitar confundir porcentajes con meses
            if re.search(r'\d+\s*%', text):
                logger.debug("[ComparisonDetector] Descartado temporal: contiene porcentajes")
                return None
            
            for comparison_type, patterns in self.temporal_patterns.items():
                for pattern in patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        return {
                            'detected': True,
                            'type': 'temporal',
                            'operator': comparison_type,
                            'confidence': 0.75
                        }
            
            return None
            
        except Exception as e:
            logger.error(f"[ComparisonDetector] Error en detección temporal: {e}")
            return None
    
    def _detect_quantity_comparison(self, text: str) -> Optional[Dict[str, Any]]:
        """Detecta comparaciones de cantidad"""
        try:
            for operator, patterns in self.quantity_patterns.items():
                for pattern in patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        return {
                            'detected': True,
                            'type': 'quantity',
                            'operator': operator,
                            'value': match.group(1),
                            'confidence': 0.8
                        }
            return None
            
        except Exception as e:
            logger.error(f"[ComparisonDetector] Error en detección de cantidad: {e}")
            return None
    
    def _detect_size_comparison(self, text: str) -> Optional[Dict[str, Any]]:
        """Detecta comparaciones de tamaño"""
        try:
            for operator, patterns in self.size_patterns.items():
                for pattern in patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        value = match.group(1)
                        unit = match.group(2) if match.lastindex >= 2 else None
                        
                        return {
                            'detected': True,
                            'type': 'size',
                            'operator': operator,
                            'value': value,
                            'unit': unit,
                            'confidence': 0.8
                        }
            return None
            
        except Exception as e:
            logger.error(f"[ComparisonDetector] Error en detección de tamaño: {e}")
            return None
    
    def _select_best_comparison(self, results: Dict[str, Optional[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
        """Selecciona la mejor comparación basándose en confianza"""
        try:
            valid_comparisons = [
                comp for comp in results.values() 
                if comp and comp.get('detected')
            ]
            
            if not valid_comparisons:
                return None
            
            # Ordenar por confianza
            best = max(valid_comparisons, key=lambda x: x.get('confidence', 0))
            
            return best
            
        except Exception as e:
            logger.error(f"[ComparisonDetector] Error seleccionando mejor comparación: {e}")
            return None
    
    def _generate_temporal_filters(self, expression: str, operator: ComparisonOperator) -> Dict[str, Any]:
        """
        NUEVA FUNCIÓN: Genera filtros temporales basados en la expresión detectada
        """
        try:
            now = datetime.now()
            filters = {}
            
            expression_lower = expression.lower()
            
            if "esta semana" in expression_lower:
                # Calcular inicio y fin de esta semana
                days_since_monday = now.weekday()
                week_start = now - timedelta(days=days_since_monday)
                week_end = week_start + timedelta(days=6)
                filters["date_from"] = week_start.strftime("%Y-%m-%d")
                filters["date_to"] = week_end.strftime("%Y-%m-%d")
                filters["period"] = "current_week"
            
            elif "este mes" in expression_lower:
                # Calcular inicio y fin de este mes
                month_start = now.replace(day=1)
                if now.month == 12:
                    next_month = now.replace(year=now.year + 1, month=1, day=1)
                else:
                    next_month = now.replace(month=now.month + 1, day=1)
                month_end = next_month - timedelta(days=1)
                filters["date_from"] = month_start.strftime("%Y-%m-%d")
                filters["date_to"] = month_end.strftime("%Y-%m-%d")
                filters["period"] = "current_month"
            
            elif "reciente" in expression_lower or "nuevo" in expression_lower:
                # Últimas 2 semanas
                filters["date_from"] = (now - timedelta(weeks=2)).strftime("%Y-%m-%d")
                filters["date_to"] = now.strftime("%Y-%m-%d")
                filters["period"] = "recent"
            
            elif "último" in expression_lower or "pasado" in expression_lower:
                # Buscar número de días/semanas/meses
                time_match = re.search(r"(?:últimos?|pasados?)\s+(\d+)\s+(días?|semanas?|meses?)", expression_lower)
                if time_match:
                    number = int(time_match.group(1))
                    unit = time_match.group(2)
                    
                    if "día" in unit:
                        start_date = now - timedelta(days=number)
                    elif "semana" in unit:
                        start_date = now - timedelta(weeks=number)
                    elif "mes" in unit:
                        start_date = now - timedelta(days=number * 30)  # Aproximación
                    else:
                        start_date = now - timedelta(weeks=1)  # Fallback
                    
                    filters["date_from"] = start_date.strftime("%Y-%m-%d")
                    filters["date_to"] = now.strftime("%Y-%m-%d")
                    filters["period"] = f"last_{number}_{unit}"
            
            elif "vigente" in expression_lower or "válido" in expression_lower:
                # Productos vigentes desde hoy hacia adelante
                filters["date_from"] = now.strftime("%Y-%m-%d")
                filters["period"] = "current_and_future"
            
            # Detectar años específicos
            year_match = re.search(r"(202[3-9])", expression_lower)
            if year_match:
                year = year_match.group(1)
                filters["date_from"] = f"{year}-01-01"
                filters["date_to"] = f"{year}-12-31"
                filters["period"] = f"year_{year}"
            
            # Detectar meses específicos
            months = {
                "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
                "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
                "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12"
            }
            
            for month_name, month_num in months.items():
                if month_name in expression_lower:
                    year = now.year  # Asumir año actual
                    filters["date_from"] = f"{year}-{month_num}-01"
                    # Calcular último día del mes
                    if month_num == "02":
                        last_day = "29" if year % 4 == 0 else "28"
                    elif month_num in ["04", "06", "09", "11"]:
                        last_day = "30"
                    else:
                        last_day = "31"
                    filters["date_to"] = f"{year}-{month_num}-{last_day}"
                    filters["period"] = f"month_{month_name}_{year}"
                    break
            
            logger.debug(f"[ComparisonDetector] Filtros temporales generados: {filters}")
            return filters
            
        except Exception as e:
            logger.error(f"[ComparisonDetector] Error generando filtros temporales: {e}")
            return {}
    
    def _normalize_temporal_expression(self, expression: str) -> Dict[str, str]:
        """
        NUEVA FUNCIÓN: Normaliza expresiones temporales a fechas ISO
        """
        try:
            normalized = {}
            
            # Buscar fechas explícitas y normalizarlas
            for pattern, formatter in self.date_patterns.items():
                matches = re.finditer(pattern, expression)
                for match in matches:
                    normalized_date = formatter(match)
                    normalized[match.group(0)] = normalized_date
            
            logger.debug(f"[ComparisonDetector] Fechas normalizadas: {normalized}")
            return normalized
            
        except Exception as e:
            logger.error(f"[ComparisonDetector] Error normalizando fechas: {e}")
            return {}
    
    def _process_entities_with_roles(self, entities: List[Dict[str, Any]], text: str) -> List[ComparisonEntity]:
        """Procesa entidades y asigna roles basados en el contexto mejorado"""
        try:
            comparison_entities = []
            
            for entity in entities:
                entity_type = entity.get("entity", "")
                entity_value = entity.get("value", "")
                
                if not entity_value:
                    continue
                
                # Determinar rol basado en el contexto mejorado
                role = self._determine_entity_role(entity_value, text)
                
                comparison_entities.append(ComparisonEntity(
                    entity_type=entity_type,
                    entity_value=entity_value,
                    role=role
                ))
                
                logger.debug(f"[ComparisonDetector] Entidad procesada: {entity_value} [{entity_type}] -> rol: {role}")
            
            return comparison_entities
            
        except Exception as e:
            logger.error(f"[ComparisonDetector] Error procesando entidades: {e}")
            return []
    
    def _determine_entity_role(self, entity_value: str, text: str) -> str:
        """Determina el rol de una entidad en la comparación con contexto mejorado"""
        try:
            entity_lower = entity_value.lower()
            
            # Buscar indicadores de rol cerca de la entidad
            entity_pos = text.find(entity_lower)
            if entity_pos == -1:
                return "target"  # rol por defecto
            
            # Analizar contexto alrededor de la entidad (50 caracteres antes y después)
            start = max(0, entity_pos - 50)
            end = min(len(text), entity_pos + len(entity_lower) + 50)
            context = text[start:end]
            
            # Buscar indicadores de rol con mayor precisión
            for role, indicators in self.role_indicators.items():
                for indicator in indicators:
                    # Verificar si el indicador está cerca de la entidad
                    indicator_pos = context.find(indicator)
                    if indicator_pos != -1:
                        # Verificar proximidad (debe estar dentro de 20 caracteres)
                        entity_in_context = context.find(entity_lower)
                        if entity_in_context != -1 and abs(indicator_pos - entity_in_context) <= 20:
                            logger.debug(f"[ComparisonDetector] Rol determinado para '{entity_value}': {role} (indicador: '{indicator}')")
                            return role
            
            # Si no se encuentra un indicador específico, inferir por patrones
            if any(word in context for word in ["comparado", "versus", "vs", "frente"]):
                return "reference"
            elif any(word in context for word in ["tipo", "como", "similar"]):
                return "target"
            elif any(word in context for word in ["entre", "grupo", "familia"]):
                return "group"
            
            return "target"
            
        except Exception as e:
            logger.error(f"[ComparisonDetector] Error determinando rol de entidad: {e}")
            return "target"
    
    def _detect_groups(self, text: str) -> List[str]:
        """Detecta grupos mencionados en el texto"""
        try:
            groups = []
            
            for pattern in self.group_patterns:
                matches = re.finditer(pattern, text)
                for match in matches:
                    group_name = match.group(1)
                    if group_name and group_name not in groups:
                        groups.append(group_name)
                        logger.debug(f"[ComparisonDetector] Grupo detectado: '{group_name}'")
            
            return groups
            
        except Exception as e:
            logger.error(f"[ComparisonDetector] Error detectando grupos: {e}")
            return []
    
    def _detect_roles(self, text: str) -> List[str]:
        """Detecta roles mencionados explícitamente"""
        try:
            detected_roles = []
            
            for role, indicators in self.role_indicators.items():
                for indicator in indicators:
                    if indicator in text and role not in detected_roles:
                        detected_roles.append(role)
                        logger.debug(f"[ComparisonDetector] Rol detectado: '{role}' (indicador: '{indicator}')")
            
            return detected_roles
            
        except Exception as e:
            logger.error(f"[ComparisonDetector] Error detectando roles: {e}")
            return []
    
    def format_comparison_message(self, result: ComparisonResult) -> str:
        """Formatea el mensaje de comparación detectada con información enriquecida"""
        try:
            if not result.detected:
                return ""
            
            lines = ["🔍 **Comparación detectada:**"]
            
            # Tipo de comparación
            type_names = {
                ComparisonType.NUMERIC: "Numérica",
                ComparisonType.PRICE: "Precio",
                ComparisonType.QUALITY: "Calidad",
                ComparisonType.QUANTITY: "Cantidad",
                ComparisonType.TEMPORAL: "Temporal",
                ComparisonType.SIZE: "Tamaño"
            }
            lines.append(f"• **Tipo:** {type_names.get(result.comparison_type, 'Desconocido')}")
            
            # Operador
            if result.operator:
                operator_names = {
                    ComparisonOperator.GREATER_THAN: "Mayor que",
                    ComparisonOperator.LESS_THAN: "Menor que",
                    ComparisonOperator.EQUAL_TO: "Igual a",
                    ComparisonOperator.DIFFERENT_FROM: "Diferente de"
                }
                lines.append(f"• **Operador:** {operator_names.get(result.operator, 'Desconocido')}")
            
            # Cantidad
            if result.quantity:
                lines.append(f"• **Cantidad/Valor:** {result.quantity}")
            
            # Filtros temporales (NUEVA FUNCIONALIDAD)
            if result.temporal_filters:
                filters_text = []
                if "date_from" in result.temporal_filters:
                    filters_text.append(f"desde {result.temporal_filters['date_from']}")
                if "date_to" in result.temporal_filters:
                    filters_text.append(f"hasta {result.temporal_filters['date_to']}")
                if "period" in result.temporal_filters:
                    filters_text.append(f"periodo: {result.temporal_filters['period']}")
                
                if filters_text:
                    lines.append(f"• **Filtros temporales:** {', '.join(filters_text)}")
            
            # Fechas normalizadas
            if result.normalized_dates:
                dates_text = [f"{orig} → {norm}" for orig, norm in result.normalized_dates.items()]
                lines.append(f"• **Fechas normalizadas:** {', '.join(dates_text)}")
            
            # Entidades
            if result.entities:
                entity_info = []
                for entity in result.entities:
                    role_text = f" ({entity.role})" if entity.role != "target" else ""
                    entity_info.append(f"{entity.entity_value} [{entity.entity_type}]{role_text}")
                lines.append(f"• **Entidades:** {', '.join(entity_info)}")
            
            # Grupos
            if result.groups_detected:
                lines.append(f"• **Grupos detectados:** {', '.join(result.groups_detected)}")
            
            # Roles
            if result.roles_detected:
                lines.append(f"• **Roles detectados:** {', '.join(result.roles_detected)}")
            
            # Confianza
            confidence_percent = int(result.confidence * 100)
            lines.append(f"• **Confianza:** {confidence_percent}%")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"[ComparisonDetector] Error formateando mensaje: {e}")
            return "Error formateando información de comparación"