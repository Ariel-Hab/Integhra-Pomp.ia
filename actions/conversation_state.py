# conversation_state.py - Sistema Unificado de Sugerencias
from typing import Dict, Any, List
from datetime import datetime

from rasa_sdk import Tracker
from .helpers import (
    is_search_intent, is_small_talk_intent, detect_sentiment_in_message,
    detect_implicit_intentions, get_intent_info, get_search_type_from_intent
)

def get_next_expected_intents(intent_name: str) -> List[str]:
    """Obtiene los intents que pueden seguir según la configuración"""
    intent_info = get_intent_info(intent_name)
    return intent_info.get("next_intents", [])

# 🔹 ESTADO DE CONVERSACION MEJORADO
class ConversationState:
    @staticmethod
    def get_conversation_context(tracker: Tracker) -> Dict[str, Any]:
        """Extrae contexto completo usando la configuración centralizada"""
        current_intent = tracker.latest_message.get("intent", {}).get("name", "")
        confidence = tracker.latest_message.get("intent", {}).get("confidence", 0.0)
        user_message = tracker.latest_message.get("text", "")
        
        # Detectar sentimiento y intenciones implícitas
        sentiment = detect_sentiment_in_message(user_message)
        implicit_intentions = detect_implicit_intentions(user_message)
        
        # Usar valores por defecto si los slots no existen
        try:
            previous_intent = tracker.get_slot("last_intent_flow")
            search_history = tracker.get_slot("search_history") or []
            context_decision_pending = tracker.get_slot("context_decision_pending")
            user_sentiment = tracker.get_slot("user_sentiment")
            engagement_level = tracker.get_slot("user_engagement_level")
            # 🔹 NUEVO: Sistema unificado de sugerencias (reemplaza pedido_incompleto y pending_search_data)
            pending_suggestion = tracker.get_slot("pending_suggestion")
            suggestion_context = tracker.get_slot("suggestion_context")
        except:
            previous_intent = None
            search_history = []
            context_decision_pending = None
            user_sentiment = "neutral"
            engagement_level = "neutral"
            pending_suggestion = None
            suggestion_context = None
        
        return {
            'current_intent': current_intent,
            'intent_confidence': confidence,
            'previous_intent': previous_intent,
            'search_history': search_history,
            'entities': tracker.latest_message.get("entities", []),
            'is_search_intent': is_search_intent(current_intent),
            'is_small_talk': is_small_talk_intent(current_intent),
            'is_completion_intent': current_intent == "completar_pedido",
            'expected_next_intents': get_next_expected_intents(previous_intent or ""),
            'context_decision_pending': context_decision_pending,
            'user_message': user_message,
            'detected_sentiment': sentiment,
            'implicit_intentions': implicit_intentions,
            'current_sentiment_slot': user_sentiment,
            'engagement_level': engagement_level,
            # 🔹 NUEVO: Contexto unificado de sugerencias
            'pending_suggestion': pending_suggestion,
            'suggestion_context': suggestion_context,
            'is_confirmation_intent': current_intent in ["afirmar", "denegar"],
            'awaiting_suggestion_response': bool(pending_suggestion)
        }

