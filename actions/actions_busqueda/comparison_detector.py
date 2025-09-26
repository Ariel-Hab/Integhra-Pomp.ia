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

class ComparisonDetector:
    """Detector de comparaciones en búsquedas"""
    
    def __init__(self):
        # Patrones para detectar comparaciones numéricas
        self.numeric_patterns = {
            ComparisonOperator.GREATER_THAN: [
                r"(?:más|mayor|superior|arriba|encima)\s+(?:de|que|a)\s+(\d+(?:\.\d+)?)\s*(%|pesos?|usd?|dólares?|unidades?)?",
                r"(?:con|que\s+tenga|que\s+sea)\s+(?:más|mayor)\s+(?:de|que|a)\s+(\d+(?:\.\d+)?)\s*(%|pesos?|usd?|dólares?|unidades?)?",
                r"(?:superar|exceder|por\s+encima\s+de)\s+(\d+(?:\.\d+)?)\s*(%|pesos?|usd?|dólares?|unidades?)?",
                r"(?:mínimo|como\s+mínimo|al\s+menos)\s+(\d+(?:\.\d+)?)\s*(%|pesos?|usd?|dólares?|unidades?)?"
            ],
            ComparisonOperator.LESS_THAN: [
                r"(?:menos|menor|inferior|abajo|debajo)\s+(?:de|que|a)\s+(\d+(?:\.\d+)?)\s*(%|pesos?|usd?|dólares?|unidades?)?",
                r"(?:con|que\s+tenga|que\s+sea)\s+(?:menos|menor)\s+(?:de|que|a)\s+(\d+(?:\.\d+)?)\s*(%|pesos?|usd?|dólares?|unidades?)?",
                r"(?:por\s+debajo\s+de|no\s+superar|máximo)\s+(\d+(?:\.\d+)?)\s*(%|pesos?|usd?|dólares?|unidades?)?",
                r"(?:como\s+máximo|hasta)\s+(\d+(?:\.\d+)?)\s*(%|pesos?|usd?|dólares?|unidades?)?"
            ],
            ComparisonOperator.EQUAL_TO: [
                r"(?:igual\s+a|exactamente|justo)\s+(\d+(?:\.\d+)?)\s*(%|pesos?|usd?|dólares?|unidades?)?",
                r"(\d+(?:\.\d+)?)\s*(%|pesos?|usd?|dólares?|unidades?)?\s+(?:exactos?|justos?)"
            ]
        }
        
        # Patrones para detectar comparaciones de precio
        self.price_patterns = {
            ComparisonOperator.LESS_THAN: [
                r"(?:más\s+)?(?:barato|económico|accesible)\s+que",
                r"(?:menor|más\s+bajo)\s+precio\s+que",
                r"(?:cuesta|vale)\s+menos\s+que",
                r"(?:ofertas?|promociones?|descuentos?)\s+(?:más\s+)?(?:grandes?|importantes?)",
                r"(?:mejor\s+)?(?:precio|oferta)"
            ],
            ComparisonOperator.GREATER_THAN: [
                r"(?:más\s+)?(?:caro|costoso|premium)\s+que",
                r"(?:mayor|más\s+alto)\s+precio\s+que",
                r"(?:cuesta|vale)\s+más\s+que",
                r"(?:calidad\s+)?premium",
                r"(?:gama\s+)?alta"
            ]
        }
        
        # Patrones para detectar comparaciones de calidad
        self.quality_patterns = {
            ComparisonOperator.GREATER_THAN: [
                r"mejor\s+que",
                r"superior\s+(?:en\s+calidad\s+)?a",
                r"de\s+(?:mayor|mejor)\s+calidad\s+que",
                r"más\s+(?:efectivo|eficaz|potente|confiable)\s+que",
                r"(?:mayor|mejor)\s+(?:rendimiento|efectividad|potencia)",
                r"(?:alta|superior)\s+calidad"
            ],
            ComparisonOperator.LESS_THAN: [
                r"peor\s+que",
                r"inferior\s+(?:en\s+calidad\s+)?a",
                r"de\s+(?:menor|peor)\s+calidad\s+que",
                r"menos\s+(?:efectivo|eficaz|potente|confiable)\s+que",
                r"(?:menor|peor)\s+(?:rendimiento|efectividad|potencia)"
            ]
        }
        
        # Nuevos patrones para detectar comparaciones temporales
        self.temporal_patterns = {
            ComparisonOperator.LESS_THAN: [  # Más reciente
                r"(?:más\s+)?(?:recientes?|nuevos?|actuales?)",
                r"(?:de\s+)?(?:esta\s+semana|esta\s+quincena|este\s+mes)",
                r"(?:últimos?|pasados?)\s+(?:\d+\s+)?(?:días?|semanas?|meses?)",
                r"(?:desde\s+)?(?:hace\s+poco|recientemente)",
                r"(?:productos?\s+)?(?:del\s+)?(?:2024|2025)",
                r"(?:lanzamientos?\s+)?(?:recientes?|nuevos?)"
            ],
            ComparisonOperator.GREATER_THAN: [  # Más antiguo
                r"(?:más\s+)?(?:antiguos?|viejos?|anteriores?)",
                r"(?:de\s+)?(?:antes\s+de|anterior\s+a)",
                r"(?:hace\s+más\s+de)\s+(?:\d+\s+)?(?:días?|semanas?|meses?)",
                r"(?:productos?\s+)?(?:clásicos?|tradicionales?)"
            ],
            ComparisonOperator.EQUAL_TO: [  # Periodo específico
                r"(?:de\s+|del\s+|en\s+)?(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)",
                r"(?:del\s+año\s+)?(?:2023|2024|2025)",
                r"(?:de\s+)?(?:esta\s+temporada|este\s+trimestre)",
                r"(?:vigentes?|válidos?)\s+(?:hasta|por)"
            ]
        }
        
        # Patrones para detectar comparaciones de cantidad
        self.quantity_patterns = {
            ComparisonOperator.GREATER_THAN: [
                r"(?:más|mayor|superior)\s+(?:cantidad|stock|existencias?|unidades?)",
                r"(?:con\s+)?(?:más|mayor)\s+(?:disponibilidad|inventario)",
                r"(?:abundante|suficiente)\s+stock",
                r"(?:gran|alta)\s+disponibilidad"
            ],
            ComparisonOperator.LESS_THAN: [
                r"(?:menos|menor|poca?)\s+(?:cantidad|stock|existencias?|unidades?)",
                r"(?:con\s+)?(?:menor|poca?)\s+(?:disponibilidad|inventario)",
                r"(?:poco|limitado)\s+stock",
                r"(?:últimas?\s+)?unidades?"
            ]
        }
        
        # Patrones para detectar comparaciones de tamaño
        self.size_patterns = {
            ComparisonOperator.GREATER_THAN: [
                r"(?:más\s+)?(?:grandes?|amplios?|extensos?)",
                r"(?:mayor|superior)\s+(?:tamaño|dimensión|capacidad)",
                r"(?:de\s+)?(?:gran|mayor)\s+(?:tamaño|capacidad)"
            ],
            ComparisonOperator.LESS_THAN: [
                r"(?:más\s+)?(?:pequeños?|compactos?|reducidos?)",
                r"(?:menor|inferior)\s+(?:tamaño|dimensión|capacidad)",
                r"(?:de\s+)?(?:pequeño|menor)\s+(?:tamaño|capacidad)"
            ]
        }
        
        # Patrones para detectar grupos y roles
        self.group_patterns = [
            r"(?:entre|de)\s+(?:los|las)\s+(\w+)s?",
            r"dentro\s+(?:del|de\s+la)\s+(?:grupo|categoría|familia)\s+(?:de\s+)?(\w+)",
            r"comparado\s+con\s+(?:otros|otras)\s+(\w+)s?",
            r"(?:del\s+grupo|de\s+la\s+línea)\s+(?:de\s+)?(\w+)"
        ]
        
        # Palabras que indican roles específicos
        self.role_indicators = {
            "reference": ["comparado con", "versus", "vs", "frente a", "respecto a", "en relación a"],
            "target": ["que sea", "que tenga", "del tipo", "como", "similar a", "parecido a"],
            "group": ["entre", "dentro de", "del grupo", "de la familia", "de la línea", "de la marca"]
        }
        
        # Patrones para normalizar fechas
        self.date_patterns = {
            r"(\d{1,2})/(\d{1,2})/(\d{4})": lambda m: f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}",
            r"(\d{4})-(\d{1,2})-(\d{1,2})": lambda m: f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}",
        }
    
    def detect_comparison(self, text: str, entities: List[Dict[str, Any]]) -> ComparisonResult:
        """
        Detecta comparaciones en el texto y entidades
        
        Args:
            text: Texto del mensaje del usuario
            entities: Lista de entidades detectadas por Rasa
            
        Returns:
            ComparisonResult con toda la información detectada
        """
        try:
            text_lower = text.lower()
            
            logger.info(f"[ComparisonDetector] Analizando texto: '{text[:100]}...'")
            
            # Inicializar resultado
            result = ComparisonResult(
                detected=False,
                comparison_type=None,
                operator=None,
                entities=[],
                quantity=None,
                groups_detected=[],
                roles_detected=[],
                confidence=0.0,
                raw_expression=text,
                temporal_filters=None,
                normalized_dates=None
            )
            
            # 1. Detectar comparaciones numéricas
            numeric_result = self._detect_numeric_comparison(text_lower)
            if numeric_result["detected"]:
                result.detected = True
                result.comparison_type = ComparisonType.NUMERIC
                result.operator = numeric_result["operator"]
                result.quantity = numeric_result["quantity"]
                result.confidence += 0.4
                logger.info(f"[ComparisonDetector] Comparación numérica detectada: {result.operator.value} {result.quantity}")
            
            # 2. Detectar comparaciones de precio
            price_result = self._detect_price_comparison(text_lower)
            if price_result["detected"]:
                result.detected = True
                if result.comparison_type is None:
                    result.comparison_type = ComparisonType.PRICE
                result.operator = price_result["operator"]
                result.confidence += 0.3
                logger.info(f"[ComparisonDetector] Comparación de precio detectada: {result.operator.value}")
            
            # 3. Detectar comparaciones de calidad
            quality_result = self._detect_quality_comparison(text_lower)
            if quality_result["detected"]:
                result.detected = True
                if result.comparison_type is None:
                    result.comparison_type = ComparisonType.QUALITY
                result.operator = quality_result["operator"]
                result.confidence += 0.3
                logger.info(f"[ComparisonDetector] Comparación de calidad detectada: {result.operator.value}")
            
            # 4. Detectar comparaciones temporales (NUEVA FUNCIONALIDAD)
            temporal_result = self._detect_temporal_comparison(text_lower)
            if temporal_result["detected"]:
                result.detected = True
                if result.comparison_type is None:
                    result.comparison_type = ComparisonType.TEMPORAL
                result.operator = temporal_result["operator"]
                result.temporal_filters = temporal_result.get("filters")
                result.normalized_dates = temporal_result.get("normalized_dates")
                result.confidence += 0.35
                logger.info(f"[ComparisonDetector] Comparación temporal detectada: {result.operator.value}, filtros: {result.temporal_filters}")
            
            # 5. Detectar comparaciones de cantidad
            quantity_result = self._detect_quantity_comparison(text_lower)
            if quantity_result["detected"]:
                result.detected = True
                if result.comparison_type is None:
                    result.comparison_type = ComparisonType.QUANTITY
                result.operator = quantity_result["operator"]
                result.confidence += 0.3
                logger.info(f"[ComparisonDetector] Comparación de cantidad detectada: {result.operator.value}")
            
            # 6. Detectar comparaciones de tamaño
            size_result = self._detect_size_comparison(text_lower)
            if size_result["detected"]:
                result.detected = True
                if result.comparison_type is None:
                    result.comparison_type = ComparisonType.SIZE
                result.operator = size_result["operator"]
                result.confidence += 0.25
                logger.info(f"[ComparisonDetector] Comparación de tamaño detectada: {result.operator.value}")
            
            # 7. Procesar entidades y detectar roles
            if result.detected and entities:
                result.entities = self._process_entities_with_roles(entities, text_lower)
                result.confidence += 0.2 if result.entities else 0
                logger.debug(f"[ComparisonDetector] Entidades procesadas: {len(result.entities)}")
            
            # 8. Detectar grupos
            groups = self._detect_groups(text_lower)
            if groups:
                result.groups_detected = groups
                result.confidence += 0.1
                logger.debug(f"[ComparisonDetector] Grupos detectados: {groups}")
            
            # 9. Detectar roles
            roles = self._detect_roles(text_lower)
            if roles:
                result.roles_detected = roles
                result.confidence += 0.1
                logger.debug(f"[ComparisonDetector] Roles detectados: {roles}")
            
            # Ajustar confianza final
            result.confidence = min(result.confidence, 1.0)
            
            if result.detected:
                logger.info(f"[ComparisonDetector] Comparación detectada exitosamente - Tipo: {result.comparison_type.value if result.comparison_type else 'None'}, Confianza: {result.confidence:.2f}")
            else:
                logger.debug(f"[ComparisonDetector] No se detectaron comparaciones en: '{text[:50]}...'")
            
            return result
            
        except Exception as e:
            logger.error(f"[ComparisonDetector] Error durante detección: {e}", exc_info=True)
            # Retornar resultado vacío en caso de error
            return ComparisonResult(
                detected=False,
                comparison_type=None,
                operator=None,
                entities=[],
                quantity=None,
                groups_detected=[],
                roles_detected=[],
                confidence=0.0,
                raw_expression=text,
                temporal_filters=None,
                normalized_dates=None
            )
    
    def _detect_numeric_comparison(self, text: str) -> Dict[str, Any]:
        """Detecta comparaciones numéricas"""
        try:
            for operator, patterns in self.numeric_patterns.items():
                for pattern in patterns:
                    match = re.search(pattern, text)
                    if match:
                        quantity_value = match.group(1)
                        unit = match.group(2) if len(match.groups()) > 1 and match.group(2) else ""
                        quantity = f"{quantity_value}{unit}" if unit else quantity_value
                        
                        logger.debug(f"[ComparisonDetector] Patrón numérico encontrado: '{match.group(0)}' -> {quantity}")
                        
                        return {
                            "detected": True,
                            "operator": operator,
                            "quantity": quantity
                        }
            
            return {"detected": False}
            
        except Exception as e:
            logger.error(f"[ComparisonDetector] Error en detección numérica: {e}")
            return {"detected": False}
    
    def _detect_price_comparison(self, text: str) -> Dict[str, Any]:
        """Detecta comparaciones de precio"""
        try:
            for operator, patterns in self.price_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, text):
                        logger.debug(f"[ComparisonDetector] Patrón de precio encontrado: '{pattern}'")
                        return {
                            "detected": True,
                            "operator": operator
                        }
            
            return {"detected": False}
            
        except Exception as e:
            logger.error(f"[ComparisonDetector] Error en detección de precio: {e}")
            return {"detected": False}
    
    def _detect_quality_comparison(self, text: str) -> Dict[str, Any]:
        """Detecta comparaciones de calidad"""
        try:
            for operator, patterns in self.quality_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, text):
                        logger.debug(f"[ComparisonDetector] Patrón de calidad encontrado: '{pattern}'")
                        return {
                            "detected": True,
                            "operator": operator
                        }
            
            return {"detected": False}
            
        except Exception as e:
            logger.error(f"[ComparisonDetector] Error en detección de calidad: {e}")
            return {"detected": False}
    
    def _detect_temporal_comparison(self, text: str) -> Dict[str, Any]:
        """
        NUEVA FUNCIÓN: Detecta comparaciones temporales y genera filtros de fecha
        """
        try:
            for operator, patterns in self.temporal_patterns.items():
                for pattern in patterns:
                    match = re.search(pattern, text)
                    if match:
                        logger.debug(f"[ComparisonDetector] Patrón temporal encontrado: '{match.group(0)}'")
                        
                        # Generar filtros temporales basados en el patrón
                        filters = self._generate_temporal_filters(match.group(0), operator)
                        normalized_dates = self._normalize_temporal_expression(match.group(0))
                        
                        return {
                            "detected": True,
                            "operator": operator,
                            "filters": filters,
                            "normalized_dates": normalized_dates
                        }
            
            return {"detected": False}
            
        except Exception as e:
            logger.error(f"[ComparisonDetector] Error en detección temporal: {e}")
            return {"detected": False}
    
    def _detect_quantity_comparison(self, text: str) -> Dict[str, Any]:
        """Detecta comparaciones de cantidad"""
        try:
            for operator, patterns in self.quantity_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, text):
                        logger.debug(f"[ComparisonDetector] Patrón de cantidad encontrado: '{pattern}'")
                        return {
                            "detected": True,
                            "operator": operator
                        }
            
            return {"detected": False}
            
        except Exception as e:
            logger.error(f"[ComparisonDetector] Error en detección de cantidad: {e}")
            return {"detected": False}
    
    def _detect_size_comparison(self, text: str) -> Dict[str, Any]:
        """Detecta comparaciones de tamaño"""
        try:
            for operator, patterns in self.size_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, text):
                        logger.debug(f"[ComparisonDetector] Patrón de tamaño encontrado: '{pattern}'")
                        return {
                            "detected": True,
                            "operator": operator
                        }
            
            return {"detected": False}
            
        except Exception as e:
            logger.error(f"[ComparisonDetector] Error en detección de tamaño: {e}")
            return {"detected": False}
    
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