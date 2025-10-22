# actions/actions_out_of_context.py (✅ CON PATRÓN COMPLETO)

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import EventType
import logging
import random

from .models.model_manager import _chat_model, generate_text_with_context,generate_with_safe_fallback

logger = logging.getLogger(__name__)

class ActionHandleOutOfContext(Action):
    """✅ MEJORADO: Manejo de off-topic con patrón streaming + fallback completo"""
    
    def name(self) -> str:
        return "action_handle_out_of_context"

    def _get_contextual_prompt(self, intent: str, user_message: str, tracker: Tracker) -> str:
        """
        ✅ NUEVO: Prompts que aprovechan el contexto automático
        """
        
        # ✅ Detectar si hay búsqueda activa (acceso seguro)
        try:
            search_history = tracker.get_slot('search_history')
            has_active_search = search_history and len(search_history) > 0
        except:
            has_active_search = False
        
        # ✅ Detectar si hay sugerencia pendiente (acceso seguro)
        try:
            pending_suggestion = tracker.get_slot('pending_suggestion')
            has_pending = pending_suggestion is not None
        except:
            has_pending = False
        
        prompts = {
            "off_topic": self._build_offtopic_prompt(
                user_message, has_active_search, has_pending
            ),
            
            "out_of_scope": self._build_outofscope_prompt(
                user_message, has_active_search
            ),
            
            "consulta_veterinaria_profesional": self._build_medical_prompt(
                user_message
            )
        }
        
        return prompts.get(intent, f'Usuario: "{user_message}"\nRespondé amigable.\nBot:')
    
    def _build_offtopic_prompt(self, user_message: str, has_search: bool, 
                              has_pending: bool) -> str:
        """Prompt para off-topic considerando contexto"""
        
        if has_pending:
            # Usuario cambió de tema con sugerencia pendiente
            return (
                f'Usuario cambió de tema: "{user_message}"\n'
                f'Tenés una sugerencia pendiente pero el usuario se distrajo.\n'
                f'Respondé brevemente al off-topic + reconducí SUAVEMENTE a la sugerencia.\n'
                f'Bot:'
            )
        elif has_search:
            # Usuario cambió de tema durante búsqueda
            return (
                f'Usuario se distrajo durante búsqueda: "{user_message}"\n'
                f'Respondé brevemente + reconducí a la búsqueda activa.\n'
                f'Bot:'
            )
        else:
            # Off-topic sin contexto previo
            return (
                f'Usuario habla casual: "{user_message}"\n'
                f'Respondé amigable + ofrecé ayuda con productos.\n'
                f'Bot:'
            )
    
    def _build_outofscope_prompt(self, user_message: str, has_search: bool) -> str:
        """Prompt para out of scope"""
        
        if has_search:
            return (
                f'Usuario pidió algo que no hacés: "{user_message}"\n'
                f'Estaba buscando productos antes.\n'
                f'Disculpate + ofrecé volver a la búsqueda.\n'
                f'Bot:'
            )
        else:
            return (
                f'Usuario pidió algo fuera de alcance: "{user_message}"\n'
                f'Disculpate amablemente + ofrecé ayuda veterinaria.\n'
                f'Bot:'
            )
    
    def _build_medical_prompt(self, user_message: str) -> str:
        """Prompt para consultas médicas (siempre serio)"""
        
        is_emergency = self._detect_emergency(user_message)
        
        if is_emergency:
            return (
                f'⚠️ EMERGENCIA VETERINARIA: "{user_message}"\n'
                f'Mostrá MÁXIMA empatía + derivá URGENTE a veterinario.\n'
                f'NO sugieras productos. Esto es urgente.\n'
                f'Bot:'
            )
        else:
            return (
                f'Consulta médica veterinaria: "{user_message}"\n'
                f'Mostrá empatía + derivá a veterinario profesional.\n'
                f'NO des consejos médicos. NO sugieras productos.\n'
                f'Bot:'
            )

    def _detect_emergency(self, message: str) -> bool:
        """Detecta emergencias veterinarias"""
        emergency_keywords = [
            "urgente", "ayuda", "sangra", "sangre", "convulsion", "convulsiona",
            "no respira", "respira mal", "envenen", "atropell", "desmayo", 
            "inconsciente", "no despierta", "golpe fuerte", "accidente",
            "vomita sangre", "diarrea sangre", "hinchado", "muy débil"
        ]
        
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in emergency_keywords)

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict) -> list[EventType]:
        try:
            current_intent = tracker.latest_message.get("intent", {}).get("name", "")
            user_message = tracker.latest_message.get("text", "")

            logger.info(f"[OutOfContext] Intent: {current_intent}, Mensaje: '{user_message[:50]}...'")

            # 1. Construir el prompt (la lógica principal de esta action)
            prompt = self._get_contextual_prompt(current_intent, user_message, tracker)
            
            # 2. Definir parámetros para la generación
            max_tokens = 150 if current_intent == "consulta_veterinaria_profesional" else 100
            
            # ✅ 3. Delegar TODA la generación y el fallback al manager con una sola llamada
            # El manager se encargará de enviar la respuesta generada o el fallback adecuado.
            generate_with_safe_fallback(
                prompt=prompt,
                dispatcher=dispatcher,
                tracker=tracker,
                fallback_template=f"utter_{current_intent}", # Usar templates de Rasa!
                max_new_tokens=max_tokens,
                temperature=0.7
            )

            # 4. Enviar botones de seguimiento (esto es lógica de la action, se mantiene)
            logger.info(f"[OutOfContext] Enviando botones de seguimiento...")
            if current_intent == "consulta_veterinaria_profesional":
                self._handle_medical_consultation(dispatcher, user_message, tracker)
            elif current_intent == "off_topic":
                self._handle_offtopic(dispatcher, tracker)
            else:  # out_of_scope
                self._handle_out_of_scope(dispatcher, tracker)

        except Exception as e:
            logger.error(f"[OutOfContext] Error crítico en la action: {e}", exc_info=True)
            # Fallback de último recurso si la action misma explota
            dispatcher.utter_message(text="Tuve un problema procesando eso. ¿Podrías decirlo de otra manera?")

        return []
    def _handle_medical_consultation(self, dispatcher: CollectingDispatcher, 
                                     user_message: str, tracker: Tracker):
        """Maneja el seguimiento de consultas médicas (solo botones y alertas)."""
        
        if self._detect_emergency(user_message):
            dispatcher.utter_message(
                text="🚨 ESTO PARECE URGENTE. Andá al veterinario INMEDIATAMENTE."
            )
        else:
            try:
                search_history = tracker.get_slot('search_history')
            except:
                search_history = None
                
            if search_history:
                dispatcher.utter_message(
                    text="Después de consultar con el vet, ¿querés volver a tu búsqueda anterior?",
                    buttons=[
                        {"title": "Volver a búsqueda", "payload": "/afirmar"},
                        {"title": "Nueva búsqueda", "payload": "/buscar_producto"}
                    ]
                )
            else:
                dispatcher.utter_message(
                    text="Después del veterinario, si necesitás productos, avisame.",
                    buttons=[
                        {"title": "Ver productos", "payload": "/buscar_producto"},
                        {"title": "Ver ofertas", "payload": "/buscar_oferta"}
                    ]
                )
    
    def _handle_offtopic(self, dispatcher: CollectingDispatcher, tracker: Tracker):
        """Maneja el seguimiento de off-topic (solo botones)."""
        
        try:
            pending_suggestion = tracker.get_slot('pending_suggestion')
        except:
            pending_suggestion = None
        
        try:
            search_history = tracker.get_slot('search_history')
        except:
            search_history = None
        
        if pending_suggestion:
            pass # No se envían botones extra si ya hay una sugerencia activa
        elif search_history:
            last_search = search_history[-1]
            search_type = last_search.get('type', 'producto')
            dispatcher.utter_message(
                buttons=[
                    {"title": f"Seguir con {search_type}s", "payload": "/afirmar"},
                    {"title": "Nueva búsqueda", "payload": f"/buscar_{search_type}"}
                ]
            )
        else:
            dispatcher.utter_message(
                buttons=[
                    {"title": "Ver productos", "payload": "/buscar_producto"},
                    {"title": "Ver ofertas", "payload": "/buscar_oferta"}
                ]
            )
    
    def _handle_out_of_scope(self, dispatcher: CollectingDispatcher, tracker: Tracker):
        """Maneja el seguimiento de out_of_scope (solo botones)."""
        
        try:
            search_history = tracker.get_slot('search_history')
        except:
            search_history = None
            
        if search_history:
            dispatcher.utter_message(
                text="¿Querés volver a lo que estabas buscando?",
                buttons=[
                    {"title": "Sí, volver", "payload": "/afirmar"},
                    {"title": "Buscar otra cosa", "payload": "/buscar_producto"}
                ]
            )
        else:
            dispatcher.utter_message(
                buttons=[
                    {"title": "Ver productos", "payload": "/buscar_producto"},
                    {"title": "Ver ofertas", "payload": "/buscar_oferta"}
                ]
            )

    def _get_fallback_response(self, intent: str) -> str:
        """Fallbacks confiables por intent"""
        
        fallbacks = {
            "off_topic": [
                "Prefiero que hablemos de productos veterinarios. ¿Necesitás algo?",
                "Mi fuerte son productos para animales. ¿Te ayudo con algo?",
                "Yo manejo productos veterinarios. ¿Buscás algo específico?"
            ],
            
            "out_of_scope": [
                "¡Uh, eso no es lo mío! Mi especialidad son productos para animales.",
                "¡Disculpá, no soy experto en eso! Lo mío son productos veterinarios.",
                "Esa se me escapa. Yo solo manejo productos para mascotas. ¿Te ayudo con eso?"
            ],
            
            "consulta_veterinaria_profesional": [
                "Entiendo tu preocupación, pero no puedo darte consejos médicos. Consultá con un veterinario urgente.",
                "Che, veo que es algo serio. No puedo ayudarte con diagnósticos. Necesitás un vet YA.",
                "Te entiendo, pero sería peligroso darte consejos médicos. Andá a una veterinaria lo antes posible."
            ]
        }
        
        return random.choice(fallbacks.get(intent, [
            "¿En qué te puedo ayudar con productos veterinarios?"
        ]))