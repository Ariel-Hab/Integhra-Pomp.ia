# actions/generic_intent_reporter.py
from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher

class ActionGenericIntentReporter(Action):

    def name(self) -> Text:
        return "action_generica"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        # Obtener el último intent detectado y su confianza
        last_intent = tracker.latest_message.get("intent", {})
        intent_name = last_intent.get("name", "unknown")
        confidence = last_intent.get("confidence", 0.0)

        # Responder al usuario con la información
        dispatcher.utter_message(
            text=f"He detectado el intent '{intent_name}' con una confianza de {confidence:.2f}"
        )

        return []
