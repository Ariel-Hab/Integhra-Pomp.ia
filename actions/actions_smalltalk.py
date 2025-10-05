# actions_smalltalk.py
from actions.logger import log_message
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import EventType
import logging

from .models.model_manager import generate_text

logger = logging.getLogger(__name__)

class ActionSmallTalkSituacion(Action):
    def name(self) -> str:
        return "action_smalltalk_situacion"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: dict
    ) -> list[EventType]:
        try:
            log_message(tracker, nlu_conf_threshold=0.6)
            current_intent = tracker.latest_message.get("intent", {}).get("name", "")
            user_message = tracker.latest_message.get("text", "")

            # Historial corto (últimos 5 mensajes usuario/bot)
            events = tracker.events[-10:]
            historial = []
            for e in events:
                if e.get("event") == "user":
                    historial.append(f"Usuario: {e.get('text')}")
                elif e.get("event") == "bot" and e.get("text"):
                    historial.append(f"Bot: {e.get('text')}")
            historial_text = "\n".join(historial[-5:])

            # Slots relevantes
            slots = {
                "sentimiento": tracker.get_slot("sentimiento"),
                "pending_search": tracker.get_slot("pending_suggestion"),
                "engagement": tracker.get_slot("user_engagement_level")
            }
            slots_text = ", ".join([f"{k}={v}" for k, v in slots.items() if v])

            # Prompt base
            prompt = f"""
Eres un asistente virtual en español.
Responde de forma breve, clara y natural, manteniendo un tono amable y cercano.

Contexto de la conversación:
{historial_text}

Último mensaje del usuario:
{user_message}

Intent detectado:
{current_intent}

Slots relevantes:
{slots_text}

Responde como el bot:
"""

            respuesta = generate_text(prompt, max_new_tokens=60)

            dispatcher.utter_message(text=respuesta)

        except Exception as e:
            logger.error(f"[ActionSmallTalkGenerativo] Error: {e}", exc_info=True)
            dispatcher.utter_message(text="¡Hola! ¿Cómo estás?")

        return []
