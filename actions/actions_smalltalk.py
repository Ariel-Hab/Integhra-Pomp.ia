from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import EventType
from transformers import pipeline
import logging

logger = logging.getLogger(__name__)

# Modelo ligero (podés cambiarlo a uno español)
generator = pipeline("text-generation", model="datificate/gpt2-small-spanish")

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
            # Intent actual
            current_intent = tracker.latest_message.get("intent", {}).get("name", "")
            user_message = tracker.latest_message.get("text", "")

            # Historial corto (últimos 5 eventos de usuario y bot)
            events = tracker.events[-10:]
            historial = []
            for e in events:
                if e.get("event") == "user":
                    historial.append(f"Usuario: {e.get('text')}")
                elif e.get("event") == "bot":
                    if e.get("text"):
                        historial.append(f"Bot: {e.get('text')}")
            historial_text = "\n".join(historial[-5:])

            # Slots relevantes (ejemplo: sentimiento, pending_search)
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

Información del bot:
- Puedes conversar con el usuario de forma ligera (smalltalk).
- Puedes responder saludos, despedidas, agradecimientos y preguntas personales simples.
- No inventes funcionalidades, solo menciona las que estén disponibles en el contexto o el historial.

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

            # Generar respuesta
            salida = generator(prompt, max_new_tokens=60, do_sample=True, top_p=0.9, temperature=0.7)
            respuesta = salida[0]["generated_text"].split("Responde como el bot:")[-1].strip()

            # Enviar respuesta
            dispatcher.utter_message(text=respuesta)

        except Exception as e:
            logger.error(f"[ActionSmallTalkGenerativo] Error: {e}", exc_info=True)
            dispatcher.utter_message(text="¡Hola! ¿Cómo estás?")

        return []
