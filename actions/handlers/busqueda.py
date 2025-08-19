from actions_helper import BusquedaHelper, INTENT_TO_SLOTS, normalize_text, cargar_lookup
from rasa_sdk.events import SlotSet
from pathlib import Path

# Cargar lookups
lookup_file = Path(__file__).parent.parent.parent / "bot" / "data" / "lookup_tables.yml"
LOOKUP_TABLES = cargar_lookup(lookup_file)

def handle_busqueda(dispatcher, tracker, domain):
    intent_name = tracker.latest_message.get("intent", {}).get("name", "buscar_producto")
    required_slots = INTENT_TO_SLOTS.get(intent_name, [])

    helper = BusquedaHelper(required_slots, LOOKUP_TABLES)

    # Validar entidades y guiar slots faltantes (no es necesario tener todos)
    entidades_validas, errores_detectados, slots_faltantes = helper.procesar_slots(
        dispatcher, tracker, completar_todos=False
    )

    # Ejecutar búsqueda si hay al menos un slot válido
    if entidades_validas:
        descripciones = [f"{slot}: {valor}" for slot, valor in entidades_validas]
        dispatcher.utter_message(
            f"Buscando {intent_name.replace('_', ' ')} con -> {', '.join(descripciones)}"
        )

        # Borrar slots usados en este intent
        return [SlotSet(s, None) for s, _ in entidades_validas]

    # Si no hay slots válidos, el helper ya guió al usuario
    return []
