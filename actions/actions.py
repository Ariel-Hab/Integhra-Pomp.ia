from typing import Any, Text, Dict, List
import logging

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import EventType

# Importamos los handlers específicos
from handlers.busqueda import handle_busqueda
from handlers.fuera import handle_fuera
from handlers.fallback import handle_fallback

# ---------------- LOGGING ----------------
logger = logging.getLogger("ActionRouter")
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)

# ---------------- MAPA INTENT -> HANDLER ----------------
INTENT_TO_HANDLER = {
    "buscar_producto": handle_busqueda,
    "buscar_oferta": handle_busqueda,
    "fuera_aplicacion": handle_fuera,
    "nlu_fallback": handle_fallback,   # intent por defecto de Rasa
    "verificar_contexto": handle_fallback,
    "completar_pedido_pendiente": handle_fallback,
}

# ---------------- ACTION GENÉRICA ----------------
class ActionGenerica(Action):
    def name(self) -> Text:
        return "action_generica"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[EventType]:
        intent = tracker.latest_message.get("intent", {}).get("name", "")
        logger.info(f"[Router] Intent detectado: {intent}")

        handler = INTENT_TO_HANDLER.get(intent, handle_fallback)
        return handler(dispatcher, tracker, domain)
