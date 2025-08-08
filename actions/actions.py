from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher

class ActionMostrarEntidades(Action):

    def name(self) -> Text:
        return "action_mostrar_entidades"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        entidades = tracker.latest_message.get("entities", [])

        entidad_map = {}
        for ent in entidades:
            entidad = ent.get("entity")
            valor = ent.get("value")
            if entidad and valor:
                entidad_map[entidad] = valor

        mensaje = ""

        if "producto" in entidad_map:
            mensaje += f"¿Estás interesado en el producto **{entidad_map['producto']}**?"

        if "tipo_oferta" in entidad_map:
            mensaje += f" Hay una oferta del tipo **{entidad_map['tipo_oferta']}**."

        if "cantidad_descuento" in entidad_map:
            mensaje += f" Tiene un descuento de **{entidad_map['cantidad_descuento']}**."

        if "bonificacion" in entidad_map:
            mensaje += f" La bonificación es de **{entidad_map['bonificacion']}**."

        if "categoria" in entidad_map:
            mensaje += f" Pertenece a la categoría **{entidad_map['categoria']}**."

        if "ingrediente_activo" in entidad_map:
            mensaje += f" Contiene **{entidad_map['ingrediente_activo']}** como principio activo."

        if "accion_terapeutica" in entidad_map:
            mensaje += f" Es usado para **{entidad_map['accion_terapeutica']}**."

        if "cantidad_stock" in entidad_map:
            mensaje += f" Hay un stock de **{entidad_map['cantidad_stock']}** unidades."

        if "fecha" in entidad_map:
            mensaje += f" La fecha mencionada es **{entidad_map['fecha']}**."

        if "tiempo" in entidad_map:
            mensaje += f" El tiempo indicado es **{entidad_map['tiempo']}**."

        if "proveedor" in entidad_map:
            mensaje += f" El proveedor es **{entidad_map['proveedor']}**."

        if "precio" in entidad_map:
            mensaje += f" El precio informado es **{entidad_map['precio']}**."

        if not mensaje:
            mensaje = "No detecté ninguna entidad relevante para continuar la conversación."

        dispatcher.utter_message(text=mensaje.strip())
        return []
