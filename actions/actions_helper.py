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
def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:  # evitar duplicados
        logger.setLevel(logging.DEBUG)
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        ch.setFormatter(formatter)
        logger.addHandler(ch)
    return logger

logger = get_logger("BusquedaHelper")


def cargar_config(path="intents_config.yml") -> Dict[str, Any]:
    path_obj = Path(path)
    if not path_obj.is_absolute():
        # buscar desde la raíz del proyecto
        path_obj = (Path(__file__).resolve().parent.parent / path).resolve()
    if not path_obj.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {path_obj}")

    with open(path_obj, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if "intents" not in data or not isinstance(data["intents"], list):
        raise ValueError(f"Formato inválido en {path_obj}: falta 'intents'")

    config = {}
    for i in data["intents"]:
        if "name" not in i:
            raise ValueError(f"Intent inválido: {i}")
        if "entities" not in i:
            i["entities"] = []   # default
        if "action" not in i:
            i["action"] = None   # default

        config[i["name"]] = i

    return config



# Diccionario global disponible en el proyecto
INTENT_CONFIG = cargar_config()

# Accesos rápidos
INTENT_TO_SLOTS = {k: v.get("entities", []) for k, v in INTENT_CONFIG.items()}
INTENT_TO_ACTION = {k: v.get("action") for k, v in INTENT_CONFIG.items()}



# -------------------- FUNCIONES AUXILIARES --------------------
def normalize_text(text: str) -> str:
    """Convierte a minúsculas y elimina acentos."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8").lower()


def cargar_lookup(path_lookup: str) -> Dict[str, List[str]]:
    """
    Carga los lookups desde un archivo Rasa NLU o lista/dict YAML.
    Devuelve diccionario: {slot_name: [valor1, valor2, ...]}
    """
    path = Path(path_lookup)
    if not path.exists():
        logger.warning(f"No existe el archivo lookup: {path_lookup}")
        return {}

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    lookup_dict = {}

    if isinstance(data, dict):
        if "nlu" in data:  # formato Rasa
            for entry in data["nlu"]:
                if "lookup" in entry and "examples" in entry:
                    ejemplos = [
                        line.strip()[2:].strip()
                        for line in entry["examples"].splitlines()
                        if line.strip().startswith("- ")
                    ]
                    lookup_dict[entry["lookup"]] = ejemplos
        else:  # diccionario directo
            lookup_dict = {k: (v if isinstance(v, list) else []) for k, v in data.items()}

    elif isinstance(data, list):  # lista de {name, elements}
        for item in data:
            if isinstance(item, dict) and "name" in item and "elements" in item:
                lookup_dict[item["name"]] = item["elements"]

    logger.info(f"Lookup cargado con {len(lookup_dict)} categorías")
    return lookup_dict


# -------------------- CLASE BUSQUEDA HELPER --------------------
class BusquedaHelper:
    """Helper PRO para validar entidades, sugerir correcciones y guiar al usuario."""

    def __init__(self, required_slots: List[str], lookup_tables: Dict[str, List[str]]):
        self.required_slots = required_slots
        self.lookup_tables = lookup_tables

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
        logger.debug(f"Mensaje recibido: '{mensaje}'")

        entidades_validas = set()
        errores_detectados = []
        slots_detectados = set()

        for slot in self.required_slots:
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
                if slot not in self.lookup_tables or not self.lookup_tables.get(slot):
                    # No hay lookup definida para este slot, dejamos pasar la entidad
                    entidades_validas.add((slot, entidad))
                    slots_detectados.add(slot)
                    logger.debug(f"Entidad válida (sin lookup): '{entidad}' ({slot})")
                else:
                    lookup_norm = [normalize_text(v) for v in self.lookup_tables.get(slot, [])]
                    if entidad_norm in lookup_norm:
                        entidades_validas.add((slot, entidad))
                        slots_detectados.add(slot)
                        logger.debug(f"Entidad válida: '{entidad}' ({slot})")
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
                            logger.info(f"Sugerencia para '{entidad}': {similares[0]}")
                        else:
                            dispatcher.utter_message(
                                f"❌ '{entidad}' no existe en '{slot}' y no encontré sugerencias."
                            )

        slots_faltantes = [s for s in self.required_slots if s not in slots_detectados]

        if (completar_todos and slots_faltantes) or not entidades_validas:
            self.guiar_slots_faltantes(dispatcher, slots_faltantes)

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
        logger.info(f"Guiando usuario para completar slots: {slots_faltantes}")
