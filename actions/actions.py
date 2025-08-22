from typing import Any, Text, Dict, List
import logging
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import EventType, SlotSet, UserUtteranceReverted

from handlers.busqueda import handle_busqueda

logger = logging.getLogger("ActionSituaciones")
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)

# -------------------- Small Talk --------------------
class ActionSmallTalk(Action):
    def name(self) -> Text:
        return "action_smalltalk_situacion"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        intent = tracker.latest_message.get("intent", {}).get("name", "")
        user_msg = tracker.latest_message.get("text", "")

        logger.info(f"[SmallTalk] Pedido recibido. Intent='{intent}', UserText='{user_msg}'")

        try:
            utter_mapping = {
                "saludo": "utter_saludo",
                "preguntar_como_estas": "utter_preguntar_como_estas",
                "responder_como_estoy": "utter_responder_como_estoy",
                "responder_estoy_bien": "utter_responder_estoy_bien",
                "despedida": "utter_despedida",
                "pedir_chiste": "utter_contar_chiste",
                "reirse_chiste": "utter_reirse_chiste"
            }

            utter_name = utter_mapping.get(intent)
            if utter_name:
                dispatcher.utter_message(response=utter_name)
                logger.info(f"[SmallTalk] Respuesta enviada con utter='{utter_name}' ✅")
            else:
                dispatcher.utter_message(f"Respondiendo small talk: {user_msg}")
                logger.warning(f"[SmallTalk] Intent no mapeado, se respondió fallback con texto del usuario")

            return []
        except Exception as e:
            logger.error(f"[SmallTalk] Error ejecutando acción: {e}", exc_info=True)
            return []

# -------------------- Confirmación / Denegación / Agradecimiento --------------------
class ActionConfirmNegarAgradecer(Action):
    def name(self) -> Text:
        return "action_conf_neg_agradecer"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        intent = tracker.latest_message.get("intent", {}).get("name", "")
        pedido_pendiente = tracker.get_slot("pedido_incompleto")

        logger.info(f"[ConfNegAgr] Pedido recibido. Intent='{intent}', PedidoPendiente={pedido_pendiente}")

        try:
            utter_mapping = {
                "afirmar": "utter_afirmar",
                "denegar": "utter_denegar",
                "agradecimiento": "utter_agradecimiento"
            }

            if pedido_pendiente:
                if intent in ["afirmar", "agradecimiento"]:
                    dispatcher.utter_message("Perfecto ✅, tu pedido ha sido completado.")
                    logger.info("[ConfNegAgr] Pedido pendiente marcado como completado ✅")
                    return [SlotSet("pedido_incompleto", None)]
                elif intent == "denegar":
                    dispatcher.utter_message("Entiendo ❌, ¿qué estabas buscando o querías completar?")
                    logger.info("[ConfNegAgr] Usuario negó el pedido pendiente ❌")
                    return [UserUtteranceReverted()]

            utter_name = utter_mapping.get(intent)
            if utter_name:
                dispatcher.utter_message(response=utter_name)
                logger.info(f"[ConfNegAgr] Respuesta enviada con utter='{utter_name}' ✅")
            else:
                logger.warning(f"[ConfNegAgr] Intent no reconocido: '{intent}'")

            return []
        except Exception as e:
            logger.error(f"[ConfNegAgr] Error ejecutando acción: {e}", exc_info=True)
            return []

# -------------------- Búsqueda --------------------
class ActionBusqueda(Action):
    def name(self) -> Text:
        return "action_busqueda_situacion"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        intent = tracker.latest_message.get("intent", {}).get("name", "")
        user_msg = tracker.latest_message.get("text", "")
        logger.info(f"[Busqueda] Pedido recibido. Intent='{intent}', UserText='{user_msg}'")

        try:
            pedido_pendiente = tracker.get_slot("pedido_incompleto")
            if pedido_pendiente:
                dispatcher.utter_message("Detecté un nuevo pedido, marco el anterior como completado ✅")
                logger.info("[Busqueda] Pedido anterior marcado como completado")

            eventos = handle_busqueda(dispatcher, tracker, domain)
            eventos.append(SlotSet("pedido_incompleto", True))
            logger.info("[Busqueda] handle_busqueda ejecutado correctamente ✅")
            return eventos
        except Exception as e:
            logger.error(f"[Busqueda] Error ejecutando acción: {e}", exc_info=True)
            dispatcher.utter_message("Lo siento, hubo un error procesando tu pedido ❌")
            return []
