import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from actions.logger import log_message
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, EventType

from .conversation_state import ConversationState, analyze_user_confirmation, get_slot_safely
from .helpers import get_intent_info
from .models.model_manager import generate_text_with_context

logger = logging.getLogger(__name__)

# ============== CONFIGURACIÓN ESTANDARIZADA ==============
DEFAULT_TEMPERATURE = 0.1
DEFAULT_MAX_TOKENS = 50

# Casos específicos que necesitan valores diferentes
SPECIAL_CASES = {
    'clarification': {'max_tokens': 70, 'temperature': 0.2},
    'error_handling': {'max_tokens': 40, 'temperature': 0.1},
}
# =========================================================


class ActionConfNegAgradecer(Action):
    """Maneja confirmaciones, negaciones y agradecimientos con LLM simplificado"""
    
    def name(self) -> str:
        return "action_conf_neg_agradecer"
    
    def _generate_response(
        self, 
        dispatcher: CollectingDispatcher,
        prompt: str,
        tracker: Tracker,
        fallback_text: str,
        special_case: Optional[str] = None
    ) -> None:
        """
        Método unificado para generar respuestas con el LLM.
        
        ✅ IMPORTANTE: generate_text_with_context SIEMPRE envía el mensaje cuando
        hay dispatcher, por lo que este método solo necesita llamarlo.
        
        Args:
            dispatcher: Para enviar mensajes
            prompt: El prompt para el LLM
            tracker: Contexto de la conversación
            fallback_text: Texto a usar si falla (ya no se usa, solo para compatibilidad)
            special_case: Si requiere configuración especial ('clarification', 'error_handling')
        """
        # Obtener configuración
        if special_case and special_case in SPECIAL_CASES:
            config = SPECIAL_CASES[special_case]
            max_tokens = config['max_tokens']
            temperature = config['temperature']
        else:
            max_tokens = DEFAULT_MAX_TOKENS
            temperature = DEFAULT_TEMPERATURE
        
        # ✅ generate_text_with_context envía el mensaje automáticamente cuando hay dispatcher
        # Retorna None después de enviar, así que no necesitamos hacer nada más
        generate_text_with_context(
            prompt=prompt,
            tracker=tracker,
            dispatcher=dispatcher,
            fallback_template=None,
            max_new_tokens=max_tokens,
            temperature=temperature
        )
    
    def run(
        self, 
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[str, Any]
    ) -> List[EventType]:
        try:
            context = ConversationState.get_conversation_context(tracker)
            current_intent = context['current_intent']
            user_msg = context['user_message']
            
            logger.info(f"[ConfNegAgradecer] Intent: {current_intent}, "
                       f"Awaiting suggestion: {context['awaiting_suggestion_response']}")
            log_message(tracker, nlu_conf_threshold=0.6)
            
            # Manejar sugerencias pendientes
            if context['awaiting_suggestion_response']:
                actual_pending = get_slot_safely(tracker, "pending_suggestion")
                if not actual_pending:
                    logger.info("[ConfNegAgradecer] Sugerencia limpiada, respuesta estándar")
                    return self._handle_standard_responses(current_intent, dispatcher, tracker)
                
                return self._handle_pending_suggestion(
                    context, current_intent, user_msg, actual_pending, tracker, dispatcher
                )
            
            # Migración sistema obsoleto
            if context.get('has_obsolete_slots', False):
                migration_result = self._handle_obsolete_system_migration(tracker, dispatcher)
                if migration_result['migrated']:
                    return migration_result['events']
            
            # Respuestas estándar
            return self._handle_standard_responses(current_intent, dispatcher, tracker)
            
        except Exception as e:
            logger.error(f"Error en ActionConfNegAgradecer: {e}", exc_info=True)
            
            self._generate_response(
                dispatcher,
                prompt="Error técnico. Pedí disculpas y ofrecé ayuda.",
                tracker=tracker,
                fallback_text="Disculpa, hubo un error. ¿Puedes intentar nuevamente?",
                special_case='error_handling'
            )
            
            return [SlotSet("user_engagement_level", "needs_help")]
    
    def _handle_pending_suggestion(
        self,
        context: Dict[str, Any],
        current_intent: str,
        user_msg: str,
        pending_suggestion: Dict[str, Any],
        tracker: Tracker,
        dispatcher: CollectingDispatcher
    ) -> List[EventType]:
        """Maneja sugerencias pendientes de forma unificada"""
        try:
            response_analysis = analyze_user_confirmation(user_msg, current_intent, pending_suggestion)
            suggestion_type = pending_suggestion.get('suggestion_type', '')
            confidence = response_analysis.get('confidence', 0.0)
            
            logger.info(f"[Sugerencia] Tipo: {suggestion_type}, "
                       f"Afirmativo: {response_analysis['is_affirmative']}, "
                       f"Negativo: {response_analysis['is_negative']}, "
                       f"Conf: {confidence:.2f}")
            
            # Confirmación de modificación (caso especial)
            if suggestion_type == 'modification_confirmation':
                return self._handle_modification_confirmation(
                    pending_suggestion, response_analysis, tracker, dispatcher
                )
            
            # Respuesta afirmativa con alta confianza
            if response_analysis['is_affirmative'] and confidence >= 0.7:
                return self._handle_affirmative_response(
                    pending_suggestion, tracker, dispatcher
                )
            
            # Respuesta negativa con alta confianza
            if response_analysis['is_negative'] and confidence >= 0.7:
                return self._handle_negative_response(
                    suggestion_type, dispatcher, tracker
                )
            
            # Respuesta ambigua o baja confianza
            if response_analysis['is_ambiguous'] or confidence < 0.7:
                return self._handle_ambiguous_response(
                    pending_suggestion, suggestion_type, tracker, dispatcher
                )
            
            # Respuesta no reconocida
            return self._handle_unrecognized_response(
                pending_suggestion, tracker, dispatcher
            )
                
        except Exception as e:
            logger.error(f"Error manejando sugerencias: {e}", exc_info=True)
            return [
                SlotSet("pending_suggestion", None),
                SlotSet("user_engagement_level", "needs_help")
            ]
    
    def _handle_modification_confirmation(
        self,
        pending_suggestion: Dict[str, Any],
        response_analysis: Dict[str, Any],
        tracker: Tracker,
        dispatcher: CollectingDispatcher
    ) -> List[EventType]:
        """Maneja confirmación de modificaciones"""
        is_affirmative = response_analysis.get('is_affirmative', False)
        is_negative = response_analysis.get('is_negative', False)
        confidence = response_analysis.get('confidence', 0.0)
        
        if is_affirmative and confidence >= 0.7:
            self._generate_response(
                dispatcher,
                prompt="Usuario confirmó la modificación. Decí que vas a buscar.",
                tracker=tracker,
                fallback_text="¡Perfecto! Aplicando los cambios..."
            )
            
            # Ejecutar búsqueda con modificaciones
            context = ConversationState.get_conversation_context(tracker)
            actions = pending_suggestion.get('actions', [])
            search_type = pending_suggestion.get('search_type', 'producto')
            
            previous_params = self._extract_previous_params(context)
            rebuilt_params = self._apply_modifications(previous_params, actions)
            
            self._execute_search(search_type, rebuilt_params, dispatcher)
            
            return [
                SlotSet("pending_suggestion", None),
                SlotSet("user_engagement_level", "satisfied")
            ]
        
        elif is_negative and confidence >= 0.7:
            self._generate_response(
                dispatcher,
                prompt="Usuario rechazó la modificación. Aceptá y pedí que reformule.",
                tracker=tracker,
                fallback_text="Entendido. ¿Podés reformular tu solicitud o usar otros términos?"
            )
            
            return [
                SlotSet("pending_suggestion", None),
                SlotSet("user_engagement_level", "needs_help")
            ]
        
        else:
            self._generate_response(
                dispatcher,
                prompt="Respuesta ambigua a confirmación. Pedí clarificación sí/no.",
                tracker=tracker,
                fallback_text="No entendí. ¿Querés que aplique estos cambios? Respondé 'sí' o 'no'.",
                special_case='clarification'
            )
            
            return []
    
    def _handle_affirmative_response(
        self,
        pending_suggestion: Dict[str, Any],
        tracker: Tracker,
        dispatcher: CollectingDispatcher
    ) -> List[EventType]:
        """Maneja respuestas afirmativas"""
        suggestion_type = pending_suggestion.get('suggestion_type', '')
        
        if suggestion_type == 'entity_correction':
            suggestions = pending_suggestion.get('suggestions', [])
            corrected_value = suggestions[0] if suggestions else ''
            entity_type = pending_suggestion.get('entity_type', '')
            
            if corrected_value and entity_type:
                self._generate_response(
                    dispatcher,
                    prompt=f"Usuario aceptó '{corrected_value}' como {entity_type}. "
                           f"Confirmá y decí que vas a buscar.",
                    tracker=tracker,
                    fallback_text=f"¡Perfecto! Buscando con '{corrected_value}'."
                )
                
                success = self._execute_search_with_corrected_entity(
                    {'value': corrected_value, 'type': entity_type},
                    pending_suggestion,
                    dispatcher
                )
                
                return [
                    SlotSet("pending_suggestion", None),
                    SlotSet("user_engagement_level", "satisfied" if success else "needs_help")
                ]
            else:
                self._generate_response(
                    dispatcher,
                    prompt="Hubo un problema técnico. Pedí disculpas.",
                    tracker=tracker,
                    fallback_text="Hubo un problema. ¿Podrías intentar nuevamente?",
                    special_case='error_handling'
                )
                return [
                    SlotSet("pending_suggestion", None),
                    SlotSet("user_engagement_level", "needs_help")
                ]
        
        elif suggestion_type == 'type_correction':
            original_value = pending_suggestion.get('original_value', '')
            correct_type = pending_suggestion.get('correct_type', '')
            
            if original_value and correct_type:
                self._generate_response(
                    dispatcher,
                    prompt=f"Usuario confirmó que '{original_value}' es {correct_type}. "
                           f"Confirmá y decí que vas a buscar.",
                    tracker=tracker,
                    fallback_text=f"¡Entendido! Buscando '{original_value}' como {correct_type}."
                )
                
                self._execute_search_with_corrected_entity(
                    {'value': original_value, 'type': correct_type},
                    pending_suggestion,
                    dispatcher
                )
        
        elif suggestion_type == 'missing_parameters':
            criteria = pending_suggestion.get('required_criteria', 'información')
            
            self._generate_response(
                dispatcher,
                prompt=f"Usuario acepta dar más info. Pedí {criteria} específico.",
                tracker=tracker,
                fallback_text=f"Perfecto. ¿Qué {criteria} específico necesitás?"
            )
        
        return [
            SlotSet("pending_suggestion", None),
            SlotSet("user_engagement_level", "engaged")
        ]
    
    def _handle_negative_response(
        self,
        suggestion_type: str,
        dispatcher: CollectingDispatcher,
        tracker: Tracker
    ) -> List[EventType]:
        """Maneja respuestas negativas"""
        if suggestion_type in ['entity_correction', 'type_correction']:
            prompt = "Usuario rechazó la sugerencia. Aceptá y pedí que escriba el término correcto."
            fallback = "Entendido. ¿Podés escribir el nombre correcto o usar otros criterios?"
        else:
            prompt = "Usuario dice que no. Aceptá y preguntá si necesita otra cosa."
            fallback = "Entendido. ¿Hay algo más en lo que pueda ayudarte?"
        
        self._generate_response(dispatcher, prompt, tracker, fallback)
        
        return [
            SlotSet("pending_suggestion", None),
            SlotSet("user_engagement_level", "needs_help")
        ]
    
    def _handle_ambiguous_response(
        self,
        pending_suggestion: Dict[str, Any],
        suggestion_type: str,
        tracker: Tracker,
        dispatcher: CollectingDispatcher
    ) -> List[EventType]:
        """Maneja respuestas ambiguas"""
        attempts = pending_suggestion.get('clarification_attempts', 0) + 1
        pending_suggestion['clarification_attempts'] = attempts
        
        logger.info(f"[Ambiguo] Intento {attempts}/3")
        
        if attempts >= 3:
            self._generate_response(
                dispatcher,
                prompt="Usuario no responde claramente después de 3 intentos. "
                       "Sugerí empezar de nuevo.",
                tracker=tracker,
                fallback_text="No logro entender. Empecemos de nuevo. ¿Qué necesitás buscar?",
                special_case='clarification'
            )
            
            return [
                SlotSet("pending_suggestion", None),
                SlotSet("user_engagement_level", "needs_help")
            ]
        
        # Construir prompt específico según tipo
        if suggestion_type == 'entity_correction':
            suggestions = pending_suggestion.get('suggestions', [])
            original = pending_suggestion.get('original_value', '')
            if suggestions:
                prompt = (f"Respuesta ambigua. Pedí confirmación directa: "
                         f"¿usa '{suggestions[0]}' en lugar de '{original}'? Sí/no.")
                fallback = (f"No estoy seguro. ¿Buscás '{suggestions[0]}' "
                           f"en lugar de '{original}'? Respondé 'sí' o 'no'.")
            else:
                prompt = "Respuesta ambigua. Pedí que responda sí o no."
                fallback = "No entendí. Respondé 'sí' o 'no' por favor."
        
        elif suggestion_type == 'type_correction':
            original = pending_suggestion.get('original_value', '')
            correct_type = pending_suggestion.get('correct_type', '')
            prompt = f"Respuesta ambigua. Pedí confirmación: ¿'{original}' es {correct_type}? Sí/no."
            fallback = f"No entendí. ¿'{original}' es {correct_type}? Respondé 'sí' o 'no'."
        
        else:
            prompt = "Respuesta ambigua. Pedí aclaración directa."
            fallback = "No entendí. ¿Puedes ser más específico?"
        
        self._generate_response(
            dispatcher,
            prompt,
            tracker,
            fallback,
            special_case='clarification'
        )
        
        return [SlotSet("pending_suggestion", pending_suggestion)]
    
    def _handle_unrecognized_response(
        self,
        pending_suggestion: Dict[str, Any],
        tracker: Tracker,
        dispatcher: CollectingDispatcher
    ) -> List[EventType]:
        """Maneja respuestas no reconocidas"""
        attempts = pending_suggestion.get('clarification_attempts', 0) + 1
        
        logger.warning(f"[No reconocido] Intento {attempts}/3")
        
        if attempts >= 3:
            self._generate_response(
                dispatcher,
                prompt="Después de 3 intentos no se entiende. Sugerí empezar de nuevo.",
                tracker=tracker,
                fallback_text="No logro entender. Empecemos de nuevo. ¿Qué necesitás?",
                special_case='clarification'
            )
            
            return [
                SlotSet("pending_suggestion", None),
                SlotSet("user_engagement_level", "needs_help")
            ]
        
        self._generate_response(
            dispatcher,
            prompt="No reconociste la respuesta. Pedí que responda SOLO sí o no.",
            tracker=tracker,
            fallback_text="No reconozco tu respuesta. Por favor, respondé únicamente 'SÍ' o 'NO'.",
            special_case='clarification'
        )
        
        pending_suggestion['clarification_attempts'] = attempts
        return [SlotSet("pending_suggestion", pending_suggestion)]
    
    def _execute_search_with_corrected_entity(
        self,
        corrected_entity: Dict[str, str],
        pending_suggestion: Dict[str, Any],
        dispatcher: CollectingDispatcher
    ) -> bool:
        """Ejecuta búsqueda con entidad corregida"""
        try:
            search_context = pending_suggestion.get('search_context', {})
            search_type = search_context.get('search_type', 'producto')
            
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
            
            self._execute_search(search_type, search_params, dispatcher)
            return True
            
        except Exception as e:
            logger.error(f"Error ejecutando búsqueda: {e}", exc_info=True)
            return False
    
    def _execute_search(
        self,
        search_type: str,
        params: Dict[str, Any],
        dispatcher: CollectingDispatcher
    ) -> None:
        """Método unificado para ejecutar búsquedas"""
        formatted_params = ", ".join([f"{k}: {v}" for k, v in params.items()])
        message = f"Buscando {search_type}s con {formatted_params}"
        
        dispatcher.utter_message(
            text=message,
            json_message={
                "type": "search_results",
                "search_type": search_type,
                "parameters": params,
                "validated": True,
                "timestamp": datetime.now().isoformat()
            }
        )
    
    def _extract_previous_params(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Extrae parámetros de búsqueda anterior"""
        search_history = context.get('search_history', [])
        return search_history[-1].get('parameters', {}) if search_history else {}
    
    def _apply_modifications(
        self,
        previous_params: Dict[str, Any],
        actions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Aplica modificaciones a parámetros"""
        rebuilt = previous_params.copy()
        
        for action in actions:
            action_type = action.get('type')
            entity_type = action.get('entity_type')
            
            if action_type in ['replace', 'add']:
                rebuilt[entity_type] = action.get('new_value')
        
        return rebuilt
    
    def _handle_obsolete_system_migration(
        self,
        tracker: Tracker,
        dispatcher: CollectingDispatcher
    ) -> Dict[str, Any]:
        """Maneja migración del sistema obsoleto"""
        return {'migrated': False, 'events': []}
    
    def _handle_standard_responses(
        self,
        current_intent: str,
        dispatcher: CollectingDispatcher,
        tracker: Tracker
    ) -> List[EventType]:
        """Maneja respuestas estándar para intents básicos"""
        intent_info = get_intent_info(current_intent)
        responses = intent_info.get("responses", [])
        
        if responses:
            dispatcher.utter_message(text=responses[0])
            return []
        
        # Mapeo de intents a prompts y fallbacks
        intent_configs = {
            "agradecimiento": {
                "prompt": "Usuario agradeció. Respondé cordialmente y ofrecé ayuda.",
                "fallback": "¡De nada! Siempre estoy aquí para ayudarte."
            },
            "afirmar": {
                "prompt": "Usuario confirmó. Preguntá en qué podés ayudar.",
                "fallback": "Perfecto. ¿En qué puedo ayudarte?"
            },
            "denegar": {
                "prompt": "Usuario negó. Aceptá y preguntá si necesita otra cosa.",
                "fallback": "No hay problema. ¿Necesitás algo más?"
            }
        }
        
        config = intent_configs.get(current_intent, {
            "prompt": "Usuario interactuó positivamente. Respondé cordialmente.",
            "fallback": "¡Gracias! ¿En qué más puedo ayudarte?"
        })
        
        self._generate_response(
            dispatcher,
            config["prompt"],
            tracker,
            config["fallback"]
        )
        
        return []