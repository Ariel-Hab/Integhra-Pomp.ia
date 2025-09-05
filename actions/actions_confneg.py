# 🔹 ACTION MEJORADA PARA CONFIRMACIONES - SISTEMA UNIFICADO ROBUSTO
import logging
from random import choice
from typing import Any, Dict, List
from datetime import datetime

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, EventType

from .conversation_state import ConversationState, SuggestionManager, get_slot_safely
from .helpers import get_intent_info

logger = logging.getLogger(__name__)

class ActionConfNegAgradecer(Action):
    """
    Maneja confirmaciones, negaciones y agradecimientos con sistema unificado de sugerencias
    Versión robusta que maneja errores y slots faltantes graciosamente
    """
    
    def name(self) -> str:
        return "action_conf_neg_agradecer"
    
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[str, Any]) -> List[EventType]:
        try:
            context = ConversationState.get_conversation_context(tracker)
            current_intent = context['current_intent']
            user_msg = context['user_message']
            
            logger.info(f"[ConfNegAgradecer] Intent: {current_intent}, Awaiting suggestion: {context['awaiting_suggestion_response']}")
            
            events = []
            
            # 🔹 PRIORIDAD 1: Manejar respuestas a sugerencias pendientes
            if context['awaiting_suggestion_response']:
                suggestion_result = self._handle_pending_suggestions(context, current_intent, user_msg, tracker, dispatcher)
                events.extend(suggestion_result['events'])
                
                # Si se manejó una sugerencia, retornar inmediatamente
                if suggestion_result['handled']:
                    return events
            
            # 🔹 PRIORIDAD 2: Manejar sistema obsoleto si existe
            if context.get('has_obsolete_slots', False):
                migration_result = self._handle_obsolete_system_migration(tracker, dispatcher)
                events.extend(migration_result['events'])
                
                if migration_result['migrated']:
                    return events
            
            # 🔹 PRIORIDAD 3: Respuestas estándar según configuración
            standard_response_events = self._handle_standard_responses(current_intent, dispatcher)
            events.extend(standard_response_events)
            
            return events
            
        except Exception as e:
            logger.error(f"Error en ActionConfNegAgradecer: {e}", exc_info=True)
            dispatcher.utter_message("Disculpa, hubo un error procesando tu respuesta. ¿Puedes intentar nuevamente?")
            return [SlotSet("user_engagement_level", "needs_help")]
    
    def _handle_pending_suggestions(self, context: Dict[str, Any], current_intent: str, 
                                  user_msg: str, tracker: Tracker, 
                                  dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Maneja sugerencias pendientes de forma robusta"""
        try:
            pending_suggestion = context.get('pending_suggestion', {})
            
            # Validar que la sugerencia sea válida
            validation_result = SuggestionManager.validate_suggestion_data(pending_suggestion)
            if not validation_result['valid']:
                logger.warning(f"Sugerencia inválida: {validation_result}")
                return {
                    'handled': False,
                    'events': [SlotSet("pending_suggestion", None)]
                }
            
            suggestion_type = pending_suggestion.get('suggestion_type', '')
            
            # Detectar si es afirmativo o negativo
            is_affirmative = self._detect_affirmative_response(current_intent, user_msg)
            is_negative = self._detect_negative_response(current_intent, user_msg)
            
            logger.info(f"[ConfNegAgradecer] Procesando sugerencia - Type: {suggestion_type}, Affirmative: {is_affirmative}, Negative: {is_negative}")
            
            if is_affirmative:
                return self._handle_affirmative_suggestion_response(pending_suggestion, context, tracker, dispatcher)
            elif is_negative:
                return self._handle_negative_suggestion_response(pending_suggestion, dispatcher)
            else:
                return self._handle_unclear_suggestion_response(pending_suggestion, dispatcher)
                
        except Exception as e:
            logger.error(f"Error manejando sugerencias pendientes: {e}", exc_info=True)
            return {
                'handled': False,
                'events': [
                    SlotSet("pending_suggestion", None),
                    SlotSet("user_engagement_level", "needs_help")
                ]
            }
    
    def _detect_affirmative_response(self, current_intent: str, user_msg: str) -> bool:
        """Detecta respuestas afirmativas con múltiples patrones"""
        if current_intent == "afirmar":
            return True
        
        affirmative_patterns = [
            "sí", "si", "ok", "dale", "perfecto", "correcto", "exacto", "ese", "esa", 
            "claro", "muy bien", "está bien", "bueno", "ya", "confirmo", "acepto",
            "genial", "excelente", "por supuesto", "desde luego", "efectivamente"
        ]
        
        user_lower = user_msg.lower().strip()
        return any(pattern in user_lower for pattern in affirmative_patterns)
    
    def _detect_negative_response(self, current_intent: str, user_msg: str) -> bool:
        """Detecta respuestas negativas con múltiples patrones"""
        if current_intent == "denegar":
            return True
        
        negative_patterns = [
            "no", "nada", "incorrecto", "otro", "diferente", "mal", "error", 
            "cancelar", "salir", "cambiar", "rechazar", "para nada", "jamás",
            "nunca", "ni loco", "de ninguna manera"
        ]
        
        user_lower = user_msg.lower().strip()
        return any(pattern in user_lower for pattern in negative_patterns)
    
    def _handle_affirmative_suggestion_response(self, pending_suggestion: Dict[str, Any], 
                                              context: Dict[str, Any], tracker: Tracker,
                                              dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Maneja respuestas afirmativas a sugerencias"""
        suggestion_type = pending_suggestion.get('suggestion_type', '')
        events = []
        
        try:
            if suggestion_type == 'entity_correction':
                # Usuario acepta sugerencia de entidad
                corrected_value = pending_suggestion.get('suggestions', [''])[0]
                entity_type = pending_suggestion.get('entity_type', '')
                
                if corrected_value and entity_type:
                    dispatcher.utter_message(f"¡Perfecto! Usando '{corrected_value}' como {entity_type}.")
                    
                    # Ejecutar búsqueda con el valor corregido
                    search_result = self._execute_search_with_corrected_entity(
                        {'value': corrected_value, 'type': entity_type}, 
                        context, tracker, dispatcher
                    )
                    
                    if search_result['success']:
                        events.extend(self._create_search_completion_events(search_result, context))
                else:
                    dispatcher.utter_message("Hubo un problema con la sugerencia. ¿Podrías intentar nuevamente?")
            
            elif suggestion_type == 'type_correction':
                # Usuario acepta corrección de tipo
                original_value = pending_suggestion.get('original_value', '')
                correct_type = pending_suggestion.get('correct_type', '')
                
                if original_value and correct_type:
                    dispatcher.utter_message(f"¡Entendido! Buscando '{original_value}' como {correct_type}.")
                    
                    # Ejecutar búsqueda con el tipo corregido
                    search_result = self._execute_search_with_corrected_entity(
                        {'value': original_value, 'type': correct_type}, 
                        context, tracker, dispatcher
                    )
                    
                    if search_result['success']:
                        events.extend(self._create_search_completion_events(search_result, context))
                else:
                    dispatcher.utter_message("Hubo un problema con la corrección. ¿Podrías intentar nuevamente?")
            
            elif suggestion_type == 'missing_parameters':
                # Para parámetros faltantes, el usuario confirma que quiere continuar
                criteria = pending_suggestion.get('required_criteria', 'información adicional')
                dispatcher.utter_message(f"¡Perfecto! ¿Qué {criteria} puedes proporcionarme?")
                events.append(SlotSet("user_engagement_level", "engaged"))
            
            # Limpiar sugerencia pendiente
            events.extend([
                SlotSet("pending_suggestion", None),
                SlotSet("user_engagement_level", "satisfied")
            ])
            
            return {'handled': True, 'events': events}
            
        except Exception as e:
            logger.error(f"Error manejando respuesta afirmativa: {e}", exc_info=True)
            dispatcher.utter_message("Hubo un error procesando tu confirmación. ¿Puedes intentar nuevamente?")
            return {
                'handled': True,
                'events': [
                    SlotSet("pending_suggestion", None),
                    SlotSet("user_engagement_level", "needs_help")
                ]
            }
    
    def _handle_negative_suggestion_response(self, pending_suggestion: Dict[str, Any], 
                                           dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Maneja respuestas negativas a sugerencias"""
        suggestion_type = pending_suggestion.get('suggestion_type', '')
        
        try:
            if suggestion_type in ['entity_correction', 'type_correction']:
                dispatcher.utter_message("Entendido. ¿Podrías especificar el nombre correcto o intentar con otros criterios de búsqueda?")
            else:
                dispatcher.utter_message("Entendido. ¿Hay algo más en lo que pueda ayudarte?")
            
            return {
                'handled': True,
                'events': [
                    SlotSet("pending_suggestion", None),
                    SlotSet("user_engagement_level", "needs_help")
                ]
            }
            
        except Exception as e:
            logger.error(f"Error manejando respuesta negativa: {e}")
            return {
                'handled': True,
                'events': [SlotSet("pending_suggestion", None)]
            }
    
    def _handle_unclear_suggestion_response(self, pending_suggestion: Dict[str, Any], 
                                          dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Maneja respuestas poco claras a sugerencias"""
        suggestion_type = pending_suggestion.get('suggestion_type', '')
        
        try:
            if suggestion_type == 'entity_correction':
                suggestions = pending_suggestion.get('suggestions', [])
                if suggestions:
                    dispatcher.utter_message(f"No estoy seguro de tu respuesta. ¿Te refieres a '{suggestions[0]}'? Responde sí o no.")
                else:
                    dispatcher.utter_message("No entendí tu respuesta. Responde sí o no.")
                    
            elif suggestion_type == 'type_correction':
                correct_type = pending_suggestion.get('correct_type', '')
                original_value = pending_suggestion.get('original_value', '')
                dispatcher.utter_message(f"No estoy seguro de tu respuesta. ¿Quieres buscar '{original_value}' como {correct_type}? Responde sí o no.")
                
            elif suggestion_type == 'missing_parameters':
                criteria = pending_suggestion.get('required_criteria', '')
                search_type = pending_suggestion.get('search_type', '')
                dispatcher.utter_message(f"Para buscar {search_type}s necesito que especifiques: {criteria}. ¿Qué información puedes darme?")
            
            return {'handled': True, 'events': []}
            
        except Exception as e:
            logger.error(f"Error manejando respuesta poco clara: {e}")
            dispatcher.utter_message("No entendí tu respuesta. ¿Podrías ser más específico?")
            return {'handled': True, 'events': []}
    
    def _execute_search_with_corrected_entity(self, corrected_entity: Dict[str, str], 
                                            context: Dict[str, Any], tracker: Tracker,
                                            dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Ejecuta búsqueda usando la entidad corregida"""
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
                "cantidad": "cantidad",
                "animal": "animal"
            }
            
            param_key = entity_mappings.get(corrected_entity['type'], corrected_entity['type'])
            search_params = {param_key: corrected_entity['value']}
            
            # Crear mensaje para el usuario
            user_message = f"Buscando {search_type}s con {param_key}: {corrected_entity['value']}..."
            
            # Enviar respuesta al frontend
            dispatcher.utter_message(
                text=user_message,
                json_message={
                    "type": "search_results",
                    "search_type": search_type,
                    "parameters": search_params,
                    "message": user_message,
                    "validated": True,
                    "corrected_from_suggestion": True,
                    "timestamp": datetime.now().isoformat()
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
            return {'success': False, 'error': str(e)}
    
    def _create_search_completion_events(self, search_result: Dict[str, Any], 
                                       context: Dict[str, Any]) -> List[EventType]:
        """Crea eventos para completar una búsqueda exitosa"""
        events = []
        
        try:
            # Agregar a historial de búsquedas
            search_history = context.get('search_history', [])
            search_history.append({
                'timestamp': datetime.now().isoformat(),
                'type': search_result['search_type'],
                'parameters': search_result['parameters'],
                'status': 'completed_with_suggestion',
                'source': 'suggestion_acceptance'
            })
            
            events.append(SlotSet("search_history", search_history))
            
        except Exception as e:
            logger.error(f"Error creando eventos de finalización de búsqueda: {e}")
        
        return events
    
    def _handle_obsolete_system_migration(self, tracker: Tracker, 
                                        dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Maneja migración desde sistema obsoleto"""
        try:
            migrated_suggestion = SuggestionManager.migrate_from_obsolete_system(tracker)
            
            if migrated_suggestion:
                dispatcher.utter_message("Veo que tienes una búsqueda pendiente. ¿Qué información adicional puedes proporcionarme?")
                
                return {
                    'migrated': True,
                    'events': [
                        SlotSet("pending_suggestion", migrated_suggestion),
                        SlotSet("pedido_incompleto", False),  # Limpiar slot obsoleto
                        SlotSet("user_engagement_level", "engaged")
                    ]
                }
            
            return {'migrated': False, 'events': []}
            
        except Exception as e:
            logger.error(f"Error en migración de sistema obsoleto: {e}")
            return {'migrated': False, 'events': []}
    
    def _handle_standard_responses(self, current_intent: str, 
                                 dispatcher: CollectingDispatcher) -> List[EventType]:
        """Maneja respuestas estándar según configuración"""
        try:
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
            
            return []
            
        except Exception as e:
            logger.error(f"Error manejando respuestas estándar: {e}")
            dispatcher.utter_message("¡Gracias! ¿En qué más puedo ayudarte?")
            return []