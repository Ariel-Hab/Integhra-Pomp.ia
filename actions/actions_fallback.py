# actions/action_fallback.py

from asyncio.log import logger
from typing import Any, Dict, List, Text
from datetime import datetime

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, EventType

from .helpers import validate_entities_for_intent
from .logger import log_message
from .conversation_state import ConversationState

# ✅ Importación única y limpia del wrapper de más alto nivel
from .models.model_manager import generate_with_safe_fallback

class ActionFallback(Action):
    """
    ✅ MEJORADO: Fallback con LLM que usa contexto de conversación para
    generar respuestas personalizadas, con fallback a mensajes pre-escritos.
    """
    
    def name(self) -> Text:
        return "action_fallback"

    def _dispatch_llm_response(self, prompt: str, dispatcher: CollectingDispatcher, tracker: Tracker,
                               fallback_template: str, max_new_tokens: int, temperature: float = 0.4):
        """
        ✅ NUEVO: Encapsula la llamada a generate_with_safe_fallback para evitar repetición.
        """
        generate_with_safe_fallback(
            prompt=prompt,
            dispatcher=dispatcher,
            tracker=tracker,
            fallback_template=fallback_template,
            max_new_tokens=max_new_tokens,
            temperature=temperature
        )

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        log_message(tracker, nlu_conf_threshold=0.6)
        context = ConversationState.get_conversation_context(tracker)
        user_msg = context['user_message']
        sentiment = context['detected_sentiment']
        implicit_intentions = context['implicit_intentions']
        current_intent = tracker.latest_message.get('intent', {}).get('name', 'unknown')
        entities = tracker.latest_message.get('entities', [])
        pending_suggestion = context.get('pending_suggestion')
        awaiting_suggestion_response = context.get('awaiting_suggestion_response', False)
        pending_search = tracker.get_slot('pending_search')
        pedido_incompleto = tracker.get_slot('pedido_incompleto')
        user_engagement_level = tracker.get_slot('user_engagement_level')
        
        self._log_context_analysis(user_msg, current_intent, sentiment, implicit_intentions, 
                                   entities, pending_suggestion, awaiting_suggestion_response, 
                                   user_engagement_level)
        
        entity_analysis = self._analyze_entities_with_fragment_protection(entities)
        
        events = [SlotSet("user_sentiment", sentiment)]
        
        # PRIORIDAD 1: Verificar si está completando una sugerencia pendiente
        if awaiting_suggestion_response and pending_suggestion:
            logger.info("[Fallback Decision] PRIORIDAD: Usuario completando sugerencia pendiente")
            events.extend(self._handle_suggestion_completion(context, entity_analysis, dispatcher, tracker))
            return events
        
        # PRIORIDAD 2: Verificar si ignoró sugerencia y cambió de tema
        elif pending_suggestion and not awaiting_suggestion_response:
            from .conversation_state import SuggestionManager
            if SuggestionManager.check_if_suggestion_ignored(current_intent, pending_suggestion, context['is_small_talk']):
                logger.info("[Fallback Decision] Usuario ignoró sugerencia pendiente")
                events.extend(self._handle_ignored_suggestion(pending_suggestion, context, entity_analysis, dispatcher, tracker))
                return events
        
        # Lógica de fallback basada en el contexto
        if current_intent in ['off_topic', 'out_of_scope']:
            logger.info(f"[Fallback Decision] Mensaje fuera de contexto detectado: {current_intent}")
            events.extend(self._handle_out_of_scope(context, entity_analysis, dispatcher, tracker))
        elif current_intent == 'ambiguity_fallback':
            logger.info(f"[Fallback Decision] Ambigüedad detectada con entidades: {[e['entity'] for e in entities]}")
            events.extend(self._handle_ambiguity(context, entity_analysis, dispatcher, tracker))
        elif sentiment == "rejection":
            logger.info("[Fallback Decision] Sentimiento de rechazo detectado")
            events.extend(self._handle_rejection(context, dispatcher, tracker))
        elif sentiment == "negative":
            logger.info("[Fallback Decision] Feedback negativo detectado")
            events.extend(self._handle_negative_feedback(context, dispatcher, tracker))
        elif "search_intentions" in implicit_intentions or entity_analysis['has_product_related']:
            logger.info(f"[Fallback Decision] Intención de búsqueda implícita o entidades de producto detectadas")
            events.extend(self._handle_implicit_search(context, entity_analysis, dispatcher, tracker))
        elif "help_requests" in implicit_intentions:
            logger.info("[Fallback Decision] Solicitud de ayuda detectada")
            events.extend(self._handle_help_request(context, dispatcher, tracker))
        elif pending_search or pedido_incompleto:
            logger.info(f"[Fallback Decision] Búsqueda pendiente o pedido incompleto activo")
            events.extend(self._handle_pending_search_fallback(context, entity_analysis, dispatcher, tracker))
        else:
            logger.info("[Fallback Decision] Fallback general - sin contexto específico")
            events.extend(self._handle_general_fallback(context, entity_analysis, dispatcher, tracker))
        
        return events
    
    def _build_context_summary(self, context: Dict[str, Any], entity_analysis: Dict) -> str:
        context_parts = []
        
        search_history = context.get('search_history', [])
        if search_history:
            last_search = search_history[-1]
            search_type = last_search.get('type', 'producto')
            params = last_search.get('parameters', {})
            if params:
                params_str = ", ".join([f"{k}='{v}'" for k, v in params.items()])
                context_parts.append(f"Última búsqueda: {search_type} con {params_str}")
        
        if entity_analysis['valid_entity_count'] > 0:
            entities_str = ", ".join([
                f"{e['type']}='{e['value']}'" 
                for e in entity_analysis['product_entities'] + entity_analysis['commercial_entities']
            ])
            context_parts.append(f"Entidades mencionadas: {entities_str}")
        
        sentiment = context.get('detected_sentiment')
        if sentiment and sentiment not in ['neutral', 'positive']:
            context_parts.append(f"Sentimiento del usuario: {sentiment}")
        
        engagement = context.get('user_engagement_level')
        if engagement:
            context_parts.append(f"Estado del usuario: {engagement}")
        
        return "\n".join(context_parts) if context_parts else "Primera interacción"
    
    def _log_context_analysis(self, user_msg: str, intent: str, sentiment: str, 
                              implicit_intentions: List[str], entities: List[Dict], 
                              pending_suggestion: Any, awaiting_response: bool, engagement_level: str):
        entity_summary = {e['entity']: e['value'] for e in entities} if entities else {}
        suggestion_info = "Ninguna"
        if pending_suggestion:
            suggestion_type = pending_suggestion.get('suggestion_type', 'unknown')
            suggestion_search_type = pending_suggestion.get('search_type', 'N/A')
            suggestion_info = f"{suggestion_type} ({suggestion_search_type})"
        
        logger.info(f"""
\n=== ANÁLISIS DE CONTEXTO FALLBACK ===
Mensaje del usuario: "{user_msg}"
Intent detectado: {intent} | Sentimiento: {sentiment}
Intenciones implícitas: {implicit_intentions}
Entidades detectadas: {entity_summary}
Sugerencia pendiente: {suggestion_info} | Esperando respuesta: {'Sí' if awaiting_response else 'No'}
Estado del usuario: {engagement_level}
======================================\n""")
    
    def _analyze_entities_with_fragment_protection(self, entities: List[Dict]) -> Dict[str, Any]:
        validation_result = validate_entities_for_intent(entities, intent_name=None, min_length=3, check_fragments=True)
        analysis = {
            'has_product_related': False, 'has_commercial_intent': False,
            'product_entities': [], 'commercial_entities': [], 'context_entities': [],
            'entity_count': len(entities), 'valid_entity_count': len(validation_result['valid_params']),
            'rejected_fragments': len([e.get('value', '') for e in entities if e.get('value')]) - len(validation_result['valid_params'])
        }
        product_related = ['nombre', 'animal', 'sintoma']
        commercial_related = ['empresa', 'cantidad_descuento', 'cantidad_bonificacion', 'cantidad', 'precio']
        
        for param_name, param_value in validation_result['valid_params'].items():
            entity_info = {'type': param_name, 'value': param_value}
            if param_name in product_related:
                analysis['has_product_related'] = True
                analysis['product_entities'].append(entity_info)
            elif param_name in commercial_related:
                analysis['has_commercial_intent'] = True
                analysis['commercial_entities'].append(entity_info)
            else:
                analysis['context_entities'].append(entity_info)
        
        analysis['validation_result'] = validation_result
        return analysis

    # ============================================================
    # HANDLERS (Ahora usan el _dispatch_llm_response)
    # ============================================================

    def _handle_suggestion_completion(self, context: Dict[str, Any], entity_analysis: Dict, 
                                      dispatcher: CollectingDispatcher, tracker: Tracker) -> List[EventType]:
        logger.info("[Action] Manejando completación de sugerencia pendiente")
        pending_suggestion = context.get('pending_suggestion', {})
        suggestion_type = pending_suggestion.get('suggestion_type', '')
        events = []
        
        try:
            if suggestion_type == 'missing_parameters':
                search_type = pending_suggestion.get('search_type', 'producto')
                current_parameters = pending_suggestion.get('current_parameters', {})
                new_params = entity_analysis.get('validation_result', {}).get('valid_params', {})
                
                if new_params:
                    combined_params = {**current_parameters, **new_params}
                    context_summary = self._build_context_summary(context, entity_analysis)
                    prompt = f"""El usuario está completando una búsqueda de {search_type}s.
Parámetros anteriores: {current_parameters}
Nuevos parámetros agregados: {new_params}
Contexto:
{context_summary}
Confirma amigablemente que agregaste los nuevos parámetros y procederás con la búsqueda. Máximo 2 oraciones."""

                    self._dispatch_llm_response(prompt, dispatcher, tracker, "utter_confirmar", 80)
                    
                    search_message_text = f"Buscando {search_type}s con: " + ", ".join([f"{k}: {v}" for k, v in combined_params.items()])
                    dispatcher.utter_message(text=search_message_text, json_message={
                        "type": "search_results", "search_type": search_type, "parameters": combined_params,
                        "completed_from_suggestion": True, "timestamp": datetime.now().isoformat()
                    })
                    
                    search_history = context.get('search_history', [])
                    search_history.append({'timestamp': datetime.now().isoformat(), 'type': search_type, 'parameters': combined_params, 'status': 'completed_from_suggestion'})
                    events.extend([SlotSet("search_history", search_history), SlotSet("pending_suggestion", None), SlotSet("user_engagement_level", "satisfied")])
                else:
                    criteria = pending_suggestion.get('required_criteria', 'información adicional')
                    dispatcher.utter_message(f"No pude identificar parámetros válidos. ¿Puedes ser más específico con {criteria}?")
                    events.append(SlotSet("user_engagement_level", "needs_clarification"))
            
            elif suggestion_type in ['entity_correction', 'type_correction']:
                dispatcher.utter_message("Si aceptas la sugerencia, responde 'sí'. Si no, intenta con otros términos.")
            
            return events
        except Exception as e:
            logger.error(f"[Action] Error manejando completación: {e}", exc_info=True)
            dispatcher.utter_message("Hubo un error procesando tu respuesta. ¿Puedes intentar nuevamente?")
            return [SlotSet("pending_suggestion", None), SlotSet("user_engagement_level", "needs_help")]

    def _handle_ignored_suggestion(self, pending_suggestion: Dict[str, Any], context: Dict[str, Any],
                                   entity_analysis: Dict, dispatcher: CollectingDispatcher, 
                                   tracker: Tracker) -> List[EventType]:
        logger.info("[Action] Manejando sugerencia ignorada")
        events = []
        try:
            if pending_suggestion.get('suggestion_type') == 'missing_parameters':
                old_search_type = pending_suggestion.get('search_type', 'producto')
                if entity_analysis['valid_entity_count'] > 0:
                    new_params = entity_analysis.get('validation_result', {}).get('valid_params', {})
                    new_search_type = 'oferta' if entity_analysis['has_commercial_intent'] else 'producto'
                    context_summary = self._build_context_summary(context, entity_analysis)
                    prompt = f"""El usuario tenía una búsqueda de {old_search_type}s pendiente, pero ahora quiere buscar {new_search_type}s.
Nuevos parámetros: {new_params}
Contexto:
{context_summary}
Reconoce el cambio de manera amigable y confirma que procederás con la nueva búsqueda. Máximo 2 oraciones."""
                    self._dispatch_llm_response(prompt, dispatcher, tracker, "utter_confirmar", 80)
                    
                    params_text = ", ".join([f"{k}: {v}" for k, v in new_params.items()])
                    dispatcher.utter_message(text=f"Buscando {new_search_type}s con {params_text}", json_message={
                        "type": "search_results", "search_type": new_search_type, "parameters": new_params,
                        "replaced_previous_suggestion": True, "previous_search_type": old_search_type,
                        "timestamp": datetime.now().isoformat()
                    })
                    events.extend([SlotSet("pending_suggestion", None), SlotSet("user_engagement_level", "engaged")])
                else:
                    prompt = f"""El usuario cambió de tema desde una búsqueda de {old_search_type}s, pero no está claro qué quiere ahora.
Pregunta amigablemente qué tipo de búsqueda quiere hacer. Máximo 2 oraciones."""
                    self._dispatch_llm_response(prompt, dispatcher, tracker, "utter_pedir_clarificacion", 60)
                    events.extend([SlotSet("pending_suggestion", None), SlotSet("user_engagement_level", "redirecting")])
            else:
                dispatcher.utter_message("Entendido, sigamos con tu nueva consulta.")
                events.append(SlotSet("pending_suggestion", None))
            return events
        except Exception as e:
            logger.error(f"[Action] Error manejando sugerencia ignorada: {e}", exc_info=True)
            return [SlotSet("pending_suggestion", None), SlotSet("user_engagement_level", "needs_help")]
    
    def _handle_out_of_scope(self, context: Dict[str, Any], entity_analysis: Dict, 
                            dispatcher: CollectingDispatcher, tracker: Tracker) -> List[EventType]:
        logger.info("[Action] Manejando out of scope")
        context_summary = self._build_context_summary(context, entity_analysis)
        
        if entity_analysis['has_product_related'] or entity_analysis['has_commercial_intent']:
            entities_str = ", ".join([f"{e['type']}: {e['value']}" for e in entity_analysis['product_entities'] + entity_analysis['commercial_entities']])
            prompt = f"""El usuario mencionó entidades relacionadas con productos: {entities_str}, pero su mensaje está fuera de contexto.
Contexto:
{context_summary}
Reconoce amigablemente que mencionó algo relacionado, pero pide que sea más específico sobre qué producto o servicio necesita. Máximo 2 oraciones."""
            self._dispatch_llm_response(prompt, dispatcher, tracker, "utter_pedir_clarificacion", 80)
            return [SlotSet("user_engagement_level", "confused_but_interested")]
        else:
            prompt = f"""El usuario dijo algo completamente fuera del contexto (productos veterinarios).
Contexto:
{context_summary}
Redirige amigablemente explicando que te especializas en productos y ofertas veterinarias. Pregunta si necesita algún producto. Máximo 2 oraciones."""
            self._dispatch_llm_response(prompt, dispatcher, tracker, "utter_out_of_scope", 80)
            return [SlotSet("user_engagement_level", "redirecting")]
    
    def _handle_ambiguity(self, context: Dict[str, Any], entity_analysis: Dict,
                          dispatcher: CollectingDispatcher, tracker: Tracker) -> List[EventType]:
        logger.info("[Action] Manejando ambigüedad")
        context_summary = self._build_context_summary(context, entity_analysis)
        
        if entity_analysis['entity_count'] == 0:
            prompt = f"""El usuario envió un mensaje ambiguo sin entidades claras.
Contexto:
{context_summary}
Pide amigablemente más información específica (nombre del producto, animal, tipo de oferta, etc). Máximo 2 oraciones."""
            self._dispatch_llm_response(prompt, dispatcher, tracker, "utter_pedir_clarificacion", 80)
            return [SlotSet("user_engagement_level", "needs_clarification")]
            
        elif entity_analysis['has_product_related']:
            products_str = ", ".join([e['value'] for e in entity_analysis['product_entities']])
            prompt = f"""El usuario mencionó: {products_str}, pero su mensaje es ambiguo.
Contexto:
{context_summary}
Reconoce lo que mencionó y pregunta amigablemente si busca un producto específico, comparar precios, o ver ofertas. Máximo 2 oraciones."""
            self._dispatch_llm_response(prompt, dispatcher, tracker, "utter_pedir_clarificacion", 100)
            return [SlotSet("user_engagement_level", "clarifying_product")]
            
        elif entity_analysis['has_commercial_intent']:
            commercial_str = ", ".join([e['value'] for e in entity_analysis['commercial_entities']])
            prompt = f"""El usuario mencionó información comercial: {commercial_str}, pero falta saber qué producto le interesa.
Contexto:
{context_summary}
Reconoce la información comercial y pregunta qué producto específico quiere buscar o comparar. Máximo 2 oraciones."""
            self._dispatch_llm_response(prompt, dispatcher, tracker, "utter_buscar_producto", 80)
            return [SlotSet("user_engagement_level", "commercial_interest")]
        else:
            return self._handle_general_fallback(context, entity_analysis, dispatcher, tracker)
    
    def _handle_rejection(self, context: Dict[str, Any], dispatcher: CollectingDispatcher,
                          tracker: Tracker) -> List[EventType]:
        logger.info("[Action] Manejando rechazo")
        events = []
        if context.get('pending_search') or context.get('pedido_incompleto'):
            events.extend([SlotSet("pending_search", None), SlotSet("pedido_incompleto", None)])
        
        context_summary = self._build_context_summary(context, {})
        prompt = f"""El usuario rechazó la ayuda o mostró desinterés.
Contexto:
{context_summary}
Responde con empatía, disculpándote si no pudiste ayudar como esperaba. Menciona que estarás disponible si cambia de opinión. Máximo 2 oraciones."""
        self._dispatch_llm_response(prompt, dispatcher, tracker, "utter_despedir", 80, temperature=0.5)
        
        events.append(SlotSet("user_engagement_level", "disengaged"))
        return events
    
    def _handle_negative_feedback(self, context: Dict[str, Any], dispatcher: CollectingDispatcher,
                                  tracker: Tracker) -> List[EventType]:
        logger.info("[Action] Manejando feedback negativo")
        context_summary = self._build_context_summary(context, {})
        prompt = f"""El usuario dio feedback negativo sobre la experiencia.
Contexto:
{context_summary}
Discúlpate con empatía y pregunta específicamente qué producto o información necesita para ayudarlo mejor. Máximo 2 oraciones."""
        self._dispatch_llm_response(prompt, dispatcher, tracker, "utter_pedir_clarificacion", 80, temperature=0.5)
        return [SlotSet("user_engagement_level", "needs_help")]
    
    def _handle_implicit_search(self, context: Dict[str, Any], entity_analysis: Dict,
                                dispatcher: CollectingDispatcher, tracker: Tracker) -> List[EventType]:
        logger.info("[Action] Manejando búsqueda implícita")
        
        if entity_analysis['has_product_related']:
            return self._handle_ambiguity(context, entity_analysis, dispatcher, tracker) # Reutilizar lógica
        
        elif entity_analysis['has_commercial_intent']:
             return self._handle_ambiguity(context, entity_analysis, dispatcher, tracker) # Reutilizar lógica
        
        else:
            context_summary = self._build_context_summary(context, entity_analysis)
            prompt = f"""El usuario parece querer buscar algo pero no es claro qué.
Contexto:
{context_summary}
Pregunta amigablemente qué quiere buscar (productos, ofertas) o qué tiene en mente. Menciona que puede buscar por nombre, animal, etc. Máximo 2 oraciones."""
            self._dispatch_llm_response(prompt, dispatcher, tracker, "utter_buscar_producto", 100)
            return [SlotSet("user_engagement_level", "search_interested")]
    
    def _handle_help_request(self, context: Dict[str, Any], dispatcher: CollectingDispatcher,
                             tracker: Tracker) -> List[EventType]:
        logger.info("[Action] Manejando solicitud de ayuda")
        context_summary = self._build_context_summary(context, {})
        prompt = f"""El usuario pidió ayuda.
Contexto:
{context_summary}
Explica brevemente cómo puedes ayudarlo a buscar productos y ofertas. Menciona que puede decir nombre del producto, animal, proveedor, síntoma, etc. Máximo 3 oraciones."""
        self._dispatch_llm_response(prompt, dispatcher, tracker, "utter_default", 120)
        return [SlotSet("user_engagement_level", "needs_guidance")]
    
    def _handle_pending_search_fallback(self, context: Dict[str, Any], entity_analysis: Dict,
                                        dispatcher: CollectingDispatcher, tracker: Tracker) -> List[EventType]:
        logger.info("[Action] Manejando fallback con búsqueda pendiente")
        context_summary = self._build_context_summary(context, entity_analysis)
        
        if entity_analysis['entity_count'] > 0:
            entities_str = ", ".join([e.get('value', '') for e in entity_analysis['product_entities'] + entity_analysis['commercial_entities']])
            prompt = f"""El usuario mencionó: {entities_str}, pero tiene una búsqueda pendiente.
Contexto:
{context_summary}
Pregunta amigablemente si quiere modificar su búsqueda actual, empezar una nueva, o continuar con la anterior. Máximo 2 oraciones."""
            self._dispatch_llm_response(prompt, dispatcher, tracker, "utter_modificar_busqueda", 100)
            return [SlotSet("user_engagement_level", "modifying_search")]
        
        pending_search = context.get('pending_search')
        if pending_search:
            search_type = pending_search.get('search_type', 'búsqueda')
            current_params = pending_search.get('parameters', {})
            if current_params:
                params_str = ", ".join([f"{k}: {v}" for k, v in current_params.items()])
                prompt = f"""El usuario envió un mensaje no claro. Tiene una búsqueda de {search_type}s pendiente con: {params_str}.
Contexto:
{context_summary}
Menciona los parámetros actuales y pregunta si quiere continuarla, modificarla o cancelarla. Máximo 2 oraciones."""
            else:
                prompt = f"""El usuario envió un mensaje no claro. Tiene una búsqueda de {search_type}s pendiente sin parámetros definidos.
Contexto:
{context_summary}
Pregunta si quiere continuar, cancelar o empezar algo diferente. Máximo 2 oraciones."""
            self._dispatch_llm_response(prompt, dispatcher, tracker, "utter_modificar_busqueda", 100)
        
        elif context.get('pedido_incompleto'):
            prompt = f"""El usuario tiene un pedido incompleto.
Contexto:
{context_summary}
Pregunta amigablemente si quiere completarlo, modificarlo o empezar de nuevo. Máximo 2 oraciones."""
            self._dispatch_llm_response(prompt, dispatcher, tracker, "utter_confirmar", 80)
        
        return [SlotSet("user_engagement_level", "pending_decision")]
    
    def _handle_general_fallback(self, context: Dict[str, Any], entity_analysis: Dict,
                                dispatcher: CollectingDispatcher, tracker: Tracker) -> List[EventType]:
        logger.info("[Action] Manejando fallback general")
        context_summary = self._build_context_summary(context, entity_analysis)
        user_msg = context.get('user_message', '')
        
        if entity_analysis['entity_count'] > 0:
            entity_types = list(set([e['type'] for e in entity_analysis['product_entities'] + entity_analysis['commercial_entities']]))
            entities_str = ", ".join(entity_types)
            prompt = f"""El usuario mencionó información relacionada con: {entities_str}. Mensaje: "{user_msg}", pero no está claro qué necesita.
Contexto:
{context_summary}
Reconoce lo que mencionó y pide amigablemente que sea más específico sobre qué producto busca o qué información necesita. Máximo 2 oraciones."""
            self._dispatch_llm_response(prompt, dispatcher, tracker, "utter_pedir_clarificacion", 100)
            return [SlotSet("user_engagement_level", "entity_confused")]
        
        prompt = f"""El usuario dijo: "{user_msg}". No se detectaron entidades claras y el mensaje no es claro.
Contexto:
{context_summary}
Pregunta amigablemente si busca productos, ofertas, o tiene otra consulta específica. Máximo 2 oraciones."""
        self._dispatch_llm_response(prompt, dispatcher, tracker, "utter_default", 80)
        return [SlotSet("user_engagement_level", "general_confused")]