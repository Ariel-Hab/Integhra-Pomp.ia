from asyncio.log import logger
import difflib
from typing import Any, Dict, List, Tuple, Optional
from xml.dom.minidom import Text

from actions.config import INTENT_CONFIG, INTENT_TO_SLOTS, LOOKUP_TABLES, normalize_text
from scripts.config_loader import ConfigLoader
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, EventType
from datetime import datetime
from .conversation_state import ConversationState, SuggestionManager


def get_search_type_from_intent(intent_name: str) -> str:
    """Extrae el tipo de búsqueda del nombre del intent"""
    if intent_name == "buscar_producto":
        return "producto"
    elif intent_name == "buscar_oferta":
        return "oferta"
    return "producto"

# 🔹 VALIDADOR DE ENTIDADES MEJORADO CON SUGERENCIAS PENDIENTES
class EntityValidationHandler:
    """Maneja validación avanzada de entidades con sistema de sugerencias pendientes"""
    
    def __init__(self):
        from actions.config import LOOKUP_TABLES
        self.lookup_tables = LOOKUP_TABLES
        self.entity_type_names = {
            "producto": "producto",
            "producto_nombre": "producto", 
            "nombre_producto": "producto",
            "proveedor": "proveedor",
            "categoria": "categoría",
            "ingrediente_activo": "ingrediente activo",
            "compuesto": "ingrediente activo",
            "dosis": "dosis",
            "cantidad": "cantidad"
        }
    
    def validate_entity_with_suggestions(self, entity_value: str, entity_type: str, 
                                       search_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Valida una entidad y retorna información completa de validación
        Retorna: dict con status, suggestions, pending_suggestion_data, etc.
        """
        if not entity_value or not entity_type:
            return {'is_valid': False, 'reason': 'empty_value'}
        
        # Mapear tipo de entidad para lookup
        lookup_key = self._get_lookup_key(entity_type)
        
        # Si no hay lookup table para este tipo, considerarla válida
        if lookup_key not in self.lookup_tables or not self.lookup_tables.get(lookup_key):
            logger.debug(f"[EntityValidation] No lookup table for '{lookup_key}', accepting '{entity_value}'")
            return {'is_valid': True}
        
        normalized_value = normalize_text(entity_value)
        lookup_values = self.lookup_tables[lookup_key]
        normalized_lookup = [normalize_text(v) for v in lookup_values]
        
        # Validación exacta
        if normalized_value in normalized_lookup:
            logger.info(f"[EntityValidation] Valid entity: '{entity_value}' as {entity_type}")
            return {'is_valid': True}
        
        # Buscar sugerencias similares - SOLO UNA SUGERENCIA
        similar_matches = difflib.get_close_matches(
            normalized_value, normalized_lookup, n=1, cutoff=0.6  # Solo 1 sugerencia
        )
        
        # Obtener valor original correspondiente a la coincidencia
        suggestion = None
        if similar_matches:
            for original in lookup_values:
                if normalize_text(original) == similar_matches[0]:
                    suggestion = original
                    break
        
        if suggestion:
            # Crear datos de sugerencia pendiente
            pending_suggestion = SuggestionManager.create_entity_suggestion(
                entity_value, entity_type, suggestion, search_context
            )
            
            return {
                'is_valid': False,
                'has_suggestions': True,
                'suggestions': [suggestion],  # Solo una sugerencia
                'pending_suggestion_data': pending_suggestion,
                'validation_message': self._create_suggestion_message(entity_value, entity_type, suggestion)
            }
        else:
            # Verificar si existe en otros tipos
            correct_type = self._find_correct_type(entity_value)
            if correct_type:
                pending_suggestion = SuggestionManager.create_type_correction(
                    entity_value, entity_type, correct_type, search_context
                )
                
                return {
                    'is_valid': False,
                    'wrong_type': True,
                    'correct_type': correct_type,
                    'pending_suggestion_data': pending_suggestion,
                    'validation_message': self._create_type_correction_message(entity_value, entity_type, correct_type)
                }
            else:
                return {
                    'is_valid': False,
                    'no_suggestions': True,
                    'validation_message': self._create_no_suggestions_message(entity_value, entity_type)
                }
    
    def _get_lookup_key(self, entity_type: str) -> str:
        """Convierte el tipo de entidad al key correcto para lookup"""
        if entity_type == "compuesto":
            return "ingrediente_activo"
        return entity_type
    
    def _find_correct_type(self, entity_value: str) -> str:
        """Busca en qué tipo de entidad existe el valor"""
        normalized_value = normalize_text(entity_value)
        
        for lookup_key, values in self.lookup_tables.items():
            if not values:
                continue
                
            normalized_lookup = [normalize_text(v) for v in values]
            if normalized_value in normalized_lookup:
                return lookup_key
        
        return None
    
    def _create_suggestion_message(self, entity_value: str, entity_type: str, suggestion: str) -> str:
        """Crea mensaje para sugerencia de entidad"""
        entity_type_name = self.entity_type_names.get(entity_type, entity_type)
        return f"🔍 '{entity_value}' no es un {entity_type_name} válido. ¿Te refieres a '{suggestion}'?"
    
    def _create_type_correction_message(self, entity_value: str, wrong_type: str, correct_type: str) -> str:
        """Crea mensaje para corrección de tipo"""
        wrong_type_name = self.entity_type_names.get(wrong_type, wrong_type)
        correct_type_name = self.entity_type_names.get(correct_type, correct_type)
        
        return f"✅ '{entity_value}' existe, pero es un {correct_type_name}, no un {wrong_type_name}. ¿Quieres buscar por {correct_type_name}?"
    
    def _create_no_suggestions_message(self, entity_value: str, entity_type: str) -> str:
        """Crea mensaje cuando no hay sugerencias"""
        entity_type_name = self.entity_type_names.get(entity_type, entity_type)
        return f"❌ '{entity_value}' no es un {entity_type_name} válido y no encontré alternativas similares. Verifica el nombre del {entity_type_name}."


# 🔹 MANEJADOR DE BÚSQUEDAS CON SISTEMA UNIFICADO DE SUGERENCIAS
class EnhancedSearchHandler:
    def __init__(self):
        self.lookup_tables = LOOKUP_TABLES
        self.entities_config = INTENT_CONFIG.get("entities", {})
        self.validator = EntityValidationHandler()
    
    def extract_and_validate_search_parameters(self, tracker: Tracker, intent_name: str, search_type: str, dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """
        Extrae y valida parámetros con manejo unificado de sugerencias
        """
        entities = tracker.latest_message.get("entities", [])
        valid_params = {}
        validation_errors = []
        pending_suggestions = []
        
        # Obtener entidades válidas desde el config
        valid_entities = ConfigLoader.get_entities_for_intent(INTENT_CONFIG, intent_name)
        
        entity_mappings = {
            "producto": "nombre",
            "producto_nombre": "nombre",
            "proveedor": "proveedor",
            "cantidad": "cantidad", 
            "dosis": "dosis",
            "ingrediente_activo": "ingrediente_activo",
            "compuesto": "ingrediente_activo",
            "categoria": "categoria"
        }
        
        logger.debug(f"[SearchHandler] Entities detected: {[(e.get('entity'), e.get('value')) for e in entities]}")
        logger.debug(f"[SearchHandler] Valid entities for {intent_name}: {valid_entities}")
        
        for entity in entities:
            entity_type = entity.get("entity")
            entity_value = entity.get("value")
            
            if not entity_value:
                continue
            
            # Verificar si la entidad es válida para este intent
            if entity_type not in valid_entities:
                logger.warning(f"[SearchHandler] Entity '{entity_type}' not valid for {search_type} search")
                continue
            
            # Validar entidad con sugerencias
            search_context = {
                'intent': intent_name,
                'search_type': search_type,
                'entities': entities
            }
            
            result = self.validator.validate_entity_with_suggestions(entity_value, entity_type, search_context)
            
            if result.get('is_valid'):
                mapped_key = entity_mappings.get(entity_type, entity_type)
                valid_params[mapped_key] = entity_value
                logger.info(f"[SearchHandler] Valid entity added: {entity_type}={entity_value} -> {mapped_key}")
            
            elif result.get('has_suggestions') or result.get('wrong_type'):
                # Guardar sugerencia pendiente
                pending_suggestions.append(result['pending_suggestion_data'])
                validation_errors.append({
                    'entity_value': entity_value,
                    'entity_type': entity_type,
                    'message': result['validation_message']
                })
            
            else:
                validation_errors.append({
                    'entity_value': entity_value,
                    'entity_type': entity_type,
                    'message': result['validation_message']
                })
        
        return {
            'valid_params': valid_params,
            'validation_errors': validation_errors,
            'pending_suggestions': pending_suggestions
        }
    
    def validate_search_parameters(self, intent_name: str, params: Dict[str, str]) -> Dict[str, Any]:
        """Valida parámetros usando reglas del config"""
        validation_rules = ConfigLoader.get_validation_rules_for_intent(INTENT_CONFIG, intent_name)
        
        if not validation_rules:
            return {'is_complete': len(params) > 0, 'missing_message': ''}
        
        requires_at_least_one = validation_rules.get("requires_at_least_one", [])
        has_required = any(param in params for param in requires_at_least_one)
        
        if has_required or len(params) > 0:
            return {'is_complete': True, 'missing_message': ''}
        else:
            criteria = self.get_human_readable_criteria(intent_name)
            return {
                'is_complete': False, 
                'missing_message': f"Especifica al menos: {criteria}"
            }
    
    def get_human_readable_criteria(self, intent_name: str) -> str:
        """Obtiene criterios legibles desde la configuración"""
        valid_entities = ConfigLoader.get_entities_for_intent(INTENT_CONFIG, intent_name)
        
        readable_mappings = {
            "producto": "nombre del producto",
            "proveedor": "proveedor",
            "categoria": "categoría",
            "ingrediente_activo": "ingrediente activo",
            "compuesto": "compuesto activo",
            "dosis": "dosis",
            "cantidad": "cantidad"
        }
        
        if not valid_entities:
            return "nombre del producto, proveedor, categoría, ingrediente activo, dosis o cantidad"
        
        readable_criteria = []
        for entity in valid_entities:
            readable = readable_mappings.get(entity, entity)
            readable_criteria.append(readable)
        
        if len(readable_criteria) > 1:
            return ", ".join(readable_criteria[:-1]) + " o " + readable_criteria[-1]
        elif len(readable_criteria) == 1:
            return readable_criteria[0]
        else:
            return "algún criterio de búsqueda"
    
    def process_search_request(self, intent_name: str, tracker: Tracker, dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """
        Procesa solicitud de búsqueda con sistema unificado de sugerencias
        """
        search_type = get_search_type_from_intent(intent_name)
        
        # Extraer y validar parámetros
        validation_result = self.extract_and_validate_search_parameters(tracker, intent_name, search_type, dispatcher)
        
        valid_params = validation_result['valid_params']
        validation_errors = validation_result['validation_errors']
        pending_suggestions = validation_result['pending_suggestions']
        
        logger.info(f"[SearchHandler] Processing {search_type} search - Valid params: {valid_params}, Errors: {len(validation_errors)}, Suggestions: {len(pending_suggestions)}")
        
        # Si hay sugerencias de entidades mal escritas/tipos incorrectos, priorizar la primera
        if pending_suggestions:
            first_suggestion = pending_suggestions[0]
            
            # Enviar mensaje de sugerencia
            for error in validation_errors:
                if error.get('message'):
                    dispatcher.utter_message(error['message'])
                    break
            
            return {
                'success': False,
                'has_entity_suggestions': True,
                'pending_suggestion_data': first_suggestion,
                'search_type': search_type,
                'parameters': valid_params
            }
        
        # Si hay errores sin sugerencias
        if validation_errors:
            for error in validation_errors:
                if error.get('message'):
                    dispatcher.utter_message(error['message'])
            
            return {
                'success': False,
                'validation_failed': True,
                'search_type': search_type,
                'parameters': valid_params
            }
        
        # Validar completitud usando reglas del config
        validation_check = self.validate_search_parameters(intent_name, valid_params)
        
        if validation_check['is_complete']:
            return {
                'success': True,
                'search_type': search_type,
                'parameters': valid_params,
                'message': f"Buscando {search_type}s con los criterios especificados..."
            }
        else:
            # CREAR SUGERENCIA DE PARÁMETROS FALTANTES
            criteria = self.get_human_readable_criteria(intent_name)
            message = f"Para buscar {search_type}s necesito que especifiques al menos uno de estos criterios: {criteria}."
            
            # Crear sugerencia de parámetros faltantes
            parameter_suggestion = SuggestionManager.create_parameter_suggestion(
                search_type, intent_name, criteria, valid_params
            )
            
            dispatcher.utter_message(message)
            
            return {
                'success': False,
                'has_parameter_suggestions': True,
                'pending_suggestion_data': parameter_suggestion,
                'search_type': search_type,
                'parameters': valid_params
            }

# 🔹 ACTION PRINCIPAL CON SISTEMA UNIFICADO

class ActionBusquedaSituacion(Action):
    """Action principal de búsqueda con sistema unificado de sugerencias"""
    
    def name(self) -> Text:
        return "action_busqueda_situacion"
    
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        context = ConversationState.get_conversation_context(tracker)
        search_handler = EnhancedSearchHandler()
        
        logger.info(f"[BusquedaSituacion] Intent: {context['current_intent']}, Awaiting suggestion: {context['awaiting_suggestion_response']}")
        
        events = []
        
        # Actualizar slot de sentimiento si cambió
        if context['detected_sentiment'] != context['current_sentiment_slot']:
            events.append(SlotSet("user_sentiment", context['detected_sentiment']))
        
        # DETECTAR SI EL USUARIO CAMBIÓ DE TEMA (descartando sugerencias previas)
        if context['awaiting_suggestion_response']:
            user_ignored_suggestion = self._check_if_user_ignored_suggestion(context)
            if user_ignored_suggestion:
                logger.info("[BusquedaSituacion] Usuario ignoró sugerencia previa, limpiando estado")
                events.extend([
                    SlotSet("pending_suggestion", None),
                    SlotSet("user_engagement_level", "topic_changed")
                ])
        
        # Procesar la búsqueda
        if context['is_completion_intent']:
            result = self._handle_completion(context, search_handler, tracker, dispatcher)
        elif context['is_search_intent']:
            result = search_handler.process_search_request(
                context['current_intent'], tracker, dispatcher
            )
        else:
            # Fallback
            dispatcher.utter_message("¿En qué puedo ayudarte hoy?")
            return events
        
        # MANEJAR SUGERENCIAS DE ENTIDADES (mal escritas/tipo incorrecto)
        if result and result.get('has_entity_suggestions'):
            pending_suggestion = result['pending_suggestion_data']
            
            events.extend([
                SlotSet("pending_suggestion", pending_suggestion),
                SlotSet("user_engagement_level", "awaiting_confirmation")
            ])
            
            logger.info(f"[BusquedaSituacion] Sugerencia de entidad creada: {pending_suggestion}")
            return events
        
        # MANEJAR SUGERENCIAS DE PARÁMETROS FALTANTES
        elif result and result.get('has_parameter_suggestions'):
            pending_suggestion = result['pending_suggestion_data']
            
            events.extend([
                SlotSet("pending_suggestion", pending_suggestion),
                SlotSet("user_engagement_level", "awaiting_parameters")
            ])
            
            logger.info(f"[BusquedaSituacion] Sugerencia de parámetros creada: {pending_suggestion}")
            return events
        
        # MANEJAR BÚSQUEDA EXITOSA
        elif result and result['success']:
            search_type = result['search_type']
            search_params = result.get('parameters', {})
            
            # Crear mensaje para el usuario
            if search_params:
                criterios = []
                for key, value in search_params.items():
                    criterios.append(f"{key}: {value}")
                user_message = f"Buscando {search_type}s con {', '.join(criterios)}..."
            else:
                user_message = f"Buscando {search_type}s disponibles..."
            
            # Enviar respuesta al frontend
            dispatcher.utter_message(
                text=user_message,
                json_message={
                    "type": "search",
                    "search_type": search_type,
                    "parameters": search_params,
                    "message": result.get('message', user_message),
                    "validated": True
                }
            )
            
            logger.info(f"[BusquedaSituacion] Búsqueda exitosa: {search_params}")
            
            # Actualizar historial y limpiar sugerencias
            search_history = context['search_history']
            search_history.append({
                'timestamp': datetime.now().isoformat(),
                'type': search_type,
                'parameters': search_params,
                'status': 'completed'
            })
            
            events.extend([
                SlotSet("search_history", search_history),
                SlotSet("pending_suggestion", None),  # Limpiar sugerencias
                SlotSet("user_engagement_level", "satisfied")
            ])
        
        return events
    
    def _check_if_user_ignored_suggestion(self, context: Dict[str, Any]) -> bool:
        """
        Detecta si el usuario ignoró la sugerencia previa cambiando de tema
        """
        current_intent = context['current_intent']
        pending_suggestion = context.get('pending_suggestion', {})
        
        if not pending_suggestion:
            return False
        
        suggestion_type = pending_suggestion.get('suggestion_type', '')
        original_search_type = pending_suggestion.get('search_context', {}).get('search_type', '')
        
        # Si es small talk, definitivamente cambió de tema
        if context['is_small_talk']:
            return True
        
        # Si es una búsqueda pero de diferente tipo
        if context['is_search_intent']:
            current_search_type = get_search_type_from_intent(current_intent)
            if current_search_type != original_search_type:
                return True
        
        # Si es completar_pedido para el mismo tipo, NO ignoró la sugerencia
        if current_intent == "completar_pedido":
            return False
        
        # Si es el mismo intent de búsqueda, NO ignoró la sugerencia (está siguiéndola)
        if context['is_search_intent'] and get_search_type_from_intent(current_intent) == original_search_type:
            return False
        
        return False
    
    def _handle_completion(self, context: Dict[str, Any], search_handler: EnhancedSearchHandler, 
                          tracker: Tracker, dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """
        Maneja el intent completar_pedido - ahora también responde a sugerencias de parámetros
        """
        # Verificar si hay sugerencia pendiente de parámetros
        pending_suggestion = context.get('pending_suggestion', {})
        
        if pending_suggestion and pending_suggestion.get('suggestion_type') == 'missing_parameters':
            # El usuario está respondiendo a la sugerencia de parámetros faltantes
            search_type = pending_suggestion.get('search_type', 'producto')
            intent_name = f"buscar_{search_type}"
            
            # Extraer nuevos parámetros
            validation_result = search_handler.extract_and_validate_search_parameters(
                tracker, intent_name, search_type, dispatcher
            )
            new_params = validation_result['valid_params']
            
            if new_params:
                # Combinar con parámetros previos
                previous_params = pending_suggestion.get('current_parameters', {})
                merged_params = {**previous_params, **new_params}
                
                logger.info(f"[Completion] Parámetros completados: {merged_params}")
                
                return {
                    'success': True,
                    'search_type': search_type,
                    'parameters': merged_params,
                    'message': f"Completando búsqueda de {search_type}s..."
                }
            else:
                dispatcher.utter_message("Necesito que especifiques algún criterio de búsqueda adicional.")
                return {'success': False, 'needs_completion': True}
        
        else:
            dispatcher.utter_message("No tienes ninguna búsqueda pendiente para completar. ¿Qué quieres buscar?")
            return {'success': False, 'needs_new_search': True}


def handle_busqueda_integrado(dispatcher, tracker, domain):
    """DEPRECATED - Mantenido por compatibilidad"""
    dispatcher.utter_message("Función migrada al nuevo sistema. ¿Qué quieres buscar?")
    return {'success': False, 'validation_failed': False, 'events': []}

def _map_slot_to_frontend_key(slot):
    """Mapear slots internos a keys que espera el frontend"""
    mapping = {
        "producto_nombre": "nombre",
        "producto": "nombre",
        "nombre_producto": "nombre",
        "proveedor": "proveedor",
        "cantidad": "cantidad", 
        "dosis": "dosis",
        "ingrediente_activo": "ingrediente_activo",
        "compuesto": "ingrediente_activo",
        "categoria": "categoria"
    }
    return mapping.get(slot, slot)