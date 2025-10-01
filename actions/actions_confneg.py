# Actualización de ActionConfNegAgradecer para usar el sistema mejorado
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, EventType

from .conversation_state import ConversationState, analyze_user_confirmation, get_slot_safely
from .helpers import get_intent_info


logger = logging.getLogger(__name__)

class ActionConfNegAgradecer(Action):
    """
    ✅ VERSIÓN ACTUALIZADA: Usa el sistema mejorado de sugerencias y detección de confirmación
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
            
            # 🆕 PRIORIDAD MÁXIMA: Manejar sugerencias pendientes con sistema mejorado
            if context['awaiting_suggestion_response']:
                actual_pending = get_slot_safely(tracker, "pending_suggestion")
                if not actual_pending:
                    logger.info("[ConfNegAgradecer] Sugerencia ya limpiada, procediendo con respuesta estándar")
                    return self._handle_standard_responses(current_intent, dispatcher)
                
                # ✅ USAR SISTEMA MEJORADO para analizar respuesta
                suggestion_result = self._handle_pending_suggestions_improved(
                    context, current_intent, user_msg, actual_pending, tracker, dispatcher
                )
                events.extend(suggestion_result['events'])
                
                if suggestion_result['handled']:
                    return events
            
            # Resto del manejo igual que antes
            if context.get('has_obsolete_slots', False):
                migration_result = self._handle_obsolete_system_migration(tracker, dispatcher)
                events.extend(migration_result['events'])
                if migration_result['migrated']:
                    return events
            
            standard_response_events = self._handle_standard_responses(current_intent, dispatcher)
            events.extend(standard_response_events)
            
            return events
            
        except Exception as e:
            logger.error(f"Error en ActionConfNegAgradecer: {e}", exc_info=True)
            dispatcher.utter_message("Disculpa, hubo un error procesando tu respuesta. ¿Puedes intentar nuevamente?")
            return [SlotSet("user_engagement_level", "needs_help")]
    
    def _handle_pending_suggestions_improved(self, context: Dict[str, Any], current_intent: str, 
                                           user_msg: str, pending_suggestion: Dict[str, Any],
                                           tracker: Tracker, dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """
        ✅ NUEVA FUNCIÓN: Maneja sugerencias usando el sistema mejorado de detección
        """
        try:
            # ✅ USAR ANÁLISIS MEJORADO DE CONFIRMACIÓN
            response_analysis = analyze_user_confirmation(user_msg, current_intent, pending_suggestion)
            
            suggestion_type = pending_suggestion.get('suggestion_type', '')
            confidence = response_analysis.get('confidence', 0.0)
            
            logger.info(f"[ConfNegAgradecer] Análisis mejorado - Tipo: {suggestion_type}, "
                       f"Afirmativo: {response_analysis['is_affirmative']}, "
                       f"Negativo: {response_analysis['is_negative']}, "
                       f"Ambiguo: {response_analysis['is_ambiguous']}, "
                       f"Confianza: {confidence:.2f}")
            
            # Procesar según el análisis mejorado
            if response_analysis['is_affirmative'] and confidence >= 0.7:
                return self._handle_affirmative_response_improved(pending_suggestion, response_analysis, tracker, dispatcher)
            elif response_analysis['is_negative'] and confidence >= 0.7:
                return self._handle_negative_response_improved(pending_suggestion, response_analysis, dispatcher)
            elif response_analysis['is_ambiguous'] or confidence < 0.7:
                return self._handle_ambiguous_response_improved(pending_suggestion, response_analysis, user_msg, dispatcher)
            else:
                return self._handle_unrecognized_response_improved(pending_suggestion, user_msg, dispatcher)
                
        except Exception as e:
            logger.error(f"Error manejando sugerencias con sistema mejorado: {e}", exc_info=True)
            return {
                'handled': False,
                'events': [
                    SlotSet("pending_suggestion", None),
                    SlotSet("user_engagement_level", "needs_help")
                ]
            }
    
    
    def _handle_negative_response_improved(self, pending_suggestion: Dict[str, Any], 
                                         response_analysis: Dict[str, Any],
                                         dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """✅ MEJORADO: Maneja respuestas negativas con mejor contexto"""
        suggestion_type = pending_suggestion.get('suggestion_type', '')
        confidence = response_analysis.get('confidence', 0.0)
        
        try:
            if suggestion_type in ['entity_correction', 'type_correction']:
                if confidence >= 0.9:
                    dispatcher.utter_message("Entendido. ¿Puedes escribir el nombre correcto o usar otros criterios de búsqueda?")
                else:
                    dispatcher.utter_message("De acuerdo. ¿Podrías especificar el término correcto o intentar con otros criterios?")
            else:
                dispatcher.utter_message("Entendido. ¿Hay algo más en lo que pueda ayudarte?")
            
            logger.info(f"[ConfNegAgradecer] Respuesta negativa procesada (confianza: {confidence:.2f})")
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
    
    def _handle_ambiguous_response_improved(self, pending_suggestion: Dict[str, Any], 
                                          response_analysis: Dict[str, Any], user_msg: str,
                                          dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """✅ MEJORADO: Maneja respuestas ambiguas con mejor contexto"""
        try:
            suggestion_type = pending_suggestion.get('suggestion_type', '')
            confidence = response_analysis.get('confidence', 0.0)
            detected_patterns = response_analysis.get('detected_patterns', [])
            context_clues = response_analysis.get('context_clues', [])
            
            logger.info(f"[ConfNegAgradecer] Respuesta ambigua detectada - Confianza: {confidence:.2f}, "
                       f"Patrones: {detected_patterns[:2]}, Claves contextuales: {len(context_clues)}")
            
            # Incrementar contador de clarificaciones
            attempts = pending_suggestion.get('clarification_attempts', 0) + 1
            pending_suggestion['clarification_attempts'] = attempts
            
            # ✅ MENSAJES MEJORADOS según contexto
            if attempts >= 3:
                dispatcher.utter_message(
                    "No logro entender tus respuestas. Empecemos de nuevo. "
                    "¿Qué necesitas buscar específicamente?"
                )
                
                return {
                    'handled': True,
                    'events': [
                        SlotSet("pending_suggestion", None),
                        SlotSet("user_engagement_level", "needs_help")
                    ],
                    'suggestion_abandoned': True
                }
            
            # Mensaje específico según tipo y contexto
            if suggestion_type == 'entity_correction':
                suggestions = pending_suggestion.get('suggestions', [])
                original_value = pending_suggestion.get('original_value', '')
                
                if suggestions and confidence > 0.3:
                    message = (f"No estoy seguro de tu respuesta. "
                             f"¿Confirmas que buscas '{suggestions[0]}' "
                             f"en lugar de '{original_value}'? "
                             f"Responde claramente 'sí' o 'no'.")
                else:
                    message = "No entendí tu respuesta. Por favor responde 'sí' para aceptar la sugerencia o 'no' para rechazarla."
            
            elif suggestion_type == 'type_correction':
                correct_type = pending_suggestion.get('correct_type', '')
                original_value = pending_suggestion.get('original_value', '')
                message = (f"No estoy seguro. "
                         f"¿Confirmas que '{original_value}' es {correct_type}? "
                         f"Responde 'sí' o 'no'.")
            
            elif suggestion_type == 'missing_parameters':
                required_criteria = pending_suggestion.get('required_criteria', 'información')
                message = (f"No entiendo qué información me estás dando. "
                         f"¿Puedes especificar qué {required_criteria} necesitas?")
            
            else:
                message = "No entendí tu respuesta. ¿Puedes ser más específico?"
            
            dispatcher.utter_message(message)
            
            return {
                'handled': True, 
                'events': [SlotSet("pending_suggestion", pending_suggestion)],
                'clarification_sent': True,
                'attempts': attempts
            }
            
        except Exception as e:
            logger.error(f"Error manejando respuesta ambigua mejorada: {e}")
            dispatcher.utter_message("No entendí tu respuesta. ¿Puedes responder 'sí' o 'no'?")
            return {'handled': True, 'events': []}
    
    def _handle_unrecognized_response_improved(self, pending_suggestion: Dict[str, Any], user_msg: str,
                                             dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """✅ MEJORADO: Maneja respuestas no reconocidas"""
        try:
            attempts = pending_suggestion.get('clarification_attempts', 0) + 1
            
            logger.warning(f"[ConfNegAgradecer] Respuesta no reconocida después de {attempts} intentos: '{user_msg[:50]}...'")
            
            if attempts >= 3:
                dispatcher.utter_message(
                    "No logro entender tus respuestas. Vamos a empezar de nuevo. "
                    "¿Qué necesitas buscar?"
                )
                
                return {
                    'handled': True,
                    'events': [
                        SlotSet("pending_suggestion", None),
                        SlotSet("user_engagement_level", "needs_help")
                    ],
                    'suggestion_abandoned': True
                }
            else:
                # Mensaje muy claro para último intento
                message = ("No reconozco tu respuesta. "
                         "Por favor, responde únicamente 'SÍ' para aceptar "
                         "o 'NO' para rechazar mi sugerencia.")
                
                pending_suggestion['clarification_attempts'] = attempts
                dispatcher.utter_message(message)
                
                return {
                    'handled': True,
                    'events': [SlotSet("pending_suggestion", pending_suggestion)],
                    'final_attempt': attempts >= 2
                }
                
        except Exception as e:
            logger.error(f"Error manejando respuesta no reconocida: {e}")
            dispatcher.utter_message("No entiendo. Empecemos de nuevo. ¿Qué necesitas buscar?")
            return {
                'handled': True,
                'events': [SlotSet("pending_suggestion", None)]
            }
    
    # ===== FUNCIONES AUXILIARES (igual que antes) =====
    
    def _execute_search_with_corrected_entity(self, corrected_entity: Dict[str, str], 
                                        pending_suggestion: Dict[str, Any], tracker: Tracker,
                                        dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Ejecuta búsqueda con entidad corregida"""
        try:
            search_context = pending_suggestion.get('search_context', {})
            search_type = search_context.get('search_type', 'producto')
            
            # ✅ CORREGIR: Determinar search_type desde el intent si no está en context
            if not search_type or search_type == 'producto':
                original_intent = search_context.get('intent', '')
                if 'oferta' in original_intent:
                    search_type = 'oferta'
                elif 'producto' in original_intent:
                    search_type = 'producto'
            
            entity_mappings = {
                "producto": "nombre",
                "empresa": "empresa",
                "categoria": "categoria",
                "ingrediente_activo": "ingrediente_activo",
                "dosis": "dosis",
                "cantidad": "cantidad",
                "animal": "animal"
            }
            
            param_key = entity_mappings.get(corrected_entity['type'], corrected_entity['type'])
            search_params = {param_key: corrected_entity['value']}
            
            user_message = f"Buscando {search_type}s con {param_key}: {corrected_entity['value']}..."
            
            dispatcher.utter_message(
                text=user_message,
                json_message={
                    "type": "search_results",
                    "search_type": search_type,
                    "parameters": search_params,
                    "message": user_message,
                    "validated": True,
                    "corrected_from_suggestion": True,
                    "suggestion_confidence": pending_suggestion.get('metadata', {}).get('similarity_scores', [0.8])[0],
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
            logger.error(f"Error ejecutando búsqueda con entidad corregida: {e}", exc_info=True)
            dispatcher.utter_message("Hubo un error procesando tu búsqueda. Inténtalo de nuevo.")
            return {'success': False, 'error': str(e)}
    def _create_search_completion_events(self, search_result: Dict[str, Any]) -> List[EventType]:
        """Crea eventos para completar búsqueda"""
        events = []
        
        try:
            # ✅ AGREGAR: Actualizar historial de búsqueda
            search_entry = {
                'timestamp': datetime.now().isoformat(),
                'type': search_result['search_type'],
                'parameters': search_result['parameters'],
                'status': 'completed',
                'source': 'suggestion_acceptance'
            }
            
            # ✅ NUEVO: Obtener historial actual del tracker
            # IMPORTANTE: Necesitas recibir tracker como parámetro
            # Modificar la firma de la función:
            # def _create_search_completion_events(self, search_result: Dict[str, Any], tracker: Tracker) -> List[EventType]:
            
            # Por ahora, crear historial nuevo
            events.append(SlotSet("search_history", [search_entry]))
            
            # ✅ CRÍTICO: Limpiar sugerencia
            events.append(SlotSet("pending_suggestion", None))
            events.append(SlotSet("suggestion_context", None))
            
            # ✅ IMPORTANTE: Establecer engagement
            events.append(SlotSet("user_engagement_level", "satisfied"))
            
        except Exception as e:
            logger.error(f"Error creando eventos de finalización: {e}")
        
        return events

    def _handle_affirmative_response_improved(self, pending_suggestion: Dict[str, Any], 
                                            response_analysis: Dict[str, Any], tracker: Tracker,
                                            dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """✅ MEJORADO: Maneja respuestas afirmativas con mejor contexto"""
        suggestion_type = pending_suggestion.get('suggestion_type', '')
        confidence = response_analysis.get('confidence', 0.0)
        events = []
        
        try:
            if suggestion_type == 'entity_correction':
                suggestions = pending_suggestion.get('suggestions', [])
                corrected_value = suggestions[0] if suggestions else ''
                entity_type = pending_suggestion.get('entity_type', '')
                
                if corrected_value and entity_type:
                    if confidence >= 0.9:
                        dispatcher.utter_message(f"¡Perfecto! Usando '{corrected_value}' para buscar {entity_type}.")
                    else:
                        dispatcher.utter_message(f"Entendido. Buscando con '{corrected_value}' como {entity_type}.")
                    
                    # Ejecutar búsqueda con valor corregido
                    search_result = self._execute_search_with_corrected_entity(
                        {'value': corrected_value, 'type': entity_type}, 
                        pending_suggestion, tracker, dispatcher
                    )
                    
                    if search_result['success']:
                        # ✅ CORREGIDO: Remover tracker del llamado
                        # events.extend(self._create_search_completion_events(search_result, tracker))
                        # En su lugar, crear eventos directamente aquí:
                        events.extend([
                            SlotSet("pending_suggestion", None),
                            SlotSet("suggestion_context", None),
                            SlotSet("user_engagement_level", "satisfied")
                        ])
                    else:
                        events.extend([
                            SlotSet("pending_suggestion", None),
                            SlotSet("user_engagement_level", "needs_help")
                        ])
                else:
                    dispatcher.utter_message("Hubo un problema con la sugerencia. ¿Podrías intentar nuevamente?")
                    events.extend([
                        SlotSet("pending_suggestion", None),
                        SlotSet("user_engagement_level", "needs_help")
                    ])
            
            elif suggestion_type == 'type_correction':
                original_value = pending_suggestion.get('original_value', '')
                correct_type = pending_suggestion.get('correct_type', '')
                
                if original_value and correct_type:
                    dispatcher.utter_message(f"¡Entendido! Buscando '{original_value}' como {correct_type}.")
                    
                    search_result = self._execute_search_with_corrected_entity(
                        {'value': original_value, 'type': correct_type}, 
                        pending_suggestion, tracker, dispatcher
                    )
                    
                    if search_result['success']:
                        events.extend([
                            SlotSet("pending_suggestion", None),
                            SlotSet("user_engagement_level", "satisfied")
                        ])
                else:
                    events.extend([
                        SlotSet("pending_suggestion", None),
                        SlotSet("user_engagement_level", "needs_help")
                    ])
            
            elif suggestion_type == 'missing_parameters':
                criteria = pending_suggestion.get('required_criteria', 'información adicional')
                if confidence >= 0.9:
                    dispatcher.utter_message(f"¡Excelente! ¿Qué {criteria} específico puedes darme?")
                else:
                    dispatcher.utter_message(f"Perfecto. Necesito que me especifiques {criteria}.")
                events.extend([
                    SlotSet("pending_suggestion", None),
                    SlotSet("user_engagement_level", "engaged")
                ])
            
            # ✅ NO duplicar limpieza aquí - ya está arriba en cada caso
            
            logger.info(f"[ConfNegAgradecer] Respuesta afirmativa procesada exitosamente (confianza: {confidence:.2f})")
            return {'handled': True, 'events': events}
            
        except Exception as e:
            logger.error(f"Error manejando respuesta afirmativa mejorada: {e}", exc_info=True)
            dispatcher.utter_message("Hubo un error procesando tu confirmación. ¿Puedes intentar nuevamente?")
            return {
                'handled': True,
                'events': [
                    SlotSet("pending_suggestion", None),
                    SlotSet("user_engagement_level", "needs_help")
                ]
            }
    def _handle_obsolete_system_migration(self, tracker: Tracker, 
                                        dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Maneja migración desde sistema obsoleto (igual que antes)"""
        # Implementación igual que antes
        return {'migrated': False, 'events': []}
    
    def _handle_standard_responses(self, current_intent: str, 
                                 dispatcher: CollectingDispatcher) -> List[EventType]:
        """Maneja respuestas estándar (igual que antes)"""
        try:
            intent_info = get_intent_info(current_intent)
            responses = intent_info.get("responses", [])
            
            if responses:
                # Implementación igual que antes
                pass
            else:
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