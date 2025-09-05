import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, EventType

from actions.config import INTENT_CONFIG, LOOKUP_TABLES, normalize_text
from scripts.config_loader import ConfigLoader
from .conversation_state import ConversationState, SuggestionManager

logger = logging.getLogger(__name__)

class ActionBusquedaSituacion(Action):
    """Action optimizada de búsqueda usando configuración centralizada"""
    
    def __init__(self):
        # Cargar configuración una sola vez
        self.config = INTENT_CONFIG
        self.lookup_tables = LOOKUP_TABLES
        self.entity_config = self.config.get("entities", {})
        self.validation_handler = UnifiedValidationHandler(self.config, self.lookup_tables)
    
    def name(self) -> str:
        return "action_busqueda_situacion"
    
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[str, Any]) -> List[EventType]:
        """Punto de entrada principal"""
        context = ConversationState.get_conversation_context(tracker)
        
        logger.info(f"[BusquedaSituacion] Intent: {context['current_intent']}")
        
        events = []
        
        # Actualizar sentimiento si es necesario
        if context['detected_sentiment'] != context['current_sentiment_slot']:
            events.append(SlotSet("user_sentiment", context['detected_sentiment']))
        
        # Procesar según el tipo de intent
        if context['is_completion_intent']:
            result = self._handle_completion_intent(context, tracker, dispatcher)
        elif context['is_search_intent']:
            result = self._handle_search_intent(context, tracker, dispatcher)
        else:
            dispatcher.utter_message("¿En qué puedo ayudarte hoy?")
            return events
        
        # Procesar resultado y actualizar slots
        events.extend(self._process_result(result, context))
        
        return events
    
    def _handle_search_intent(self, context: Dict[str, Any], tracker: Tracker, dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Maneja intents de búsqueda"""
        intent_name = context['current_intent']
        search_type = self._get_search_type(intent_name)
        
        # Validar entidades extraídas
        validation_result = self.validation_handler.validate_entities_for_intent(
            tracker, intent_name, dispatcher
        )
        
        if validation_result['has_suggestions']:
            return {
                'type': 'entity_suggestion',
                'suggestion_data': validation_result['suggestion_data'],
                'search_type': search_type
            }
        
        if validation_result['has_errors']:
            return {
                'type': 'validation_error',
                'errors': validation_result['errors'],
                'search_type': search_type
            }
        
        # Verificar completitud según reglas del config
        completeness_check = self.validation_handler.check_parameter_completeness(
            intent_name, validation_result['valid_params']
        )
        
        if completeness_check['is_complete']:
            return self._execute_search(search_type, validation_result['valid_params'], dispatcher)
        else:
            return {
                'type': 'parameter_suggestion',
                'suggestion_data': completeness_check['suggestion_data'],
                'search_type': search_type,
                'current_params': validation_result['valid_params']
            }
    
    def _handle_completion_intent(self, context: Dict[str, Any], tracker: Tracker, dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Maneja intent de completar_pedido"""
        pending_suggestion = context.get('pending_suggestion', {})
        
        if not pending_suggestion or pending_suggestion.get('suggestion_type') != 'missing_parameters':
            dispatcher.utter_message("No hay ninguna búsqueda pendiente para completar.")
            return {'type': 'no_completion_needed'}
        
        # Extraer nuevos parámetros para completar la búsqueda
        search_type = pending_suggestion.get('search_type', 'producto')
        intent_name = f"buscar_{search_type}"
        
        validation_result = self.validation_handler.validate_entities_for_intent(
            tracker, intent_name, dispatcher
        )
        
        if validation_result['valid_params']:
            # Combinar parámetros previos con nuevos
            previous_params = pending_suggestion.get('current_parameters', {})
            merged_params = {**previous_params, **validation_result['valid_params']}
            
            return self._execute_search(search_type, merged_params, dispatcher)
        else:
            dispatcher.utter_message("Necesito que especifiques algún criterio adicional.")
            return {'type': 'completion_failed'}
    
    def _execute_search(self, search_type: str, parameters: Dict[str, str], dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Ejecuta la búsqueda con parámetros validados"""
        # Crear mensaje descriptivo
        if parameters:
            criteria_list = [f"{key}: {value}" for key, value in parameters.items()]
            message = f"Buscando {search_type}s con {', '.join(criteria_list)}"
        else:
            message = f"Mostrando {search_type}s disponibles"
        
        # Enviar respuesta estructurada al frontend
        dispatcher.utter_message(
            text=message,
            json_message={
                "type": "search_results",
                "search_type": search_type,
                "parameters": parameters,
                "validated": True
            }
        )
        
        return {
            'type': 'search_success',
            'search_type': search_type,
            'parameters': parameters,
            'message': message
        }
    
    def _process_result(self, result: Dict[str, Any], context: Dict[str, Any]) -> List[EventType]:
        """Procesa el resultado y genera eventos de slot apropiados"""
        events = []
        result_type = result.get('type')
        
        if result_type == 'entity_suggestion':
            events.extend([
                SlotSet("pending_suggestion", result['suggestion_data']),
                SlotSet("user_engagement_level", "awaiting_confirmation")
            ])
        
        elif result_type == 'parameter_suggestion':
            events.extend([
                SlotSet("pending_suggestion", result['suggestion_data']),
                SlotSet("user_engagement_level", "awaiting_parameters")
            ])
        
        elif result_type == 'search_success':
            # Actualizar historial y limpiar sugerencias
            search_history = context.get('search_history', [])
            search_history.append({
                'timestamp': datetime.now().isoformat(),
                'type': result['search_type'],
                'parameters': result['parameters'],
                'status': 'completed'
            })
            
            events.extend([
                SlotSet("search_history", search_history),
                SlotSet("pending_suggestion", None),
                SlotSet("user_engagement_level", "satisfied")
            ])
        
        return events
    
    def _get_search_type(self, intent_name: str) -> str:
        """Extrae tipo de búsqueda desde la configuración"""
        # Leer desde config en lugar de hardcodear
        intent_config = self.config.get("intents", {}).get(intent_name, {})
        
        # Mapeo basado en configuración
        if intent_name == "buscar_oferta":
            return "oferta"
        elif intent_name == "buscar_producto":
            return "producto"
        else:
            # Fallback desde la configuración
            return intent_config.get("search_type", "producto")


class UnifiedValidationHandler:
    """Manejador unificado de validación usando configuración centralizada"""
    
    def __init__(self, config: Dict[str, Any], lookup_tables: Dict[str, List[str]]):
        self.config = config
        self.lookup_tables = lookup_tables
        self.entities_config = config.get("entities", {})
        
        # Generar mapeos dinámicamente desde la configuración
        self.entity_mappings = self._build_entity_mappings()
        self.entity_display_names = self._build_display_names()
    
    def _build_entity_mappings(self) -> Dict[str, str]:
        """Construye mapeos de entidades desde la configuración"""
        mappings = {}
        
        for entity_name, entity_config in self.entities_config.items():
            # Usar el nombre de la entidad como clave por defecto
            mapped_name = entity_name
            
            # Aplicar reglas específicas desde la configuración
            if entity_name in ["producto", "producto_nombre", "nombre_producto"]:
                mapped_name = "nombre"
            elif entity_name == "compuesto":
                mapped_name = "ingrediente_activo"
            
            mappings[entity_name] = mapped_name
        
        return mappings
    
    def _build_display_names(self) -> Dict[str, str]:
        """Construye nombres para mostrar desde la configuración"""
        display_names = {}
        
        for entity_name in self.entities_config.keys():
            # Nombres legibles para el usuario
            if entity_name == "ingrediente_activo":
                display_names[entity_name] = "ingrediente activo"
            elif entity_name == "categoria":
                display_names[entity_name] = "categoría"
            else:
                display_names[entity_name] = entity_name.replace("_", " ")
        
        return display_names
    
    def validate_entities_for_intent(self, tracker: Tracker, intent_name: str, dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Validación unificada de entidades para un intent específico"""
        entities = tracker.latest_message.get("entities", [])
        
        # Obtener entidades válidas desde configuración
        valid_entities = self._get_valid_entities_for_intent(intent_name)
        
        valid_params = {}
        validation_errors = []
        suggestions = []
        
        for entity in entities:
            entity_type = entity.get("entity")
            entity_value = entity.get("value")
            
            if not entity_value or entity_type not in valid_entities:
                continue
            
            # Validar usando lookup tables
            validation_result = self._validate_single_entity(entity_value, entity_type, intent_name)
            
            if validation_result['is_valid']:
                mapped_key = self.entity_mappings.get(entity_type, entity_type)
                valid_params[mapped_key] = entity_value
            
            elif validation_result.get('has_suggestion'):
                suggestions.append(validation_result['suggestion_data'])
                dispatcher.utter_message(validation_result['message'])
            
            else:
                validation_errors.append(validation_result['message'])
                dispatcher.utter_message(validation_result['message'])
        
        return {
            'valid_params': valid_params,
            'has_suggestions': len(suggestions) > 0,
            'suggestion_data': suggestions[0] if suggestions else None,
            'has_errors': len(validation_errors) > 0,
            'errors': validation_errors
        }
    
    def _validate_single_entity(self, entity_value: str, entity_type: str, intent_name: str) -> Dict[str, Any]:
        """Valida una entidad individual"""
        # Obtener lookup key (mapear compuesto -> ingrediente_activo, etc.)
        lookup_key = entity_type if entity_type != "compuesto" else "ingrediente_activo"
        
        # Si no hay lookup table, aceptar como válida
        if lookup_key not in self.lookup_tables:
            return {'is_valid': True}
        
        lookup_values = self.lookup_tables[lookup_key]
        normalized_value = normalize_text(entity_value)
        normalized_lookup = [normalize_text(v) for v in lookup_values]
        
        # Validación exacta
        if normalized_value in normalized_lookup:
            return {'is_valid': True}
        
        # Buscar sugerencias usando difflib
        import difflib
        suggestions = difflib.get_close_matches(
            normalized_value, normalized_lookup, n=1, cutoff=0.6
        )
        
        if suggestions:
            # Obtener valor original
            original_suggestion = None
            for original in lookup_values:
                if normalize_text(original) == suggestions[0]:
                    original_suggestion = original
                    break
            
            if original_suggestion:
                display_name = self.entity_display_names.get(entity_type, entity_type)
                message = f"🔍 '{entity_value}' no es un {display_name} válido. ¿Te refieres a '{original_suggestion}'?"
                
                suggestion_data = SuggestionManager.create_entity_suggestion(
                    entity_value, entity_type, original_suggestion, {'intent': intent_name}
                )
                
                return {
                    'is_valid': False,
                    'has_suggestion': True,
                    'message': message,
                    'suggestion_data': suggestion_data
                }
        
        # Sin sugerencias válidas
        display_name = self.entity_display_names.get(entity_type, entity_type)
        return {
            'is_valid': False,
            'has_suggestion': False,
            'message': f"❌ '{entity_value}' no es un {display_name} válido."
        }
    
    def check_parameter_completeness(self, intent_name: str, params: Dict[str, str]) -> Dict[str, Any]:
        """Verifica completitud de parámetros usando reglas del config"""
        intent_config = self.config.get("intents", {}).get(intent_name, {})
        validation_rules = intent_config.get("validation_rules", {})
        
        if not validation_rules:
            # Si no hay reglas específicas, cualquier parámetro es suficiente
            is_complete = len(params) > 0
        else:
            required_entities = validation_rules.get("requires_at_least_one", [])
            is_complete = any(self.entity_mappings.get(entity, entity) in params for entity in required_entities)
        
        if is_complete:
            return {'is_complete': True}
        
        # Crear sugerencia de parámetros faltantes
        criteria = self._get_readable_criteria(intent_name)
        search_type = "producto" if "producto" in intent_name else "oferta"
        
        suggestion_data = SuggestionManager.create_parameter_suggestion(
            search_type, intent_name, criteria, params
        )
        
        return {
            'is_complete': False,
            'suggestion_data': suggestion_data,
            'message': f"Necesito que especifiques: {criteria}"
        }
    
    def _get_valid_entities_for_intent(self, intent_name: str) -> List[str]:
        """Obtiene entidades válidas desde la configuración"""
        intent_config = self.config.get("intents", {}).get(intent_name, {})
        return intent_config.get("entities", [])
    
    def _get_readable_criteria(self, intent_name: str) -> str:
        """Genera criterios legibles desde la configuración"""
        valid_entities = self._get_valid_entities_for_intent(intent_name)
        
        readable_criteria = []
        for entity in valid_entities:
            display_name = self.entity_display_names.get(entity, entity)
            readable_criteria.append(display_name)
        
        if len(readable_criteria) > 1:
            return ", ".join(readable_criteria[:-1]) + " o " + readable_criteria[-1]
        elif readable_criteria:
            return readable_criteria[0]
        else:
            return "algún criterio de búsqueda"