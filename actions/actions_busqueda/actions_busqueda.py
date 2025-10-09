import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import re

from actions.logger import log_message
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, EventType

from actions.config import (
    config_manager,
    get_intent_config,
    get_lookup_tables,
    get_entities_for_intent,
    validate_entity_value,
    get_entity_suggestions
)
from ..conversation_state import ConversationState, SuggestionManager, create_smart_suggestion, get_improved_suggestions
from .comparison_detector import ComparisonDetector
from .modification_detector import ModificationDetector
from ..helpers import validate_entities_for_intent, validate_entity_detection

logger = logging.getLogger(__name__)

class ActionBusquedaSituacion(Action):
    """Action optimizada con soporte completo para roles y grupos del NLU"""
    
    def __init__(self):
        try:
            self.comparison_detector = ComparisonDetector()
            self.modification_detector = ModificationDetector()
            logger.info("[ActionBusquedaSituacion] Detectores inicializados correctamente")
        except Exception as e:
            logger.error(f"[ActionBusquedaSituacion] Error inicializando detectores: {e}")
            self.comparison_detector = None
            self.modification_detector = None
    
    def name(self) -> str:
        return "action_busqueda_situacion"
    
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[str, Any]) -> List[EventType]:
        """Punto de entrada principal"""
        try:
            context = ConversationState.get_conversation_context(tracker)
            intent_name = context['current_intent']
            user_message = context.get('user_message', '')
            
            logger.info(f"[ActionBusquedaSituacion] Procesando intent: {intent_name}")
            
            events = []

            log_message(tracker, nlu_conf_threshold=0.6)
            
            # Detectar y limpiar sugerencias ignoradas
            ignored_suggestion_cleanup = self._handle_ignored_suggestions(context, intent_name, dispatcher)
            events.extend(ignored_suggestion_cleanup['events'])
            
            if ignored_suggestion_cleanup['suggestion_was_ignored']:
                context['pending_suggestion'] = None
                context['awaiting_suggestion_response'] = False
            
            # Validar intent
            intent_config = get_intent_config()
            if intent_name not in intent_config.get("intents", {}):
                logger.warning(f"[ActionBusquedaSituacion] Intent desconocido: {intent_name}")
                dispatcher.utter_message("Lo siento, no pude entender tu solicitud.")
                return events
            
            # ✅ NUEVO: Detectar comparaciones con grupos
            comparison_info = None
            if self._is_search_intent(intent_name):
                comparison_info = self._analyze_comparison_with_groups(tracker)
                logger.debug(f"[ActionBusquedaSituacion] Comparación con grupos: {comparison_info}")
            
            # Actualizar sentimiento
            if context['detected_sentiment'] != context['current_sentiment_slot']:
                events.append(SlotSet("user_sentiment", context['detected_sentiment']))
            
            # Procesar según tipo de intent
            if self._is_search_or_modify_intent(intent_name):
                result = self._handle_search_intent(context, tracker, dispatcher, comparison_info)
            else:
                if intent_name not in ['afirmar', 'denegar', 'agradecer']:
                    dispatcher.utter_message("¿En qué puedo ayudarte hoy?")
                result = {'type': 'generic_response'}
            
            events.extend(self._process_result(result, context))
            logger.info(f"[ActionBusquedaSituacion] Procesamiento completado. Eventos: {len(events)}")
            
            return events
            
        except Exception as e:
            logger.error(f"[ActionBusquedaSituacion] Error crítico: {e}", exc_info=True)
            try:
                dispatcher.utter_message("Ocurrió un error procesando tu solicitud.")
            except:
                pass
            return []

    def _analyze_comparison_with_groups(self, tracker: Tracker) -> Dict[str, Any]:
        """
        ✅ NUEVO: Analiza comparaciones extrayendo grupos del NLU
        """
        try:
            if not self.comparison_detector:
                return {}
            
            text = tracker.latest_message.get("text", "")
            entities = tracker.latest_message.get("entities", [])
            
            if not text:
                return {}
            
            logger.debug(f"[Comparison] Analizando con {len(entities)} entidades")
            
            # ✅ NUEVO: Extraer grupos antes de la detección
            entity_groups = self._extract_entity_groups(entities)
            
            # Ejecutar detección estándar
            comparison_result = self.comparison_detector.detect_comparison(text, entities)
            
            if not comparison_result.detected:
                return {}
            
            # ✅ NUEVO: Enriquecer con grupos del NLU
            comparison_info = {
                'detected': True,
                'operator': comparison_result.operator.value if comparison_result.operator else None,
                'operator_role': self._map_operator_to_role(comparison_result.operator),
                'quantity': comparison_result.quantity,
                'type': comparison_result.comparison_type.value if comparison_result.comparison_type else None,
                'entities': comparison_result.entities,
                'groups': comparison_result.groups_detected,
                'roles': comparison_result.roles_detected,
                'confidence': comparison_result.confidence,
                'temporal_filters': comparison_result.temporal_filters,
                'normalized_dates': comparison_result.normalized_dates,
                # ✅ NUEVO: Grupos del NLU
                'nlu_groups': entity_groups,
                'grouped_entities': self._group_entities_by_filter(entity_groups)
            }
            
            logger.info(
                f"[Comparison] Detectada con grupos: {list(entity_groups.keys())}, "
                f"confianza: {comparison_result.confidence:.2f}"
            )
            
            return comparison_info
            
        except Exception as e:
            logger.error(f"[Comparison] Error: {e}", exc_info=True)
            return {}

    def _extract_entity_groups(self, entities: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        ✅ NUEVO: Extrae grupos de entidades del NLU
        """
        try:
            groups = {}
            
            for entity in entities:
                group = entity.get('group')
                if group:
                    if group not in groups:
                        groups[group] = []
                    
                    groups[group].append({
                        'entity': entity.get('entity'),
                        'value': entity.get('value'),
                        'role': entity.get('role'),
                        'confidence': entity.get('confidence', 0.0)
                    })
            
            if groups:
                logger.debug(f"[Groups] Extraídos {len(groups)} grupos: {list(groups.keys())}")
                for group_name, group_entities in groups.items():
                    logger.debug(f"[Groups]   {group_name}: {[e['entity'] for e in group_entities]}")
            
            return groups
            
        except Exception as e:
            logger.error(f"[Groups] Error extrayendo: {e}")
            return {}

    def _group_entities_by_filter(self, entity_groups: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
        """
        ✅ NUEVO: Agrupa entidades por tipo de filtro (descuento, precio, stock, etc.)
        """
        try:
            grouped = {}
            
            for group_name, entities in entity_groups.items():
                # Identificar tipo de filtro del nombre del grupo
                if 'descuento' in group_name:
                    filter_type = 'descuento'
                elif 'precio' in group_name:
                    filter_type = 'precio'
                elif 'stock' in group_name:
                    filter_type = 'stock'
                elif 'bonificacion' in group_name:
                    filter_type = 'bonificacion'
                else:
                    filter_type = group_name
                
                # Organizar entidades del grupo
                filter_data = {}
                for entity in entities:
                    entity_type = entity['entity']
                    role = entity.get('role')
                    
                    if entity_type == 'comparador':
                        filter_data['operator'] = role
                        filter_data['operator_text'] = entity['value']
                    else:
                        filter_data['value'] = entity['value']
                        filter_data['entity_type'] = entity_type
                
                grouped[filter_type] = filter_data
            
            if grouped:
                logger.debug(f"[GroupedFilters] {len(grouped)} filtros agrupados")
                for filter_type, data in grouped.items():
                    logger.debug(f"[GroupedFilters]   {filter_type}: {data}")
            
            return grouped
            
        except Exception as e:
            logger.error(f"[GroupedFilters] Error: {e}")
            return {}

    def _map_operator_to_role(self, operator) -> Optional[str]:
        """
        ✅ NUEVO: Mapea operador de comparación a role del NLU
        """
        try:
            from .comparison_detector import ComparisonOperator
            
            mapping = {
                ComparisonOperator.GREATER_THAN: 'gt',
                ComparisonOperator.LESS_THAN: 'lt',
                ComparisonOperator.EQUAL_TO: 'eq',
                ComparisonOperator.DIFFERENT_FROM: 'neq'
            }
            
            return mapping.get(operator)
            
        except Exception as e:
            logger.error(f"[OperatorMap] Error: {e}")
            return None
    def _handle_multiple_modifications(self, context, tracker, dispatcher):
        """Maneja múltiples modificaciones en una oración"""
        try:
            entities = tracker.latest_message.get("entities", [])
            previous_params = self._extract_previous_search_parameters(context)
            search_type = previous_params.pop('_previous_search_type', 'producto')
            
            # Clasificar entidades por acción según role
            to_add = []
            to_remove = []
            to_replace = {}
            
            for entity in entities:
                entity_type = entity.get('entity')
                entity_value = entity.get('value')
                entity_role = entity.get('role')
                
                if entity_role == 'add':
                    to_add.append({'type': entity_type, 'value': entity_value})
                
                elif entity_role == 'remove':
                    to_remove.append(entity_type)
                
                elif entity_role == 'old':
                    # Buscar el correspondiente 'new'
                    if entity_type not in to_replace:
                        to_replace[entity_type] = {}
                    to_replace[entity_type]['old'] = entity_value
                
                elif entity_role == 'new':
                    if entity_type not in to_replace:
                        to_replace[entity_type] = {}
                    to_replace[entity_type]['new'] = entity_value
            
            logger.info(f"[MultiMod] Agregar: {to_add}, Remover: {to_remove}, Reemplazar: {to_replace}")
            
            # Aplicar modificaciones en orden
            # 1. Remover
            for entity_type in to_remove:
                self._remove_entire_parameter(previous_params, entity_type)
            
            # 2. Reemplazar
            for entity_type, values in to_replace.items():
                if 'old' in values and 'new' in values:
                    if entity_type in previous_params:
                        if isinstance(previous_params[entity_type], dict):
                            previous_params[entity_type]['value'] = values['new']
                        else:
                            previous_params[entity_type] = values['new']
            
            # 3. Agregar
            for item in to_add:
                entity_type = item['type']
                entity_value = item['value']
                
                if entity_type in previous_params:
                    # Ya existe, concatenar
                    current = previous_params[entity_type]
                    if isinstance(current, dict):
                        current['value'] += f", {entity_value}"
                    else:
                        previous_params[entity_type] += f", {entity_value}"
                else:
                    # No existe, crear
                    previous_params[entity_type] = entity_value
            
            # Ejecutar búsqueda con todos los cambios
            result = self._execute_search(search_type, previous_params, dispatcher, None, None)
            result['modifications'] = {
                'added': to_add,
                'removed': to_remove,
                'replaced': to_replace
            }
            
            return result
            
        except Exception as e:
            logger.error(f"[MultiMod] Error: {e}", exc_info=True)
            return {'type': 'multi_mod_error'}
    def _extract_search_parameters_from_entities(self, tracker: Tracker) -> Dict[str, Any]:
        try:
            search_params = {}
            current_entities = tracker.latest_message.get("entities", [])
            
            if not current_entities:
                return {}
            
            logger.info(f"[EntityParams] Procesando {len(current_entities)} entidades")
            
            entity_to_param = {
                'producto': 'nombre',
                'empresa': 'empresa',
                'categoria': 'categoria',
                'animal': 'animal',
                'sintoma': 'sintoma',
                'dosis': 'dosis',
                'estado': 'estado',
                'cantidad': 'cantidad',
                'precio': 'precio',
                'cantidad_descuento': 'descuento',
                'cantidad_bonificacion': 'bonificacion',
                'cantidad_stock': 'stock',
                'comparador': 'comparador',
                'tiempo': 'tiempo',
                'fecha': 'fecha'
            }
            
            # ✅ NUEVO: Deduplicar por tipo+valor, priorizando las que tienen role
            entity_map = {}  # key: "tipo:valor" → value: mejor entidad
            
            for entity in current_entities:
                entity_type = entity.get("entity")
                entity_value = entity.get("value", "").strip().lower()
                entity_role = entity.get("role")
                group = entity.get('group')
                
                if not entity_type or not entity_value:
                    continue
                
                # Clave sin role (para deduplicar independiente del extractor)
                entity_key = f"{entity_type}:{entity_value}"
                
                # Priorizar: con group > con role > sin role
                if entity_key not in entity_map:
                    entity_map[entity_key] = entity
                else:
                    existing = entity_map[entity_key]
                    
                    # Priorizar la que tiene group
                    if group and not existing.get('group'):
                        entity_map[entity_key] = entity
                    # Priorizar la que tiene role
                    elif entity_role and not existing.get('role'):
                        entity_map[entity_key] = entity
            
            deduplicated_entities = list(entity_map.values())
            logger.info(f"[EntityParams] Deduplicadas: {len(current_entities)} → {len(deduplicated_entities)}")
            
            # Agrupar entidades
            entities_by_type = {}
            grouped_comparisons = {}
            
            for entity in deduplicated_entities:
                entity_type = entity.get("entity")
                entity_value = entity.get("value", "").strip()
                entity_role = entity.get("role")
                group = entity.get('group')
                
                # Procesar grupos de comparación
                if group:
                    if group not in grouped_comparisons:
                        grouped_comparisons[group] = []
                    grouped_comparisons[group].append(entity)
                    continue
                
                # Agrupar entidades sin grupo por tipo
                if entity_type not in entities_by_type:
                    entities_by_type[entity_type] = []
                
                entities_by_type[entity_type].append({
                    'value': entity_value,
                    'role': entity_role,
                    'entity': entity
                })
            
            # Procesar grupos de comparación
            for group_name, group_entities in grouped_comparisons.items():
                self._process_comparison_group(group_name, group_entities, search_params)
            
            # Procesar entidades agrupadas por tipo
            for entity_type, entity_list in entities_by_type.items():
                if entity_type not in entity_to_param:
                    continue
                
                param_name = entity_to_param[entity_type]
                valid_values = []
                common_role = None
                
                for item in entity_list:
                    entity_value = item['value']
                    entity_role = item['role']
                    
                    validation_result = validate_entity_detection(
                        entity_type=entity_type,
                        entity_value=entity_value,
                        min_length=2,
                        check_fragments=True
                    )
                    
                    if validation_result.get("valid"):
                        normalized_value = validation_result.get("normalized", entity_value)
                        valid_values.append(normalized_value)
                        if entity_role and not common_role:
                            common_role = entity_role
                        logger.info(f"[EntityParams] ✅ {entity_type}='{entity_value}' válido")
                    else:
                        logger.warning(f"[EntityParams] ❌ {entity_type}='{entity_value}' rechazado")
                
                # Guardar valores
                if valid_values:
                    if len(valid_values) > 1:
                        if entity_type in ["empresa", "dosis", "estado"]:
                            search_params[param_name] = {
                                "value": ", ".join(valid_values),
                                "role": common_role or "unspecified"
                            }
                        else:
                            search_params[param_name] = ", ".join(valid_values)
                        
                        logger.info(f"[EntityParams] ✅ Múltiples {entity_type}: {valid_values}")
                    else:
                        if entity_type in ["empresa", "dosis", "estado"]:
                            search_params[param_name] = {
                                "value": valid_values[0],
                                "role": common_role or "unspecified"
                            }
                        else:
                            search_params[param_name] = valid_values[0]
            
            logger.info(f"[EntityParams] {len(search_params)} parámetros extraídos")
            return search_params
            
        except Exception as e:
            logger.error(f"[EntityParams] Error: {e}", exc_info=True)
            return {}

    def _process_comparison_group(self, group_name: str, group_entities: List[Dict[str, Any]], 
                                   search_params: Dict[str, Any]) -> None:
        """
        ✅ NUEVO: Procesa un grupo de comparación del NLU
        """
        try:
            logger.debug(f"[CompGroup] Procesando grupo '{group_name}' con {len(group_entities)} entidades")
            
            operator_entity = None
            value_entity = None
            
            # Separar operador y valor
            for entity in group_entities:
                if entity.get('entity') == 'comparador':
                    operator_entity = entity
                else:
                    value_entity = entity
            
            if not operator_entity or not value_entity:
                logger.warning(f"[CompGroup] Grupo '{group_name}' incompleto")
                return
            
            # Extraer información
            operator_role = operator_entity.get('role')  # gt, lt, gte, lte, eq
            value_type = value_entity.get('entity')
            value = value_entity.get('value')
            
            # Determinar tipo de filtro
            if 'descuento' in group_name:
                filter_key = 'descuento_filter'
                param_name = 'descuento'
            elif 'precio' in group_name:
                filter_key = 'precio_filter'
                param_name = 'precio'
            elif 'stock' in group_name:
                filter_key = 'stock_filter'
                param_name = 'stock'
            elif 'bonificacion' in group_name:
                filter_key = 'bonificacion_filter'
                param_name = 'bonificacion'
            else:
                filter_key = group_name
                param_name = value_type
            
            # Guardar en search_params
            search_params[filter_key] = {
                'operator': operator_role,
                'value': value,
                'type': value_type,
                'group': group_name
            }
            
            logger.info(f"[CompGroup] ✅ {filter_key}: {operator_role} {value}")
            
        except Exception as e:
            logger.error(f"[CompGroup] Error procesando grupo: {e}")

    def _handle_modify_search_intent(self, context: Dict[str, Any], tracker: Tracker, 
                                    dispatcher: CollectingDispatcher, search_type: str,
                                    comparison_info: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        ✅ OPTIMIZADO: Maneja modificaciones usando roles old/new del NLU
        """
        try:
            user_message = context.get('user_message', '')
            
            logger.info(f"[ModifySearch] Procesando modificación (tipo: {search_type})")
            
            # ✅ NUEVO: Extraer modificaciones directamente del NLU
            nlu_modifications = self._extract_nlu_modifications(tracker)
            
            # PASO 1: Si hay modificaciones del NLU, usarlas prioritariamente
            if nlu_modifications['detected']:
                logger.info(f"[ModifySearch] Usando {len(nlu_modifications['actions'])} modificaciones del NLU")
                
                # Validar entidades para el tipo de búsqueda
                validation_result = self._validate_modification_entities(
                    nlu_modifications['actions'], search_type
                )
                
                if validation_result['has_invalid']:
                    return self._handle_invalid_entity_modification(
                        validation_result, search_type, dispatcher
                    )
                
                # Aplicar modificaciones
                previous_params = self._extract_previous_search_parameters(context)
                rebuilt_params = self._apply_nlu_modifications(
                    previous_params, nlu_modifications['actions']
                )
                
            else:
                # Fallback: usar detector de modificaciones
                logger.info("[ModifySearch] No hay modificaciones NLU, usando detector")
                
                if not self.modification_detector:
                    logger.warning("[ModifySearch] Detector no disponible")
                    dispatcher.utter_message("No pude procesar la modificación.")
                    return {'type': 'modify_error', 'reason': 'no_detector'}
                
                previous_params = self._extract_previous_search_parameters(context)
                entities = tracker.latest_message.get("entities", [])
                
                modification_result = self.modification_detector.detect_and_rebuild(
                    user_message, entities, previous_params, search_type=search_type
                )
                
                if not modification_result.detected:
                    logger.warning("[ModifySearch] No se detectaron modificaciones")
                    dispatcher.utter_message("No pude identificar qué modificar.")
                    return {'type': 'modify_error', 'reason': 'no_detection'}
                
                if modification_result.has_invalid_entities:
                    return self._handle_invalid_entity_modification(
                        modification_result, search_type, dispatcher
                    )
                
                rebuilt_params = modification_result.rebuilt_params
            
            # PASO 2: Ejecutar búsqueda modificada
            if not rebuilt_params:
                dispatcher.utter_message("No hay parámetros válidos para modificar.")
                return {'type': 'modify_error', 'reason': 'no_params'}
            
            temporal_filters = self._extract_temporal_filters(user_message, comparison_info)
            
            logger.info(f"[ModifySearch] Ejecutando búsqueda modificada de {search_type}")
            result = self._execute_search(search_type, rebuilt_params, dispatcher, comparison_info, temporal_filters)
            
            # Marcar como modificación
            result['modification_applied'] = True
            result['combined_params'] = rebuilt_params
            
            return result
            
        except Exception as e:
            logger.error(f"[ModifySearch] Error: {e}", exc_info=True)
            dispatcher.utter_message("Hubo un error modificando tu búsqueda.")
            return {'type': 'modify_error', 'error': str(e)}

    def _extract_nlu_modifications(self, tracker: Tracker) -> Dict[str, Any]:
        """
        ✅ OPTIMIZADO: Extrae modificaciones de roles old/new del NLU (incluyendo formatos compuestos)
        """
        try:
            entities = tracker.latest_message.get("entities", [])
            
            modifications = {
                'detected': False,
                'actions': []
            }
            
            logger.debug(f"[NLUMod] Analizando {len(entities)} entidades")
            
            # Agrupar entidades por tipo para encontrar pares old/new
            entities_by_type = {}
            for entity in entities:
                entity_type = entity.get('entity')
                role = entity.get('role', '')
                value = entity.get('value')
                
                if not role or not value:
                    continue
                
                # ✅ NUEVO: Detectar roles que terminen en _old o _new (ej: proveedor_old, proveedor_new)
                role_suffix = None
                if role.endswith('_old') or role == 'old':
                    role_suffix = 'old'
                elif role.endswith('_new') or role == 'new':
                    role_suffix = 'new'
                
                if role_suffix:
                    if entity_type not in entities_by_type:
                        entities_by_type[entity_type] = {}
                    entities_by_type[entity_type][role_suffix] = value
                    logger.debug(f"[NLUMod] Detectado: {entity_type} con role '{role}' → {role_suffix} = '{value}'")
            
            # Crear acciones de modificación
            for entity_type, roles in entities_by_type.items():
                if 'old' in roles and 'new' in roles:
                    modifications['actions'].append({
                        'type': 'replace',
                        'entity_type': entity_type,
                        'old_value': roles['old'],
                        'new_value': roles['new']
                    })
                    modifications['detected'] = True
                    logger.info(f"[NLUMod] ✅ Reemplazo detectado: {entity_type} '{roles['old']}' → '{roles['new']}'")
                
                elif 'new' in roles and 'old' not in roles:
                    # Solo hay new, es una adición
                    modifications['actions'].append({
                        'type': 'add',
                        'entity_type': entity_type,
                        'new_value': roles['new']
                    })
                    modifications['detected'] = True
                    logger.info(f"[NLUMod] ✅ Adición detectada: {entity_type} = '{roles['new']}'")
            
            if modifications['detected']:
                logger.info(f"[NLUMod] ✅ {len(modifications['actions'])} modificaciones extraídas del NLU")
            else:
                logger.debug("[NLUMod] No se encontraron modificaciones en el NLU")
            
            return modifications
            
        except Exception as e:
            logger.error(f"[NLUMod] Error: {e}", exc_info=True)
            return {'detected': False, 'actions': []}

    def _validate_modification_entities(self, actions: List[Dict[str, Any]], 
                                       search_type: str) -> Dict[str, Any]:
        """
        ✅ NUEVO: Valida que las entidades modificadas sean válidas para el tipo de búsqueda
        """
        try:
            if not self.modification_detector:
                return {'has_invalid': False, 'valid_actions': actions, 'invalid_actions': []}
            
            valid_actions = []
            invalid_actions = []
            validation_errors = []
            
            for action in actions:
                entity_type = action['entity_type']
                
                if self.modification_detector._is_valid_entity_for_search_type(entity_type, search_type):
                    valid_actions.append(action)
                else:
                    invalid_actions.append(action)
                    valid_for = self.modification_detector._get_valid_search_types(entity_type)
                    validation_errors.append({
                        'entity_type': entity_type,
                        'value': action.get('new_value') or action.get('old_value'),
                        'reason': f'not_valid_for_{search_type}',
                        'valid_for': valid_for
                    })
            
            return {
                'has_invalid': len(invalid_actions) > 0,
                'valid_actions': valid_actions,
                'invalid_actions': invalid_actions,
                'validation_errors': validation_errors
            }
            
        except Exception as e:
            logger.error(f"[ModValidation] Error: {e}")
            return {'has_invalid': False, 'valid_actions': actions, 'invalid_actions': []}

    def _apply_nlu_modifications(self, current_params: Dict[str, Any], 
                                 actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        ✅ NUEVO: Aplica modificaciones extraídas del NLU
        """
        try:
            rebuilt = {}
            
            # Copiar parámetros actuales
            for key, value in current_params.items():
                if not key.startswith('_'):
                    rebuilt[key] = value
            
            # Aplicar modificaciones
            for action in actions:
                action_type = action['type']
                entity_type = action['entity_type']
                
                if action_type == 'replace':
                    old_value = action['old_value']
                    new_value = action['new_value']
                    
                    # Reemplazar
                    if entity_type in rebuilt:
                        if isinstance(rebuilt[entity_type], dict) and 'value' in rebuilt[entity_type]:
                            rebuilt[entity_type]['value'] = new_value
                        else:
                            rebuilt[entity_type] = new_value
                        logger.info(f"[NLUApply] Reemplazado: {entity_type} '{old_value}' → '{new_value}'")
                    else:
                        rebuilt[entity_type] = new_value
                        logger.info(f"[NLUApply] Agregado (reemplazo): {entity_type} = '{new_value}'")
                
                elif action_type == 'add':
                    new_value = action['new_value']
                    rebuilt[entity_type] = new_value
                    logger.info(f"[NLUApply] Agregado: {entity_type} = '{new_value}'")
            
            logger.info(f"[NLUApply] {len(rebuilt)} parámetros después de modificaciones")
            return rebuilt
            
        except Exception as e:
            logger.error(f"[NLUApply] Error: {e}")
            return current_params

    
    def _handle_search_intent(self, context: Dict[str, Any], tracker: Tracker, 
                            dispatcher: CollectingDispatcher, 
                            comparison_info: Dict[str, Any] = None) -> Dict[str, Any]:
        """Manejo principal de búsquedas"""
        try:
            intent_name = context['current_intent']
            search_type = self._get_search_type(intent_name, context)
            user_message = context.get('user_message', '')
            
            # ✅ Manejar sub-intents de modificación
            if intent_name == 'modificar_busqueda:remover':
                return self._handle_remove_filter(context, tracker, dispatcher)
            elif intent_name == 'modificar_busqueda:multiple':
                return self._handle_multiple_modifications(context, tracker, dispatcher)
            elif intent_name == 'modificar_busqueda:agregar':
                # TODO: Implementar
                pass
            
            elif intent_name == 'modificar_busqueda:reemplazar':
                return self._handle_modify_search_intent(context, tracker, dispatcher, 
                                                        search_type, comparison_info)
            
            elif intent_name.startswith('modificar_busqueda'):
                return self._handle_modify_search_intent(context, tracker, dispatcher, 
                                                        search_type, comparison_info)
            
            # Búsqueda normal
            slot_cleanup_events = self._generate_slot_cleanup_events(tracker, intent_name)
            search_params = self._extract_search_parameters_from_entities(tracker)
        
            
            if search_params:
                # Validar coherencia de comparación
                if comparison_info and comparison_info.get('detected'):
                    is_coherent = self._validate_comparison_coherence(comparison_info, search_params)
                    if not is_coherent:
                        logger.warning("[Search] Comparación descartada por incoherencia")
                        comparison_info = None
                
                temporal_filters = self._extract_temporal_filters(user_message, comparison_info)
                
                result = self._execute_search(search_type, search_params, dispatcher, comparison_info, temporal_filters)
                result['slot_cleanup_events'] = slot_cleanup_events
                return result
            else:
                # Sin parámetros válidos - validar y sugerir
                validation_result = self._validate_entities_with_helper(tracker, intent_name, dispatcher)
                
                if validation_result.get('has_suggestions'):
                    return {
                        'type': 'entity_suggestion',
                        'suggestion_data': validation_result['suggestion_data'],
                        'slot_cleanup_events': slot_cleanup_events
                    }
                else:
                    dispatcher.utter_message("Por favor indicame parametros para realizar la busqueda")
                    return {'type': 'validation_error', 'slot_cleanup_events': slot_cleanup_events}
                
        except Exception as e:
            logger.error(f"[Search] Error: {e}", exc_info=True)
            dispatcher.utter_message("Ocurrió un error procesando tu búsqueda.")
            return {'type': 'search_error'}

    # Métodos auxiliares (sin cambios)
    def _is_search_intent(self, intent_name: str) -> bool:
        search_intents = ['buscar_producto', 'buscar_oferta', 'consultar_novedades_producto', 
                         'consultar_novedades_oferta', 'consultar_recomendaciones_producto',
                         'consultar_recomendaciones_oferta']
        return intent_name in search_intents
    
    def _is_search_or_modify_intent(self, intent_name: str) -> bool:
        """Detecta intents de búsqueda o modificación (incluyendo sub-intents)"""
        return (
            self._is_search_intent(intent_name) or 
            intent_name.startswith('modificar_busqueda')  # ✅ Incluye todos los sub-intents
        )
    
    def _get_search_type(self, intent_name: str, context: Dict[str, Any] = None) -> str:
        if intent_name == "modificar_busqueda":
            if context:
                search_history = context.get('search_history', [])
                if search_history:
                    return search_history[-1].get('type', 'producto')
            return "producto"
        elif "oferta" in intent_name:
            return "oferta"
        elif "producto" in intent_name:
            return "producto"
        else:
            return "producto"
    def _handle_remove_filter(self, context: Dict[str, Any], tracker: Tracker, 
                         dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Maneja remoción de filtros - VERSIÓN CORREGIDA"""
        try:
            entities = tracker.latest_message.get("entities", [])
            
            if not entities:
                dispatcher.utter_message("No identifiqué qué filtro remover.")
                return {'type': 'remove_error'}
            
            # Extraer parámetros de búsqueda anterior
            previous_params = self._extract_previous_search_parameters(context)
            search_type = previous_params.pop('_previous_search_type', 'producto')
            
            logger.info(f"[RemoveFilter] Parámetros previos: {previous_params}")
            
            # Agrupar entidades por tipo
            entities_by_type = {}
            for entity in entities:
                entity_type = entity.get('entity')
                entity_value = entity.get('value')
                
                if entity_type not in entities_by_type:
                    entities_by_type[entity_type] = []
                entities_by_type[entity_type].append(entity_value)
            
            # Procesar cada tipo de entidad
            for entity_type, values in entities_by_type.items():
                # ✅ NUEVO: Detectar si se está mencionando la categoría misma vs un valor específico
                is_removing_category = self._is_category_removal(entity_type, values)
                
                if is_removing_category:
                    # CASO 1: Remover categoría completa
                    self._remove_entire_parameter(previous_params, entity_type)
                    logger.info(f"[RemoveFilter] Categoría completa removida: {entity_type}")
                else:
                    # CASO 2: Remover valores específicos
                    self._remove_specific_values(previous_params, entity_type, values)
                    logger.info(f"[RemoveFilter] Valores específicos removidos de {entity_type}: {values}")
            
            logger.info(f"[RemoveFilter] Parámetros después: {previous_params}")
            
            if not previous_params:
                dispatcher.utter_message("No quedan filtros. ¿Qué querés buscar?")
                return {'type': 'no_filters_remaining'}
            
            # Ejecutar búsqueda sin los filtros removidos
            result = self._execute_search(search_type, previous_params, dispatcher, None, None)
            result['filters_removed'] = entities_by_type
            
            return result
            
        except Exception as e:
            logger.error(f"[RemoveFilter] Error: {e}", exc_info=True)
            dispatcher.utter_message("Hubo un error al remover el filtro.")
            return {'type': 'remove_error', 'error': str(e)}

    def _is_category_removal(self, entity_type: str, values: List[str]) -> bool:
        """
        ✅ NUEVO: Detecta si el usuario quiere remover la categoría completa
        vs un valor específico dentro de ella
        """
        try:
            # Si no hay valores o todos son None → remover categoría
            if not values or all(v is None for v in values):
                return True
            
            # Si el valor mencionado es el nombre de la categoría misma → remover categoría
            # Ej: "sin estado" donde value='estado' y entity_type='estado'
            category_names = [entity_type, entity_type.lower()]
            
            for value in values:
                if value and value.lower() in category_names:
                    return True
            
            # Casos especiales para ciertos tipos de entidad
            generic_removal_terms = ['filtro', 'restriccion', 'limite', 'parametro']
            for value in values:
                if value and value.lower() in generic_removal_terms:
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"[CategoryRemoval] Error: {e}")
            return True  # En caso de error, asumir remoción de categoría

    def _remove_entire_parameter(self, params: Dict, entity_type: str):
        """Remueve un parámetro completo y sus variantes"""
        keys_to_remove = [
            entity_type,
            f"{entity_type}_min",
            f"{entity_type}_max"
        ]
        
        for key in keys_to_remove:
            params.pop(key, None)

    def _remove_specific_values(self, params: Dict, entity_type: str, values_to_remove: List[str]):
        """Remueve valores específicos de un parámetro que puede tener múltiples valores"""
        
        # Buscar el parámetro en params
        param_key = entity_type
        if param_key not in params:
            # Intentar con variantes
            param_key = f"{entity_type}_min" if f"{entity_type}_min" in params else \
                        f"{entity_type}_max" if f"{entity_type}_max" in params else None
            
            if not param_key:
                return  # No existe el parámetro
        
        current_value = params[param_key]
        
        # Si es string simple, verificar si contiene múltiples valores separados por coma
        if isinstance(current_value, str):
            current_values = [v.strip() for v in current_value.split(',')]
            
            # Remover valores especificados
            remaining_values = [v for v in current_values if v.lower() not in [r.lower() for r in values_to_remove]]
            
            if remaining_values:
                # Actualizar con valores restantes
                params[param_key] = ', '.join(remaining_values)
            else:
                # Si no quedan valores, remover el parámetro completo
                params.pop(param_key)
        
        # Si es dict con value/role
        elif isinstance(current_value, dict) and 'value' in current_value:
            value_str = current_value['value']
            current_values = [v.strip() for v in value_str.split(',')]
            
            remaining_values = [v for v in current_values if v.lower() not in [r.lower() for r in values_to_remove]]
            
            if remaining_values:
                current_value['value'] = ', '.join(remaining_values)
            else:
                params.pop(param_key)

    def _handle_ignored_suggestions(self, context: Dict[str, Any], current_intent: str, 
                                   dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Detecta y limpia sugerencias ignoradas automáticamente"""
        try:
            pending_suggestion = context.get('pending_suggestion')
            if not pending_suggestion:
                return {'suggestion_was_ignored': False, 'events': []}
            
            suggestion_ignored = SuggestionManager.check_if_suggestion_ignored(
                current_intent, pending_suggestion, context.get('is_small_talk', False)
            )
            
            if suggestion_ignored:
                suggestion_type = pending_suggestion.get('suggestion_type', 'unknown')
                original_search_type = pending_suggestion.get('search_type', 'unknown')
                
                logger.info(f"[IgnoredSugg] Detectada - Tipo: {suggestion_type}")
                
                if suggestion_type == 'entity_correction':
                    original_value = pending_suggestion.get('original_value', '')
                    message = f"Entiendo que prefieres hacer una nueva búsqueda en lugar de corregir '{original_value}'."
                elif suggestion_type == 'type_correction':
                    message = "Perfecto, te ayudo con esta nueva búsqueda."
                else:
                    message = "Perfecto, te ayudo con tu nueva búsqueda."
                
                current_search_type = self._get_search_type(current_intent)
                if original_search_type != 'unknown' and current_search_type != original_search_type:
                    try:
                        dispatcher.utter_message(message)
                    except Exception as msg_error:
                        logger.error(f"[IgnoredSugg] Error enviando mensaje: {msg_error}")
                
                cleanup_events = [
                    SlotSet("pending_suggestion", None),
                    SlotSet("suggestion_context", None),
                    SlotSet("user_engagement_level", "engaged"),
                ]
                
                return {
                    'suggestion_was_ignored': True,
                    'events': cleanup_events,
                    'cleanup_reason': 'user_changed_search_type'
                }
            
            return {'suggestion_was_ignored': False, 'events': []}
            
        except Exception as e:
            logger.error(f"[IgnoredSugg] Error: {e}", exc_info=True)
            return {
                'suggestion_was_ignored': True,
                'events': [SlotSet("pending_suggestion", None)],
                'cleanup_reason': 'error_recovery'
            }

    def _validate_comparison_coherence(self, comparison_info: Dict[str, Any], 
                                       parameters: Dict[str, str]) -> bool:
        """
        ✅ OPTIMIZADO: Valida coherencia usando grupos del NLU
        """
        try:
            if not comparison_info or not comparison_info.get('detected'):
                return False
            
            # ✅ NUEVO: Validar usando grupos del NLU si están disponibles
            nlu_groups = comparison_info.get('nlu_groups', {})
            if nlu_groups:
                # Si hay grupos del NLU, la comparación es inherentemente coherente
                # porque ya fue validada por el NLU
                logger.info(f"[CoherenceCheck] Validada por NLU groups: {list(nlu_groups.keys())}")
                return True
            
            # Fallback: validación original
            comparison_type = comparison_info.get('type')
            confidence = comparison_info.get('confidence', 0.0)
            
            if confidence < 0.7:
                logger.warning(f"[CoherenceCheck] Baja confianza: {confidence:.2f}")
                return False
            
            if comparison_type == 'price':
                has_price_entities = any(
                    key in parameters for key in ['precio', 'descuento', 'bonificacion']
                )
                if not has_price_entities:
                    logger.warning(f"[CoherenceCheck] Tipo 'price' sin entidades de precio")
                    return False
            
            elif comparison_type == 'quantity':
                if 'cantidad' not in parameters:
                    logger.warning(f"[CoherenceCheck] Tipo 'quantity' sin entidad cantidad")
                    return False
            
            elif comparison_type == 'stock':
                if 'stock' not in parameters:
                    logger.warning(f"[CoherenceCheck] Tipo 'stock' sin entidad stock")
                    return False
            
            logger.info(f"[CoherenceCheck] Validada: {comparison_type} (conf: {confidence:.2f})")
            return True
            
        except Exception as e:
            logger.error(f"[CoherenceCheck] Error: {e}")
            return False

    def _extract_temporal_filters(self, text: str, comparison_info: Dict[str, Any] = None) -> Dict[str, Any]:
        """Extrae filtros temporales del texto"""
        try:
            temporal_filters = {}
            text_lower = text.lower()
            
            # Si hay filtros temporales de comparación, usarlos como base
            if comparison_info and comparison_info.get('temporal_filters'):
                temporal_filters.update(comparison_info['temporal_filters'])
                logger.debug(f"[TemporalFilters] Usando de comparación: {temporal_filters}")
            
            # Detectar términos temporales adicionales
            now = datetime.now()
            
            if not temporal_filters and any(word in text_lower for word in ["reciente", "nuevo", "últimos"]):
                temporal_filters["date_from"] = (now - timedelta(weeks=2)).strftime("%Y-%m-%d")
                temporal_filters["date_to"] = now.strftime("%Y-%m-%d")
                temporal_filters["period"] = "recent"
            
            if any(word in text_lower for word in ["vigente", "válido", "activo"]):
                if not temporal_filters.get("date_from"):
                    temporal_filters["date_from"] = now.strftime("%Y-%m-%d")
                temporal_filters["status"] = "active"
            
            if any(phrase in text_lower for phrase in ["que vencen", "próximos a vencer", "por vencer"]):
                temporal_filters["date_to"] = (now + timedelta(days=30)).strftime("%Y-%m-%d")
                temporal_filters["status"] = "expiring_soon"
            
            if temporal_filters:
                logger.info(f"[TemporalFilters] Extraídos: {temporal_filters}")
            
            return temporal_filters
            
        except Exception as e:
            logger.error(f"[TemporalFilters] Error: {e}", exc_info=True)
            return {}

    def _format_temporal_description(self, temporal_filters: Dict[str, Any]) -> str:
        """Formatea descripción legible de filtros temporales"""
        try:
            if not temporal_filters:
                return ""
            
            descriptions = []
            
            if temporal_filters.get("period"):
                period_descriptions = {
                    "current_week": "de esta semana",
                    "current_month": "de este mes",
                    "recent": "recientes",
                    "current_and_future": "vigentes"
                }
                period = temporal_filters["period"]
                if period in period_descriptions:
                    descriptions.append(period_descriptions[period])
            
            if temporal_filters.get("date_from") and temporal_filters.get("date_to"):
                if temporal_filters["date_from"] == temporal_filters["date_to"]:
                    descriptions.append(f"del {temporal_filters['date_from']}")
                else:
                    descriptions.append(f"desde {temporal_filters['date_from']} hasta {temporal_filters['date_to']}")
            elif temporal_filters.get("date_from"):
                descriptions.append(f"desde {temporal_filters['date_from']}")
            elif temporal_filters.get("date_to"):
                descriptions.append(f"hasta {temporal_filters['date_to']}")
            
            if temporal_filters.get("status") == "expiring_soon":
                descriptions.append("que vencen pronto")
            elif temporal_filters.get("status") == "active":
                descriptions.append("activos")
            
            return " ".join(descriptions) if descriptions else ""
            
        except Exception as e:
            logger.error(f"[TemporalDesc] Error: {e}")
            return ""

    def _validate_entities_with_helper(self, tracker: Tracker, intent_name: str, 
                                       dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Valida entidades priorizando las de mayor confianza"""
        try:
            entities = tracker.latest_message.get("entities", [])
            
            # Ordenar por confianza
            entities_with_confidence = []
            for entity in entities:
                confidence = entity.get("confidence_entity", entity.get("confidence", 0.0))
                entities_with_confidence.append({
                    **entity,
                    "confidence_score": confidence
                })
            
            entities_sorted = sorted(entities_with_confidence, key=lambda x: x["confidence_score"], reverse=True)
            
            logger.debug(f"[EntityValidation] Validando {len(entities_sorted)} entidades")
            
            helper_result = validate_entities_for_intent(entities_sorted, intent_name, min_length=2, check_fragments=True)
            
            # Aplicar validación cruzada
            enhanced_suggestions = []
            cross_entity_suggestions = []
            
            if helper_result['has_suggestions']:
                for suggestion_item in helper_result['suggestions']:
                    try:
                        entity_type = suggestion_item.get('entity_type')
                        raw_value = suggestion_item.get('raw_value')
                        suggestions_list = suggestion_item.get('suggestions', [])
                        
                        original_confidence = 0.0
                        for original_ent in entities_sorted:
                            if original_ent.get('value') == raw_value and original_ent.get('entity') == entity_type:
                                original_confidence = original_ent['confidence_score']
                                break
                        
                        if suggestions_list:
                            suggestion_text = suggestions_list[0]
                            message = f"'{raw_value}' no es válido. ¿Te refieres a '{suggestion_text}'?"
                            
                            suggestion_data = SuggestionManager.create_entity_suggestion(
                                raw_value, entity_type, suggestion_text, 
                                {
                                    'intent': tracker.get_intent_of_latest_message(),
                                    'original_confidence': original_confidence
                                }
                            )
                            enhanced_suggestions.append(suggestion_data)
                            dispatcher.utter_message(message)
                            logger.info(f"[EntityValidation] Sugerencia normal: '{raw_value}' → '{suggestion_text}'")
                        else:
                            # Validación cruzada
                            cross_matches = self.validate_and_suggest_entities(raw_value, entity_type)
                            
                            if cross_matches:
                                cross_message = self.format_cross_entity_suggestions(cross_matches)
                                dispatcher.utter_message(f"'{raw_value}' no es válido como {entity_type}. {cross_message}")
                                
                                best_match = cross_matches[0]
                                cross_suggestion_data = SuggestionManager.create_entity_suggestion(
                                    raw_value, best_match['entity_type'], best_match['suggestion'],
                                    {
                                        'intent': tracker.get_intent_of_latest_message(), 
                                        'cross_entity': True,
                                        'original_confidence': original_confidence
                                    }
                                )
                                cross_entity_suggestions.append(cross_suggestion_data)
                                logger.info(f"[EntityValidation] Sugerencia cruzada: '{raw_value}' → '{best_match['suggestion']}'")
                            else:
                                dispatcher.utter_message(f"'{raw_value}' no es válido como {entity_type}.")
                    
                    except Exception as suggestion_error:
                        logger.error(f"[EntityValidation] Error en sugerencia: {suggestion_error}")
                        continue
            
            all_suggestions = enhanced_suggestions + cross_entity_suggestions
            all_suggestions.sort(key=lambda x: -x.get('metadata', {}).get('original_confidence', 0.0))
            
            return {
                'valid_params': helper_result['valid_params'],
                'has_suggestions': len(all_suggestions) > 0,
                'suggestion_data': all_suggestions[0] if all_suggestions else None,
                'has_errors': helper_result['has_errors'] and len(all_suggestions) == 0,
                'errors': helper_result['errors'] if len(all_suggestions) == 0 else []
            }
            
        except Exception as e:
            logger.error(f"[EntityValidation] Error: {e}", exc_info=True)
            return {
                'valid_params': {},
                'has_suggestions': False,
                'suggestion_data': None,
                'has_errors': True,
                'errors': ["Error validando entidades"]
            }

    def validate_and_suggest_entities(self, invalid_value: str, original_entity_type: str) -> List[Dict[str, Any]]:
        """Usa sistema avanzado de similitud"""
        try:
            logger.debug(f"[CrossValidation] Para '{invalid_value}' (tipo: {original_entity_type})")
            
            suggestions = get_improved_suggestions(
                invalid_value, 
                original_entity_type, 
                max_suggestions=5
            )
            
            if not suggestions:
                return []
            
            formatted_suggestions = []
            for suggestion in suggestions:
                formatted_suggestions.append({
                    'entity_type': suggestion['entity_type'],
                    'suggestion': suggestion['suggestion'],
                    'similarity': suggestion['similarity'],
                    'original_value': suggestion['original_input'],
                    'match_confidence': suggestion['match_confidence'],
                    'priority': 1,
                    'match_type': 'advanced_similarity'
                })
            
            formatted_suggestions.sort(key=lambda x: x['similarity'], reverse=True)
            
            logger.info(f"[CrossValidation] {len(formatted_suggestions)} sugerencias para '{invalid_value}'")
            return formatted_suggestions
            
        except Exception as e:
            logger.error(f"[CrossValidation] Error: {e}", exc_info=True)
            return []

    def format_cross_entity_suggestions(self, matches: List[Dict[str, Any]]) -> str:
        """Formatea sugerencias priorizando spelling"""
        try:
            if not matches:
                return "No se encontraron sugerencias alternativas."
            
            spelling_matches = [m for m in matches if m.get('match_type') == 'spelling']
            cross_entity_matches = [m for m in matches if m.get('match_type') == 'cross_entity']
            
            if spelling_matches:
                best_spelling = spelling_matches[0]
                return f"¿Te refieres a '{best_spelling['suggestion']}'? (corrección de ortografía)"
            
            elif len(cross_entity_matches) == 1:
                match = cross_entity_matches[0]
                entity_display = self._get_entity_display_name(match['entity_type'])
                return f"¿Te refieres a '{match['suggestion']}' como {entity_display}?"
            
            elif cross_entity_matches:
                suggestions = []
                for match in cross_entity_matches[:3]:
                    entity_display = self._get_entity_display_name(match['entity_type'])
                    suggestions.append(f"'{match['suggestion']}' ({entity_display})")
                
                if len(suggestions) == 2:
                    return f"¿Te refieres a {suggestions[0]} o {suggestions[1]}?"
                else:
                    return f"¿Te refieres a {', '.join(suggestions[:-1])} o {suggestions[-1]}?"
            
            return "¿Podrías intentar con otro término?"
                    
        except Exception as e:
            logger.error(f"[CrossFormat] Error: {e}")
            return "¿Podrías intentar con otro término?"

    def _get_entity_display_name(self, entity_type: str) -> str:
        """Convierte nombres técnicos a legibles"""
        display_names = {
            'categoria': 'categoría',
            'empresa': 'empresa', 
            'ingrediente_activo': 'ingrediente activo',
            'animal': 'animal',
            'producto': 'producto',
            'accion_terapeutica': 'acción terapéutica'
        }
        return display_names.get(entity_type, entity_type)

    def _extract_previous_search_parameters(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        ✅ OPTIMIZADO: Extrae parámetros preservando estructura con roles
        """
        try:
            search_history = context.get('search_history', [])
            
            if not search_history:
                return {}
            
            latest_search = search_history[-1]
            previous_params = latest_search.get('parameters', {})
            search_type = latest_search.get('type', 'producto')
            
            # Incluir metadata
            enriched_params = previous_params.copy()
            enriched_params['_previous_search_type'] = search_type
            enriched_params['_previous_timestamp'] = latest_search.get('timestamp')
            
            if previous_params:
                logger.info(f"[PrevParams] {len(previous_params)} parámetros de búsqueda anterior ({search_type})")
            
            return enriched_params
            
        except Exception as e:
            logger.error(f"[PrevParams] Error: {e}")
            return {}

    def _generate_slot_cleanup_events(self, tracker: Tracker, intent_name: str = None) -> List[EventType]:
        """
        ✅ OPTIMIZADO: Limpieza inteligente preservando contexto
        """
        try:
            cleanup_events = []
            
            current_entities = tracker.latest_message.get("entities", [])
            current_entity_types = {entity.get("entity") for entity in current_entities if entity.get("entity")}
            
            search_slots = [
                'producto', 'empresa', 'categoria', 'animal', 'sintoma', 'dosis',
                'estado', 'cantidad', 'precio', 'descuento', 'bonificacion', 
                'stock', 'tiempo', 'fecha'
            ]
            
            if intent_name == 'modificar_busqueda':
                logger.info("[SlotCleanup] Modo conservador para modificar_busqueda")
                # No limpiar nada - preservar todo el contexto
            else:
                slots_cleaned = []
                for slot_name in search_slots:
                    current_slot_value = tracker.get_slot(slot_name)
                    
                    if current_slot_value and slot_name not in current_entity_types:
                        cleanup_events.append(SlotSet(slot_name, None))
                        slots_cleaned.append(slot_name)
                
                if slots_cleaned:
                    logger.info(f"[SlotCleanup] Limpiados {len(slots_cleaned)} slots")
            
            return cleanup_events
            
        except Exception as e:
            logger.error(f"[SlotCleanup] Error: {e}")
            return []

    def _handle_invalid_entity_modification(self, modification_result: Any,
                                           search_type: str, dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Maneja entidades inválidas en modificaciones"""
        try:
            if isinstance(modification_result, dict):
                invalid_actions = modification_result.get('invalid_actions', [])
                validation_errors = modification_result.get('validation_errors', [])
            else:
                invalid_actions = modification_result.invalid_actions
                validation_errors = modification_result.validation_errors
            
            logger.info(f"[InvalidMod] Procesando {len(invalid_actions)} entidades inválidas")
            
            # ✅ NUEVO: Serializar invalid_actions a diccionarios
            serialized_invalid_actions = []
            for action in invalid_actions:
                if isinstance(action, dict):
                    serialized_invalid_actions.append(action)
                else:
                    # Convertir objeto ModificationAction a dict
                    serialized_invalid_actions.append({
                        'action_type': action.action_type.value if hasattr(action.action_type, 'value') else str(action.action_type),
                        'entity_type': action.entity_type,
                        'old_value': action.old_value,
                        'new_value': action.new_value,
                        'confidence': getattr(action, 'confidence', None)
                    })
            
            if len(serialized_invalid_actions) == 1:
                invalid_action = serialized_invalid_actions[0]
                entity_type = invalid_action.get('entity_type')
                valid_for = validation_errors[0].get('valid_for', []) if validation_errors else []
                
                if valid_for:
                    valid_types_text = ' o '.join(valid_for)
                    message = (
                        f"'{entity_type}' no es válido para buscar {search_type}s. "
                        f"Este parámetro se usa para: {valid_types_text}.\n\n"
                        f"¿Querés cambiar a buscar {valid_for[0]}s?"
                    )
                else:
                    message = f"'{entity_type}' no es válido para buscar {search_type}s."
            else:
                invalid_list = ', '.join([f"'{a.get('entity_type')}'" for a in serialized_invalid_actions])
                message = f"Los siguientes parámetros no son válidos para buscar {search_type}s: {invalid_list}."
            
            dispatcher.utter_message(message)
            
            suggestion_data = {
                'suggestion_type': 'invalid_entity_modification',
                'search_type': search_type,
                'invalid_actions': serialized_invalid_actions,  # ✅ Usar versión serializada
                'validation_errors': validation_errors,
                'timestamp': datetime.now().isoformat(),
                'awaiting_response': True
            }
            
            return {
                'type': 'entity_suggestion',
                'suggestion_data': suggestion_data,
                'slot_cleanup_events': []
            }
            
        except Exception as e:
            logger.error(f"[InvalidMod] Error: {e}", exc_info=True)
            dispatcher.utter_message("Hubo un error validando la modificación.")
            return {'type': 'modify_error', 'error': str(e)}

    def _execute_search(self, search_type: str, parameters: Dict[str, str], dispatcher: CollectingDispatcher, 
                       comparison_info: Dict[str, Any] = None, temporal_filters: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        ✅ OPTIMIZADO: Ejecuta búsqueda usando información de grupos y roles
        """
        try:
            logger.info(f"[ExecuteSearch] {search_type} con {len(parameters)} parámetros")
            
            # Validar comparación
            if comparison_info and comparison_info.get('detected'):
                is_valid = self._validate_comparison_coherence(comparison_info, parameters)
                if not is_valid:
                    logger.warning("[ExecuteSearch] Comparación invalidada")
                    comparison_info = None
            
            # Formatear parámetros para mensaje
            formatted_params = self._format_parameters_for_display(parameters)
            
            # Construir mensaje
            if formatted_params:
                criteria_text = ", ".join([f"{k}: {v}" for k, v in formatted_params.items()])
                base_message = f"Buscando {search_type}s con {criteria_text}"
            else:
                base_message = f"Mostrando {search_type}s disponibles"
            
            # Enriquecer con comparación
            enriched_message = base_message
            if comparison_info and comparison_info.get('detected'):
                enriched_message = self._enrich_message_with_comparison(base_message, parameters, comparison_info)
            
            # Enriquecer con filtros temporales
            if temporal_filters:
                temporal_description = self._format_temporal_description(temporal_filters)
                if temporal_description:
                    enriched_message += f" {temporal_description}"
            
            # Preparar JSON message
            json_message = {
                "type": "search_results",
                "search_type": search_type,
                "parameters": self._serialize_parameters(parameters),
                "validated": True,
                "timestamp": datetime.now().isoformat()
            }
            
            # ✅ NUEVO: Agregar información de grupos si está disponible
            if comparison_info:
                nlu_groups = comparison_info.get('nlu_groups', {})
                if nlu_groups:
                    json_message["nlu_groups"] = {
                        group_name: [
                            {
                                'entity': e['entity'],
                                'value': e['value'],
                                'role': e.get('role')
                            }
                            for e in entities
                        ]
                        for group_name, entities in nlu_groups.items()
                    }
                
                grouped_entities = comparison_info.get('grouped_entities', {})
                if grouped_entities:
                    json_message["grouped_filters"] = grouped_entities
            
            if temporal_filters:
                json_message["temporal_filters"] = temporal_filters
            
            # Enviar respuesta
            dispatcher.utter_message(
                text=enriched_message,
                json_message=json_message
            )
            
            logger.info("[ExecuteSearch] Respuesta enviada exitosamente")
            
            return {
                'type': 'search_success',
                'search_type': search_type,
                'parameters': parameters,
                'message': enriched_message,
                'comparison_info': comparison_info,
                'temporal_filters': temporal_filters
            }
            
        except Exception as e:
            logger.error(f"[ExecuteSearch] Error: {e}", exc_info=True)
            dispatcher.utter_message("Ocurrió un error ejecutando la búsqueda.")
            return {'type': 'search_execution_error', 'error': str(e)}

    def _enrich_message_with_comparison(self, base_message: str, parameters: Dict[str, str], 
                                        comparison_info: Dict[str, Any]) -> str:
        """Enriquece mensaje con información de comparación"""
        try:
            if not comparison_info or not comparison_info.get('detected'):
                return base_message
            
            operator = comparison_info.get('operator')
            quantity = comparison_info.get('quantity')
            
            if operator and quantity:
                operator_text = self._get_operator_text(operator)
                comparison_detail = f" ({operator_text} {quantity})"
            else:
                comparison_type = comparison_info.get('type', '')
                if comparison_type:
                    comparison_detail = f" (con filtros de {comparison_type})"
                else:
                    comparison_detail = " (con comparación aplicada)"
            
            return base_message + comparison_detail
            
        except Exception as e:
            logger.error(f"[EnrichMessage] Error: {e}")
            return base_message

    def _get_operator_text(self, operator: str) -> str:
        """Convierte operador a texto legible"""
        operator_mapping = {
            'greater_than': 'más de',
            'less_than': 'menos de',
            'equal_to': 'igual a',
            'different_from': 'diferente de',
            'gt': 'más de',
            'lt': 'menos de',
            'gte': 'al menos',
            'lte': 'hasta',
            'eq': 'igual a'
        }
        return operator_mapping.get(operator, operator)

    def _determine_quantity_usage(self, parameters: Dict[str, str], comparison_info: Dict[str, Any]) -> str:
        """Determina uso de la cantidad"""
        try:
            operator = comparison_info.get('operator')
            
            if operator in ['greater_than', 'less_than', 'gt', 'lt', 'gte', 'lte']:
                return 'comparison'
            elif operator in ['equal_to', 'eq']:
                return 'exact_value'
            else:
                return 'exact_value'
                    
        except Exception as e:
            logger.error(f"[QuantityUsage] Error: {e}")
            return 'exact_value'

    def _format_parameters_for_display(self, parameters: Dict[str, Any]) -> Dict[str, str]:
        """
        ✅ OPTIMIZADO: Formatea parámetros con roles para display
        """
        try:
            formatted = {}
            
            for key, value in parameters.items():
                if isinstance(value, dict) and 'value' in value and 'role' in value:
                    role = value['role']
                    val = value['value']
                    
                    if key == 'estado':
                        role_display = {
                            'nuevo': 'nuevo',
                            'poco_stock': 'poco_stock',
                            'vence_pronto': 'vence_pronto',
                            'en_oferta': 'en_oferta'
                        }.get(role, val)
                        formatted[key] = role_display
                    elif key == 'empresa':
                        formatted[key] = f"{val}" if role == 'proveedor' else f"{val} ({role})"
                    elif key == 'dosis':
                        formatted[key] = f"{val} ({role})" if role != 'unspecified' else val
                    else:
                        formatted[key] = val
                else:
                    formatted[key] = str(value)
            
            return formatted
            
        except Exception as e:
            logger.error(f"[FormatDisplay] Error: {e}")
            return parameters

    def _serialize_parameters(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        ✅ OPTIMIZADO: Serializa parámetros preservando estructura de roles
        """
        try:
            serialized = {}
            
            for key, value in parameters.items():
                if isinstance(value, dict) and 'value' in value and 'role' in value:
                    serialized[key] = {
                        "value": value['value'],
                        "role": value['role']
                    }
                else:
                    serialized[key] = value
            
            return serialized
            
        except Exception as e:
            logger.error(f"[Serialize] Error: {e}")
            return parameters

    def _process_result(self, result: Dict[str, Any], context: Dict[str, Any]) -> List[EventType]:
        """Genera eventos de slot apropiados"""
        try:
            events = []
            result_type = result.get('type')
            
            logger.debug(f"[ProcessResult] Tipo: {result_type}")
            
            if result_type == 'entity_suggestion':
                suggestion_data = result['suggestion_data']
                events.extend([
                    SlotSet("pending_suggestion", suggestion_data),
                    SlotSet("user_engagement_level", "awaiting_confirmation")
                ])
            
            elif result_type == 'parameter_suggestion':
                suggestion_data = result.get('suggestion_data', {})
                events.extend([
                    SlotSet("pending_suggestion", suggestion_data),
                    SlotSet("user_engagement_level", "awaiting_parameters")
                ])
            
            elif result_type == 'search_success':
                search_history = context.get('search_history', [])
                
                history_entry = {
                    'timestamp': datetime.now().isoformat(),
                    'type': result['search_type'],
                    'parameters': result['parameters'],
                    'status': 'completed'
                }
                
                if result.get('comparison_info'):
                    history_entry['comparison_info'] = {
                        'detected': result['comparison_info'].get('detected', False),
                        'type': result['comparison_info'].get('type'),
                        'operator': result['comparison_info'].get('operator')
                    }
                
                search_history.append(history_entry)
                
                events.extend([
                    SlotSet("search_history", search_history),
                    SlotSet("pending_suggestion", None),
                    SlotSet("user_engagement_level", "satisfied")
                ])
                
                logger.info(f"[ProcessResult] Búsqueda exitosa. Historial: {len(search_history)} entradas")
            
            elif result_type in ['validation_error', 'configuration_error', 'search_error', 'modify_error']:
                events.append(SlotSet("user_engagement_level", "needs_help"))
            
            if 'slot_cleanup_events' in result:
                cleanup_events = result['slot_cleanup_events']
                events.extend(cleanup_events)
            
            logger.info(f"[ProcessResult] {len(events)} eventos generados")
            return events
            
        except Exception as e:
            logger.error(f"[ProcessResult] Error: {e}", exc_info=True)
            return [SlotSet("user_engagement_level", "needs_help")]