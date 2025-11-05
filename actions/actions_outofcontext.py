# actions/actions_out_of_context.py (✅ CON CLASIFICACIÓN INTELIGENTE LLM)

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import EventType, SlotSet
import logging
import random
from datetime import datetime
from typing import Optional, List, Dict, Any

from actions.functions.chat_handler import generate_with_safe_fallback

logger = logging.getLogger(__name__)

class ActionHandleOutOfContext(Action):
    """✅ MEJORADO: Manejo de off-topic con clasificación LLM + streaming + fallback"""
    
    def name(self) -> str:
        return "action_handle_out_of_context"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict) -> list[EventType]:
        try:
            current_intent = tracker.latest_message.get("intent", {}).get("name", "")
            user_message = tracker.latest_message.get("text", "")

            logger.info(f"[OutOfContext] Intent: {current_intent}, Mensaje: '{user_message[:50]}...'")

            # ============================================================
            # ✅ NUEVA LÓGICA: CLASIFICACIÓN INTELIGENTE CON LLM
            # ============================================================
            
            # Solo clasificar con LLM en casos ambiguos (off_topic y out_of_scope)
            # NO para consultas médicas (siempre son serias y no son búsquedas)
            should_classify_with_llm = current_intent in ['off_topic', 'out_of_scope']
            
            if should_classify_with_llm:
                logger.info("[OutOfContext] 🧠 Usando LLM para clasificar si es búsqueda...")
                
                classification_result = self._classify_and_handle_with_llm(
                    user_message, current_intent, dispatcher, tracker
                )
                
                # Si el LLM manejó el caso (búsqueda o error), retornar eventos
                if classification_result is not None:
                    return classification_result
                
                # Si retorna None, continuar con lógica conversacional normal
                logger.info("[OutOfContext] 💬 LLM clasificó como conversacional, continuando...")

            # ============================================================
            # LÓGICA CONVERSACIONAL EXISTENTE
            # ============================================================
            
            # 1. Construir el prompt contextual
            prompt = self._get_contextual_prompt(current_intent, user_message, tracker)
            
            # 2. Definir parámetros para la generación
            max_tokens = 150 if current_intent == "consulta_veterinaria_profesional" else 100
            
            # 3. Delegar generación al chat_handler
            generate_with_safe_fallback(
                prompt=prompt,
                dispatcher=dispatcher,
                tracker=tracker,
                fallback_template=f"utter_{current_intent}",
                max_new_tokens=max_tokens,
                temperature=0.7
            )

            # 4. Enviar botones de seguimiento
            logger.info(f"[OutOfContext] Enviando botones de seguimiento...")
            if current_intent == "consulta_veterinaria_profesional":
                self._handle_medical_consultation(dispatcher, user_message, tracker)
            elif current_intent == "off_topic":
                self._handle_offtopic(dispatcher, tracker)
            else:  # out_of_scope
                self._handle_out_of_scope(dispatcher, tracker)

        except Exception as e:
            logger.error(f"[OutOfContext] Error crítico en la action: {e}", exc_info=True)
            dispatcher.utter_message(text="Tuve un problema procesando eso. ¿Podrías decirlo de otra manera?")

        return []

    # ============================================================
    # ✅ NUEVO MÉTODO: CLASIFICACIÓN Y MANEJO CON LLM
    # ============================================================
    
    def _classify_and_handle_with_llm(
        self,
        user_message: str,
        current_intent: str,
        dispatcher: CollectingDispatcher,
        tracker: Tracker
    ) -> Optional[List[EventType]]:
        """
        Usa el modelo de búsqueda (MistralB) para:
        1. Clasificar si es búsqueda o conversacional
        2a. Si es búsqueda → generar parámetros y ejecutar
        2b. Si NO es búsqueda → retornar None para continuar con lógica conversacional
        """
        try:
            from actions.models.model_manager import get_search_engine
            search_engine = get_search_engine()
            
            # Construir contexto
            context = self._build_context_dict(tracker)
            
            # ===== PASO 1: CLASIFICAR =====
            logger.info(f"[OutOfContext LLM] Clasificando: '{user_message}'")
            classification = search_engine.classify_intent(user_message, context)
            
            is_search = classification.get('is_search', False)
            confidence = classification.get('confidence', 0.0)
            reasoning = classification.get('reasoning', '')
            llm_used = classification.get('llm_used', 'none')
            
            logger.info(
                f"[OutOfContext LLM] Resultado: {'🔍 BÚSQUEDA' if is_search else '💬 CONVERSACIONAL'} "
                f"(conf: {confidence:.2f}, {llm_used.upper()})\n"
                f"    Razón: {reasoning}"
            )
            
            # ===== PASO 2a: ES BÚSQUEDA → GENERAR Y EJECUTAR =====
            if is_search and confidence >= 0.6:  # Umbral de confianza
                logger.info("[OutOfContext LLM] ✅ Detectada búsqueda, generando parámetros...")
                
                # Generar parámetros de búsqueda
                generation_result = search_engine.generate_search_from_message(
                    user_message, context, search_type="productos"
                )
                
                if not generation_result.get('success'):
                    logger.error(f"[OutOfContext LLM] ❌ Error generando búsqueda: {generation_result.get('error')}")
                    # Fallback a mensaje conversacional
                    dispatcher.utter_message(
                        "Creo que querés buscar algo, pero no entendí bien. "
                        "¿Podrías ser más específico? Por ejemplo: 'busco pipetas para gatos'"
                    )
                    return [SlotSet("user_engagement_level", "needs_clarification")]
                
                search_params = generation_result['search_params']
                search_type = generation_result['search_type']
                llm_time = generation_result.get('llm_time', 0.0)
                
                logger.info(
                    f"[OutOfContext LLM] ✅ Parámetros: {search_params}\n"
                    f"    Tipo: {search_type}, Tiempo: {llm_time:.2f}s"
                )
                
                # Ejecutar búsqueda
                try:
                    search_result = search_engine.execute_search(
                        search_params=search_params,
                        search_type=search_type,
                        user_message=user_message,
                        is_modification=False,
                        previous_params=None
                    )
                    
                    if search_result.get('success'):
                        total_results = search_result.get('total_results', 0)
                        
                        # Formatear parámetros para display
                        params_display = self._format_parameters_for_display(search_params)
                        params_str = ", ".join([f"{k}: {v}" for k, v in params_display.items()])
                        
                        if total_results > 0:
                            text_message = f"✅ Encontré {total_results} {'ofertas' if search_type == 'ofertas' else 'productos'}."
                        else:
                            text_message = f"❌ No encontré {search_type} con: {params_str}"
                        
                        # Enviar resultados
                        custom_payload = {
                            "type": "search_results",
                            "search_type": search_type,
                            "validated": True,
                            "timestamp": datetime.now().isoformat(),
                            "parameters": search_params,
                            "search_results": search_result.get('results', {}),
                            "generated_by_llm": True,
                            "llm_confidence": confidence,
                            "recovered_from_intent": current_intent
                        }
                        
                        dispatcher.utter_message(text=text_message, custom=custom_payload)
                        
                        # Actualizar historial
                        search_history = context.get('search_history', [])
                        search_history.append({
                            'timestamp': datetime.now().isoformat(),
                            'type': search_type,
                            'parameters': search_params,
                            'status': 'completed_by_llm',
                            'llm_confidence': confidence,
                            'recovered_from': current_intent
                        })
                        
                        return [
                            SlotSet("search_history", search_history),
                            SlotSet("user_engagement_level", "satisfied")
                        ]
                    
                    else:
                        error = search_result.get('error', 'Error desconocido')
                        logger.error(f"[OutOfContext LLM] ❌ Error en búsqueda: {error}")
                        dispatcher.utter_message(
                            "Entendí que querés buscar algo, pero hubo un error. "
                            "¿Podrías reformular tu búsqueda?"
                        )
                        return [SlotSet("user_engagement_level", "needs_help")]
                
                except Exception as search_error:
                    logger.error(f"[OutOfContext LLM] ❌ Excepción: {search_error}", exc_info=True)
                    dispatcher.utter_message(
                        "Hubo un error procesando tu búsqueda. ¿Podrías intentar de nuevo?"
                    )
                    return [SlotSet("user_engagement_level", "needs_help")]
            
            # ===== PASO 2b: NO ES BÚSQUEDA → CONTINUAR CON LÓGICA CONVERSACIONAL =====
            else:
                logger.info("[OutOfContext LLM] 💬 No es búsqueda, continuando con respuesta conversacional")
                return None  # Retornar None para que continúe el flujo normal
        
        except Exception as e:
            logger.error(f"[OutOfContext LLM] ❌ Error crítico: {e}", exc_info=True)
            # En caso de error, continuar con lógica conversacional
            return None

    def _build_context_dict(self, tracker: Tracker) -> Dict[str, Any]:
        """Construye diccionario de contexto desde el tracker."""
        try:
            search_history = tracker.get_slot('search_history') or []
            pending_suggestion = tracker.get_slot('pending_suggestion')
            user_sentiment = tracker.get_slot('user_sentiment') or 'neutral'
            
            # Obtener últimos mensajes para contexto
            events = tracker.events
            chat_history = []
            for event in events[-10:]:  # Últimos 10 eventos
                if event.get('event') == 'user':
                    chat_history.append({
                        'role': 'user',
                        'text': event.get('text', '')
                    })
                elif event.get('event') == 'bot':
                    chat_history.append({
                        'role': 'bot',
                        'text': event.get('text', '')
                    })
            
            return {
                'user_message': tracker.latest_message.get('text', ''),
                'search_history': search_history,
                'pending_suggestion': pending_suggestion,
                'detected_sentiment': user_sentiment,
                'chat_history': chat_history,
                'implicit_intentions': []  # Puedes agregar detección de intenciones si existe
            }
        
        except Exception as e:
            logger.error(f"[OutOfContext] Error construyendo contexto: {e}")
            return {
                'user_message': tracker.latest_message.get('text', ''),
                'search_history': [],
                'detected_sentiment': 'neutral'
            }

    def _format_parameters_for_display(self, parameters: Dict[str, Any]) -> Dict[str, str]:
        """Formatea parámetros para mostrar al usuario."""
        formatted = {}
        
        for key, value in parameters.items():
            if isinstance(value, dict):
                if 'value' in value:
                    formatted[key] = str(value['value'])
                else:
                    formatted[key] = str(value)
            else:
                formatted[key] = str(value)
        
        return formatted

    # ============================================================
    # MÉTODOS EXISTENTES (sin cambios en la lógica conversacional)
    # ============================================================

    def _get_contextual_prompt(self, intent: str, user_message: str, tracker: Tracker) -> str:
        """
        ✅ Prompts que aprovechan el contexto automático
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
            return (
                f'Usuario cambió de tema: "{user_message}"\n'
                f'Tenés una sugerencia pendiente pero el usuario se distrajo.\n'
                f'Respondé brevemente al off-topic + reconducí SUAVEMENTE a la sugerencia.\n'
                f'Bot:'
            )
        elif has_search:
            return (
                f'Usuario se distrajo durante búsqueda: "{user_message}"\n'
                f'Respondé brevemente + reconducí a la búsqueda activa.\n'
                f'Bot:'
            )
        else:
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
            pass  # No se envían botones extra si ya hay una sugerencia activa
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