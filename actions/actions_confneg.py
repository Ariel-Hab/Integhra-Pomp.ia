# actions/actions_conf_neg_agradecer.py
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from actions.logger import log_message
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, EventType

from .conversation_state import ConversationState, analyze_user_confirmation, get_slot_safely
from .helpers import get_intent_info
from .models.model_manager import generate_text_with_context  # ✅ CORREGIDO

logger = logging.getLogger(__name__)

class ActionConfNegAgradecer(Action):
    """
    ✅ VERSIÓN CON GROQ: Lógica intacta, respuestas generadas por LLM
    """
    
    def name(self) -> str:
        return "action_conf_neg_agradecer"
    
    def _generate_response(self, prompt: str, tracker: Tracker, max_tokens: int = 80) -> str:
        """
        ✅ ACTUALIZADO: Genera respuesta CON contexto
        """
        try:
            response = generate_text_with_context(
                prompt=prompt,
                tracker=tracker,
                max_new_tokens=max_tokens,
                temperature=0.7
            )
            
            if not response or len(response.strip()) < 5:
                logger.warning(f"[Groq] Respuesta vacía")
                return None
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"[Groq] Error: {e}")
            return None
    
    def _send_message(self, dispatcher: CollectingDispatcher, prompt: str, 
                 fallback: str, tracker: Tracker, max_tokens: int = 80):
        """
        ✅ Envía mensaje generado por Groq con fallback
        
        Args:
            dispatcher: Dispatcher de Rasa
            prompt: Prompt para Groq
            fallback: Mensaje de respaldo si Groq falla
            tracker: Tracker de Rasa para contexto
            max_tokens: Límite de tokens
        """
        response = self._generate_response(prompt, tracker, max_tokens)
        
        if response:
            dispatcher.utter_message(text=response)
            logger.debug(f"[Groq] ✓ Respuesta: '{response[:50]}...'")
        else:
            dispatcher.utter_message(text=fallback)
            logger.warning(f"[Groq] ✗ Usando fallback")
    
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, 
            domain: Dict[str, Any]) -> List[EventType]:
        try:
            context = ConversationState.get_conversation_context(tracker)
            current_intent = context['current_intent']
            user_msg = context['user_message']
            
            logger.info(f"[ConfNegAgradecer] Intent: {current_intent}, "
                       f"Awaiting suggestion: {context['awaiting_suggestion_response']}")
            log_message(tracker, nlu_conf_threshold=0.6)
            events = []
            
            # Manejar sugerencias pendientes
            if context['awaiting_suggestion_response']:
                actual_pending = get_slot_safely(tracker, "pending_suggestion")
                if not actual_pending:
                    logger.info("[ConfNegAgradecer] Sugerencia limpiada, respuesta estándar")
                    return self._handle_standard_responses(current_intent, dispatcher, tracker)  # ✅ CORREGIDO
                
                suggestion_result = self._handle_pending_suggestions_improved(
                    context, current_intent, user_msg, actual_pending, tracker, dispatcher
                )
                events.extend(suggestion_result['events'])
                
                if suggestion_result['handled']:
                    return events
            
            # Migración sistema obsoleto
            if context.get('has_obsolete_slots', False):
                migration_result = self._handle_obsolete_system_migration(tracker, dispatcher)
                events.extend(migration_result['events'])
                if migration_result['migrated']:
                    return events
            
            # Respuestas estándar
            standard_response_events = self._handle_standard_responses(current_intent, dispatcher, tracker)  # ✅ CORREGIDO
            events.extend(standard_response_events)
            
            return events
            
        except Exception as e:
            logger.error(f"Error en ActionConfNegAgradecer: {e}", exc_info=True)
            
            self._send_message(
                dispatcher,
                prompt="Usuario: [error técnico]\nPedí disculpas brevemente y ofrecé ayuda.",
                fallback="Disculpa, hubo un error. ¿Puedes intentar nuevamente?",
                tracker=tracker,
                max_tokens=50
            )
            
            return [SlotSet("user_engagement_level", "needs_help")]
    
    def _handle_pending_suggestions_improved(self, context: Dict[str, Any], current_intent: str, 
                                           user_msg: str, pending_suggestion: Dict[str, Any],
                                           tracker: Tracker, dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Maneja sugerencias usando análisis mejorado"""
        try:
            response_analysis = analyze_user_confirmation(user_msg, current_intent, pending_suggestion)
            
            suggestion_type = pending_suggestion.get('suggestion_type', '')
            confidence = response_analysis.get('confidence', 0.0)
            
            logger.info(f"[ConfNegAgradecer] Análisis - Tipo: {suggestion_type}, "
                       f"Afirmativo: {response_analysis['is_affirmative']}, "
                       f"Negativo: {response_analysis['is_negative']}, "
                       f"Confianza: {confidence:.2f}")
            # ✅ NUEVO: Manejar confirmación de modificación
            if suggestion_type == 'modification_confirmation':
                return self._handle_modification_confirmation(
                    pending_suggestion, response_analysis, tracker, dispatcher
                )
            if response_analysis['is_affirmative'] and confidence >= 0.7:
                return self._handle_affirmative_response_improved(
                    pending_suggestion, response_analysis, tracker, dispatcher
                )
            elif response_analysis['is_negative'] and confidence >= 0.7:
                return self._handle_negative_response_improved(
                    pending_suggestion, response_analysis, tracker, dispatcher
                )
            elif response_analysis['is_ambiguous'] or confidence < 0.7:
                return self._handle_ambiguous_response_improved(
                    pending_suggestion, response_analysis, user_msg, tracker, dispatcher
                )
            else:
                return self._handle_unrecognized_response_improved(
                    pending_suggestion, user_msg, tracker, dispatcher
                )
                
        except Exception as e:
            logger.error(f"Error manejando sugerencias: {e}", exc_info=True)
            return {
                'handled': False,
                'events': [
                    SlotSet("pending_suggestion", None),
                    SlotSet("user_engagement_level", "needs_help")
                ]
            }
    def _handle_modification_confirmation(self, pending_suggestion: Dict[str, Any],
                                        response_analysis: Dict[str, Any],
                                        tracker: Tracker,
                                        dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Maneja confirmación de modificaciones ambiguas"""
        try:
            is_affirmative = response_analysis.get('is_affirmative', False)
            is_negative = response_analysis.get('is_negative', False)
            confidence = response_analysis.get('confidence', 0.0)
            
            if is_affirmative and confidence >= 0.7:
                # Usuario confirmó la modificación
                actions = pending_suggestion.get('actions', [])
                search_type = pending_suggestion.get('search_type', 'producto')
                
                self._send_message(
                    dispatcher,
                    prompt="Usuario confirmó la modificación. Decí que vas a buscar.",
                    fallback="¡Perfecto! Aplicando los cambios...",
                    tracker=tracker,
                    max_tokens=40
                )
                
                # Ejecutar la modificación ahora
                context = ConversationState.get_conversation_context(tracker)
                previous_params = self._extract_previous_params_from_history(context)
                
                # Aplicar modificaciones
                rebuilt_params = self._apply_confirmed_modifications(previous_params, actions)
                
                # Ejecutar búsqueda
                self._execute_search_from_confirmation(
                    search_type, rebuilt_params, dispatcher, tracker
                )
                
                return {
                    'handled': True,
                    'events': [
                        SlotSet("pending_suggestion", None),
                        SlotSet("user_engagement_level", "satisfied")
                    ]
                }
            
            elif is_negative and confidence >= 0.7:
                # Usuario rechazó la modificación
                self._send_message(
                    dispatcher,
                    prompt="Usuario rechazó la modificación. Aceptá y pedí que reformule o use otros términos.",
                    fallback="Entendido. ¿Podés reformular tu solicitud o usar otros términos?",
                    tracker=tracker,
                    max_tokens=50
                )
                
                return {
                    'handled': True,
                    'events': [
                        SlotSet("pending_suggestion", None),
                        SlotSet("user_engagement_level", "needs_help")
                    ]
                }
            
            else:
                # Respuesta ambigua
                self._send_message(
                    dispatcher,
                    prompt="Respuesta ambigua a confirmación de modificación. Pedí clarificación sí/no.",
                    fallback="No entendí. ¿Querés que aplique estos cambios? Respondé 'sí' o 'no'.",
                    tracker=tracker,
                    max_tokens=50
                )
                
                return {
                    'handled': True,
                    'events': []  # Mantener pending_suggestion
                }
            
        except Exception as e:
            logger.error(f"[ModConfirmation] Error: {e}")
            
            self._send_message(
                dispatcher,
                prompt="Error procesando confirmación. Pedí disculpas.",
                fallback="Hubo un error. ¿Puedes intentar de nuevo?",
                tracker=tracker,
                max_tokens=40
            )
            
            return {
                'handled': True,
                'events': [SlotSet("pending_suggestion", None)]
            }

    # ✅ NUEVO: Métodos auxiliares
    def _extract_previous_params_from_history(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Extrae parámetros de búsqueda anterior del historial"""
        search_history = context.get('search_history', [])
        if search_history:
            return search_history[-1].get('parameters', {})
        return {}

    def _apply_confirmed_modifications(self, previous_params: Dict[str, Any], 
                                    actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aplica modificaciones confirmadas"""
        rebuilt = previous_params.copy()
        
        for action in actions:
            action_type = action.get('type')
            entity_type = action.get('entity_type')
            
            if action_type == 'replace':
                rebuilt[entity_type] = action.get('new_value')
            elif action_type == 'add':
                rebuilt[entity_type] = action.get('new_value')
        
        return rebuilt

    def _execute_search_from_confirmation(self, search_type: str, params: Dict[str, Any],
                                        dispatcher: CollectingDispatcher, tracker: Tracker):
        """Ejecuta búsqueda después de confirmación"""
        formatted_params = ", ".join([f"{k}: {v}" for k, v in params.items()])
        message = f"Buscando {search_type}s con {formatted_params}"
        
        dispatcher.utter_message(
            text=message,
            json_message={
                "type": "search_results",
                "search_type": search_type,
                "parameters": params,
                "validated": True,
                "from_confirmation": True,
                "timestamp": datetime.now().isoformat()
            }
        )
    def _handle_affirmative_response_improved(self, pending_suggestion: Dict[str, Any], 
                                            response_analysis: Dict[str, Any], tracker: Tracker,
                                            dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """✅ CON GROQ: Respuestas afirmativas"""
        suggestion_type = pending_suggestion.get('suggestion_type', '')
        confidence = response_analysis.get('confidence', 0.0)
        events = []
        
        try:
            if suggestion_type == 'entity_correction':
                suggestions = pending_suggestion.get('suggestions', [])
                corrected_value = suggestions[0] if suggestions else ''
                entity_type = pending_suggestion.get('entity_type', '')
                
                if corrected_value and entity_type:
                    self._send_message(
                        dispatcher,
                        prompt=f"Usuario aceptó usar '{corrected_value}' como {entity_type}. "
                               f"Confirmá brevemente y decí que vas a buscar.",
                        fallback=f"¡Perfecto! Buscando con '{corrected_value}'.",
                        tracker=tracker,
                        max_tokens=60
                    )
                    
                    search_result = self._execute_search_with_corrected_entity(
                        {'value': corrected_value, 'type': entity_type}, 
                        pending_suggestion, tracker, dispatcher
                    )
                    
                    if search_result['success']:
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
                    self._send_message(
                        dispatcher,
                        prompt="Hubo un problema técnico. Pedí disculpas y sugerí intentar de nuevo.",
                        fallback="Hubo un problema. ¿Podrías intentar nuevamente?",
                        tracker=tracker,
                        max_tokens=50
                    )
                    events.extend([
                        SlotSet("pending_suggestion", None),
                        SlotSet("user_engagement_level", "needs_help")
                    ])
            
            elif suggestion_type == 'type_correction':
                original_value = pending_suggestion.get('original_value', '')
                correct_type = pending_suggestion.get('correct_type', '')
                
                if original_value and correct_type:
                    self._send_message(
                        dispatcher,
                        prompt=f"Usuario confirmó que '{original_value}' es un {correct_type}. "
                               f"Confirmá y decí que vas a buscar.",
                        fallback=f"¡Entendido! Buscando '{original_value}' como {correct_type}.",
                        tracker=tracker,
                        max_tokens=60
                    )
                    
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
                criteria = pending_suggestion.get('required_criteria', 'información')
                
                self._send_message(
                    dispatcher,
                    prompt=f"Usuario acepta dar más info. Pedí que especifique {criteria}.",
                    fallback=f"Perfecto. ¿Qué {criteria} específico necesitás?",
                    tracker=tracker,
                    max_tokens=50
                )
                
                events.extend([
                    SlotSet("pending_suggestion", None),
                    SlotSet("user_engagement_level", "engaged")
                ])
            
            logger.info(f"[ConfNegAgradecer] Afirmativo procesado (conf: {confidence:.2f})")
            return {'handled': True, 'events': events}
            
        except Exception as e:
            logger.error(f"Error en respuesta afirmativa: {e}", exc_info=True)
            
            self._send_message(
                dispatcher,
                prompt="Error procesando confirmación. Pedí disculpas y sugerí reintentar.",
                fallback="Hubo un error. ¿Puedes intentar nuevamente?",
                tracker=tracker,
                max_tokens=50
            )
            
            return {
                'handled': True,
                'events': [
                    SlotSet("pending_suggestion", None),
                    SlotSet("user_engagement_level", "needs_help")
                ]
            }
    
    def _handle_negative_response_improved(self, pending_suggestion: Dict[str, Any], 
                                         response_analysis: Dict[str, Any],
                                         tracker: Tracker,
                                         dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """✅ CON GROQ: Respuestas negativas"""
        suggestion_type = pending_suggestion.get('suggestion_type', '')
        confidence = response_analysis.get('confidence', 0.0)
        
        try:
            if suggestion_type in ['entity_correction', 'type_correction']:
                self._send_message(
                    dispatcher,
                    prompt="Usuario rechazó la sugerencia. Aceptá su decisión y pedí que escriba el término correcto o use otros criterios.",
                    fallback="Entendido. ¿Podés escribir el nombre correcto o usar otros criterios?",
                    tracker=tracker,
                    max_tokens=60
                )
            else:
                self._send_message(
                    dispatcher,
                    prompt="Usuario dice que no. Aceptá y preguntá si necesita otra cosa.",
                    fallback="Entendido. ¿Hay algo más en lo que pueda ayudarte?",
                    tracker=tracker,
                    max_tokens=50
                )
            
            logger.info(f"[ConfNegAgradecer] Negativo procesado (conf: {confidence:.2f})")
            return {
                'handled': True,
                'events': [
                    SlotSet("pending_suggestion", None),
                    SlotSet("user_engagement_level", "needs_help")
                ]
            }
            
        except Exception as e:
            logger.error(f"Error en respuesta negativa: {e}")
            return {
                'handled': True,
                'events': [SlotSet("pending_suggestion", None)]
            }
    
    def _handle_ambiguous_response_improved(self, pending_suggestion: Dict[str, Any], 
                                          response_analysis: Dict[str, Any], user_msg: str,
                                          tracker: Tracker,
                                          dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """✅ CON GROQ: Respuestas ambiguas"""
        try:
            suggestion_type = pending_suggestion.get('suggestion_type', '')
            confidence = response_analysis.get('confidence', 0.0)
            
            attempts = pending_suggestion.get('clarification_attempts', 0) + 1
            pending_suggestion['clarification_attempts'] = attempts
            
            logger.info(f"[ConfNegAgradecer] Ambiguo - Intento {attempts}, Conf: {confidence:.2f}")
            
            if attempts >= 3:
                self._send_message(
                    dispatcher,
                    prompt="Usuario no responde claramente después de 3 intentos. "
                           "Sugerí amablemente empezar de nuevo y preguntá qué necesita.",
                    fallback="No logro entender. Empecemos de nuevo. ¿Qué necesitás buscar?",
                    tracker=tracker,
                    max_tokens=60
                )
                
                return {
                    'handled': True,
                    'events': [
                        SlotSet("pending_suggestion", None),
                        SlotSet("user_engagement_level", "needs_help")
                    ],
                    'suggestion_abandoned': True
                }
            
            if suggestion_type == 'entity_correction':
                suggestions = pending_suggestion.get('suggestions', [])
                original_value = pending_suggestion.get('original_value', '')
                
                if suggestions:
                    prompt = (f"Respuesta ambigua. Pedí clarificación directa: "
                            f"¿confirma '{suggestions[0]}' en lugar de '{original_value}'? "
                            f"Pedí respuesta clara sí/no.")
                    fallback = (f"No estoy seguro. ¿Buscás '{suggestions[0]}' "
                              f"en lugar de '{original_value}'? Respondé 'sí' o 'no'.")
                else:
                    prompt = "Respuesta ambigua. Pedí que responda claramente sí o no."
                    fallback = "No entendí. Respondé 'sí' o 'no' por favor."
            
            elif suggestion_type == 'type_correction':
                original_value = pending_suggestion.get('original_value', '')
                correct_type = pending_suggestion.get('correct_type', '')
                prompt = (f"Respuesta ambigua sobre si '{original_value}' es {correct_type}. "
                         f"Pedí confirmación clara sí/no.")
                fallback = f"No entendí. ¿'{original_value}' es {correct_type}? Respondé 'sí' o 'no'."
            
            else:
                prompt = "Respuesta ambigua. Pedí aclaración directa."
                fallback = "No entendí. ¿Puedes ser más específico?"
            
            self._send_message(dispatcher, prompt, fallback, tracker, max_tokens=70)
            
            return {
                'handled': True,
                'events': [SlotSet("pending_suggestion", pending_suggestion)],
                'clarification_sent': True,
                'attempts': attempts
            }
            
        except Exception as e:
            logger.error(f"Error en respuesta ambigua: {e}")
            
            self._send_message(
                dispatcher,
                prompt="No entendiste. Pedí respuesta clara sí/no.",
                fallback="No entendí. ¿Puedes responder 'sí' o 'no'?",
                tracker=tracker,
                max_tokens=40
            )
            
            return {'handled': True, 'events': []}
    
    def _handle_unrecognized_response_improved(self, pending_suggestion: Dict[str, Any], 
                                             user_msg: str,
                                             tracker: Tracker,
                                             dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """✅ CON GROQ: Respuestas no reconocidas"""
        try:
            attempts = pending_suggestion.get('clarification_attempts', 0) + 1
            
            logger.warning(f"[ConfNegAgradecer] No reconocido - Intento {attempts}: '{user_msg[:50]}'")
            
            if attempts >= 3:
                self._send_message(
                    dispatcher,
                    prompt="Después de 3 intentos no se entiende. "
                           "Sugerí empezar de nuevo amablemente.",
                    fallback="No logro entender. Empecemos de nuevo. ¿Qué necesitás?",
                    tracker=tracker,
                    max_tokens=50
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
                self._send_message(
                    dispatcher,
                    prompt="No reconociste la respuesta. Pedí MUY claramente que responda SOLO sí o no.",
                    fallback="No reconozco tu respuesta. Por favor, respondé únicamente 'SÍ' o 'NO'.",
                    tracker=tracker,
                    max_tokens=50
                )
                
                pending_suggestion['clarification_attempts'] = attempts
                
                return {
                    'handled': True,
                    'events': [SlotSet("pending_suggestion", pending_suggestion)],
                    'final_attempt': attempts >= 2
                }
                
        except Exception as e:
            logger.error(f"Error en no reconocido: {e}")
            
            self._send_message(
                dispatcher,
                prompt="Error. Sugerí empezar de nuevo.",
                fallback="No entiendo. Empecemos de nuevo. ¿Qué buscás?",
                tracker=tracker,
                max_tokens=40
            )
            
            return {
                'handled': True,
                'events': [SlotSet("pending_suggestion", None)]
            }
    
    def _execute_search_with_corrected_entity(self, corrected_entity: Dict[str, str], 
                                        pending_suggestion: Dict[str, Any], tracker: Tracker,
                                        dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Ejecuta búsqueda con entidad corregida (lógica intacta)"""
        try:
            search_context = pending_suggestion.get('search_context', {})
            search_type = search_context.get('search_type', 'producto')
            
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
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            logger.info(f"[ConfNegAgradecer] Búsqueda ejecutada: {search_params}")
            
            return {
                'success': True,
                'search_type': search_type,
                'parameters': search_params,
                'message': user_message
            }
            
        except Exception as e:
            logger.error(f"Error ejecutando búsqueda: {e}", exc_info=True)
            
            self._send_message(
                dispatcher,
                prompt="Error ejecutando búsqueda. Pedí disculpas y sugerí reintentar.",
                fallback="Hubo un error. Inténtalo de nuevo.",
                tracker=tracker,
                max_tokens=40
            )
            
            return {'success': False, 'error': str(e)}
    
    def _handle_obsolete_system_migration(self, tracker: Tracker, 
                                        dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Maneja migración (sin cambios)"""
        return {'migrated': False, 'events': []}
    
    def _handle_standard_responses(self, current_intent: str, 
                                 dispatcher: CollectingDispatcher,
                                 tracker: Tracker) -> List[EventType]:  # ✅ CORREGIDO
        """✅ CON GROQ: Respuestas estándar"""
        try:
            intent_info = get_intent_info(current_intent)
            responses = intent_info.get("responses", [])
            
            if responses:
                dispatcher.utter_message(text=responses[0])
            else:
                intent_prompts = {
                    "agradecimiento": "Usuario agradeció. Respondé cordialmente y ofrecé ayuda.",
                    "afirmar": "Usuario confirmó. Preguntá en qué podés ayudar.",
                    "denegar": "Usuario negó. Aceptá y preguntá si necesita otra cosa."
                }
                
                prompt = intent_prompts.get(
                    current_intent, 
                    "Usuario interactuó positivamente. Respondé cordialmente."
                )
                
                fallbacks = {
                    "agradecimiento": "¡De nada! Siempre estoy aquí para ayudarte.",
                    "afirmar": "Perfecto. ¿En qué puedo ayudarte?",
                    "denegar": "No hay problema. ¿Necesitás algo más?"
                }
                
                fallback = fallbacks.get(
                    current_intent,
                    "¡Gracias! ¿En qué más puedo ayudarte?"
                )
                
                self._send_message(dispatcher, prompt, fallback, tracker, max_tokens=50)
            
            return []
            
        except Exception as e:
            logger.error(f"Error en respuestas estándar: {e}")
            
            self._send_message(
                dispatcher,
                prompt="Usuario interactuó. Respondé cordialmente y ofrecé ayuda.",
                fallback="¡Gracias! ¿En qué más puedo ayudarte?",
                tracker=tracker,
                max_tokens=40
            )
            
            return []