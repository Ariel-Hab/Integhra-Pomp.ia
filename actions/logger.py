import csv
import os
from datetime import datetime
from typing import Dict, Any

# LOG_FILE = "unrecognized_messages.csv"

def log_message(tracker: Any, nlu_conf_threshold: float = 0.5):
    """
    Guarda en un CSV los mensajes con baja confianza o sin reconocimiento de intent.

    Args:
        tracker: El tracker de Rasa pasado en la action.
        nlu_conf_threshold: Umbral de confianza mínimo (default=0.5).
    """

    latest_message = tracker.latest_message
    text = latest_message.get("text", "")
    intent = latest_message.get("intent", {}).get("name", "none")
    confidence = latest_message.get("intent", {}).get("confidence", 0.0)

    # Condición: baja confianza o intent 'nlu_fallback'
    if confidence < nlu_conf_threshold or intent in ["nlu_fallback", "None"]:
        row = {
            "timestamp": datetime.utcnow().isoformat(),
            "user_message": text,
            "detected_intent": intent,
            "confidence": confidence,
            "sender_id": tracker.sender_id,
        }

        # file_exists = os.path.isfile(LOG_FILE)
        # with open(LOG_FILE, mode="a", newline="", encoding="utf-8") as f:
        #     writer = csv.DictWriter(f, fieldnames=row.keys())
        #     if not file_exists:
        #         writer.writeheader()
        #     writer.writerow(row)
