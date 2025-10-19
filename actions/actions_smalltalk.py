# actions/actions_smalltalk_situacion.py

from actions.logger import log_message
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import EventType
import logging
import random

# ✅ IMPORTACIÓN SIMPLIFICADA
from .models.model_manager import generate_text_with_context

logger = logging.getLogger(__name__)

class ActionSmallTalkSituacion(Action):
    def name(self) -> str:
        return "action_smalltalk_situacion"

    def _get_simple_prompt(self, intent: str, user_message: str) -> str:
        """Prompts ultra simples"""
        
        prompts = {
            "saludo": f'Usuario dice: "{user_message}"\nRespondé: Hola + pregunta qué necesita.\nBot:',
            "despedida": f'Usuario: "{user_message}"\nRespondé: Despedida amigable.\nBot:',
            "preguntar_como_estas": f'Usuario: "{user_message}"\nRespondé: "Todo bien" + pregunta qué necesita.\nBot:',
            "responder_como_estoy": f'Usuario: "{user_message}"\nRespondé: Empatía + pregunta cómo ayudar.\nBot:',
            "responder_estoy_bien": f'Usuario: "{user_message}"\nRespondé: "Genial" + pregunta qué necesita.\nBot:',
            "pedir_chiste": f'Usuario: "{user_message}"\nContá un chiste corto de animales + pregunta.\nBot:',
            "reirse": f'Usuario: "{user_message}"\nRespondé alegre + pregunta qué necesita.\nBot:' # CORREGIDO
        }
        
        return prompts.get(intent, f'Usuario: "{user_message}"\nBot:')

    # ✅ MÉTODO RUN COMPLETAMENTE REFACTORIZADO
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict) -> list[EventType]:
        try:
            log_message(tracker, nlu_conf_threshold=0.6)
            current_intent = tracker.latest_message.get("intent", {}).get("name", "")
            user_message = tracker.latest_message.get("text", "")

            prompt = self._get_simple_prompt(current_intent, user_message)
            logger.info(f"[SmallTalk] Intent: {current_intent}")

            temp = 0.6 if current_intent in ["saludo", "despedida"] else 0.7
            max_tokens = 30 if current_intent in ["saludo", "despedida"] else 40
            
            # 1. Intentar generar la respuesta
            logger.info("[SmallTalk] Intentando generar respuesta...")
            respuesta = generate_text_with_context(
                prompt=prompt,
                tracker=tracker,
                max_new_tokens=max_tokens,
                temperature=temp
            )

            # 2. Validar la respuesta generada
            if not self._is_response_valid(respuesta, current_intent):
                logger.warning(f"[SmallTalk] La respuesta generada ('{respuesta}') no pasó la validación. Usando fallback.")
                respuesta = self._get_fallback_response(current_intent)
            
            # 3. Enviar la respuesta final (ya sea la generada o el fallback)
            logger.info(f"[SmallTalk] ✓ Respuesta final: '{respuesta}'")
            dispatcher.utter_message(text=respuesta)

        except Exception as e:
            logger.error(f"[SmallTalk] Error crítico en run: {e}", exc_info=True)
            fallback = self._get_fallback_response(tracker.latest_message.get("intent", {}).get("name", ""))
            dispatcher.utter_message(text=fallback)

        return []

    def _is_response_valid(self, response: str, intent: str) -> bool:
        """
        Realiza una validación estricta de la respuesta del LLM para small talk.
        Devuelve True si la respuesta es válida, False en caso contrario.
        """
        # Falla si no hay respuesta o está vacía
        if not response or not response.strip():
            logger.debug("[Validation] Falla: Respuesta vacía o None.")
            return False
        
        # Falla si es muy corta o muy larga
        if len(response) < 5 or len(response) > 100:
            logger.debug(f"[Validation] Falla: Longitud inválida ({len(response)} caracteres).")
            return False

        # Falla si contiene palabras que no deberían estar en un small talk simple
        palabras_raras = [
            'ciñel', 'pedazo', 'pluma', 'víbora', 'dioses', 'universo', 
            'estrellas', 'castellano', 'verbo', 'adjetivo', 'diccionario'
        ]
        if any(palabra in response.lower() for palabra in palabras_raras):
            logger.debug("[Validation] Falla: Contiene 'palabras raras'.")
            return False
        
        # Falla si no contiene palabras clave esperadas (excepto para despedidas)
        if intent != "despedida" and not any(palabra in response.lower() for palabra in 
                                             ['hola', 'che', 'dale', 'joya', 'bien', 'genial', 
                                              'ayudo', 'necesitás', 'buscás', 'qué', 'cómo']):
            logger.debug("[Validation] Falla: No contiene palabras clave de contexto.")
            return False

        return True

    def _get_fallback_response(self, intent: str) -> str:
        """Fallbacks confiables y variados (sin cambios)."""
        fallbacks = {
            "saludo": [
                "¡Hola! ¿En qué te puedo ayudar?",
                "¡Che, hola! ¿Qué necesitás?",
                "¡Buenas! ¿En qué te ayudo?"
            ],
            "despedida": [
                "¡Chau! Acá estoy si me necesitás.",
                "¡Nos vemos! Cualquier cosa avisame.",
                "¡Dale, cuidate!",
            ],
            "preguntar_como_estas": [
                "¡Todo bien! ¿Y vos? ¿Qué necesitás?",
                "¡Joya! ¿En qué te puedo ayudar?",
            ],
            "responder_como_estoy": [
                "¡Qué bueno che! ¿En qué te ayudo?",
                "Te entiendo. ¿Te puedo ayudar con algo?",
            ],
            "responder_estoy_bien": [
                "¡Genial! ¿Qué necesitás?",
                "¡Joya! ¿En qué te ayudo?",
            ],
            "pedir_chiste": [
                "¿Por qué los perros no usan computadora? Le tienen miedo al mouse. ¿Necesitás algo?",
                "¿Cómo se llama un perro mago? Labracadabrador. Jaja. ¿Te ayudo con algo?",
            ],
            "reirse": [
                "¡Jaja me alegro! ¿En qué te ayudo?",
                "¡Qué bueno! ¿Necesitás algo?",
            ]
        }
        
        default_fallbacks = ["¿En qué te puedo ayudar?", "Contame qué necesitás.", "¿Qué buscás?"]
        return random.choice(fallbacks.get(intent, default_fallbacks))