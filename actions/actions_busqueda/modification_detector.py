# actions/actions_busqueda/modification_detector.py
import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class ModificationType(Enum):
    REPLACE = "replace"
    ADD_FILTER = "add_filter"
    REMOVE_FILTER = "remove_filter"
    MIXED = "mixed"

@dataclass
class ModificationAction:
    action_type: ModificationType
    entity_type: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    confidence: float = 0.0

# actions/actions_busqueda/modification_detector.py

@dataclass
class ModificationResult:
    detected: bool
    modification_type: Optional[ModificationType] = None
    actions: List[ModificationAction] = None
    rebuilt_params: Dict[str, Any] = None
    confidence: float = 0.0
    raw_text: str = ""
    
    # ✅ Validación de entidades
    validation_errors: List[Dict[str, Any]] = None
    valid_actions: List[ModificationAction] = None
    invalid_actions: List[ModificationAction] = None
    
    # ✅ NUEVO: Información de confirmación
    needs_confirmation: bool = False
    confirmation_reason: Optional[str] = None
    confirmation_message: Optional[str] = None
    ambiguity_details: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.actions is None:
            self.actions = []
        if self.rebuilt_params is None:
            self.rebuilt_params = {}
        if self.validation_errors is None:
            self.validation_errors = []
        if self.valid_actions is None:
            self.valid_actions = []
        if self.invalid_actions is None:
            self.invalid_actions = []
        if self.ambiguity_details is None:
            self.ambiguity_details = {}
    
    @property
    def has_invalid_entities(self) -> bool:
        """Verifica si hay entidades inválidas"""
        return len(self.invalid_actions) > 0
    
    @property
    def can_proceed_directly(self) -> bool:
        """Verifica si puede proceder sin confirmación"""
        return (
            self.detected and 
            not self.needs_confirmation and 
            not self.has_invalid_entities and
            self.confidence >= 0.75
        )

