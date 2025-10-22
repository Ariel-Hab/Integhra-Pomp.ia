# actions/actions_busqueda/modification_detector.py
import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

class ModificationType(Enum):
    REPLACE = "replace"
    ADD_FILTER = "add_filter"
    REMOVE_FILTER = "remove_filter"

@dataclass
class ModificationAction:
    action_type: ModificationType
    entity_type: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    confidence: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'action_type': self.action_type.value if hasattr(self.action_type, 'value') else str(self.action_type),
            'entity_type': self.entity_type,
            'old_value': self.old_value,
            'new_value': self.new_value,
            'confidence': getattr(self, 'confidence', None)
        }

@dataclass
class ModificationResult:
    # ... (sin cambios)
    detected: bool
    actions: List[ModificationAction] = field(default_factory=list)
    rebuilt_params: Tuple[Dict[str, Any], List[str]] = field(default_factory=lambda: ({}, []))
    valid_actions: List[ModificationAction] = field(default_factory=list)
    invalid_actions: List[ModificationAction] = field(default_factory=list)
    # ...etc.

    @property
    def has_invalid_entities(self) -> bool: return len(self.invalid_actions) > 0
    
    @property
    def can_proceed_directly(self) -> bool:
        return self.detected and not self.has_invalid_entities

class ModificationDetector:

    def __init__(self):
        self.valid_entities_by_search_type = {
            'producto': ['producto', 'empresa', 'categoria', 'animal', 'sintoma', 'dosis', 'cantidad'],
            'oferta': ['producto', 'empresa', 'categoria', 'animal', 'estado', 'cantidad_descuento', 'cantidad_bonificacion', 'cantidad_stock', 'precio']
        }

    # ❗ MÉTODO PRINCIPAL REDISEÑADO
    def detect_and_rebuild(self, text: str, entities: List[Dict[str, Any]], 
                          intent_name: str, current_params: Dict[str, Any],
                          search_type: str) -> ModificationResult:
        try:
            # 1. ✅ Detectar acciones 100% desde el NLU
            actions = self._detect_from_nlu(intent_name, text, entities)

            if not actions:
                return ModificationResult(detected=False)

            # 2. Validar entidades
            valid_actions, invalid_actions, errors = self._validate_actions(actions, search_type)

            if invalid_actions:
                return ModificationResult(detected=True, actions=actions, valid_actions=valid_actions, invalid_actions=invalid_actions, validation_errors=errors)

            # 3. Reconstruir parámetros
            rebuilt_params, warnings = self._rebuild_parameters(current_params, valid_actions)
            
            # Adjuntar warnings al resultado (para ser mostrados al usuario)
            # (Se puede hacer aquí o en la action)
            
            return ModificationResult(
                detected=True,
                actions=valid_actions,
                valid_actions=valid_actions,
                rebuilt_params=(rebuilt_params, warnings)
            )
            
        except Exception as e:
            logger.error(f"[ModificationDetector] Error crítico: {e}", exc_info=True)
            return ModificationResult(detected=False)

    # ✅ 1. DETECTOR 100% NLU-FIRST (SIN FALLBACKS)
    def _detect_from_nlu(self, intent_name: str, text: str, entities: List[Dict[str, Any]]) -> List[ModificationAction]:
        """Crea una lista de ModificationAction basándose 100% en el intent y los roles/entidades del NLU."""
        actions = []
        sub_intent = intent_name.split(':')[-1]

        if sub_intent == 'agregar':
            for entity in entities:
                # La entidad 'comparador' se maneja por su grupo, no se agrega como filtro directo
                if entity.get('entity') != 'comparador':
                    actions.append(ModificationAction(ModificationType.ADD_FILTER, entity.get('entity'), new_value=entity.get('value')))
            logger.info(f"[NLU Detector] ➕ ADD: {len(actions)} acciones detectadas.")

        elif sub_intent == 'remover':
            for entity in entities:
                entity_type = entity.get('entity')
                if entity_type == 'filter_name':
                    # CASO 1: Remover filtro completo. El valor es el nombre del filtro.
                    filter_to_remove = entity.get('value')
                    actions.append(ModificationAction(ModificationType.REMOVE_FILTER, filter_to_remove))
                    logger.info(f"[NLU Detector] ➖ REMOVE (Full Filter): Se removerá el filtro '{filter_to_remove}'.")
                else:
                    # CASO 2: Remover valor específico (ej. "saca holliday").
                    actions.append(ModificationAction(ModificationType.REMOVE_FILTER, entity_type, old_value=entity.get('value')))
                    logger.info(f"[NLU Detector] ➖ REMOVE (Specific Value): Se removerá el valor '{entity.get('value')}' del filtro '{entity_type}'.")

        elif sub_intent in ['reemplazar', 'multiple']:
            # Esta lógica ya era NLU-First y funciona perfecto con los roles.
            replacements = {}
            for entity in entities:
                role = entity.get("role")
                entity_type = entity.get("entity")
                value = entity.get("value")

                if role == 'add':
                    actions.append(ModificationAction(ModificationType.ADD_FILTER, entity_type, new_value=value))
                elif role == 'remove':
                    actions.append(ModificationAction(ModificationType.REMOVE_FILTER, entity_type, old_value=value))
                elif role == 'old':
                    replacements.setdefault(entity_type, {})["old"] = value
                elif role == 'new':
                    replacements.setdefault(entity_type, {})["new"] = value
            
            for entity_type, values in replacements.items():
                if "old" in values and "new" in values:
                    actions.append(ModificationAction(ModificationType.REPLACE, entity_type, old_value=values["old"], new_value=values["new"]))
            logger.info(f"[NLU Detector] 🔄 REPLACE/MULTIPLE: {len(actions)} acciones totales detectadas.")

        return actions

    # ✅ 2 y 6. RECONSTRUCTOR MULTIVALOR Y CON EDGE CASES
    def _rebuild_parameters(self, current_params: Dict[str, Any], 
                           actions: List[ModificationAction]) -> Tuple[Dict[str, Any], List[str]]:
        rebuilt = {k: v for k, v in current_params.items() if not k.startswith('_')}
        warnings = []

        for action in actions:
            entity_type = action.entity_type
            
            if action.action_type == ModificationType.ADD_FILTER:
                if entity_type in rebuilt:
                    current = rebuilt[entity_type]
                    values = [v.strip() for v in str(current).split(',')]
                    if action.new_value not in values:
                        values.append(action.new_value)
                    rebuilt[entity_type] = ','.join(values)
                else:
                    rebuilt[entity_type] = action.new_value
            
            elif action.action_type == ModificationType.REMOVE_FILTER:
                if entity_type not in rebuilt:
                    warnings.append(f"Info: No había filtro de '{entity_type}' para remover.")
                    continue

                if action.old_value:  # Remover valor específico
                    current = rebuilt[entity_type]
                    values = [v.strip() for v in str(current).split(',')]
                    values = [v for v in values if v.lower() != action.old_value.lower()]
                    
                    if values:
                        rebuilt[entity_type] = ','.join(values)
                    else:
                        del rebuilt[entity_type]
                else:  # Remover filtro completo
                    rebuilt.pop(entity_type, None)
                    rebuilt.pop(f"{entity_type}_min", None)
                    rebuilt.pop(f"{entity_type}_max", None)
            
            elif action.action_type == ModificationType.REPLACE:
                if entity_type not in rebuilt:
                    rebuilt[entity_type] = action.new_value
                    warnings.append(f"Info: No encontré '{action.old_value}', pero agregué el filtro '{action.new_value}'.")
                else:
                    rebuilt[entity_type] = action.new_value
        
        return rebuilt, warnings

    # ❗ NUEVO MÉTODO DE VALIDACIÓN
    def _validate_actions(self, actions: List[ModificationAction], search_type: str) -> Tuple[List, List, List]:
        """Separa las acciones en válidas e inválidas."""
        valid_actions, invalid_actions, errors = [], [], []
        for action in actions:
            if self._is_valid_entity_for_search_type(action.entity_type, search_type):
                valid_actions.append(action)
            else:
                invalid_actions.append(action)
                errors.append({
                    'entity_type': action.entity_type,
                    'value': action.new_value or action.old_value,
                    'reason': f'not_valid_for_{search_type}',
                    'valid_for': self._get_valid_search_types(action.entity_type)
                })
        return valid_actions, invalid_actions, errors


    # ... (El resto de tus métodos auxiliares como _is_valid_entity_for_search_type, etc., pueden permanecer)
    def _is_valid_entity_for_search_type(self, entity_type: str, search_type: str) -> bool:
        """Verifica si una entidad es válida para el tipo de búsqueda"""
        if not entity_type: return False
        return entity_type in self.valid_entities_by_search_type.get(search_type, [])
    
    def _get_valid_search_types(self, entity_type: str) -> List[str]:
        """Retorna los tipos de búsqueda donde la entidad es válida"""
        return [st for st, entities in self.valid_entities_by_search_type.items() if entity_type in entities]