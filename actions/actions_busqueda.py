import logging
from typing import Any, Dict, List
from datetime import datetime

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, EventType

# Import actualizado - usa el nuevo sistema
from actions.config import (
    config_manager,
    get_intent_config,
    get_lookup_tables,
    get_entities_for_intent,
    validate_entity_value,
    get_entity_suggestions
)
from .conversation_state import ConversationState, SuggestionManager

logger = logging.getLogger(__name__)

class ActionBusquedaSituacion(Action):
    """Action optimizada usando el nuevo sistema de configuración"""
    
    def __init__(self):
        # Ya no necesitas cargar configuración aquí - se hace automáticamente
        pass
    
    def name(self) -> str:
        return "action_busqueda_situacion"
    
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[str, Any]) -> List[EventType]:
        """Punto de entrada principal"""
        try:
            context = ConversationState.get_conversation_context(tracker)
            intent_name = context['current_intent']
            
            logger.info(f"[BusquedaSituacion] Processing intent: {intent_name}")
            
            # Validar que el intent existe en la configuración
            intent_config = get_intent_config()
            if intent_name not in intent_config.get("intents", {}):
                logger.warning(f"Intent desconocido: {intent_name}")
                dispatcher.utter_message("Lo siento, no pude entender tu solicitud.")
                return []
            
            events = []
            
            # Actualizar sentimiento si cambió
            if context['detected_sentiment'] != context['current_sentiment_slot']:
                events.append(SlotSet("user_sentiment", context['detected_sentiment']))
            
            # Procesar según el tipo de intent
            if self._is_completion_intent(intent_name):
                result = self._handle_completion_intent(context, tracker, dispatcher)
            elif self._is_search_intent(intent_name):
                result = self._handle_search_intent(context, tracker, dispatcher)
            else:
                dispatcher.utter_message("¿En qué puedo ayudarte hoy?")
                return events
            
            # Procesar resultado y generar eventos
            events.extend(self._process_result(result, context))
            
            return events
            
        except Exception as e:
            logger.error(f"Error en ActionBusquedaSituacion: {e}")
            dispatcher.utter_message("Ocurrió un error procesando tu solicitud. ¿Puedes intentar nuevamente?")
            return []
    
    def _is_search_intent(self, intent_name: str) -> bool:
        """Determina si es un intent de búsqueda"""
        search_intents = ['buscar_producto', 'buscar_oferta', 'consultar_novedades_producto', 
                         'consultar_novedades_oferta', 'consultar_recomendaciones_producto',
                         'consultar_recomendaciones_oferta']
        return intent_name in search_intents
    
    def _is_completion_intent(self, intent_name: str) -> bool:
        """Determina si es un intent de completar pedido"""
        return intent_name == 'completar_pedido'
    
    def _handle_search_intent(self, context: Dict[str, Any], tracker: Tracker, dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Maneja intents de búsqueda usando el nuevo sistema"""
        intent_name = context['current_intent']
        
        # Obtener entidades válidas desde configuración
        valid_entities = get_entities_for_intent(intent_name)
        if not valid_entities:
            logger.warning(f"No hay entidades configuradas para intent: {intent_name}")
            dispatcher.utter_message("Lo siento, hay un problema con la configuración de búsqueda.")
            return {'type': 'configuration_error'}
        
        # Validar entidades extraídas
        validation_result = self._validate_entities(tracker, valid_entities, dispatcher)
        
        if validation_result['has_suggestions']:
            return {
                'type': 'entity_suggestion',
                'suggestion_data': validation_result['suggestion_data'],
                'search_type': self._get_search_type(intent_name)
            }
        
        if validation_result['has_errors']:
            return {
                'type': 'validation_error',
                'errors': validation_result['errors'],
                'search_type': self._get_search_type(intent_name)
            }
        
        # Verificar completitud
        if validation_result['valid_params']:
            search_type = self._get_search_type(intent_name)
            return self._execute_search(search_type, validation_result['valid_params'], dispatcher)
        else:
            return {
                'type': 'parameter_suggestion',
                'search_type': self._get_search_type(intent_name),
                'message': f"Necesito que especifiques algún criterio de búsqueda como: {', '.join(valid_entities[:3])}"
            }
    
    def _validate_entities(self, tracker: Tracker, valid_entities: List[str], dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Valida entidades usando el nuevo sistema de configuración"""
        entities = tracker.latest_message.get("entities", [])
        
        valid_params = {}
        suggestions = []
        errors = []
        
        for entity in entities:
            entity_type = entity.get("entity")
            entity_value = entity.get("value")
            
            # Verificar que la entidad es válida para este intent
            if not entity_value or entity_type not in valid_entities:
                continue
            
            # Validar usando lookup tables
            if validate_entity_value(entity_type, entity_value):
                # Mapear entidad al nombre del parámetro
                param_name = self._map_entity_to_param(entity_type)
                valid_params[param_name] = entity_value
            else:
                # Buscar sugerencias
                suggestions_list = get_entity_suggestions(entity_type, entity_value)
                
                if suggestions_list:
                    suggestion_text = suggestions_list[0]
                    message = f"'{entity_value}' no es válido. ¿Te refieres a '{suggestion_text}'?"
                    
                    suggestion_data = SuggestionManager.create_entity_suggestion(
                        entity_value, entity_type, suggestion_text, {'intent': tracker.get_intent_of_latest_message()}
                    )
                    
                    suggestions.append(suggestion_data)
                    dispatcher.utter_message(message)
                else:
                    error_msg = f"'{entity_value}' no es un {entity_type} válido."
                    errors.append(error_msg)
                    dispatcher.utter_message(error_msg)
        
        return {
            'valid_params': valid_params,
            'has_suggestions': len(suggestions) > 0,
            'suggestion_data': suggestions[0] if suggestions else None,
            'has_errors': len(errors) > 0,
            'errors': errors
        }
    
    def _map_entity_to_param(self, entity_type: str) -> str:
        """Mapea tipos de entidad a nombres de parámetros"""
        # Mapeo desde configuración o reglas de negocio
        mapping = {
            'producto': 'nombre',
            'compuesto': 'ingrediente_activo',
            'categoria': 'categoria',
            'proveedor': 'proveedor',
            'ingrediente_activo': 'ingrediente_activo',
            'animal': 'animal',
            'dosis': 'dosis',
            'cantidad': 'cantidad'
        }
        return mapping.get(entity_type, entity_type)
    
    def _handle_completion_intent(self, context: Dict[str, Any], tracker: Tracker, dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Maneja intent de completar pedido"""
        pending_suggestion = context.get('pending_suggestion', {})
        
        if not pending_suggestion:
            dispatcher.utter_message("No hay ninguna búsqueda pendiente para completar.")
            return {'type': 'no_completion_needed'}
        
        # Obtener nuevos parámetros
        search_type = pending_suggestion.get('search_type', 'producto')
        intent_name = f"buscar_{search_type}"
        
        valid_entities = get_entities_for_intent(intent_name)
        validation_result = self._validate_entities(tracker, valid_entities, dispatcher)
        
        if validation_result['valid_params']:
            # Combinar con parámetros anteriores
            previous_params = pending_suggestion.get('current_parameters', {})
            merged_params = {**previous_params, **validation_result['valid_params']}
            
            return self._execute_search(search_type, merged_params, dispatcher)
        else:
            dispatcher.utter_message("Necesito que especifiques algún criterio adicional.")
            return {'type': 'completion_failed'}
    
    def _execute_search(self, search_type: str, parameters: Dict[str, str], dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Ejecuta búsqueda con parámetros validados"""
        if parameters:
            criteria_text = ", ".join([f"{k}: {v}" for k, v in parameters.items()])
            message = f"Buscando {search_type}s con {criteria_text}"
        else:
            message = f"Mostrando {search_type}s disponibles"
        
        # Respuesta estructurada
        dispatcher.utter_message(
            text=message,
            json_message={
                "type": "search_results",
                "search_type": search_type,
                "parameters": parameters,
                "validated": True,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        return {
            'type': 'search_success',
            'search_type': search_type,
            'parameters': parameters,
            'message': message
        }
    
    def _get_search_type(self, intent_name: str) -> str:
        """Extrae tipo de búsqueda del nombre del intent"""
        if "oferta" in intent_name:
            return "oferta"
        elif "producto" in intent_name:
            return "producto"
        elif "recomendacion" in intent_name:
            return "recomendacion"
        elif "novedad" in intent_name:
            return "novedad"
        else:
            return "producto"  # fallback
    
    def _process_result(self, result: Dict[str, Any], context: Dict[str, Any]) -> List[EventType]:
        """Genera eventos de slot apropiados"""
        events = []
        result_type = result.get('type')
        
        if result_type == 'entity_suggestion':
            events.extend([
                SlotSet("pending_suggestion", result['suggestion_data']),
                SlotSet("user_engagement_level", "awaiting_confirmation")
            ])
        
        elif result_type == 'parameter_suggestion':
            events.extend([
                SlotSet("pending_suggestion", result.get('suggestion_data', {})),
                SlotSet("user_engagement_level", "awaiting_parameters")
            ])
        
        elif result_type == 'search_success':
            # Actualizar historial
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
        
        elif result_type in ['validation_error', 'configuration_error']:
            events.append(SlotSet("user_engagement_level", "needs_help"))
        
        return events