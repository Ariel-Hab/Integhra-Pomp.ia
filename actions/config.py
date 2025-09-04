import logging
from pathlib import Path
from typing import Dict, List
import unicodedata
from scripts.config_loader import ConfigLoader
import yaml
# from actions.lookup_loader import get_lookup_tables

logger = logging.getLogger("LookupLoader")

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

# Cargar las lookup tables al importar el módulo
try:
    lookup_file = Path(__file__).parent.parent / "bot" / "data" / "lookup_tables.yml"
    LOOKUP_TABLES = cargar_lookup(str(lookup_file))
    logger.info(f"Lookup tables cargadas exitosamente: {list(LOOKUP_TABLES.keys())}")
except Exception as e:
    logger.error(f"Error cargando lookup tables: {e}")
    LOOKUP_TABLES = {}

# Función para obtener las lookup tables desde otros módulos
def get_lookup_tables() -> Dict[str, List[str]]:
    """Devuelve las lookup tables cargadas."""
    return LOOKUP_TABLES

logger = logging.getLogger("ConfigModule")

# Cargar configuración centralizada
try:
    INTENT_CONFIG = ConfigLoader.cargar_config()
    LOOKUP_TABLES = get_lookup_tables()
    logger.info("Configuración centralizada y lookup tables cargadas exitosamente")
    # Accesos rápidos
    INTENT_TO_SLOTS = {}
    INTENT_TO_ACTION = {}

    if isinstance(INTENT_CONFIG, dict):
        # Diccionario de diccionarios
        for k, v in INTENT_CONFIG.items():
            if isinstance(v, dict):
                INTENT_TO_SLOTS[k] = v.get("entities", [])
                INTENT_TO_ACTION[k] = v.get("action")
    elif isinstance(INTENT_CONFIG, list):
        # Lista de dicts
        for item in INTENT_CONFIG:
            if isinstance(item, dict) and "intent" in item:
                INTENT_TO_SLOTS[item["intent"]] = item.get("entities", [])
                INTENT_TO_ACTION[item["intent"]] = item.get("action")
    else:
        logger.error(f"Formato de INTENT_CONFIG inesperado: {type(INTENT_CONFIG)}")


except Exception as e:
    logger.error(f"Error cargando configuración: {e}")
    INTENT_CONFIG = {"intents": {}, "entities": {}, "detection_patterns": {}}
    LOOKUP_TABLES = {}
    INTENT_TO_SLOTS = {}
    INTENT_TO_ACTION = {}
        