class ModificationDetector:
    
    def __init__(self):
        self.replacement_patterns = [
            r'(?:modifica|cambia|reemplaza)\s+(?P<old>[\w\s]+?)\s+por\s+(?P<new>[\w\s]+?)(?:\s+y|\s*$|,)',
            r'en\s+(?:lugar|vez)\s+de\s+(?P<old>[\w\s]+?)\s+(?:usa|busca|pon)\s+(?P<new>[\w\s]+?)(?:\s+y|\s*$|,)',
            r'(?P<old>[\w\s]+?)\s+por\s+(?P<new>[\w\s]+?)(?:\s+y|\s*$|,)',
        ]
        
        self.addition_patterns = [
            r'(?:agrega|añade|incluye)\s+(?:filtro\s+(?:de|por)\s+)?(?P<entity>[\w]+)\s+(?P<value>[\w]+)',
            r'filtra\s+por\s+(?P<entity>[\w]+)\s+(?P<value>[\w]+)',
            r'con\s+(?P<entity>[\w]+)\s+(?P<value>[\w]+)',
        ]
        
        self.entity_keywords = {
            'producto': ['producto', 'medicamento', 'artículo'],
            'empresa': ['proveedor', 'empresa', 'laboratorio', 'marca'],
            'categoria': ['categoría', 'tipo', 'clase'],
            'animal': ['animal', 'especie', 'mascota'],
            'dosis': ['dosis', 'presentación', 'formato'],
        }
        self.valid_entities_by_search_type = {
            'producto': [
                'producto', 'empresa', 'categoria', 'animal', 
                'sintoma', 'dosis', 'cantidad', 'ingrediente_activo'
            ],
            'oferta': [
                'producto', 'empresa', 'categoria', 'animal',
                'estado', 'descuento', 'bonificacion', 'stock',
                'precio', 'fecha', 'tiempo'
            ]
        }
        # ✅ NUEVO: Thresholds configurables
        self.confidence_threshold_high = 0.85  # No confirmar
        self.confidence_threshold_low = 0.65   # Siempre confirmar
        self.max_entities_without_confirmation = 3
        
        # ✅ NUEVO: Patrones de conjunciones
        self.conjunction_patterns = [
            r'\s+y\s+',
            r'\s+e\s+',
            r',\s*y\s+',
            r'\s+pero\s+',
            r'\s+además\s+',
            r',\s+(?:saca|quita|elimina|agrega|añade)',
        ]
        
        # Entidades comunes a ambos
        self.common_entities = ['producto', 'empresa', 'categoria', 'animal']
    def _is_valid_entity_for_search_type(self, entity_type: str, search_type: str) -> bool:
        """Verifica si una entidad es válida para el tipo de búsqueda"""
        valid_entities = self.valid_entities_by_search_type.get(search_type, [])
        is_valid = entity_type in valid_entities
        
        logger.debug(f"[ModificationDetector] Validando {entity_type} para {search_type}: {'✅' if is_valid else '❌'}")
        
        return is_valid
    
    def _get_valid_search_types(self, entity_type: str) -> List[str]:
        """Retorna los tipos de búsqueda donde la entidad es válida"""
        valid_types = []
        
        for search_type, entities in self.valid_entities_by_search_type.items():
            if entity_type in entities:
                valid_types.append(search_type)
        
        return valid_types
    
        
    def detect_and_rebuild(self, text: str, entities: List[Dict[str, Any]], 
                          current_params: Dict[str, Any],
                          search_type: str = 'producto',
                          user_experience_level: str = 'beginner') -> ModificationResult:
        """
        Detecta modificaciones, valida y determina si necesita confirmación
        """
        try:
            text_lower = text.lower()
            
            logger.info(f"[ModificationDetector] === INICIANDO ANÁLISIS ===")
            logger.info(f"[ModificationDetector] Texto: '{text}'")
            logger.info(f"[ModificationDetector] Parámetros actuales: {list(current_params.keys())}")
            logger.info(f"[ModificationDetector] Entidades detectadas: {len(entities)}")
            
            # Verificar palabras clave
            has_modification = any(kw in text_lower for kw in ['modifica', 'cambia', 'reemplaza', 'por'])
            has_addition = any(kw in text_lower for kw in ['agrega', 'añade', 'filtra por', 'con'])
            
            if not has_modification and not has_addition:
                logger.debug("[ModificationDetector] No hay palabras clave, no es modificación")
                return ModificationResult(detected=False, raw_text=text)
            
            actions = []
            
            # Detectar reemplazos
            if has_modification:
                replacement_actions = self._detect_replacements(text_lower, entities, current_params)
                actions.extend(replacement_actions)
            
            # Detectar adiciones
            if has_addition:
                addition_actions = self._detect_additions(text_lower, entities, current_params)
                actions.extend(addition_actions)
            
            if not actions:
                logger.warning("[ModificationDetector] No se detectaron acciones válidas")
                return ModificationResult(detected=False, raw_text=text)
            
            # ✅ Validar entidades
            invalid_actions = []
            valid_actions = []
            for action in actions:
                if self._is_valid_entity_for_search_type(action.entity_type, search_type):
                    valid_actions.append(action)
                else:
                    invalid_actions.append(action)
                    logger.warning(
                        f"[ModificationDetector] ⚠️ Entidad '{action.entity_type}' NO válida para búsqueda de {search_type}"
                    )
            
            # Calcular confianza general
            if valid_actions:
                confidence = sum(action.confidence for action in valid_actions) / len(valid_actions)
            else:
                confidence = 0.0
            
            # ✅ NUEVO: Detectar ambigüedad y decidir si necesita confirmación
            ambiguity_check = self._check_ambiguity(
                text=text,
                actions=actions,
                valid_actions=valid_actions,
                invalid_actions=invalid_actions,
                confidence=confidence,
                search_type=search_type,
                user_experience_level=user_experience_level
            )
            
            # Si hay entidades inválidas O necesita confirmación por ambigüedad
            if invalid_actions or ambiguity_check['needs_confirmation']:
                logger.info(f"[ModificationDetector] ⚠️ Requiere confirmación")
                
                result = ModificationResult(
                    detected=True,
                    modification_type=self._determine_modification_type(actions),
                    actions=actions,
                    valid_actions=valid_actions,
                    invalid_actions=invalid_actions,
                    rebuilt_params={},  # No rearmar hasta confirmar
                    confidence=confidence,
                    raw_text=text,
                    # ✅ Información de confirmación
                    needs_confirmation=True,
                    confirmation_reason=ambiguity_check['reason'],
                    confirmation_message=ambiguity_check['message'],
                    ambiguity_details=ambiguity_check['details']
                )
                
                # Agregar errores de validación si hay
                if invalid_actions:
                    result.validation_errors = [
                        {
                            'entity_type': action.entity_type,
                            'value': action.new_value or action.old_value,
                            'reason': f'not_valid_for_{search_type}',
                            'valid_for': self._get_valid_search_types(action.entity_type)
                        }
                        for action in invalid_actions
                    ]
                
                return result
            
            # ✅ Si pasa todas las validaciones, rearmar parámetros
            rebuilt_params = self._rebuild_parameters(current_params, valid_actions)
            
            result = ModificationResult(
                detected=True,
                modification_type=self._determine_modification_type(valid_actions),
                actions=valid_actions,
                valid_actions=valid_actions,
                rebuilt_params=rebuilt_params,
                confidence=confidence,
                raw_text=text,
                needs_confirmation=False
            )
            
            logger.info(f"[ModificationDetector] ✅ Modificación validada y lista")
            logger.info(f"[ModificationDetector] ✅ Confianza: {confidence:.2f}")
            
            return result
            
        except Exception as e:
            logger.error(f"[ModificationDetector] Error: {e}", exc_info=True)
            return ModificationResult(detected=False, raw_text=text)
    
    def _check_ambiguity(
        self,
        text: str,
        actions: List[ModificationAction],
        valid_actions: List[ModificationAction],
        invalid_actions: List[ModificationAction],
        confidence: float,
        search_type: str,
        user_experience_level: str
    ) -> Dict[str, Any]:
        """
        Verifica si hay ambigüedad y decide si necesita confirmación
        
        Returns:
            {
                'needs_confirmation': bool,
                'reason': str,
                'message': str,
                'details': dict
            }
        """
        
        # ✅ 1. Confianza muy baja -> SIEMPRE confirmar
        if confidence < self.confidence_threshold_low:
            return {
                'needs_confirmation': True,
                'reason': 'low_confidence',
                'message': self._build_confirmation_message(actions, 'low_confidence'),
                'details': {'confidence': confidence}
            }
        
        # ✅ 2. Usuario experto + confianza alta -> NO confirmar
        if user_experience_level == 'expert' and confidence >= self.confidence_threshold_high:
            return {
                'needs_confirmation': False,
                'reason': None,
                'message': None,
                'details': {}
            }
        
        # ✅ 3. Entidades inválidas -> CONFIRMAR (para informar)
        if invalid_actions:
            return {
                'needs_confirmation': True,
                'reason': 'invalid_entities',
                'message': self._build_confirmation_message(actions, 'invalid_entities', invalid_actions),
                'details': {
                    'invalid_count': len(invalid_actions),
                    'invalid_entities': [a.entity_type for a in invalid_actions]
                }
            }
        
        # ✅ 4. Detectar ambigüedad intent: tiene conjunción pero solo 1 acción
        has_conjunction = self._has_conjunction(text)
        if has_conjunction and len(actions) == 1:
            return {
                'needs_confirmation': True,
                'reason': 'conjunction_mismatch',
                'message': (
                    f"Veo que usaste 'y' en tu frase, pero solo detecté UNA operación. "
                    f"¿Querés solo **{self._action_to_text(actions[0])}**?"
                ),
                'details': {'has_conjunction': True, 'action_count': 1}
            }
        
        # ✅ 5. No tiene conjunción pero detectó múltiples acciones
        if not has_conjunction and len(actions) > 1:
            return {
                'needs_confirmation': True,
                'reason': 'multiple_without_conjunction',
                'message': (
                    f"Detecté {len(actions)} operaciones, ¿es correcto?\n" +
                    "\n".join([f"{i+1}. {self._action_to_text(a)}" for i, a in enumerate(actions)])
                ),
                'details': {'has_conjunction': False, 'action_count': len(actions)}
            }
        
        # ✅ 6. Demasiadas entidades -> confirmar
        if len(actions) > self.max_entities_without_confirmation:
            return {
                'needs_confirmation': True,
                'reason': 'too_many_entities',
                'message': self._build_confirmation_message(actions, 'too_many_entities'),
                'details': {'action_count': len(actions)}
            }
        
        # ✅ 7. Confianza media -> confirmar (solo para beginners)
        if user_experience_level == 'beginner' and confidence < self.confidence_threshold_high:
            return {
                'needs_confirmation': True,
                'reason': 'medium_confidence',
                'message': self._build_confirmation_message(actions, 'medium_confidence'),
                'details': {'confidence': confidence}
            }
        
        # ✅ Todo OK, no necesita confirmación
        return {
            'needs_confirmation': False,
            'reason': None,
            'message': None,
            'details': {}
        }
    
    def _has_conjunction(self, text: str) -> bool:
        """Detecta si hay conjunciones en el texto"""
        return any(
            re.search(pattern, text, re.IGNORECASE) 
            for pattern in self.conjunction_patterns
        )
    
    def _action_to_text(self, action: ModificationAction) -> str:
        """Convierte una acción a texto legible"""
        if action.action_type == ModificationType.REPLACE:
            return f"Cambiar {action.entity_type} de '{action.old_value}' a '{action.new_value}'"
        elif action.action_type == ModificationType.ADD_FILTER:
            return f"Agregar filtro {action.entity_type} = '{action.new_value}'"
        elif action.action_type == ModificationType.REMOVE_FILTER:
            return f"Quitar filtro {action.entity_type}"
        else:
            return f"Modificar {action.entity_type}"
    
    def _build_confirmation_message(
        self,
        actions: List[ModificationAction],
        reason: str,
        invalid_actions: List[ModificationAction] = None
    ) -> str:
        """Construye mensaje de confirmación según el motivo"""
        
        if reason == 'invalid_entities':
            invalid_list = "\n".join([
                f"  • {a.entity_type}: '{a.new_value or a.old_value}'"
                for a in invalid_actions
            ])
            return (
                f"⚠️ Detecté entidades que no son válidas para este tipo de búsqueda:\n"
                f"{invalid_list}\n\n"
                f"¿Querés continuar solo con los filtros válidos?"
            )
        
        elif reason == 'too_many_entities':
            action_list = "\n".join([
                f"  {i+1}. {self._action_to_text(a)}"
                for i, a in enumerate(actions)
            ])
            return (
                f"Detecté {len(actions)} operaciones:\n"
                f"{action_list}\n\n"
                f"¿Es correcto?"
            )
        
        elif reason == 'low_confidence':
            return (
                f"No estoy 100% seguro de lo que querés hacer. "
                f"¿Podrías confirmarlo?"
            )
        
        elif reason == 'medium_confidence':
            if len(actions) == 1:
                return f"¿Querés **{self._action_to_text(actions[0])}**?"
            else:
                action_list = "\n".join([
                    f"  {i+1}. {self._action_to_text(a)}"
                    for i, a in enumerate(actions)
                ])
                return f"¿Querés hacer esto?\n{action_list}"
        
        # Fallback genérico
        return "¿Es esto lo que querés hacer?"
    
    def _determine_modification_type(self, actions: List[ModificationAction]) -> ModificationType:
        """Determina el tipo de modificación general"""
        if not actions:
            return None
        
        action_types = [action.action_type for action in actions]
        
        if len(set(action_types)) > 1:
            return ModificationType.MIXED
        else:
            return action_types[0]
    
    def _detect_replacements(self, text: str, entities: List[Dict[str, Any]], 
                            current_params: Dict[str, Any]) -> List[ModificationAction]:
        """Detecta acciones de reemplazo"""
        actions = []
        
        for pattern in self.replacement_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            
            for match in matches:
                old_value = match.group('old').strip()
                new_value = match.group('new').strip()
                
                logger.debug(f"[ModificationDetector] Match encontrado: '{old_value}' → '{new_value}'")
                
                # Inferir tipo de entidad
                entity_type = self._infer_entity_type(old_value, new_value, entities, current_params)
                
                if entity_type:
                    confidence = 0.9 if 'modifica|cambia' in pattern else 0.7
                    
                    action = ModificationAction(
                        action_type=ModificationType.REPLACE,
                        entity_type=entity_type,
                        old_value=old_value,
                        new_value=new_value,
                        confidence=confidence
                    )
                    actions.append(action)
                    
                    logger.info(f"[ModificationDetector] ✏️ Reemplazo: {entity_type} '{old_value}' → '{new_value}' (conf: {confidence:.2f})")
                else:
                    logger.warning(f"[ModificationDetector] No se pudo inferir tipo para '{old_value}' → '{new_value}'")
        
        return actions
    
    def _detect_additions(self, text: str, entities: List[Dict[str, Any]], 
                         current_params: Dict[str, Any]) -> List[ModificationAction]:
        """Detecta acciones de adición"""
        actions = []
        
        # Buscar patrones explícitos primero
        for pattern in self.addition_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            
            for match in matches:
                if 'entity' in match.groupdict():
                    entity_type_keyword = match.group('entity').strip()
                    entity_value = match.group('value').strip()
                    
                    # Mapear keyword a tipo de entidad
                    entity_type = self._map_keyword_to_entity_type(entity_type_keyword)
                    
                    if entity_type:
                        action = ModificationAction(
                            action_type=ModificationType.ADD_FILTER,
                            entity_type=entity_type,
                            old_value=None,
                            new_value=entity_value,
                            confidence=0.85
                        )
                        actions.append(action)
                        
                        logger.info(f"[ModificationDetector] ➕ Adición: {entity_type} = '{entity_value}'")
        
        # Detectar entidades nuevas que no están en current_params
        if not actions:
            current_values = self._extract_current_values(current_params)
            
            for entity in entities:
                entity_type = entity.get('entity')
                entity_value = entity.get('value', '').lower()
                
                if entity_value and entity_value not in current_values:
                    # Esta es una entidad nueva, probablemente una adición
                    if self._is_in_addition_context(entity_value, text):
                        action = ModificationAction(
                            action_type=ModificationType.ADD_FILTER,
                            entity_type=entity_type,
                            old_value=None,
                            new_value=entity.get('value'),
                            confidence=0.75
                        )
                        actions.append(action)
                        
                        logger.info(f"[ModificationDetector] ➕ Adición inferida: {entity_type} = '{entity.get('value')}'")
        
        return actions
    
    def _infer_entity_type(self, old_value: str, new_value: str, 
                          entities: List[Dict[str, Any]], 
                          current_params: Dict[str, Any]) -> Optional[str]:
        """Infiere el tipo de entidad"""
        
        # 1. Buscar en entidades detectadas (prioridad)
        for entity in entities:
            entity_value = entity.get('value', '').lower()
            if entity_value == old_value.lower() or entity_value == new_value.lower():
                logger.debug(f"[ModificationDetector] Tipo inferido de entidades: {entity.get('entity')}")
                return entity.get('entity')
        
        # 2. Buscar en parámetros actuales
        for param_key, param_value in current_params.items():
            if param_key.startswith('_'):
                continue
                
            if isinstance(param_value, dict) and 'value' in param_value:
                if param_value['value'].lower() == old_value.lower():
                    logger.debug(f"[ModificationDetector] Tipo inferido de params: {param_key}")
                    return param_key
            elif isinstance(param_value, str):
                if param_value.lower() == old_value.lower():
                    logger.debug(f"[ModificationDetector] Tipo inferido de params: {param_key}")
                    return param_key
        
        # 3. Buscar por keywords en el texto
        for entity_type, keywords in self.entity_keywords.items():
            if any(kw in old_value.lower() or kw in new_value.lower() for kw in keywords):
                logger.debug(f"[ModificationDetector] Tipo inferido por keyword: {entity_type}")
                return entity_type
        
        logger.warning(f"[ModificationDetector] No se pudo inferir tipo para '{old_value}' / '{new_value}'")
        return None
    
    def _map_keyword_to_entity_type(self, keyword: str) -> Optional[str]:
        """Mapea keyword a tipo de entidad"""
        keyword_lower = keyword.lower()
        
        for entity_type, keywords in self.entity_keywords.items():
            if keyword_lower in keywords or keyword_lower == entity_type:
                return entity_type
        
        return keyword_lower  # Fallback: usar el keyword como tipo
    
    def _extract_current_values(self, current_params: Dict[str, Any]) -> set:
        """Extrae todos los valores actuales"""
        values = set()
        
        for param_value in current_params.values():
            if isinstance(param_value, dict) and 'value' in param_value:
                values.add(param_value['value'].lower())
            elif isinstance(param_value, str):
                values.add(param_value.lower())
        
        return values
    
    def _is_in_addition_context(self, value: str, text: str) -> bool:
        """Verifica si el valor está en contexto de adición"""
        addition_words = ['agrega', 'añade', 'incluye', 'filtra por', 'con', 'y']
        
        # Buscar el valor en el texto y verificar palabras cercanas
        value_pos = text.lower().find(value.lower())
        if value_pos == -1:
            return False
        
        # Verificar 30 caracteres antes del valor
        context_before = text[max(0, value_pos - 30):value_pos].lower()
        
        return any(word in context_before for word in addition_words)
    
    def _rebuild_parameters(self, current_params: Dict[str, Any], 
                           actions: List[ModificationAction]) -> Dict[str, Any]:
        """
        Rearma los parámetros aplicando todas las modificaciones
        """
        rebuilt = {}
        
        # Copiar parámetros actuales (sin metadata)
        for key, value in current_params.items():
            if not key.startswith('_'):
                rebuilt[key] = value
        
        logger.info(f"[ModificationDetector] Rearmando desde {len(rebuilt)} parámetros base")
        
        # Aplicar cada acción
        for i, action in enumerate(actions, 1):
            logger.debug(f"[ModificationDetector] Aplicando acción {i}/{len(actions)}: {action.action_type.value}")
            
            if action.action_type == ModificationType.REPLACE:
                # Reemplazar valor existente
                if action.entity_type in rebuilt:
                    old_val = rebuilt[action.entity_type]
                    
                    if isinstance(old_val, dict) and 'value' in old_val:
                        rebuilt[action.entity_type] = {
                            'value': action.new_value,
                            'role': old_val.get('role', 'unspecified')
                        }
                    else:
                        rebuilt[action.entity_type] = action.new_value
                    
                    logger.info(f"[ModificationDetector]   ✏️ {action.entity_type}: '{action.old_value}' → '{action.new_value}'")
                else:
                    logger.warning(f"[ModificationDetector]   ⚠️ {action.entity_type} no existe en params, agregando como nuevo")
                    rebuilt[action.entity_type] = action.new_value
            
            elif action.action_type == ModificationType.ADD_FILTER:
                # Agregar nuevo filtro
                rebuilt[action.entity_type] = action.new_value
                logger.info(f"[ModificationDetector]   ➕ {action.entity_type} = '{action.new_value}'")
        
        logger.info(f"[ModificationDetector] ✅ Parámetros rearmados: {len(rebuilt)} total")
        for key, value in rebuilt.items():
            if isinstance(value, dict):
                logger.info(f"[ModificationDetector]   • {key}: {value['value']} (role: {value.get('role')})")
            else:
                logger.info(f"[ModificationDetector]   • {key}: {value}")
        
        return rebuilt