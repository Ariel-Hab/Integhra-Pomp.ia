# actions/actions_out_of_context.py (✅ CON CONTEXTO)

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import EventType
import logging
import random

from .models.model_manager import generate_text_with_context  # ✅ CAMBIO

logger = logging.getLogger(__name__)

class ActionHandleOutOfContext(Action):
    """✅ MEJORADO: Manejo de off-topic con contexto conversacional"""
    
    def name(self) -> str:
        return "action_handle_out_of_context"

    def _get_contextual_prompt(self, intent: str, user_message: str, tracker: Tracker) -> str:
        """
        ✅ NUEVO: Prompts que aprovechan el contexto automático
        El contexto se agrega automáticamente en generate_text_with_context()
        """
        
        # Detectar si hay búsqueda activa
        search_history = tracker.get_slot('search_history')
        has_active_search = search_history and len(search_history) > 0
        
        # Detectar si hay sugerencia pendiente
        pending_suggestion = tracker.get_slot('pending_suggestion')
        has_pending = pending_suggestion is not None
        
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

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, 
            domain: dict) -> list[EventType]:
        try:
            current_intent = tracker.latest_message.get("intent", {}).get("name", "")
            user_message = tracker.latest_message.get("text", "")

            logger.info(f"[OutOfContext] Intent: {current_intent}, Mensaje: '{user_message[:50]}...'")

            # ✅ Construir prompt contextual
            prompt = self._get_contextual_prompt(current_intent, user_message, tracker)
            
            # ✅ Generar CON contexto automático
            max_tokens = 70 if current_intent == "consulta_veterinaria_profesional" else 60
            
            respuesta = generate_text_with_context(
                prompt=prompt,
                tracker=tracker,  # ✅ Contexto automático
                max_new_tokens=max_tokens,
                temperature=0.7
            )

            # Limpieza
            if respuesta:
                respuesta = respuesta.strip()
                
                # Remover prefijos comunes
                for prefix in ["Bot:", "Pompi:", "Respuesta:", "Asistente:"]:
                    if respuesta.startswith(prefix):
                        respuesta = respuesta[len(prefix):].strip()
                
                # Validación de longitud
                if len(respuesta) < 10 or len(respuesta) > 250:
                    logger.warning(f"[OutOfContext] Respuesta fuera de rango: {len(respuesta)} chars")
                    respuesta = None
            
            # Fallback si falla generación
            if not respuesta:
                respuesta = self._get_fallback_response(current_intent)
                logger.warning(f"[OutOfContext] Usando fallback")
            
            logger.info(f"[OutOfContext] ✓ Respuesta: '{respuesta[:60]}...'")
            
            # ✅ Responder según tipo
            if current_intent == "consulta_veterinaria_profesional":
                self._handle_medical_consultation(
                    dispatcher, respuesta, user_message, tracker
                )
            elif current_intent == "off_topic":
                self._handle_offtopic(
                    dispatcher, respuesta, tracker
                )
            else:  # out_of_scope
                self._handle_out_of_scope(
                    dispatcher, respuesta, tracker
                )

        except Exception as e:
            logger.error(f"[OutOfContext] Error: {e}", exc_info=True)
            fallback = self._get_fallback_response(current_intent)
            dispatcher.utter_message(text=fallback)

        return []
    
    def _handle_medical_consultation(self, dispatcher: CollectingDispatcher, 
                                    respuesta: str, user_message: str, 
                                    tracker: Tracker):
        """Maneja consultas médicas con mayor detalle"""
        
        # Respuesta principal
        dispatcher.utter_message(text=respuesta)
        
        # Alert si es emergencia
        if self._detect_emergency(user_message):
            dispatcher.utter_message(
                text="🚨 ESTO PARECE URGENTE. Andá al veterinario INMEDIATAMENTE."
            )
        
        # Botones de acción (solo si NO es emergencia)
        else:
            search_history = tracker.get_slot('search_history')
            
            if search_history and len(search_history) > 0:
                # Tenía búsqueda activa
                dispatcher.utter_message(
                    text="Después de consultar con el vet, ¿querés volver a tu búsqueda anterior?",
                    buttons=[
                        {"title": "Volver a búsqueda", "payload": "/afirmar"},
                        {"title": "Nueva búsqueda", "payload": "/buscar_producto"}
                    ]
                )
            else:
                # Sin búsqueda previa
                dispatcher.utter_message(
                    text="Después del veterinario, si necesitás productos, avisame.",
                    buttons=[
                        {"title": "Ver productos", "payload": "/buscar_producto"},
                        {"title": "Ver ofertas", "payload": "/buscar_oferta"}
                    ]
                )
    
    def _handle_offtopic(self, dispatcher: CollectingDispatcher, 
                        respuesta: str, tracker: Tracker):
        """Maneja off-topic con reconducción contextual"""
        
        # Respuesta principal
        dispatcher.utter_message(text=respuesta)
        
        # Botones según contexto
        pending_suggestion = tracker.get_slot('pending_suggestion')
        search_history = tracker.get_slot('search_history')
        
        if pending_suggestion:
            # Hay sugerencia pendiente - no agregar botones (ya está en la respuesta)
            pass
        
        elif search_history and len(search_history) > 0:
            # Había búsqueda activa
            last_search = search_history[-1]
            search_type = last_search.get('type', 'producto')
            
            dispatcher.utter_message(
                buttons=[
                    {"title": f"Seguir con {search_type}s", "payload": "/afirmar"},
                    {"title": "Nueva búsqueda", "payload": f"/buscar_{search_type}"}
                ]
            )
        
        else:
            # Sin contexto previo - botones generales
            dispatcher.utter_message(
                buttons=[
                    {"title": "Ver productos", "payload": "/buscar_producto"},
                    {"title": "Ver ofertas", "payload": "/buscar_oferta"}
                ]
            )
    
    def _handle_out_of_scope(self, dispatcher: CollectingDispatcher, 
                           respuesta: str, tracker: Tracker):
        """Maneja out of scope con redirección"""
        
        # Respuesta principal
        dispatcher.utter_message(text=respuesta)
        
        # Siempre ofrecer ayuda veterinaria
        search_history = tracker.get_slot('search_history')
        
        if search_history and len(search_history) > 0:
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
                "¡Che, copado! Pero yo te ayudo con productos veterinarios. ¿Necesitás algo?",
                "¡Dale! Mi fuerte son productos para animales. ¿Te ayudo con algo?",
                "¡Buenísimo! Yo manejo productos veterinarios. ¿Buscás algo específico?"
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