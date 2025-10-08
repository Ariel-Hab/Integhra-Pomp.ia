from actions.logger import log_message
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import EventType
import logging
import random

from .models.model_manager import generate_text

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
            
            "reirse": f'Usuario: "{user_message}"\nRespondé alegre + pregunta qué necesita.\nBot:'
        }
        
        return prompts.get(intent, f'Usuario: "{user_message}"\nBot:')

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict) -> list[EventType]:
        try:
            log_message(tracker, nlu_conf_threshold=0.6)
            current_intent = tracker.latest_message.get("intent", {}).get("name", "")
            user_message = tracker.latest_message.get("text", "")

            # Prompt simple
            prompt = self._get_simple_prompt(current_intent, user_message)

            logger.info(f"[SmallTalk] Intent: {current_intent}")
            logger.info(f"[SmallTalk] Prompt: {prompt}")

            # Parámetros conservadores
            temp = 0.6 if current_intent in ["saludo", "despedida"] else 0.7
            max_tokens = 40 if current_intent in ["saludo", "despedida"] else 50
            
            # Intentar generar
            respuesta = generate_text(prompt, max_new_tokens=max_tokens, temperature=temp)

            logger.info(f"[SmallTalk] Respuesta generada: '{respuesta}'")

            # Limpieza adicional
            respuesta = respuesta.strip()
            
            # Remover prefijos
            for prefix in ["Bot:", "Pompi:", "Respuesta:", "R:", "B:", "-", "•", ">"]:
                if respuesta.startswith(prefix):
                    respuesta = respuesta[len(prefix):].strip()
            
            # Validación estricta
            palabras_raras = ['ciñel', 'pedazo', 'pluma', 'víbora', 'dioses', 'universo', 
                            'estrellas', 'castellano', 'verbo', 'adjetivo', 'diccionario']
            
            tiene_palabras_raras = any(palabra in respuesta.lower() for palabra in palabras_raras)
            es_muy_corta = len(respuesta) < 5
            es_muy_larga = len(respuesta) > 100
            no_tiene_sentido = not any(palabra in respuesta.lower() for palabra in 
                                      ['hola', 'che', 'dale', 'joya', 'bien', 'genial', 
                                       'ayudo', 'necesita', 'busca', 'chau', 'qué', 'como'])
            
            if tiene_palabras_raras or es_muy_corta or es_muy_larga or no_tiene_sentido:
                logger.warning(f"Respuesta inválida: raras={tiene_palabras_raras}, "
                             f"corta={es_muy_corta}, larga={es_muy_larga}, sin_sentido={no_tiene_sentido}")
                respuesta = self._get_fallback_response(current_intent)

            logger.info(f"[SmallTalk] ✓ Final: '{respuesta}'")
            dispatcher.utter_message(text=respuesta)

        except Exception as e:
            logger.error(f"[SmallTalk] Error: {e}", exc_info=True)
            dispatcher.utter_message(text=self._get_fallback_response(current_intent))

        return []

    def _get_fallback_response(self, intent: str) -> str:
        """Fallbacks confiables y variados"""
        fallbacks = {
            "saludo": [
                "¡Hola! ¿En qué te puedo ayudar?",
                "¡Che, hola! ¿Qué necesitás?",
                "¡Hola! Contame qué buscás.",
                "¡Buenas! ¿En qué te ayudo?"
            ],
            "despedida": [
                "¡Chau! Acá estoy si me necesitás.",
                "¡Nos vemos! Cualquier cosa avisame.",
                "¡Dale, cuidate!",
                "¡Hasta luego!"
            ],
            "preguntar_como_estas": [
                "¡Todo bien! ¿Y vos? ¿Qué necesitás?",
                "¡Joya! ¿En qué te puedo ayudar?",
                "¡De diez! ¿Qué buscás?",
                "¡Re bien! ¿Necesitás algo?"
            ],
            "responder_como_estoy": [
                "¡Qué bueno che! ¿En qué te ayudo?",
                "Dale. ¿Necesitás algo?",
                "Te entiendo. ¿Te puedo ayudar con algo?",
                "Ah. ¿Querés que te ayude con algo?"
            ],
            "responder_estoy_bien": [
                "¡Genial! ¿Qué necesitás?",
                "¡Joya! ¿En qué te ayudo?",
                "¡Dale! Contame.",
                "¡Perfecto! ¿Buscás algo?"
            ],
            "pedir_chiste": [
                "¿Por qué los perros no usan computadora? Le tienen miedo al mouse. ¿Necesitás algo?",
                "¿Cómo se llama un perro mago? Labracadabrador. Jaja. ¿Te ayudo con algo?",
                "¿Qué hace un perro con un taladro? Taladrando. ¿Buscás algún producto?",
                "¿Por qué las vacas usan campanas? Porque los cuernos no les funcionan. ¿Qué necesitás?"
            ],
            
            "reirse": [
                "¡Jaja me alegro! ¿En qué te ayudo?",
                "¡Qué bueno! ¿Necesitás algo?",
                "¡Dale! ¿Te puedo ayudar con algo?",
                "¡Jeje genial! Contame qué buscás."
            ]
        }
        
        return random.choice(fallbacks.get(intent, [
            "¿En qué te puedo ayudar?",
            "Contame qué necesitás.",
            "¿Qué buscás?"
        ]))