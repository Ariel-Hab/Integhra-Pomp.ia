from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher

class ActionMostrarEntidades(Action):

    def name(self) -> Text:
        return "action_mostrar_entidades"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Obtener intent detectado
        intent = tracker.latest_message.get("intent", {}).get("name", "desconocido")

        # Obtener entidades
        entidades = tracker.latest_message.get("entities", [])

        # Armar mensaje
        mensaje = f"Intent detectado: {intent}\n"

        if not entidades:
            mensaje += "No detecté ninguna entidad en tu mensaje."
        else:
            mensaje += "Detecté las siguientes entidades:\n"
            # Mostrar entidades sin duplicados (por entidad y valor)
            entidades_vistas = set()
            for ent in entidades:
                entidad = ent.get("entity", "desconocida")
                valor = ent.get("value", "sin valor")
                clave = (entidad, valor)
                if clave not in entidades_vistas:
                    mensaje += f"• {entidad}: {valor}\n"
                    entidades_vistas.add(clave)


        # Enviar mensaje al usuario
        dispatcher.utter_message(text=mensaje.strip())

        return []
