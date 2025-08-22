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

from scripts.config_loader import ConfigLoader


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


# def cargar_config(path="intents_config.yml") -> Dict[str, Any]:
    # path_obj = Path(path)
    # if not path_obj.is_absolute():
    #     # buscar desde la raíz del proyecto
    #     path_obj = (Path(__file__).resolve().parent.parent / path).resolve()
    # if not path_obj.exists():
    #     raise FileNotFoundError(f"No se encontró el archivo: {path_obj}")

    # with open(path_obj, "r", encoding="utf-8") as f:
    #     data = yaml.safe_load(f) or {}

    # if "intents" not in data or not isinstance(data["intents"], list):
    #     raise ValueError(f"Formato inválido en {path_obj}: falta 'intents'")

    # config = {}
    # for i in data["intents"]:
    #     if "name" not in i:
    #         raise ValueError(f"Intent inválido: {i}")
    #     if "entities" not in i:
    #         i["entities"] = []   # default
    #     if "action" not in i:
    #         i["action"] = None   # default

    #     config[i["name"]] = i

    # return config



# Diccionario global disponible en el proyecto
config_data = ConfigLoader.cargar_config("intents_config.yml")
INTENT_CONFIG = config_data["intents"]
fallback = config_data.get("fallback", {})

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


