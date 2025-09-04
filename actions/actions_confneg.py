# 🔹 ACTION MEJORADA PARA CONFIRMACIONES - SISTEMA UNIFICADO
from asyncio.log import logger
from random import choice
from typing import Any, Dict, List
from xml.dom.minidom import Text
from datetime import datetime

from actions.actions_busqueda import EntityValidationHandler, EnhancedSearchHandler
from actions.helpers import get_intent_info
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, EventType
from .conversation_state import ConversationState, SuggestionManager

class ActionConfNegAgradecer(Action):
    """
    Maneja confirmaciones, negaciones y agradecimientos con sistema unificado de sugerencias
    (reemplaza el concepto de pedido_incompleto)
    """
    
    def name(self) -> Text:
        return "action_conf_neg_agradecer"
    
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        context = ConversationState.get_conversation_context(tracker)
        current_intent = context['current_intent']
        user_msg = context['user_message']
        
        logger.info(f"[ConfNegAgradecer] Intent: {current_intent}, Awaiting suggestion: {context['awaiting_suggestion_response']}")
        
        events = []
        
        # 🔹 PRIORIDAD 1: Manejar respuestas a sugerencias pendientes
        if context['awaiting_suggestion_response']:
            pending_suggestion = context.get('pending_suggestion', {})
            suggestion_type = pending_suggestion.get('suggestion_type', '')
            
            # Detectar si es afirmativo o negativo
            is_affirmative = (current_intent == "afirmar" or 
                            any(word in user_msg.lower() for word in ["sí", "si", "ok", "dale", "perfecto", "correcto", "exacto", "ese", "esa", "claro"]))
            is_negative = (current_intent == "denegar" or 
                         any(word in user_msg.lower() for word in ["no", "nada", "incorrecto", "otro", "diferente"]))
            
            logger.info(f"[ConfNegAgradecer] Procesando sugerencia - Type: {suggestion_type}, Affirmative: {is_affirmative}, Negative: {is_negative}")
            
            if is_affirmative:
                if suggestion_type == 'entity_correction':
                    # Usuario acepta sugerencia de entidad
                    corrected_value = pending_suggestion['suggestions'][0]
                    entity_type = pending_suggestion['entity_type']
                    
                    dispatcher.utter_message(f"¡Perfecto! Usando '{corrected_value}' como {entity_type}.")
                    
                    # EJECUTAR BÚSQUEDA CON EL VALOR CORREGIDO
                    search_result = self._execute_search_with_corrected_entity(
                        {'value': corrected_value, 'type': entity_type}, context, tracker, dispatcher
                    )
                    
                    events.extend([
                        SlotSet("pending_suggestion", None),
                        SlotSet("user_engagement_level", "satisfied")
                    ])
                    
                    if search_result['success']:
                        events.extend(self._create_search_completion_events(search_result, context))
                    
                elif suggestion_type == 'type_correction':
                    # Usuario acepta corrección de tipo
                    original_value = pending_suggestion['original_value']
                    correct_type = pending_suggestion['correct_type']
                    
                    dispatcher.utter_message(f"¡Entendido! Buscando '{original_value}' como {correct_type}.")
                    
                    # EJECUTAR BÚSQUEDA CON EL TIPO CORREGIDO
                    search_result = self._execute_search_with_corrected_entity(
                        {'value': original_value, 'type': correct_type}, context, tracker, dispatcher
                    )
                    
                    events.extend([
                        SlotSet("pending_suggestion", None),
                        SlotSet("user_engagement_level", "satisfied")
                    ])
                    
                    if search_result['success']:
                        events.extend(self._create_search_completion_events(search_result, context))
                
                elif suggestion_type == 'missing_parameters':
                    # Para parámetros faltantes, el usuario está confirmando que quiere continuar
                    dispatcher.utter_message("¡Perfecto! ¿Qué información adicional puedes proporcionarme?")
                    events.append(SlotSet("user_engagement_level", "engaged"))
                
                return events
                    
            elif is_negative:
                # Usuario rechaza la sugerencia
                if suggestion_type in ['entity_correction', 'type_correction']:
                    dispatcher.utter_message("Entendido. ¿Podrías especificar el nombre correcto o intentar con otros criterios de búsqueda?")
                else:
                    dispatcher.utter_message("Entendido. ¿Hay algo más en lo que pueda ayudarte?")
                
                events.extend([
                    SlotSet("pending_suggestion", None),
                    SlotSet("user_engagement_level", "needs_help")
                ])
                
                return events
            
            else:
                # Respuesta no clara, pedir clarificación
                self._handle_unclear_suggestion_response(context, dispatcher)
                return events
        
        # 🔹 PRIORIDAD 2: Sin contexto específico - usar responses del config
        intent_info = get_intent_info(current_intent)
        responses = intent_info.get("responses", [])
        
        if responses:
            if isinstance(responses, list) and responses:
                message_data = choice(responses)
                message = message_data.get("text", str(message_data)) if isinstance(message_data, dict) else str(message_data)
            elif isinstance(responses, dict) and "text" in responses:
                message = responses["text"]
            else:
                message = str(responses)
            
            dispatcher.utter_message(text=message)
        else:
            # Fallback específico por intent
            fallback_messages = {
                "agradecimiento": "¡De nada! Siempre estoy aquí para ayudarte.",
                "afirmar": "Perfecto. ¿En qué puedo ayudarte hoy?",
                "denegar": "No hay problema. ¿Hay algo más en lo que pueda asistirte?"
            }
            message = fallback_messages.get(current_intent, "¡Gracias! Siempre estoy aquí si cambias de opinión.")
            dispatcher.utter_message(text=message)
        
        return events
    
    def _execute_search_with_corrected_entity(self, corrected_entity: Dict[str, str], 
                                            context: Dict[str, Any], tracker: Tracker,
                                            dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """
        Ejecuta búsqueda usando la entidad corregida
        """
        try:
            # Obtener contexto de búsqueda original
            pending_suggestion = context.get('pending_suggestion', {})
            search_context = pending_suggestion.get('search_context', {})
            original_intent = search_context.get('intent', 'buscar_producto')
            
            # Determinar tipo de búsqueda
            search_type = search_context.get('search_type', 'producto')
            
            # Mapear entidad corregida a parámetros de búsqueda
            entity_mappings = {
                "producto": "nombre",
                "producto_nombre": "nombre",
                "proveedor": "proveedor",
                "categoria": "categoria",
                "ingrediente_activo": "ingrediente_activo",
                "compuesto": "ingrediente_activo",
                "dosis": "dosis",
                "cantidad": "cantidad"
            }
            
            param_key = entity_mappings.get(corrected_entity['type'], corrected_entity['type'])
            search_params = {param_key: corrected_entity['value']}
            
            # Crear mensaje para el usuario
            user_message = f"Buscando {search_type}s con {param_key}: {corrected_entity['value']}..."
            
            # Enviar respuesta al frontend
            dispatcher.utter_message(
                text=user_message,
                json_message={
                    "type": "search",
                    "search_type": search_type,
                    "parameters": search_params,
                    "message": user_message,
                    "validated": True,
                    "corrected_from_suggestion": True
                }
            )
            
            logger.info(f"[ConfNegAgradecer] Búsqueda ejecutada con entidad corregida: {search_params}")
            
            return {
                'success': True,
                'search_type': search_type,
                'parameters': search_params,
                'message': user_message
            }
            
        except Exception as e:
            logger.error(f"[ConfNegAgradecer] Error ejecutando búsqueda con entidad corregida: {e}", exc_info=True)
            dispatcher.utter_message("Hubo un error procesando tu búsqueda. Inténtalo de nuevo.")
            return {'success': False}
    
    def _create_search_completion_events(self, search_result: Dict[str, Any], 
                                       context: Dict[str, Any]) -> List[EventType]:
        """
        Crea eventos para completar una búsqueda exitosa
        """
        events = []
        
        # Agregar a historial de búsquedas
        search_history = context.get('search_history', [])
        search_history.append({
            'timestamp': datetime.now().isoformat(),
            'type': search_result['search_type'],
            'parameters': search_result['parameters'],
            'status': 'completed_with_suggestion'
        })
        
        events.append(SlotSet("search_history", search_history))
        
        return events
    
    def _handle_unclear_suggestion_response(self, context: Dict[str, Any], 
                                          dispatcher: CollectingDispatcher):
        """
        Maneja respuestas poco claras a sugerencias
        """
        pending = context.get('pending_suggestion', {})
        suggestion_type = pending.get('suggestion_type', '')
        
        if suggestion_type == 'entity_correction':
            suggestions = pending.get('suggestions', [])
            if suggestions:
                dispatcher.utter_message(f"No estoy seguro de tu respuesta. ¿Te refieres a '{suggestions[0]}'? Responde sí o no.")
            else:
                dispatcher.utter_message("No entendí tu respuesta. Responde sí o no.")
                
        elif suggestion_type == 'type_correction':
            correct_type = pending.get('correct_type', '')
            original_value = pending.get('original_value', '')
            dispatcher.utter_message(f"No estoy seguro de tu respuesta. ¿Quieres buscar '{original_value}' como {correct_type}? Responde sí o no.")
            
        elif suggestion_type == 'missing_parameters':
            criteria = pending.get('required_criteria', '')
            search_type = pending.get('search_type', '')
            dispatcher.utter_message(f"Para buscar {search_type}s necesito que especifiques: {criteria}. ¿Qué información puedes darme?")
    
    def _should_clear_suggestion_on_topic_change(self, context: Dict[str, Any]) -> bool:
        """
        Determina si se debe limpiar la sugerencia por cambio de tema
        (Esta lógica ahora está en ActionBusquedaSituacion)
        """
        return False