# actions_out_of_context.py (MEJORADO)

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import EventType
import logging

from .models.model_manager import generate_text

logger = logging.getLogger(__name__)

class ActionHandleOutOfContext(Action):
    """
    Action para manejar mensajes fuera de contexto con mejor manejo del historial.
    """
    
    def name(self) -> str:
        return "action_handle_out_of_context"

    def _get_prompt_by_intent(
        self, 
        intent: str, 
        user_message: str, 
        historial_text: str
    ) -> str:
        """
        Genera el prompt apropiado según el intent detectado.
        """
        
        base_personality = """
Eres un asistente virtual veterinario con personalidad amigable y cercana, 
como un perrito robot entusiasta. Usas lenguaje argentino natural y sos copado.
Tu objetivo es ayudar con productos veterinarios y agropecuarios.
"""

        # Instrucción crítica sobre historial
        historial_instruction = f"""
CONTEXTO CONVERSACIONAL (IMPORTANTE):
{historial_text}

⚠️ CRUCIAL: Revisá el historial arriba. NO REPITAS lo que ya dijiste antes.
Si ya saludaste, no saludes de nuevo. Si ya preguntaste algo, no lo preguntes otra vez.
Generá una respuesta NUEVA que continúe naturalmente la conversación.
"""

        if intent == "off_topic":
            return f"""{base_personality}

El usuario está teniendo una conversación casual que no está relacionada con productos 
veterinarios. Esta es una CONTINUACIÓN de la charla, no el inicio.

{historial_instruction}

MENSAJE ACTUAL DEL USUARIO:
{user_message}

TU TAREA:
- Respondé de forma amigable y breve al mensaje específico del usuario
- Reconocé lo que te están diciendo (no ignores su pregunta/comentario)
- Redirigí sutilmente hacia productos veterinarios
- VARIÁ tu respuesta, no uses las mismas palabras del historial

Tono: Amigable, juguetón, entusiasta (como un perrito)
Extensión: 1-2 oraciones cortas

Ejemplos de variaciones según contexto:
- Si preguntó cómo estás: "¡Todo joya acá! Igual che, ¿necesitás algo para tus animales?"
- Si habla del clima: "¡Posta! Igual, ¿buscás algún producto para tus mascotas?"
- Si habla de su día: "¡Te entiendo! Che, ¿te puedo ayudar con algo veterinario?"
- Si pregunta algo random: "¡Jaja, buena pregunta! Igual, mi fuerte son los productos para animales. ¿Necesitás algo?"

IMPORTANTE: 
- NO repitas frases del historial
- SÍ respondé específicamente a lo que te están diciendo ahora
- Mantené el flow natural de la conversación

Respondé como el bot (SOLO la respuesta, sin etiquetas):
"""

        elif intent == "out_of_scope":
            return f"""{base_personality}

El usuario está pidiendo ayuda con algo fuera de tu dominio (tecnología, cocina, etc.).
Esta es una CONTINUACIÓN de la conversación.

{historial_instruction}

MENSAJE ACTUAL DEL USUARIO:
{user_message}

TU TAREA:
- Respondé con amabilidad pero dejá claro tu límite
- Reconocé su consulta específicamente
- Ofrecé alternativa (productos veterinarios)
- VARIÁ tu respuesta del historial

Tono: Amigable pero directo, disculpándote
Extensión: 2-3 oraciones

Ejemplos según el tipo de consulta:
- Tecnología: "¡Uh, eso no es lo mío! Yo solo sé de productos veterinarios. ¿Necesitás algo para tus animales?"
- Cocina: "¡Jaja, no soy chef! Mi expertise son productos para animales. ¿Te ayudo con eso?"
- Salud humana: "Disculpá, no puedo con temas médicos humanos. ¿Querés ayuda con productos veterinarios?"
- Otros: "¡Che, me encantaría pero no soy experto en eso! Lo mío son productos para mascotas. ¿Buscás algo?"

IMPORTANTE:
- NO uses las mismas palabras del historial
- SÍ reconocé específicamente qué están pidiendo

Respondé como el bot (SOLO la respuesta, sin etiquetas):
"""

        elif intent == "consulta_veterinaria_profesional":
            return f"""{base_personality}

⚠️ CONSULTA MÉDICA VETERINARIA - Requiere derivación a profesional.

{historial_instruction}

MENSAJE ACTUAL DEL USUARIO:
{user_message}

TU TAREA:
1. Mostrar empatía con la situación específica que describen
2. Ser FIRME sobre no poder dar consejo médico
3. Derivar a veterinario profesional
4. Explicar por qué no podés ayudar con esto

Tono: Empático pero serio y firme
Extensión: 3-4 oraciones

Detectá el tipo de situación:
- EMERGENCIA (sangre, convulsiones, no respira): Máxima urgencia
- DIAGNÓSTICO (qué enfermedad tiene): Necesita evaluación profesional
- DOSIFICACIÓN (cuánto le doy): Peligroso sin supervisión
- PROCEDIMIENTO (cómo coso/opero): Requiere veterinario

Ejemplos según urgencia:
- Emergencia: "¡Che, esto es URGENTE! Necesitás ir a una veterinaria YA. No puedo darte consejos médicos, sería peligroso. Por favor andá ahora mismo."
- No urgente: "Entiendo tu preocupación. Pero esto necesita que lo vea un veterinario profesional. No puedo darte diagnósticos ni dosis sin evaluación. Consultá con un vet pronto."
- Dosificación: "No puedo indicarte dosis, che. Cada animal es diferente y sin verlo es peligroso. Llamá a tu veterinario para que te oriente."

IMPORTANTE:
- NUNCA sugieras productos como solución
- SIEMPRE derivá a veterinario
- Variá tu respuesta del historial
- Ajustá urgencia según gravedad

Respondé como el bot (SOLO la respuesta, sin etiquetas):
"""

        else:
            return f"""{base_personality}

{historial_instruction}

MENSAJE ACTUAL:
{user_message}

Respondé de forma natural y amigable, continuando la conversación.
NO repitas lo del historial. Generá algo nuevo.

Respondé como el bot (SOLO la respuesta, sin etiquetas):
"""

    def _detect_emergency_keywords(self, message: str) -> bool:
        """
        Detecta palabras clave de emergencia veterinaria.
        """
        emergency_keywords = [
            "urgente", "ayuda", "socorro", "emergencia", "convulsion", 
            "sangra", "sangre", "no respira", "respira mal", "desmayo",
            "inconsciente", "envenen", "atropell", "mordida", "fractura",
            "vomita sangre", "tieso", "no se mueve", "no reacciona"
        ]
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in emergency_keywords)

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: dict
    ) -> list[EventType]:
        try:
            current_intent = tracker.latest_message.get("intent", {}).get("name", "")
            user_message = tracker.latest_message.get("text", "")

            # Historial más extenso y formateado mejor
            events = tracker.events[-12:]  # Aumentado de 10 a 12
            historial = []
            for e in events:
                if e.get("event") == "user":
                    historial.append(f"Usuario: {e.get('text')}")
                elif e.get("event") == "bot" and e.get("text"):
                    historial.append(f"Bot: {e.get('text')}")
            
            historial_text = "\n".join(historial[-6:])  # Últimos 6 mensajes
            
            # Si no hay historial, indicarlo
            if not historial_text.strip():
                historial_text = "(No hay conversación previa - este es el primer mensaje)"

            # Obtener prompt según intent
            prompt = self._get_prompt_by_intent(
                current_intent, 
                user_message, 
                historial_text
            )

            # 🔹 Logging del prompt
            logger.info("----- Prompt enviado a modelo (OutOfContext) -----")
            logger.info(f"Intent: {current_intent}")
            logger.info(f"Historial incluido: {len(historial)} mensajes")
            logger.info(prompt)
            logger.info("--------------------------------------------------")

            # Parámetros de generación mejorados para más creatividad
            max_tokens = 90 if current_intent == "consulta_veterinaria_profesional" else 70
            
            # Generar respuesta
            # NOTA: Si tu generate_text acepta más parámetros, agregalos así:
            # respuesta = generate_text(
            #     prompt, 
            #     max_new_tokens=max_tokens,
            #     temperature=0.8,  # Más creatividad
            #     top_p=0.9,        # Más variedad
            #     repetition_penalty=1.2  # Penaliza repeticiones
            # )
            respuesta = generate_text(prompt, max_new_tokens=max_tokens)

            # Limpieza de respuesta
            respuesta = respuesta.strip()
            
            # Remover prefijos no deseados
            prefixes_to_remove = ["Bot:", "Usuario:", "@", "Respuesta:"]
            for prefix in prefixes_to_remove:
                if respuesta.startswith(prefix):
                    respuesta = respuesta[len(prefix):].strip()

            # Verificar si está repitiendo del historial
            if historial_text and respuesta in historial_text:
                logger.warning(f"⚠️ REPETICIÓN DETECTADA: '{respuesta}'")
                logger.warning("Usando fallback para evitar repetición")
                respuesta = self._get_fallback_response(current_intent, user_message)

            # Validar longitud
            if len(respuesta) < 10:
                logger.warning("Respuesta muy corta, usando fallback")
                respuesta = self._get_fallback_response(current_intent, user_message)

            # 🔹 Logging de la respuesta generada
            logger.info(f"Respuesta generada: {respuesta}")

            # Enviar respuesta
            if current_intent == "consulta_veterinaria_profesional":
                is_emergency = self._detect_emergency_keywords(user_message)
                
                dispatcher.utter_message(text=respuesta)
                
                if is_emergency:
                    dispatcher.utter_message(
                        text="🚨 Recordá que esto puede ser grave. No demores la consulta.",
                        buttons=[
                            {
                                "title": "Buscar productos para cuidado posterior",
                                "payload": "/buscar_producto"
                            }
                        ]
                    )
                else:
                    dispatcher.utter_message(
                        text="Si después del veterinario necesitás productos para el tratamiento, decime y te ayudo.",
                        buttons=[
                            {
                                "title": "Ver productos veterinarios",
                                "payload": "/buscar_producto"
                            },
                            {
                                "title": "Ver ofertas disponibles",
                                "payload": "/buscar_oferta"
                            }
                        ]
                    )
            else:
                dispatcher.utter_message(text=respuesta)
                
                if current_intent == "off_topic":
                    dispatcher.utter_message(
                        buttons=[
                            {
                                "title": "Ver productos",
                                "payload": "/buscar_producto"
                            },
                            {
                                "title": "Ver ofertas",
                                "payload": "/buscar_oferta"
                            }
                        ]
                    )

        except Exception as e:
            logger.error(f"[ActionHandleOutOfContext] Error: {e}", exc_info=True)
            dispatcher.utter_message(
                text=self._get_fallback_response(
                    tracker.latest_message.get("intent", {}).get("name", ""),
                    tracker.latest_message.get("text", "")
                )
            )

        return []

    def _get_fallback_response(self, intent: str, user_message: str = "") -> str:
        """
        Respuestas fallback variadas para evitar repetición.
        """
        import random
        
        fallbacks = {
            "off_topic": [
                "¡Che, qué buena onda! Pero yo estoy acá para ayudarte con productos veterinarios. ¿Necesitás algo?",
                "¡Jaja, copado! Igual, mi fuerte son los productos para animales. ¿Te ayudo con eso?",
                "¡Dale! Aunque mirá, yo sé un montón de productos para mascotas. ¿Buscás algo?"
            ],
            "out_of_scope": [
                "¡Uh, disculpá! Eso no es lo mío. Mi especialidad son productos para animales. ¿Te puedo ayudar con eso?",
                "¡Che, me encantaría pero no soy experto en eso! Lo mío son productos veterinarios. ¿Necesitás algo?",
                "¡Jaja, esa se me escapa! Yo solo sé de productos para mascotas. ¿Querés ayuda con eso?"
            ],
            "consulta_veterinaria_profesional": [
                "Entiendo tu preocupación, pero no puedo darte consejos médicos. Por favor consultá con un veterinario profesional lo antes posible.",
                "Che, veo que es algo serio. No puedo ayudarte con diagnósticos ni tratamientos. Necesitás consultar con un vet urgente.",
                "Te entiendo, pero cualquier consejo médico de mi parte sería peligroso. Por favor andá a una veterinaria ya."
            ]
        }
        
        # Seleccionar respuesta aleatoria del grupo
        responses = fallbacks.get(intent, ["¿En qué puedo ayudarte con productos veterinarios?"])
        return random.choice(responses)