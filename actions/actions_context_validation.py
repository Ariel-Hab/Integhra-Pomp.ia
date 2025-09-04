from typing import Any, Dict, List
from asyncio.log import logger
from xml.dom.minidom import Text

from actions.conversation_state import ConversationState
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, EventType

class ActionContextValidator(Action):
    """Valida y maneja cambios de contexto en la conversación"""
    def name(self) -> Text:
        return "action_context_validator"
    
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        context = ConversationState.get_conversation_context(tracker)
        current_intent = context['current_intent']
        previous_intent = context['previous_intent']
        
        logger.info(f"[ContextValidator] Intent={current_intent}, PedidoPendiente={bool(context['pending_search'] or context['pedido_incompleto'])}, FlujoPrevio={previous_intent}")
        
        context_switch_messages = {
            ("buscar_producto", "saludo"): "¡Hola de nuevo! ¿Seguimos con la búsqueda que habías empezado?",
            ("buscar_oferta", "pedir_chiste"): "¿Quieres un chiste? ¡Después podemos continuar con ofertas!",
            ("pedir_chiste", "completar_pedido"): "Perfecto, vamos a completar tu pedido.",
            ("buscar_producto", "despedida"): "¿Te vas? Tu búsqueda se guardará para más tarde."
        }
        
        context_key = (previous_intent or "", current_intent)
        events = []

        if context_key in context_switch_messages:
            dispatcher.utter_message(text=context_switch_messages[context_key])
            logger.info(f"[ContextValidator] Cambio de contexto detectado: {context_key}")
            if current_intent == "despedida":
                events.extend([
                    SlotSet("pedido_incompleto", None),
                    SlotSet("pending_search_data", None)
                ])

        events.append(SlotSet("last_intent_flow", current_intent))
        return events