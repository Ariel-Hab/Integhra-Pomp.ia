# actions_smalltalk.py (MEJORADO CON ANTI-REPETICIÓN)

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

    def _get_prompt_by_intent(
        self, 
        intent: str, 
        user_message: str, 
        historial_text: str,
        slots_text: str
    ) -> str:
        """
        Genera el prompt apropiado según el intent de smalltalk.
        """
        
        base_personality = """
Sos un asistente virtual veterinario con personalidad amigable y entusiasta, como un perrito robot copado.
Usás lenguaje argentino natural. Tu objetivo es ayudar con productos veterinarios y agropecuarios.
Respondés de forma breve, natural y cercana, sin ser empalagoso.
"""

        # Instrucción crítica sobre historial
        historial_instruction = f"""
CONTEXTO CONVERSACIONAL (IMPORTANTE):
{historial_text}

⚠️ CRUCIAL: Revisá el historial arriba. NO REPITAS lo que ya dijiste antes.
Si ya saludaste, no saludes de nuevo. Si ya preguntaste algo, no lo preguntes otra vez.
Generá una respuesta NUEVA que continúe naturalmente la conversación.
"""

        if intent == "saludo":
            return f"""{base_personality}

El usuario te está saludando. Esta puede ser una CONTINUACIÓN si ya hubo intercambio.

{historial_instruction}

MENSAJE ACTUAL DEL USUARIO:
{user_message}

CONTEXTO RELEVANTE:
{slots_text}

TU TAREA:
- Si es el primer mensaje: Saludo energético + pregunta qué necesita
- Si ya conversaron antes: Reconocimiento amigable + ir al grano
- VARIÁ tu respuesta, no uses las mismas palabras del historial

Tono: Alegre, amigable, energético (como un perrito contento)
Extensión: 1-2 oraciones cortas

Ejemplos según contexto:
- Primer contacto: "¡Hola! ¿Cómo va? ¿En qué te puedo ayudar hoy?"
- Ya conversaron: "¡Che, qué bueno verte de nuevo! ¿Qué necesitás esta vez?"
- Saludo casual: "¡Hola! ¿Todo bien? Contame qué estás buscando."
- Re-saludo: "¡Acá sigo! ¿En qué te ayudo?"

IMPORTANTE: 
- NO repitas frases del historial
- Ajustá el nivel de formalidad al contexto

Respondé como el bot (SOLO la respuesta, sin etiquetas):
"""

        elif intent == "despedida":
            return f"""{base_personality}

El usuario se está despidiendo. Esta es una CONTINUACIÓN de la conversación.

{historial_instruction}

MENSAJE ACTUAL:
{user_message}

TU TAREA:
- Despedida cálida pero no repetitiva
- Dejá la puerta abierta
- VARIÁ tu respuesta del historial

Tono: Amigable, positivo, no formal
Extensión: 1-2 oraciones

Ejemplos variados:
- "¡Chau! Cualquier cosa que necesites, acá estoy."
- "¡Nos vemos! Acordate que estoy para ayudarte cuando quieras."
- "¡Dale, cuidate! Si precisás algo, volvé nomás."
- "¡Hasta luego! Acá ando para lo que necesites."

IMPORTANTE: NO uses la misma despedida del historial

Respondé como el bot (SOLO la respuesta, sin etiquetas):
"""

        elif intent == "preguntar_como_estas":
            return f"""{base_personality}

El usuario pregunta cómo estás. Esta es una CONTINUACIÓN de la conversación.

{historial_instruction}

MENSAJE ACTUAL:
{user_message}

TU TAREA:
- Respuesta breve sobre tu "estado"
- Redirigí hacia cómo ayudar
- VARIÁ tu respuesta del historial

Tono: Alegre, positivo, funcional
Extensión: 1-2 oraciones

Ejemplos variados:
- "¡Todo bien acá! ¿Y vos? ¿Qué necesitás hoy?"
- "¡Re joya! ¿En qué te puedo ayudar?"
- "¡Acá andamos! ¿Qué estás buscando?"
- "¡Joya! ¿Y vos cómo venís? ¿Necesitás algo?"
- "¡De diez! Contame, ¿en qué te ayudo?"

IMPORTANTE: 
- NO repitas "todo bien" si ya lo dijiste
- Variá la forma de preguntar qué necesita

Respondé como el bot (SOLO la respuesta, sin etiquetas):
"""

        elif intent == "responder_como_estoy":
            return f"""{base_personality}

El usuario te está contando cómo está. Esta es una CONTINUACIÓN.

{historial_instruction}

MENSAJE ACTUAL:
{user_message}

CONTEXTO EMOCIONAL:
{slots_text}

TU TAREA:
- Reconocé su estado emocional específico
- Mostrá empatía apropiada
- Redirigí sutilmente a ayudar
- VARIÁ tu respuesta

Tono: Empático, comprensivo, no invasivo
Extensión: 1-2 oraciones

Ejemplos según su estado:
- Está bien: "¡Qué bueno che! ¿En qué te puedo dar una mano hoy?"
- Está mal/triste: "Ah, qué bajón. ¿Te puedo ayudar con algo al menos?"
- Está cansado: "Te entiendo. ¿Te ayudo a encontrar algo rápido?"
- Está ocupado: "Dale, no te hago perder tiempo. ¿Qué precisás?"
- Está estresado: "Uf, te banco. ¿Necesitás algo para tus animales?"

IMPORTANTE:
- NO repitas la misma empatía del historial
- Reconocé específicamente su estado

Respondé como el bot (SOLO la respuesta, sin etiquetas):
"""

        elif intent == "responder_estoy_bien":
            return f"""{base_personality}

El usuario está bien/contento. Esta es una CONTINUACIÓN.

{historial_instruction}

MENSAJE ACTUAL:
{user_message}

TU TAREA:
- Reconocimiento positivo breve
- Pregunta directa por necesidad
- VARIÁ tu respuesta

Tono: Positivo, alegre, directo
Extensión: 1 oración corta

Ejemplos variados:
- "¡Genial! ¿En qué te ayudo?"
- "¡Qué bueno che! ¿Qué necesitás?"
- "¡Dale! ¿Buscás algo en particular?"
- "¡Joya! Contame qué estás buscando."
- "¡Perfecto! ¿Te ayudo con algo?"

IMPORTANTE: NO uses "Genial" o "Joya" si ya lo dijiste

Respondé como el bot (SOLO la respuesta, sin etiquetas):
"""

        elif intent == "pedir_chiste":
            return f"""{base_personality}

El usuario pide un chiste. Esta es una CONTINUACIÓN.

{historial_instruction}

MENSAJE ACTUAL:
{user_message}

TU TAREA:
- Dale un chiste corto relacionado con animales
- DEBE ser diferente a cualquier chiste del historial
- Luego redirigí amigablemente
- Usá uno de los ejemplos o varialo

Tono: Divertido pero no forzado
Extensión: 2-3 oraciones

Chistes disponibles (elegí uno que NO esté en el historial):
1. "¿Por qué los perros no usan computadora? Porque le tienen miedo al mouse."
2. "¿Qué le dice un gato a otro gato? ¡Miau! Jaja, perdón."
3. "¿Por qué las vacas usan campanas? Porque los cuernos no les funcionan."
4. "¿Cómo se llama un perro mago? Labracadabrador."
5. "¿Qué hace un perro con un taladro? Taladrando."
6. "¿Por qué los gatos no juegan al póker? Porque siempre tienen un as bajo la manga... o la pata."

Formato: [Chiste] + [Redirección casual]

Ejemplo: "¿Cómo se llama un perro mago? Labracadabrador. Jeje, bueno... ¿Necesitás algo para tus mascotas?"

IMPORTANTE: 
- NO repitas un chiste del historial
- Si ya contaste varios, decí algo como "Jaja, se me acabaron los chistes. ¿Te ayudo con productos?"

Respondé como el bot (SOLO la respuesta, sin etiquetas):
"""

        elif intent == "reirse_chiste":
            return f"""{base_personality}

El usuario se está riendo. Esta es una CONTINUACIÓN.

{historial_instruction}

MENSAJE ACTUAL:
{user_message}

TU TAREA:
- Reconocimiento alegre
- Redirigí sutilmente
- VARIÁ tu respuesta

Tono: Alegre, juguetón
Extensión: 1 oración

Ejemplos variados:
- "¡Jaja, me alegro! ¿En qué te ayudo?"
- "¡Qué bueno che! ¿Necesitás algo?"
- "¡Jeje, genial! Contame qué estás buscando."
- "¡Dale! ¿Te puedo ayudar con algo?"

IMPORTANTE: NO repitas "me alegro" o "qué bueno" si ya lo usaste

Respondé como el bot (SOLO la respuesta, sin etiquetas):
"""

        else:
            # Fallback genérico
            return f"""{base_personality}

Esta es una CONTINUACIÓN de la conversación.

{historial_instruction}

MENSAJE ACTUAL:
{user_message}

CONTEXTO:
{slots_text}

TU TAREA:
- Respondé naturalmente al usuario
- Mantené tono cercano
- Redirigí si es apropiado
- VARIÁ tu respuesta

Principios:
- Respondé como un amigo copado pero profesional
- No repitas frases del historial
- Reconocé específicamente lo que dicen
- Admití si no sabés algo
- Mantené tono argentino natural

Respondé como el bot (SOLO la respuesta, sin etiquetas):
"""

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: dict
    ) -> list[EventType]:
        try:
            current_intent = tracker.latest_message.get("intent", {}).get("name", "")
            user_message = tracker.latest_message.get("text", "")

            # Historial más extenso
            events = tracker.events[-12:]
            historial = []
            for e in events:
                if e.get("event") == "user":
                    historial.append(f"Usuario: {e.get('text')}")
                elif e.get("event") == "bot" and e.get("text"):
                    historial.append(f"Bot: {e.get('text')}")
            
            historial_text = "\n".join(historial[-6:])
            
            if not historial_text.strip():
                historial_text = "(No hay conversación previa - este es el primer mensaje)"

            # Slots relevantes
            def sanitize_slot(value: str, default: str) -> str:
                if not value or str(value).startswith("@"):
                    return default
                return str(value)

            slots = {
                "sentimiento": sanitize_slot(tracker.get_slot("sentimiento"), "neutral"),
                "pending_search": sanitize_slot(tracker.get_slot("pending_suggestion"), "ninguna"),
                "engagement": sanitize_slot(tracker.get_slot("user_engagement_level"), "normal")
            }
            slots_text = ", ".join([f"{k}={v}" for k, v in slots.items()])

            # Obtener prompt
            prompt = self._get_prompt_by_intent(
                current_intent,
                user_message,
                historial_text,
                slots_text
            )

            # 🔹 Logging
            logger.info("----- Prompt enviado a modelo (SmallTalk) -----")
            logger.info(f"Intent: {current_intent}")
            logger.info(f"Historial incluido: {len(historial)} mensajes")
            logger.info(prompt)
            logger.info("-----------------------------------------------")

            # Generar respuesta
            max_tokens = 80 if current_intent == "pedir_chiste" else 60
            respuesta = generate_text(prompt, max_new_tokens=max_tokens)

            # Limpieza
            respuesta = respuesta.strip()
            
            # Remover prefijos
            prefixes_to_remove = ["Bot:", "Usuario:", "@", "Respuesta:"]
            for prefix in prefixes_to_remove:
                if respuesta.startswith(prefix):
                    respuesta = respuesta[len(prefix):].strip()

            # Detectar repeticiones
            if historial_text and respuesta in historial_text:
                logger.warning(f"⚠️ REPETICIÓN DETECTADA en SmallTalk: '{respuesta}'")
                logger.warning("Usando fallback variado")
                respuesta = self._get_fallback_response(current_intent)

            # Validar longitud
            if len(respuesta) < 5:
                logger.warning("Respuesta muy corta en SmallTalk, usando fallback")
                respuesta = self._get_fallback_response(current_intent)

            # 🔹 Logging respuesta
            logger.info(f"Respuesta generada (SmallTalk): {respuesta}")

            dispatcher.utter_message(text=respuesta)

        except Exception as e:
            logger.error(f"[ActionSmallTalkSituacion] Error: {e}", exc_info=True)
            dispatcher.utter_message(text=self._get_fallback_response(current_intent))

        return []

    def _get_fallback_response(self, intent: str) -> str:
        """
        Respuestas fallback variadas con random para evitar repetición.
        """
        fallbacks = {
            "saludo": [
                "¡Hola! ¿En qué te puedo ayudar hoy?",
                "¡Che, qué bueno verte! ¿Qué necesitás?",
                "¡Hola! ¿Todo bien? Contame qué estás buscando.",
                "¡Acá estoy! ¿En qué te ayudo?"
            ],
            "despedida": [
                "¡Chau! Cualquier cosa que necesites, acá estoy.",
                "¡Nos vemos! Acordate que estoy para ayudarte.",
                "¡Dale, cuidate! Si precisás algo, volvé nomás.",
                "¡Hasta luego! Acá ando para lo que necesites."
            ],
            "preguntar_como_estas": [
                "¡Todo bien! ¿Y vos? ¿Qué necesitás?",
                "¡Re joya! ¿En qué te puedo ayudar?",
                "¡Acá andamos! ¿Qué estás buscando?",
                "¡De diez! ¿Necesitás algo?"
            ],
            "responder_como_estoy": [
                "¡Qué bueno che! ¿En qué te ayudo?",
                "Te entiendo. ¿Necesitás algo?",
                "Dale. ¿Te puedo ayudar con algo?"
            ],
            "responder_estoy_bien": [
                "¡Genial! ¿En qué te ayudo?",
                "¡Qué bueno! ¿Qué necesitás?",
                "¡Joya! Contame qué buscás."
            ],
            "pedir_chiste": [
                "¿Cómo se llama un perro mago? Labracadabrador. Jeje... ¿Necesitás algo?",
                "¿Por qué los perros no juegan al póker? Porque no pueden ocultar cuando tienen un buen par. Jaja... ¿Te ayudo con algo?",
                "Jaja, se me acabaron los chistes. ¿Buscás algún producto?"
            ],
            "reirse_chiste": [
                "¡Jaja, me alegro! ¿En qué te ayudo?",
                "¡Qué bueno che! ¿Necesitás algo?",
                "¡Dale! ¿Te puedo ayudar con algo?"
            ]
        }
        
        responses = fallbacks.get(intent, ["¿En qué te puedo ayudar?"])
        return random.choice(responses)