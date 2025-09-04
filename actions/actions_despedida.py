from asyncio.log import logger
from typing import Any, Dict, List
from xml.dom.minidom import Text

from actions.conversation_state import ConversationState
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, EventType


class ActionDespedidaLimpiaContexto(Action):
    """Despedida que limpia todo el contexto"""
    def name(self) -> Text:
        return "action_despedida_limpia_contexto"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        context = ConversationState.get_conversation_context(tracker)
        
        if context['pedido_incompleto'] or context['pending_search']:
            dispatcher.utter_message("¡Hasta luego! Tu búsqueda quedará guardada para más tarde.")
        else:
            dispatcher.utter_message("¡Hasta la próxima! Que tengas un excelente día.")
        
        logger.info("[DespedidaLimpia] Contexto limpiado")
        return [SlotSet(slot, None) for slot in tracker.slots.keys()] 