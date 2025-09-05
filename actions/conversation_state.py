# conversation_state.py - Sistema Unificado de Sugerencias - Versión Robusta
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from rasa_sdk import Tracker
from .helpers import (
    is_search_intent, is_small_talk_intent, detect_sentiment_in_message,
    detect_implicit_intentions, get_intent_info, get_search_type_from_intent
)

logger = logging.getLogger(__name__)

def get_next_expected_intents(intent_name: str) -> List[str]:
    """Obtiene los intents que pueden seguir según la configuración"""
    intent_info = get_intent_info(intent_name)
    return intent_info.get("next_intents", [])

def get_slot_safely(tracker: Tracker, slot_name: str, default_value: Any = None) -> Any:
    """
    Obtiene un slot de forma segura, manejando casos donde el slot no existe
    """
    try:
        value = tracker.get_slot(slot_name)
        return value if value is not None else default_value
    except Exception as e:
        logger.warning(f"Slot '{slot_name}' no existe o no se puede acceder: {e}")
        return default_value

# 🔹 ESTADO DE CONVERSACION MEJORADO Y ROBUSTO
class ConversationState:
    @staticmethod
    def get_conversation_context(tracker: Tracker) -> Dict[str, Any]:
        """Extrae contexto completo usando la configuración centralizada de forma robusta"""
        try:
            current_intent = tracker.latest_message.get("intent", {}).get("name", "")
            confidence = tracker.latest_message.get("intent", {}).get("confidence", 0.0)
            user_message = tracker.latest_message.get("text", "")
            
            # Detectar sentimiento y intenciones implícitas
            sentiment = detect_sentiment_in_message(user_message)
            implicit_intentions = detect_implicit_intentions(user_message)
            
            # 🔹 OBTENER SLOTS DE FORMA SEGURA
            # Slots básicos de control
            previous_intent = get_slot_safely(tracker, "last_intent_flow")
            user_sentiment = get_slot_safely(tracker, "user_sentiment", "neutral")
            engagement_level = get_slot_safely(tracker, "user_engagement_level", "neutral")
            
            # Slots del sistema de sugerencias unificado
            pending_suggestion = get_slot_safely(tracker, "pending_suggestion")
            suggestion_context = get_slot_safely(tracker, "suggestion_context")
            
            # Slots de historial y contexto
            search_history = get_slot_safely(tracker, "search_history", [])
            context_decision_pending = get_slot_safely(tracker, "context_decision_pending", False)
            current_search_params = get_slot_safely(tracker, "current_search_params")
            validation_errors = get_slot_safely(tracker, "validation_errors", [])
            
            # 🔹 SLOTS OBSOLETOS - Con manejo graceful
            # Estos slots pueden no existir en configuraciones actualizadas
            pedido_incompleto = get_slot_safely(tracker, "pedido_incompleto", False)
            
            # Si pending_suggestion no existe pero pedido_incompleto sí, migrar el concepto
            if not pending_suggestion and pedido_incompleto:
                logger.info("Detectado sistema obsoleto de pedido_incompleto, usando como fallback")
                # Crear una sugerencia equivalente para mantener compatibilidad
                pending_suggestion = {
                    'suggestion_type': 'missing_parameters',
                    'search_type': 'producto',  # Asumir producto por defecto
                    'awaiting_response': True,
                    'migrated_from_obsolete': True
                }
            
            # 🔹 CONSTRUIR CONTEXTO COMPLETO
            context = {
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
                
                # 🔹 SISTEMA UNIFICADO DE SUGERENCIAS
                'pending_suggestion': pending_suggestion,
                'suggestion_context': suggestion_context,
                'is_confirmation_intent': current_intent in ["afirmar", "denegar"],
                'awaiting_suggestion_response': bool(pending_suggestion),
                
                # 🔹 CONTEXTO DE BÚSQUEDA ACTUAL
                'current_search_params': current_search_params,
                'validation_errors': validation_errors,
                
                # 🔹 INFORMACIÓN DE MIGRACIÓN
                'has_obsolete_slots': pedido_incompleto and not pending_suggestion,
                'system_migrated': bool(pending_suggestion and pending_suggestion.get('migrated_from_obsolete')),
            }
            
            logger.debug(f"Contexto extraído - Intent: {current_intent}, Pending: {bool(pending_suggestion)}, Engagement: {engagement_level}")
            
            return context
            
        except Exception as e:
            logger.error(f"Error extrayendo contexto de conversación: {e}", exc_info=True)
            # Retornar contexto mínimo en caso de error
            return {
                'current_intent': tracker.latest_message.get("intent", {}).get("name", ""),
                'intent_confidence': 0.0,
                'previous_intent': None,
                'search_history': [],
                'entities': [],
                'is_search_intent': False,
                'is_small_talk': False,
                'is_completion_intent': False,
                'expected_next_intents': [],
                'context_decision_pending': False,
                'user_message': tracker.latest_message.get("text", ""),
                'detected_sentiment': "neutral",
                'implicit_intentions': [],
                'current_sentiment_slot': "neutral",
                'engagement_level': "neutral",
                'pending_suggestion': None,
                'suggestion_context': None,
                'is_confirmation_intent': False,
                'awaiting_suggestion_response': False,
                'current_search_params': None,
                'validation_errors': [],
                'has_obsolete_slots': False,
                'system_migrated': False,
                'error_in_context_extraction': True
            }

