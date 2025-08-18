# actions_helper.py
from typing import Any, Text, Dict, List, Tuple
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk import Tracker
from rasa_sdk.events import EventType
import difflib
import unicodedata
import yaml
from pathlib import Path
import logging

# -------------------- LOGGING --------------------
logger = logging.getLogger("BusquedaHelper")
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)

# -------------------- CONSTANTES --------------------
INTENT_TO_SLOTS = {
    "buscar_producto": ["producto", "categoria", "proveedor"],
    "buscar_oferta": ["producto", "cantidad_descuento", "proveedor"]
}

# -------------------- FUNCIONES AUXILIARES --------------------
def normalize_text(text: str) -> str:
    """Convierte a minúsculas y elimina acentos."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8").lower()

def cargar_lookup(path_lookup: str) -> Dict[str, List[str]]:
    """
    Carga los lookups desde un archivo Rasa NLU o lista/dict YAML.
    Devuelve diccionario: {slot_name: [valor1, valor2, ...]}
    """
    logger.info(f"Cargando lookup desde: {path_lookup}")
    path = Path(path_lookup)
    if not path.exists():
        logger.warning(f"No existe el archivo lookup: {path_lookup}")
        return {}

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    lookup_dict = {}

    # Rasa NLU lookup
    if isinstance(data, dict) and "nlu" in data:
        for entry in data["nlu"]:
            if "lookup" in entry and "examples" in entry:
                key = entry["lookup"]
                ejemplos = [
                    line.strip()[2:].strip()
                    for line in entry["examples"].splitlines()
                    if line.strip().startswith("- ")
                ]
                lookup_dict[key] = ejemplos

    # Diccionario directo {slot: [valores]}
    elif isinstance(data, dict):
        for k, v in data.items():
            lookup_dict[k] = v if isinstance(v, list) else []

    # Lista de dicts {name, elements}
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "name" in item and "elements" in item:
                lookup_dict[item["name"]] = item["elements"]

    logger.info(f"Lookup cargado: {list(lookup_dict.keys())}")
    return lookup_dict

# -------------------- CLASE BUSQUEDA HELPER --------------------
class BusquedaHelper:
    """
    Helper PRO para validar entidades, sugerir correcciones, guiar al usuario
    y generar logs detallados.
    """

    def __init__(self, required_slots: List[str], lookup_tables: Dict[str, List[str]]):
        self.required_slots = required_slots
        self.lookup_tables = lookup_tables

    def guiar_slots_faltantes(self, dispatcher: CollectingDispatcher, slots_faltantes: List[str] = None):
        """Mensaje dinámico al usuario según slots faltantes"""
        if not slots_faltantes:
            slots_faltantes = self.required_slots

        if not slots_faltantes:
            return

        if len(slots_faltantes) == 1:
            mensaje = f"Por favor indica el valor para '{slots_faltantes[0]}'."
        elif len(slots_faltantes) > 1:
            mensaje = f"Por favor provee alguno de los siguientes valores: {', '.join(slots_faltantes)}."

        dispatcher.utter_message(mensaje)
        logger.info(f"Guiando usuario para completar slots: {slots_faltantes}")

    def validar_entidades(
        self, dispatcher: CollectingDispatcher, tracker: Tracker
    ) -> Tuple[List[Tuple[str, str]], List[Dict[str, Any]]]:
        """
        Valida entidades detectadas por Rasa contra las lookup tables.
        Devuelve: (entidades_validas -> [(slot, valor)], errores_detectados)
        """
        entidades_validas: List[Tuple[str, str]] = []
        errores_detectados = []

        mensaje = tracker.latest_message.get("text", "")
        logger.debug(f"Mensaje para validación: '{mensaje}'")

        for slot in self.required_slots:
            # Extraer entidades detectadas por Rasa
            entidades_slot = [
                e.get("value") for e in tracker.latest_message.get("entities", [])
                if e.get("entity") == slot
            ]

            if not entidades_slot:
                logger.debug(f"No se detectaron entidades para slot '{slot}'")
                continue

            lookup_norm = [normalize_text(v) for v in self.lookup_tables.get(slot, [])]

            for entidad in entidades_slot:
                entidad_norm = normalize_text(entidad)
                if entidad_norm in lookup_norm:
                    entidades_validas.append((slot, entidad))
                    logger.debug(f"Entidad válida detectada: '{entidad}' para slot '{slot}'")
                else:
                    similares = difflib.get_close_matches(entidad_norm, lookup_norm, n=3, cutoff=0.7)
                    errores_detectados.append({
                        "palabra": entidad,
                        "categoria": slot,
                        "sugerencias": similares
                    })
                    if similares:
                        dispatcher.utter_message(
                            f"⚠ La palabra '{entidad}' (categoría '{slot}') no existe. "
                            f"¿Quisiste decir '{similares[0]}'?"
                        )
                        logger.info(f"Entidad '{entidad}' sugerida: '{similares[0]}'")
                    else:
                        dispatcher.utter_message(
                            f"❌ La palabra '{entidad}' (categoría '{slot}') no existe y no encontré sugerencias."
                        )
                        logger.info(f"Entidad '{entidad}' no encontrada en lookup '{slot}'")

        # Deduplicar (por slot, valor)
        entidades_validas = list(dict.fromkeys(entidades_validas))
        logger.debug(f"Entidades válidas finales: {entidades_validas}")
        return entidades_validas, errores_detectados


        # Deduplicar
        entidades_validas = list(dict.fromkeys(entidades_validas))
        logger.debug(f"Entidades válidas finales: {entidades_validas}")
        return entidades_validas, errores_detectados
