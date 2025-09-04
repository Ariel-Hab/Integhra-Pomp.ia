from typing import Dict, Any, List
from rasa_sdk import Tracker
from scripts.config_loader import ConfigLoader
from .config import INTENT_CONFIG

def get_intent_info(intent_name: str) -> Dict[str, Any]:
    return INTENT_CONFIG.get("intents", {}).get(intent_name, {})

def is_search_intent(intent_name: str) -> bool:
    return get_intent_info(intent_name).get("grupo") == "busqueda"

def is_small_talk_intent(intent_name: str) -> bool:
    return get_intent_info(intent_name).get("grupo") == "small_talk"

def detect_sentiment_in_message(user_message: str) -> str:
    return ConfigLoader.detect_sentiment_in_message(INTENT_CONFIG, user_message)

def detect_implicit_intentions(user_message: str) -> List[str]:
    return ConfigLoader.detect_implicit_intentions(INTENT_CONFIG, user_message)

def get_search_type_from_intent(intent_name: str) -> str:
    if intent_name == "buscar_producto":
        return "producto"
    elif intent_name == "buscar_oferta":
        return "oferta"
    return "producto"