# 🔹 MANEJADOR UNIFICADO DE SUGERENCIAS
class SuggestionManager:
    """Maneja el estado y flujo unificado de sugerencias (entidades y parámetros)"""
    
    @staticmethod
    def create_entity_suggestion(entity_value: str, entity_type: str, suggestion: str, 
                               search_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Crea una sugerencia para entidad mal escrita"""
        return {
            'suggestion_type': 'entity_correction',
            'original_value': entity_value,
            'entity_type': entity_type,
            'suggestions': [suggestion],
            'timestamp': datetime.now().isoformat(),
            'search_context': search_context or {},
            'awaiting_response': True
        }
    
    @staticmethod
    def create_type_correction(entity_value: str, wrong_type: str, correct_type: str,
                              search_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Crea una sugerencia para corrección de tipo de entidad"""
        return {
            'suggestion_type': 'type_correction',
            'original_value': entity_value,
            'wrong_type': wrong_type,
            'correct_type': correct_type,
            'timestamp': datetime.now().isoformat(),
            'search_context': search_context or {},
            'awaiting_response': True
        }
    
    @staticmethod
    def create_parameter_suggestion(search_type: str, intent_name: str, criteria: str,
                                  current_parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        🔹 NUEVO: Crea una sugerencia para parámetros faltantes
        Esta reemplaza el concepto de pedido_incompleto
        """
        return {
            'suggestion_type': 'missing_parameters',
            'search_type': search_type,
            'intent_name': intent_name,
            'required_criteria': criteria,
            'current_parameters': current_parameters or {},
            'timestamp': datetime.now().isoformat(),
            'search_context': {
                'search_type': search_type,
                'intent': intent_name
            },
            'awaiting_response': True
        }
    
    @staticmethod
    def handle_suggestion_response(context: Dict[str, Any], user_response: str) -> Dict[str, Any]:
        """Procesa la respuesta del usuario a cualquier tipo de sugerencia"""
        pending = context['pending_suggestion']
        if not pending:
            return {'handled': False}
        
        suggestion_type = pending.get('suggestion_type', '')
        response_lower = user_response.lower()
        
        # Detectar respuestas afirmativas y negativas
        is_affirmative = any(word in response_lower for word in [
            "sí", "si", "ok", "dale", "perfecto", "correcto", "exacto", "ese", "esa"
        ])
        is_negative = any(word in response_lower for word in [
            "no", "nada", "incorrecto", "otro", "diferente"
        ])
        
        result = {
            'handled': True,
            'is_affirmative': is_affirmative,
            'is_negative': is_negative,
            'suggestion_data': pending,
            'suggestion_type': suggestion_type
        }
        
        if suggestion_type == 'entity_correction':
            if is_affirmative:
                result['action'] = 'accept_suggestion'
                result['corrected_entity'] = {
                    'value': pending['suggestions'][0],
                    'type': pending['entity_type']
                }
            elif is_negative:
                result['action'] = 'reject_suggestion'
            else:
                result['action'] = 'unclear_response'
        
        elif suggestion_type == 'type_correction':
            if is_affirmative:
                result['action'] = 'accept_type_correction'
                result['corrected_entity'] = {
                    'value': pending['original_value'],
                    'type': pending['correct_type']
                }
            elif is_negative:
                result['action'] = 'reject_suggestion'
            else:
                result['action'] = 'unclear_response'
        
        elif suggestion_type == 'missing_parameters':
            # Para parámetros faltantes, cualquier intent de búsqueda o completar_pedido
            # del mismo tipo se considera como "siguiendo la sugerencia"
            # Esto se maneja en el action principal, no aquí
            result['action'] = 'parameters_being_provided'
        
        return result
    
    @staticmethod
    def check_if_suggestion_followed(current_intent: str, pending_suggestion: Dict[str, Any]) -> bool:
        """
        🔹 NUEVO: Verifica si el usuario está siguiendo una sugerencia de parámetros
        """
        if not pending_suggestion:
            return False
        
        suggestion_type = pending_suggestion.get('suggestion_type', '')
        
        if suggestion_type == 'missing_parameters':
            suggested_search_type = pending_suggestion.get('search_type', '')
            
            # Si es completar_pedido, definitivamente está siguiendo la sugerencia
            if current_intent == 'completar_pedido':
                return True
            
            # Si es una búsqueda del mismo tipo, está siguiendo la sugerencia
            if current_intent.startswith('buscar_'):
                current_search_type = get_search_type_from_intent(current_intent)
                if current_search_type == suggested_search_type:
                    return True
        
        return False
    
    @staticmethod
    def check_if_suggestion_ignored(current_intent: str, pending_suggestion: Dict[str, Any], 
                                   is_small_talk: bool = False) -> bool:
        """
        🔹 NUEVO: Verifica si el usuario ignoró la sugerencia cambiando de tema
        """
        if not pending_suggestion:
            return False
        
        # Si es small talk, definitivamente cambió de tema
        if is_small_talk:
            return True
        
        suggestion_type = pending_suggestion.get('suggestion_type', '')
        
        if suggestion_type == 'missing_parameters':
            suggested_search_type = pending_suggestion.get('search_type', '')
            
            # Si es una búsqueda de diferente tipo, ignoró la sugerencia
            if current_intent.startswith('buscar_'):
                current_search_type = get_search_type_from_intent(current_intent)
                if current_search_type != suggested_search_type:
                    return True
        
        elif suggestion_type in ['entity_correction', 'type_correction']:
            suggested_search_type = pending_suggestion.get('search_context', {}).get('search_type', '')
            
            # Si es una búsqueda de diferente tipo, ignoró la sugerencia
            if current_intent.startswith('buscar_'):
                current_search_type = get_search_type_from_intent(current_intent)
                if current_search_type != suggested_search_type:
                    return True
        
        return False