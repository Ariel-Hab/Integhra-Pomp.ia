from asyncio.log import logger
import difflib
from random import random
from typing import Any, Dict, List
from xml.dom.minidom import Text

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, EventType
from datetime import datetime
from .conversation_state import ConversationState

class ActionFallback(Action):
    """Fallback mejorado con detección de sentimiento desde el config"""
    
    def name(self) -> Text:
        return "action_fallback"
    
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        context = ConversationState.get_conversation_context(tracker)
        user_msg = context['user_message']
        sentiment = context['detected_sentiment']
        implicit_intentions = context['implicit_intentions']
        
        logger.info(f"[Fallback] Sentiment: {sentiment}, Intentions: {implicit_intentions}, Pending: {bool(context['pending_search'] or context['pedido_incompleto'])}")
        
        events = []
        
        # Actualizar slot de sentimiento
        events.append(SlotSet("user_sentiment", sentiment))
        
        if sentiment == "rejection":
            events.extend(self._handle_rejection(context, dispatcher))
        elif sentiment == "negative":
            events.extend(self._handle_negative_feedback(context, dispatcher))
        elif "search_intentions" in implicit_intentions:
            events.extend(self._handle_implicit_search(context, dispatcher))
        elif "help_requests" in implicit_intentions:
            events.extend(self._handle_help_request(context, dispatcher))
        elif context['pending_search'] or context['pedido_incompleto']:
            events.extend(self._handle_pending_search_fallback(context, dispatcher))
        else:
            events.extend(self._handle_general_fallback(context, dispatcher))
        
        return events
    
    def _handle_rejection(self, context: Dict[str, Any], dispatcher: CollectingDispatcher) -> List[EventType]:
        """Maneja rechazo total del usuario"""
        events = []
        
        if context['pending_search'] or context['pedido_incompleto']:
            events.extend([
                SlotSet("pending_search_data", None),
                SlotSet("pedido_incompleto", None)
            ])
        
        dispatcher.utter_message(
            "Entiendo, disculpa si no pude ayudarte como esperabas. "
            "Si cambias de opinión, estaré aquí para asistirte."
        )
        
        events.extend([
            SlotSet("user_engagement_level", "disengaged"),
            SlotSet("context_decision_pending", None)
        ])
        
        return events
    
    def _handle_negative_feedback(self, context: Dict[str, Any], dispatcher: CollectingDispatcher) -> List[EventType]:
        """Maneja feedback negativo del usuario"""
        dispatcher.utter_message(
            "Lamento que la experiencia no haya sido la esperada. "
            "¿Podrías decirme específicamente qué necesitas? Me gustaría ayudarte mejor."
        )
        
        return [SlotSet("user_engagement_level", "needs_help")]
    
    def _handle_implicit_search(self, context: Dict[str, Any], dispatcher: CollectingDispatcher) -> List[EventType]:
        """Maneja intención implícita de búsqueda"""
        dispatcher.utter_message(
            "Parece que quieres buscar algo. ¿Te interesa buscar productos, ofertas, "
            "o tienes algo específico en mente?"
        )
        return [SlotSet("user_engagement_level", "interested")]
    
    def _handle_help_request(self, context: Dict[str, Any], dispatcher: CollectingDispatcher) -> List[EventType]:
        """Maneja solicitud de ayuda"""
        dispatcher.utter_message(
            "Puedo ayudarte a buscar productos y ofertas. Solo dime qué necesitas: "
            "el nombre del producto, proveedor, categoría, ingrediente activo, o cualquier detalle que tengas."
        )
        return [SlotSet("user_engagement_level", "needs_guidance")]
    
    def _handle_pending_search_fallback(self, context: Dict[str, Any], dispatcher: CollectingDispatcher) -> List[EventType]:
        """Maneja fallback con búsqueda pendiente"""
        if context['pending_search']:
            search_type = context['pending_search'].get('search_type', 'búsqueda')
            current_params = context['pending_search'].get('parameters', {})
        else:
            search_type = 'búsqueda'
            current_params = {}
        
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
        
        return []
    
    def _handle_general_fallback(self, context: Dict[str, Any], dispatcher: CollectingDispatcher) -> List[EventType]:
        """Maneja fallback general"""
        fallback_messages = [
            "No estoy seguro de entender. ¿Buscas productos, ofertas, o tienes otra consulta?",
            "Disculpa, no comprendí bien. ¿Puedes ser más específico sobre lo que necesitas?",
            "No logré entender tu mensaje. ¿Te gustaría buscar algún producto en particular?"
        ]
        
        dispatcher.utter_message(random.choice(fallback_messages))
        return [SlotSet("user_engagement_level", "confused")]