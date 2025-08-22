import logging
from actions_helper import INTENT_TO_SLOTS, normalize_text, cargar_lookup
from rasa_sdk.events import SlotSet
from typing import Any, Text, Dict, List, Tuple
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk import Tracker
from rasa_sdk.events import EventType
import difflib
from pathlib import Path

# Logger
logger = logging.getLogger("ActionSituaciones")

# Cargar lookups
lookup_file = Path(__file__).parent.parent.parent / "bot" / "data" / "lookup_tables.yml"
LOOKUP_TABLES = cargar_lookup(lookup_file)

def handle_busqueda(dispatcher, tracker, domain):
    intent_name = tracker.latest_message.get("intent", {}).get("name", "buscar_producto")
    required_slots = INTENT_TO_SLOTS.get(intent_name, [])

    logger.info(f"[handle_busqueda] Intent recibido='{intent_name}', RequiredSlots={required_slots}")

    helper = BusquedaHelper(required_slots, LOOKUP_TABLES)

    try:
        entidades_validas, errores_detectados, slots_faltantes = helper.procesar_slots(
            dispatcher, tracker, completar_todos=False
        )

        logger.debug(f"[handle_busqueda] Entidades válidas={entidades_validas}")
        logger.debug(f"[handle_busqueda] Errores detectados={errores_detectados}")
        logger.debug(f"[handle_busqueda] Slots faltantes={slots_faltantes}")

        if entidades_validas:
            descripciones = [f"{slot}: {valor}" for slot, valor in entidades_validas]
            dispatcher.utter_message(
                f"Buscando {intent_name.replace('_', ' ')} con -> {', '.join(descripciones)}"
            )
            logger.info(f"[handle_busqueda] Búsqueda ejecutada con entidades={descripciones} ✅")

            # Borrar slots usados en este intent
            return [SlotSet(s, None) for s, _ in entidades_validas]

        logger.warning("[handle_busqueda] No se encontraron entidades válidas, guiando al usuario...")
        return []

    except Exception as e:
        logger.error(f"[handle_busqueda] Error durante ejecución: {e}", exc_info=True)
        dispatcher.utter_message("❌ Hubo un error procesando la búsqueda.")
        return []

# -------------------- CLASE BUSQUEDA HELPER --------------------
class BusquedaHelper:
    """Helper PRO para validar entidades, sugerir correcciones y guiar al usuario."""

    def __init__(self, required_slots: List[str], lookup_tables: Dict[str, List[str]]):
        self.required_slots = required_slots
        self.lookup_tables = lookup_tables
        logger.debug(f"[BusquedaHelper] Inicializado con required_slots={required_slots}")

    def procesar_slots(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        completar_todos: bool = True
    ) -> Tuple[List[Tuple[str, str]], List[Dict[str, Any]], List[str]]:
        """
        Valida entidades y guía slots faltantes.
        Devuelve: (entidades_validas, errores_detectados, slots_faltantes)
        """
        mensaje = tracker.latest_message.get("text", "")
        logger.debug(f"[BusquedaHelper] Mensaje recibido: '{mensaje}'")

        entidades_validas = set()
        errores_detectados = []
        slots_detectados = set()

        for slot in self.required_slots:
            entidades_slot = [
                e.get("value") for e in tracker.latest_message.get("entities", [])
                if e.get("entity") == slot
            ]

            if not entidades_slot:
                logger.debug(f"[BusquedaHelper] No se detectaron entidades para slot '{slot}'")
                continue

            for entidad in entidades_slot:
                entidad_norm = normalize_text(entidad)
                lookup_norm = [normalize_text(v) for v in self.lookup_tables.get(slot, [])]

                if slot not in self.lookup_tables or not self.lookup_tables.get(slot):
                    entidades_validas.add((slot, entidad))
                    slots_detectados.add(slot)
                    logger.debug(f"[BusquedaHelper] Entidad válida (sin lookup): '{entidad}' ({slot})")
                elif entidad_norm in lookup_norm:
                    entidades_validas.add((slot, entidad))
                    slots_detectados.add(slot)
                    logger.debug(f"[BusquedaHelper] Entidad válida: '{entidad}' ({slot})")
                else:
                    similares = difflib.get_close_matches(entidad_norm, lookup_norm, n=3, cutoff=0.7)
                    errores_detectados.append({
                        "palabra": entidad,
                        "categoria": slot,
                        "sugerencias": similares
                    })
                    if similares:
                        dispatcher.utter_message(
                            f"⚠ '{entidad}' no existe en '{slot}'. ¿Quisiste decir '{similares[0]}'?"
                        )
                        logger.warning(f"[BusquedaHelper] Entidad inválida '{entidad}', sugerencias={similares}")
                    else:
                        dispatcher.utter_message(
                            f"❌ '{entidad}' no existe en '{slot}' y no encontré sugerencias."
                        )
                        logger.error(f"[BusquedaHelper] Entidad inválida '{entidad}', sin sugerencias.")

        slots_faltantes = [s for s in self.required_slots if s not in slots_detectados]

        if (completar_todos and slots_faltantes) or not entidades_validas:
            self.guiar_slots_faltantes(dispatcher, slots_faltantes)

        logger.debug(f"[BusquedaHelper] Resultado -> EntidadesValidas={entidades_validas}, Errores={errores_detectados}, SlotsFaltantes={slots_faltantes}")
        return list(entidades_validas), errores_detectados, slots_faltantes

    def guiar_slots_faltantes(self, dispatcher: CollectingDispatcher, slots_faltantes: List[str] = None):
        """Guía al usuario dinámicamente según los slots faltantes"""
        slots_faltantes = slots_faltantes or self.required_slots
        if not slots_faltantes:
            return

        mensaje = (
            f"Por favor indica el valor para '{slots_faltantes[0]}'"
            if len(slots_faltantes) == 1
            else f"Por favor provee alguno de los siguientes valores: {', '.join(slots_faltantes)}"
        )

        dispatcher.utter_message(mensaje)
        logger.info(f"[BusquedaHelper] Guiando usuario para completar slots: {slots_faltantes}")
