from asyncio.log import logger
import difflib
from random import choice
from typing import Any, Dict, List
from xml.dom.minidom import Text

from actions.helpers import validate_entities_for_intent
from actions.logger import log_message
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, EventType
from datetime import datetime
from .conversation_state import ConversationState

class ActionFallback(Action):
    """Fallback avanzado con detección de sentimiento, análisis de entidades y manejo de ambigüedad"""
    
    def name(self) -> Text:
        return "action_fallback"
    
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        # Obtener contexto de conversación
        log_message(tracker, nlu_conf_threshold=0.6)
        context = ConversationState.get_conversation_context(tracker)
        user_msg = context['user_message']
        sentiment = context['detected_sentiment']
        implicit_intentions = context['implicit_intentions']
        
        # Obtener intent actual y entidades
        current_intent = tracker.latest_message.get('intent', {}).get('name', 'unknown')
        entities = tracker.latest_message.get('entities', [])
        
        # ✅ NUEVA PRIORIDAD: Obtener sugerencia pendiente del sistema unificado
        pending_suggestion = context.get('pending_suggestion')
        awaiting_suggestion_response = context.get('awaiting_suggestion_response', False)
        
        # Obtener slots activos (compatibilidad con sistema obsoleto)
        pending_search = tracker.get_slot('pending_search')
        pedido_incompleto = tracker.get_slot('pedido_incompleto')
        user_engagement_level = tracker.get_slot('user_engagement_level')
        
        # Logging detallado del contexto actual
        self._log_context_analysis(user_msg, current_intent, sentiment, implicit_intentions, 
                                 entities, pending_suggestion, awaiting_suggestion_response, 
                                 user_engagement_level)
        
        # Analizar entidades para determinar intención (con validación mejorada)
        entity_analysis = self._analyze_entities_with_fragment_protection(entities)
        
        events = []
        events.append(SlotSet("user_sentiment", sentiment))
        
        # ✅ PRIORIDAD 1: Verificar si está completando una sugerencia pendiente
        if awaiting_suggestion_response and pending_suggestion:
            logger.info(f"[Fallback Decision] PRIORIDAD: Usuario completando sugerencia pendiente")
            events.extend(self._handle_suggestion_completion(context, entity_analysis, dispatcher))
            return events
        
        # ✅ PRIORIDAD 2: Verificar si ignoró sugerencia y cambió de tema
        elif pending_suggestion and not awaiting_suggestion_response:
            from ..conversation_state import SuggestionManager
            if SuggestionManager.check_if_suggestion_ignored(current_intent, pending_suggestion, context['is_small_talk']):
                logger.info("[Fallback Decision] Usuario ignoró sugerencia pendiente")
                events.extend(self._handle_ignored_suggestion(pending_suggestion, context, entity_analysis, dispatcher))
                return events
        
        # Resto de la lógica original (sin cambios)...
        if current_intent in ['off_topic', 'out_of_scope']:
            logger.info(f"[Fallback Decision] Mensaje fuera de contexto detectado: {current_intent}")
            events.extend(self._handle_out_of_scope(context, entity_analysis, dispatcher))
            
        elif current_intent == 'ambiguity_fallback':
            logger.info(f"[Fallback Decision] Ambigüedad detectada con entidades: {[e['entity'] for e in entities]}")
            events.extend(self._handle_ambiguity(context, entity_analysis, dispatcher))
            
        elif sentiment == "rejection":
            logger.info("[Fallback Decision] Sentimiento de rechazo detectado")
            events.extend(self._handle_rejection(context, dispatcher))
            
        elif sentiment == "negative":
            logger.info("[Fallback Decision] Feedback negativo detectado")
            events.extend(self._handle_negative_feedback(context, dispatcher))
            
        elif "search_intentions" in implicit_intentions or entity_analysis['has_product_related']:
            logger.info(f"[Fallback Decision] Intención de búsqueda implícita o entidades de producto detectadas")
            events.extend(self._handle_implicit_search(context, entity_analysis, dispatcher))
            
        elif "help_requests" in implicit_intentions:
            logger.info("[Fallback Decision] Solicitud de ayuda detectada")
            events.extend(self._handle_help_request(context, dispatcher))
            
        elif pending_search or pedido_incompleto:
            logger.info(f"[Fallback Decision] Búsqueda pendiente o pedido incompleto activo (sistema obsoleto)")
            events.extend(self._handle_pending_search_fallback(context, entity_analysis, dispatcher))
            
        else:
            logger.info("[Fallback Decision] Fallback general - sin contexto específico")
            events.extend(self._handle_general_fallback(context, entity_analysis, dispatcher))
        
        return events
    
    def _log_context_analysis(self, user_msg: str, intent: str, sentiment: str, 
                            implicit_intentions: List[str], entities: List[Dict], 
                            pending_suggestion: Any, awaiting_response: bool, engagement_level: str):
        """✅ LOGGING MEJORADO: Análisis detallado del contexto incluyendo sistema unificado de sugerencias"""
        entity_summary = {e['entity']: e['value'] for e in entities} if entities else {}
        
        suggestion_info = "Ninguna"
        if pending_suggestion:
            suggestion_type = pending_suggestion.get('suggestion_type', 'unknown')
            suggestion_search_type = pending_suggestion.get('search_type', 'N/A')
            suggestion_info = f"{suggestion_type} ({suggestion_search_type})"
        
        logger.info(f"""
=== ANÁLISIS DE CONTEXTO FALLBACK MEJORADO ===
Mensaje del usuario: "{user_msg}"
Intent detectado: {intent}
Sentimiento: {sentiment}
Intenciones implícitas: {implicit_intentions}
Entidades detectadas: {entity_summary}
Sistema Unificado de Sugerencias:
  - Sugerencia pendiente: {suggestion_info}
  - Esperando respuesta: {'Sí' if awaiting_response else 'No'}
Estado del usuario:
  - user_engagement_level: {engagement_level}
=================================================
        """)
    
    def _analyze_entities_with_fragment_protection(self, entities: List[Dict]) -> Dict[str, Any]:
        """✅ ANÁLISIS MEJORADO: Analiza las entidades con protección contra fragmentos de palabras"""
        
        # Usar el helper mejorado para validar todas las entidades
        validation_result = validate_entities_for_intent(
            entities, 
            intent_name=None,  # No tenemos intent específico en fallback
            min_length=3, 
            check_fragments=True  # ✅ Activar protección anti-fragmentos
        )
        
        analysis = {
            'has_product_related': False,
            'has_commercial_intent': False,
            'product_entities': [],
            'commercial_entities': [],
            'context_entities': [],
            'entity_count': len(entities),
            'valid_entity_count': len(validation_result['valid_params']),
            'rejected_fragments': 0
        }
        
        # Contar fragmentos rechazados analizando entidades originales vs validadas
        original_values = [e.get('value', '') for e in entities if e.get('value')]
        analysis['rejected_fragments'] = len(original_values) - analysis['valid_entity_count']
        
        # Categorizar entidades válidas
        product_related = ['nombre', 'animal', 'sintoma']  # Parámetros mapeados
        commercial_related = ['empresa', 'cantidad_descuento', 'cantidad_bonificacion', 'cantidad', 'precio']
        
        for param_name, param_value in validation_result['valid_params'].items():
            if param_name in product_related:
                analysis['has_product_related'] = True
                analysis['product_entities'].append({'type': param_name, 'value': param_value})
                
            elif param_name in commercial_related:
                analysis['has_commercial_intent'] = True
                analysis['commercial_entities'].append({'type': param_name, 'value': param_value})
                
            else:
                analysis['context_entities'].append({'type': param_name, 'value': param_value})
        
        logger.info(f"[Entity Analysis Enhanced] Total: {analysis['entity_count']}, "
                   f"Válidos: {analysis['valid_entity_count']}, "
                   f"Fragmentos rechazados: {analysis['rejected_fragments']}, "
                   f"Producto-relacionado: {analysis['has_product_related']}, "
                   f"Comercial: {analysis['has_commercial_intent']}")
        
        # Agregar datos de validación completos para uso posterior
        analysis['validation_result'] = validation_result
        
        return analysis

    def _handle_suggestion_completion(self, context: Dict[str, Any], entity_analysis: Dict, 
                                    dispatcher: CollectingDispatcher) -> List[EventType]:
        """✅ NUEVA FUNCIÓN: Maneja cuando el usuario está completando una sugerencia pendiente"""
        logger.info("[Action] Manejando completación de sugerencia pendiente")
        
        pending_suggestion = context.get('pending_suggestion', {})
        suggestion_type = pending_suggestion.get('suggestion_type', '')
        
        events = []
        
        try:
            if suggestion_type == 'missing_parameters':
                # Usuario está proporcionando parámetros faltantes para búsqueda
                search_type = pending_suggestion.get('search_type', 'producto')
                current_parameters = pending_suggestion.get('current_parameters', {})
                
                # Obtener parámetros válidos del análisis de entidades
                new_params = entity_analysis.get('validation_result', {}).get('valid_params', {})
                
                if new_params:
                    # Combinar parámetros anteriores con nuevos
                    combined_params = {**current_parameters, **new_params}
                    
                    params_text = ", ".join([f"{k}: {v}" for k, v in new_params.items()])
                    dispatcher.utter_message(f"¡Perfecto! Agregando {params_text} a tu búsqueda de {search_type}s.")
                    
                    # Ejecutar búsqueda con parámetros combinados
                    search_message = f"Buscando {search_type}s con: " + ", ".join([f"{k}: {v}" for k, v in combined_params.items()])
                    
                    dispatcher.utter_message(
                        text=search_message,
                        json_message={
                            "type": "search_results",
                            "search_type": search_type,
                            "parameters": combined_params,
                            "completed_from_suggestion": True,
                            "original_parameters": current_parameters,
                            "added_parameters": new_params,
                            "timestamp": datetime.now().isoformat()
                        }
                    )
                    
                    # Actualizar historial
                    search_history = context.get('search_history', [])
                    search_history.append({
                        'timestamp': datetime.now().isoformat(),
                        'type': search_type,
                        'parameters': combined_params,
                        'status': 'completed_from_suggestion',
                        'original_suggestion': suggestion_type
                    })
                    
                    events.extend([
                        SlotSet("search_history", search_history),
                        SlotSet("pending_suggestion", None),
                        SlotSet("user_engagement_level", "satisfied")
                    ])
                    
                else:
                    # No se detectaron parámetros válidos
                    criteria = pending_suggestion.get('required_criteria', 'información adicional')
                    dispatcher.utter_message(f"No pude identificar parámetros válidos en tu mensaje. ¿Puedes ser más específico con {criteria}?")
                    
                    events.append(SlotSet("user_engagement_level", "needs_clarification"))
            
            elif suggestion_type in ['entity_correction', 'type_correction']:
                # Para correcciones de entidad, redirigir a ActionConfNegAgradecer
                dispatcher.utter_message("Si aceptas la sugerencia, responde 'sí'. Si no, puedes decir 'no' o intentar con otros términos.")
                
            return events
            
        except Exception as e:
            logger.error(f"[Action] Error manejando completación de sugerencia: {e}", exc_info=True)
            dispatcher.utter_message("Hubo un error procesando tu respuesta. ¿Puedes intentar nuevamente?")
            
            return [
                SlotSet("pending_suggestion", None),
                SlotSet("user_engagement_level", "needs_help")
            ]

    def _handle_ignored_suggestion(self, pending_suggestion: Dict[str, Any], context: Dict[str, Any],
                                 entity_analysis: Dict, dispatcher: CollectingDispatcher) -> List[EventType]:
        """✅ NUEVA FUNCIÓN: Maneja cuando el usuario ignoró una sugerencia y cambió de tema"""
        logger.info("[Action] Manejando sugerencia ignorada - usuario cambió de tema")
        
        events = []
        
        try:
            suggestion_type = pending_suggestion.get('suggestion_type', '')
            
            if suggestion_type == 'missing_parameters':
                old_search_type = pending_suggestion.get('search_type', 'producto')
                
                # Si tiene entidades válidas para nueva búsqueda, proceder con la nueva
                if entity_analysis['valid_entity_count'] > 0:
                    new_params = entity_analysis.get('validation_result', {}).get('valid_params', {})
                    
                    # Determinar nuevo tipo de búsqueda basado en entidades
                    if entity_analysis['has_commercial_intent']:
                        new_search_type = 'oferta'
                    else:
                        new_search_type = 'producto'
                    
                    dispatcher.utter_message(
                        f"Entiendo que quieres hacer una nueva búsqueda de {new_search_type}s "
                        f"en lugar de completar la búsqueda de {old_search_type}s anterior. ¡Procedamos!"
                    )
                    
                    # Ejecutar nueva búsqueda
                    params_text = ", ".join([f"{k}: {v}" for k, v in new_params.items()])
                    search_message = f"Buscando {new_search_type}s con {params_text}"
                    
                    dispatcher.utter_message(
                        text=search_message,
                        json_message={
                            "type": "search_results",
                            "search_type": new_search_type,
                            "parameters": new_params,
                            "replaced_previous_suggestion": True,
                            "previous_search_type": old_search_type,
                            "timestamp": datetime.now().isoformat()
                        }
                    )
                    
                    events.extend([
                        SlotSet("pending_suggestion", None),
                        SlotSet("user_engagement_level", "engaged")
                    ])
                    
                else:
                    # Cambió de tema pero sin entidades claras
                    dispatcher.utter_message(
                        f"Veo que quieres cambiar de la búsqueda de {old_search_type}s anterior. "
                        f"¿Qué tipo de búsqueda quieres hacer ahora?"
                    )
                    
                    events.extend([
                        SlotSet("pending_suggestion", None),
                        SlotSet("user_engagement_level", "redirecting")
                    ])
            
            else:
                # Para otros tipos de sugerencia, simplemente limpiar y continuar
                dispatcher.utter_message("Entendido, sigamos con tu nueva consulta.")
                events.append(SlotSet("pending_suggestion", None))
            
            return events
            
        except Exception as e:
            logger.error(f"[Action] Error manejando sugerencia ignorada: {e}", exc_info=True)
            
            return [
                SlotSet("pending_suggestion", None),
                SlotSet("user_engagement_level", "needs_help")
            ]
    
    def _handle_out_of_scope(self, context: Dict[str, Any], entity_analysis: Dict, 
                           dispatcher: CollectingDispatcher) -> List[EventType]:
        """Maneja mensajes completamente fuera del contexto del sistema"""
        logger.info("[Action] Manejando mensaje fuera de contexto")
        
        if entity_analysis['has_product_related'] or entity_analysis['has_commercial_intent']:
            # Tiene entidades relevantes, intentar reconducir
            dispatcher.utter_message(
                "Parece que mencionas algo relacionado con productos o búsquedas, "
                "pero no entiendo completamente tu mensaje. ¿Podrías ser más específico "
                "sobre qué producto o servicio necesitas?"
            )
            return [SlotSet("user_engagement_level", "confused_but_interested")]
        else:
            # Sin entidades relevantes, redirigir suavemente
            dispatcher.utter_message(
                "Me especializo en ayudarte a buscar productos y ofertas. "
                "¿Hay algún producto específico que necesites encontrar?"
            )
            return [SlotSet("user_engagement_level", "redirecting")]
    
    def _handle_ambiguity(self, context: Dict[str, Any], entity_analysis: Dict,
                         dispatcher: CollectingDispatcher) -> List[EventType]:
        """Maneja mensajes ambiguos usando las entidades detectadas para aclarar"""
        logger.info("[Action] Manejando ambigüedad con análisis de entidades")
        
        if entity_analysis['entity_count'] == 0:
            # Sin entidades, solicitar más información
            dispatcher.utter_message(
                "Tu mensaje no es del todo claro para mí. ¿Puedes ser más específico? "
                "Por ejemplo, dime el nombre del producto, para qué animal es, "
                "o qué tipo de oferta buscas."
            )
            return [SlotSet("user_engagement_level", "needs_clarification")]
            
        elif entity_analysis['has_product_related']:
            # Tiene entidades de producto, solicitar más detalles
            product_mentions = [e['value'] for e in entity_analysis['product_entities']]
            dispatcher.utter_message(
                f"Mencionas {', '.join(product_mentions)}, pero necesito más detalles. "
                f"¿Buscas un producto específico, comparar precios, o necesitas información sobre ofertas?"
            )
            return [SlotSet("user_engagement_level", "clarifying_product")]
            
        elif entity_analysis['has_commercial_intent']:
            # Tiene entidades comerciales, guiar hacia búsqueda
            commercial_mentions = [e['value'] for e in entity_analysis['commercial_entities']]
            dispatcher.utter_message(
                f"Veo que mencionas {', '.join(commercial_mentions)}. "
                f"¿Qué producto específico te interesa buscar o comparar?"
            )
            return [SlotSet("user_engagement_level", "commercial_interest")]
            
        else:
            return self._handle_general_fallback(context, entity_analysis, dispatcher)
    
    def _handle_rejection(self, context: Dict[str, Any], dispatcher: CollectingDispatcher) -> List[EventType]:
        """Maneja rechazo total del usuario"""
        logger.info("[Action] Manejando rechazo del usuario")
        events = []
        
        # Limpiar búsquedas pendientes
        if context.get('pending_search') or context.get('pedido_incompleto'):
            logger.info("[Action] Limpiando búsquedas pendientes por rechazo")
            events.extend([
                SlotSet("pending_search", None),
                SlotSet("pedido_incompleto", None)
            ])
        
        dispatcher.utter_message(
            "Entiendo, disculpa si no pude ayudarte como esperabas. "
            "Si cambias de opinión, estaré aquí para asistirte con productos y ofertas."
        )
        
        events.extend([
            SlotSet("user_engagement_level", "disengaged")
        ])
        
        return events
    
    def _handle_negative_feedback(self, context: Dict[str, Any], dispatcher: CollectingDispatcher) -> List[EventType]:
        """Maneja feedback negativo del usuario"""
        logger.info("[Action] Manejando feedback negativo")
        
        dispatcher.utter_message(
            "Lamento que la experiencia no haya sido la esperada. "
            "¿Podrías decirme específicamente qué producto o información necesitas? "
            "Me gustaría ayudarte de manera más efectiva."
        )
        
        return [SlotSet("user_engagement_level", "needs_help")]
    
    def _handle_implicit_search(self, context: Dict[str, Any], entity_analysis: Dict,
                              dispatcher: CollectingDispatcher) -> List[EventType]:
        """Maneja intención implícita de búsqueda usando entidades detectadas"""
        logger.info("[Action] Manejando búsqueda implícita")
        
        if entity_analysis['has_product_related']:
            products = [e['value'] for e in entity_analysis['product_entities']]
            dispatcher.utter_message(
                f"Veo que te interesa buscar información sobre {', '.join(products)}. "
                f"¿Quieres ver productos disponibles, comparar precios, o buscar ofertas específicas?"
            )
            return [SlotSet("user_engagement_level", "product_focused")]
            
        elif entity_analysis['has_commercial_intent']:
            dispatcher.utter_message(
                "Parece que quieres hacer una consulta comercial. "
                "¿Qué producto específico te interesa buscar o comparar?"
            )
            return [SlotSet("user_engagement_level", "commercial_interested")]
            
        else:
            dispatcher.utter_message(
                "Parece que quieres buscar algo. ¿Te interesa buscar productos, ofertas, "
                "o tienes algo específico en mente? Puedes decirme el nombre del producto, "
                "animal, o proveedor."
            )
            return [SlotSet("user_engagement_level", "search_interested")]
    
    def _handle_help_request(self, context: Dict[str, Any], dispatcher: CollectingDispatcher) -> List[EventType]:
        """Maneja solicitud de ayuda"""
        logger.info("[Action] Manejando solicitud de ayuda")
        
        dispatcher.utter_message(
            "Puedo ayudarte a buscar productos y ofertas. Solo dime qué necesitas: "
            "el nombre del producto, para qué animal es, qué proveedor prefieres, "
            "ingrediente activo, síntomas que quieres tratar, o cualquier detalle que tengas."
        )
        return [SlotSet("user_engagement_level", "needs_guidance")]
    
    def _handle_pending_search_fallback(self, context: Dict[str, Any], entity_analysis: Dict,
                                      dispatcher: CollectingDispatcher) -> List[EventType]:
        """Maneja fallback con búsqueda pendiente considerando nuevas entidades"""
        logger.info("[Action] Manejando fallback con búsqueda pendiente")
        
        pending_search = context.get('pending_search')
        pedido_incompleto = context.get('pedido_incompleto')
        
        if entity_analysis['entity_count'] > 0:
            # Tiene nuevas entidades, preguntar si quiere modificar búsqueda actual
            entity_values = [e.get('value', '') for e in 
                           entity_analysis['product_entities'] + entity_analysis['commercial_entities']]
            dispatcher.utter_message(
                f"Mencionas {', '.join(entity_values)} pero tienes una búsqueda pendiente. "
                f"¿Quieres modificar tu búsqueda actual, empezar una nueva, o continuar con la anterior?"
            )
            return [SlotSet("user_engagement_level", "modifying_search")]
        
        # Sin nuevas entidades relevantes
        if pending_search:
            search_type = pending_search.get('search_type', 'búsqueda')
            current_params = pending_search.get('parameters', {})
            
            if current_params:
                params_str = ", ".join([f"{k}: {v}" for k, v in current_params.items()])
                dispatcher.utter_message(
                    f"No entendí tu mensaje. Tu búsqueda de {search_type}s actual tiene: {params_str}. "
                    f"¿Quieres continuarla, modificarla o cancelarla?"
                )
            else:
                dispatcher.utter_message(
                    f"No entendí tu mensaje. Tienes una búsqueda de {search_type}s pendiente. "
                    f"¿Quieres continuarla, cancelarla o empezar algo diferente?"
                )
        
        elif pedido_incompleto:
            dispatcher.utter_message(
                "Tienes un pedido incompleto. ¿Quieres completarlo, modificarlo o empezar de nuevo?"
            )
        
        return [SlotSet("user_engagement_level", "pending_decision")]
    
    def _handle_general_fallback(self, context: Dict[str, Any], entity_analysis: Dict,
                               dispatcher: CollectingDispatcher) -> List[EventType]:
        """Maneja fallback general usando entidades si están disponibles"""
        logger.info("[Action] Manejando fallback general")
        
        if entity_analysis['entity_count'] > 0:
            # Tiene entidades, ser específico en la respuesta
            entity_types = list(set([e.get('entity', '') for e in 
                                   context.get('latest_message', {}).get('entities', [])]))
            
            dispatcher.utter_message(
                f"Veo que mencionas información relacionada con {', '.join(entity_types)}, "
                f"pero no estoy seguro de qué necesitas exactamente. "
                f"¿Podrías ser más específico sobre qué producto buscas o qué información necesitas?"
            )
            return [SlotSet("user_engagement_level", "entity_confused")]
        
        # Sin entidades, respuesta general
        fallback_messages = [
            "No estoy seguro de entender. ¿Buscas productos, ofertas, o tienes otra consulta específica?",
            "Disculpa, no comprendí bien. ¿Puedes ser más específico sobre qué producto o información necesitas?",
            "No logré entender tu mensaje. ¿Te gustaría buscar algún producto en particular para algún animal?",
            "Me especializo en productos veterinarios y ofertas. ¿Hay algo específico que pueda ayudarte a encontrar?"
        ]
        
        dispatcher.utter_message(choice(fallback_messages))
        return [SlotSet("user_engagement_level", "general_confused")]