from actions_helper import BusquedaHelper, INTENT_TO_SLOTS, normalize_text, cargar_lookup
from pathlib import Path

# Cargar lookups
lookup_file = Path(__file__).parent.parent.parent / "bot" / "data" / "lookup_tables.yml"
LOOKUP_TABLES = cargar_lookup(lookup_file)

def handle_busqueda(dispatcher, tracker, domain):
    intent_name = tracker.latest_message.get("intent", {}).get("name", "buscar_producto")
    required_slots = INTENT_TO_SLOTS.get(intent_name, [])

    helper = BusquedaHelper(required_slots, LOOKUP_TABLES)
    entidades_validas, errores_detectados = helper.validar_entidades(dispatcher, tracker)

    # Identificar slots faltantes
    slots_detectados = [normalize_text(slot) for slot, _ in entidades_validas]
    slots_faltantes = [s for s in required_slots if normalize_text(s) not in slots_detectados]

    if entidades_validas:
        descripciones = [f"{slot}: {valor}" for slot, valor in entidades_validas]
        dispatcher.utter_message(
            f"Buscando {intent_name.replace('_', ' ')} con -> {', '.join(descripciones)}"
        )

    if slots_faltantes:
        helper.guiar_slots_faltantes(dispatcher, slots_faltantes)

    return []