# 🔹 MANEJADOR UNIFICADO DE SUGERENCIAS - VERSIÓN ROBUSTA
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
            'suggestions': [suggestion] if isinstance(suggestion, str) else suggestion,
            'timestamp': datetime.now().isoformat(),
            'search_context': search_context or {},
            'awaiting_response': True,
            'version': '1.0'
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
            'awaiting_response': True,
            'version': '1.0'
        }
    
    @staticmethod
    def create_parameter_suggestion(search_type: str, intent_name: str, criteria: str,
                                  current_parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        🔹 Crea una sugerencia para parámetros faltantes
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
            'awaiting_response': True,
            'version': '1.0'
        }
    
    @staticmethod
    def handle_suggestion_response(context: Dict[str, Any], user_response: str) -> Dict[str, Any]:
        """Procesa la respuesta del usuario a cualquier tipo de sugerencia"""
        pending = context.get('pending_suggestion')
        if not pending:
            return {'handled': False, 'reason': 'no_pending_suggestion'}
        
        try:
            suggestion_type = pending.get('suggestion_type', '')
            response_lower = user_response.lower().strip()
            
            # Detectar respuestas afirmativas y negativas con más patrones
            affirmative_patterns = [
                "sí", "si", "ok", "dale", "perfecto", "correcto", "exacto", "ese", "esa", 
                "claro", "muy bien", "está bien", "bueno", "ya", "confirmo", "acepto"
            ]
            negative_patterns = [
                "no", "nada", "incorrecto", "otro", "diferente", "mal", "error", 
                "cancelar", "salir", "cambiar", "rechazar"
            ]
            
            is_affirmative = any(pattern in response_lower for pattern in affirmative_patterns)
            is_negative = any(pattern in response_lower for pattern in negative_patterns)
            
            result = {
                'handled': True,
                'is_affirmative': is_affirmative,
                'is_negative': is_negative,
                'suggestion_data': pending,
                'suggestion_type': suggestion_type,
                'processing_timestamp': datetime.now().isoformat()
            }
            
            if suggestion_type == 'entity_correction':
                if is_affirmative:
                    result['action'] = 'accept_suggestion'
                    suggestions = pending.get('suggestions', [])
                    result['corrected_entity'] = {
                        'value': suggestions[0] if suggestions else pending.get('original_value'),
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
                result['action'] = 'parameters_being_provided'
            
            return result
            
        except Exception as e:
            logger.error(f"Error procesando respuesta a sugerencia: {e}", exc_info=True)
            return {
                'handled': False, 
                'reason': 'processing_error',
                'error': str(e)
            }
    
    @staticmethod
    def check_if_suggestion_followed(current_intent: str, pending_suggestion: Dict[str, Any]) -> bool:
        """
        🔹 Verifica si el usuario está siguiendo una sugerencia de parámetros
        """
        if not pending_suggestion:
            return False
        
        try:
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
            
        except Exception as e:
            logger.error(f"Error verificando si se siguió la sugerencia: {e}")
            return False
    
    @staticmethod
    def check_if_suggestion_ignored(current_intent: str, pending_suggestion: Dict[str, Any], 
                                   is_small_talk: bool = False) -> bool:
        """
        🔹 Verifica si el usuario ignoró la sugerencia cambiando de tema
        """
        if not pending_suggestion:
            return False
        
        try:
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
            
        except Exception as e:
            logger.error(f"Error verificando si se ignoró la sugerencia: {e}")
            return False
    
    @staticmethod
    def validate_suggestion_data(suggestion_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Valida que los datos de sugerencia sean correctos
        """
        if not suggestion_data:
            return {'valid': False, 'reason': 'empty_suggestion'}
        
        required_fields = ['suggestion_type', 'timestamp', 'awaiting_response']
        missing_fields = [field for field in required_fields if field not in suggestion_data]
        
        if missing_fields:
            return {
                'valid': False, 
                'reason': 'missing_fields',
                'missing_fields': missing_fields
            }
        
        suggestion_type = suggestion_data.get('suggestion_type')
        valid_types = ['entity_correction', 'type_correction', 'missing_parameters']
        
        if suggestion_type not in valid_types:
            return {
                'valid': False,
                'reason': 'invalid_suggestion_type',
                'provided_type': suggestion_type,
                'valid_types': valid_types
            }
        
        return {'valid': True}
    
    @staticmethod
    def migrate_from_obsolete_system(tracker: Tracker) -> Optional[Dict[str, Any]]:
        """
        Migra desde el sistema obsoleto de pedido_incompleto al nuevo sistema unificado
        """
        try:
            pedido_incompleto = get_slot_safely(tracker, "pedido_incompleto", False)
            
            if pedido_incompleto:
                logger.info("Migrando desde sistema obsoleto pedido_incompleto")
                
                # Crear sugerencia equivalente
                return SuggestionManager.create_parameter_suggestion(
                    search_type="producto",  # Asumir producto por defecto
                    intent_name="buscar_producto",
                    criteria="producto, categoría o proveedor",
                    current_parameters={}
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error migrando desde sistema obsoleto: {e}")
            return None