from asyncio.log import logger
import difflib
from random import choice
from typing import Any, Dict, List
from xml.dom.minidom import Text

from actions.helpers import validate_entities_for_intent
from actions.logger import log_message
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, EventType
from datetime import datetime
from .conversation_state import ConversationState

# ✅ Importar generación con Ollama
from actions.models.model_manager import generate_text_with_context

class ActionFallback(Action):
    """Fallback avanzado con generación de respuestas usando Ollama"""
    
    def name(self) -> Text:
        return "action_fallback"
    
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        # Obtener contexto de conversación
        log_message(tracker, nlu_conf_threshold=0.6)
        context = ConversationState.get_conversation_context(tracker)
        user_msg = context['user_message']
        sentiment = context['detected_sentiment']
        implicit_intentions = context['implicit_intentions']
        
        # Obtener intent actual y entidades
        current_intent = tracker.latest_message.get('intent', {}).get('name', 'unknown')
        entities = tracker.latest_message.get('entities', [])
        
        # Obtener sugerencia pendiente del sistema unificado
        pending_suggestion = context.get('pending_suggestion')
        awaiting_suggestion_response = context.get('awaiting_suggestion_response', False)
        
        # Obtener slots activos
        pending_search = tracker.get_slot('pending_search')
        pedido_incompleto = tracker.get_slot('pedido_incompleto')
        user_engagement_level = tracker.get_slot('user_engagement_level')
        
        # Logging detallado del contexto actual
        self._log_context_analysis(user_msg, current_intent, sentiment, implicit_intentions, 
                                 entities, pending_suggestion, awaiting_suggestion_response, 
                                 user_engagement_level)
        
        # Analizar entidades para determinar intención
        entity_analysis = self._analyze_entities_with_fragment_protection(entities)
        
        events = []
        events.append(SlotSet("user_sentiment", sentiment))
        
        # PRIORIDAD 1: Verificar si está completando una sugerencia pendiente
        if awaiting_suggestion_response and pending_suggestion:
            logger.info(f"[Fallback Decision] PRIORIDAD: Usuario completando sugerencia pendiente")
            events.extend(self._handle_suggestion_completion(context, entity_analysis, dispatcher, tracker))
            return events
        
        # PRIORIDAD 2: Verificar si ignoró sugerencia y cambió de tema
        elif pending_suggestion and not awaiting_suggestion_response:
            from ..conversation_state import SuggestionManager
            if SuggestionManager.check_if_suggestion_ignored(current_intent, pending_suggestion, context['is_small_talk']):
                logger.info("[Fallback Decision] Usuario ignoró sugerencia pendiente")
                events.extend(self._handle_ignored_suggestion(pending_suggestion, context, entity_analysis, dispatcher, tracker))
                return events
        
        # Resto de la lógica con generación Ollama
        if current_intent in ['off_topic', 'out_of_scope']:
            logger.info(f"[Fallback Decision] Mensaje fuera de contexto detectado: {current_intent}")
            events.extend(self._handle_out_of_scope(context, entity_analysis, dispatcher, tracker))
            
        elif current_intent == 'ambiguity_fallback':
            logger.info(f"[Fallback Decision] Ambigüedad detectada con entidades: {[e['entity'] for e in entities]}")
            events.extend(self._handle_ambiguity(context, entity_analysis, dispatcher, tracker))
            
        elif sentiment == "rejection":
            logger.info("[Fallback Decision] Sentimiento de rechazo detectado")
            events.extend(self._handle_rejection(context, dispatcher, tracker))
            
        elif sentiment == "negative":
            logger.info("[Fallback Decision] Feedback negativo detectado")
            events.extend(self._handle_negative_feedback(context, dispatcher, tracker))
            
        elif "search_intentions" in implicit_intentions or entity_analysis['has_product_related']:
            logger.info(f"[Fallback Decision] Intención de búsqueda implícita o entidades de producto detectadas")
            events.extend(self._handle_implicit_search(context, entity_analysis, dispatcher, tracker))
            
        elif "help_requests" in implicit_intentions:
            logger.info("[Fallback Decision] Solicitud de ayuda detectada")
            events.extend(self._handle_help_request(context, dispatcher, tracker))
            
        elif pending_search or pedido_incompleto:
            logger.info(f"[Fallback Decision] Búsqueda pendiente o pedido incompleto activo")
            events.extend(self._handle_pending_search_fallback(context, entity_analysis, dispatcher, tracker))
            
        else:
            logger.info("[Fallback Decision] Fallback general - sin contexto específico")
            events.extend(self._handle_general_fallback(context, entity_analysis, dispatcher, tracker))
        
        return events
    
    def _log_context_analysis(self, user_msg: str, intent: str, sentiment: str, 
                            implicit_intentions: List[str], entities: List[Dict], 
                            pending_suggestion: Any, awaiting_response: bool, engagement_level: str):
        """Análisis detallado del contexto"""
        entity_summary = {e['entity']: e['value'] for e in entities} if entities else {}
        
        suggestion_info = "Ninguna"
        if pending_suggestion:
            suggestion_type = pending_suggestion.get('suggestion_type', 'unknown')
            suggestion_search_type = pending_suggestion.get('search_type', 'N/A')
            suggestion_info = f"{suggestion_type} ({suggestion_search_type})"
        
        logger.info(f"""
=== ANÁLISIS DE CONTEXTO FALLBACK CON OLLAMA ===
Mensaje del usuario: "{user_msg}"
Intent detectado: {intent}
Sentimiento: {sentiment}
Intenciones implícitas: {implicit_intentions}
Entidades detectadas: {entity_summary}
Sistema Unificado de Sugerencias:
  - Sugerencia pendiente: {suggestion_info}
  - Esperando respuesta: {'Sí' if awaiting_response else 'No'}
Estado del usuario:
  - user_engagement_level: {engagement_level}
=================================================
        """)
    
    def _analyze_entities_with_fragment_protection(self, entities: List[Dict]) -> Dict[str, Any]:
        """Analiza las entidades con protección contra fragmentos de palabras"""
        validation_result = validate_entities_for_intent(
            entities, 
            intent_name=None,
            min_length=3, 
            check_fragments=True
        )
        
        analysis = {
            'has_product_related': False,
            'has_commercial_intent': False,
            'product_entities': [],
            'commercial_entities': [],
            'context_entities': [],
            'entity_count': len(entities),
            'valid_entity_count': len(validation_result['valid_params']),
            'rejected_fragments': 0
        }
        
        original_values = [e.get('value', '') for e in entities if e.get('value')]
        analysis['rejected_fragments'] = len(original_values) - analysis['valid_entity_count']
        
        product_related = ['nombre', 'animal', 'sintoma']
        commercial_related = ['empresa', 'cantidad_descuento', 'cantidad_bonificacion', 'cantidad', 'precio']
        
        for param_name, param_value in validation_result['valid_params'].items():
            if param_name in product_related:
                analysis['has_product_related'] = True
                analysis['product_entities'].append({'type': param_name, 'value': param_value})
                
            elif param_name in commercial_related:
                analysis['has_commercial_intent'] = True
                analysis['commercial_entities'].append({'type': param_name, 'value': param_value})
                
            else:
                analysis['context_entities'].append({'type': param_name, 'value': param_value})
        
        logger.info(f"[Entity Analysis] Total: {analysis['entity_count']}, "
                   f"Válidos: {analysis['valid_entity_count']}, "
                   f"Fragmentos rechazados: {analysis['rejected_fragments']}")
        
        analysis['validation_result'] = validation_result
        return analysis

    def _generate_response_with_fallback(self, prompt: str, fallback_msg: str, 
                                        tracker: Tracker, dispatcher: CollectingDispatcher) -> None:
        """✅ NUEVA: Genera respuesta con Ollama y fallback hardcoded"""
        logger.info("[Fallback] Intentando generar respuesta con Ollama...")
        
        response = generate_text_with_context(
            prompt=prompt,
            tracker=tracker,
            max_new_tokens=120,
            temperature=0.4
        )
        
        if response:
            dispatcher.utter_message(text=response)
            logger.info("[Fallback] ✓ Respuesta generada con Ollama enviada.")
        else:
            logger.warning("[Fallback] Generación falló. Usando fallback hardcodeado.")
            dispatcher.utter_message(text=fallback_msg)

    def _handle_suggestion_completion(self, context: Dict[str, Any], entity_analysis: Dict, 
                                    dispatcher: CollectingDispatcher, tracker: Tracker) -> List[EventType]:
        """Maneja cuando el usuario está completando una sugerencia pendiente"""
        logger.info("[Action] Manejando completación de sugerencia pendiente")
        
        pending_suggestion = context.get('pending_suggestion', {})
        suggestion_type = pending_suggestion.get('suggestion_type', '')
        
        events = []
        
        try:
            if suggestion_type == 'missing_parameters':
                search_type = pending_suggestion.get('search_type', 'producto')
                current_parameters = pending_suggestion.get('current_parameters', {})
                new_params = entity_analysis.get('validation_result', {}).get('valid_params', {})
                
                if new_params:
                    combined_params = {**current_parameters, **new_params}
                    params_text = ", ".join([f"{k}: {v}" for k, v in new_params.items()])
                    
                    # ✅ Generar respuesta con Ollama
                    prompt = f"""
                    El usuario agregó nuevos parámetros a su búsqueda de {search_type}s.
                    Parámetros agregados: {params_text}
                    Parámetros totales: {', '.join([f'{k}: {v}' for k, v in combined_params.items()])}
                    
                    Generá una respuesta corta y amigable confirmando los parámetros agregados.
                    Mostrá entusiasmo y preguntá si quiere agregar algo más o ejecutar la búsqueda.
                    """
                    
                    fallback = f"¡Perfecto! Agregando {params_text} a tu búsqueda de {search_type}s."
                    self._generate_response_with_fallback(prompt, fallback, tracker, dispatcher)
                    
                    search_message = f"Buscando {search_type}s con: " + ", ".join([f"{k}: {v}" for k, v in combined_params.items()])
                    
                    dispatcher.utter_message(
                        text=search_message,
                        json_message={
                            "type": "search_results",
                            "search_type": search_type,
                            "parameters": combined_params,
                            "completed_from_suggestion": True,
                            "timestamp": datetime.now().isoformat()
                        }
                    )
                    
                    search_history = context.get('search_history', [])
                    search_history.append({
                        'timestamp': datetime.now().isoformat(),
                        'type': search_type,
                        'parameters': combined_params,
                        'status': 'completed_from_suggestion'
                    })
                    
                    events.extend([
                        SlotSet("search_history", search_history),
                        SlotSet("pending_suggestion", None),
                        SlotSet("user_engagement_level", "satisfied")
                    ])
                    
                else:
                    criteria = pending_suggestion.get('required_criteria', 'información adicional')
                    
                    prompt = f"""
                    El usuario intentó agregar parámetros pero no fueron válidos.
                    Necesitamos: {criteria}
                    
                    Pedile amablemente que sea más específico. Mantené el tono cordial.
                    """
                    
                    fallback = f"No pude identificar parámetros válidos. ¿Puedes ser más específico con {criteria}?"
                    self._generate_response_with_fallback(prompt, fallback, tracker, dispatcher)
                    
                    events.append(SlotSet("user_engagement_level", "needs_clarification"))
            
            elif suggestion_type in ['entity_correction', 'type_correction']:
                dispatcher.utter_message("Si aceptas la sugerencia, responde 'sí'. Si no, puedes decir 'no' o intentar con otros términos.")
                
            return events
            
        except Exception as e:
            logger.error(f"[Action] Error manejando completación: {e}", exc_info=True)
            dispatcher.utter_message("Hubo un error procesando tu respuesta. ¿Puedes intentar nuevamente?")
            return [SlotSet("pending_suggestion", None), SlotSet("user_engagement_level", "needs_help")]

    def _handle_ignored_suggestion(self, pending_suggestion: Dict[str, Any], context: Dict[str, Any],
                                 entity_analysis: Dict, dispatcher: CollectingDispatcher, 
                                 tracker: Tracker) -> List[EventType]:
        """Maneja cuando el usuario ignoró una sugerencia"""
        logger.info("[Action] Manejando sugerencia ignorada")
        
        events = []
        suggestion_type = pending_suggestion.get('suggestion_type', '')
        
        if suggestion_type == 'missing_parameters':
            old_search_type = pending_suggestion.get('search_type', 'producto')
            
            if entity_analysis['valid_entity_count'] > 0:
                new_params = entity_analysis.get('validation_result', {}).get('valid_params', {})
                new_search_type = 'oferta' if entity_analysis['has_commercial_intent'] else 'producto'
                
                # ✅ Generar respuesta con Ollama
                prompt = f"""
                El usuario ignoró su búsqueda anterior de {old_search_type}s y quiere buscar {new_search_type}s.
                Nuevos parámetros: {', '.join([f'{k}: {v}' for k, v in new_params.items()])}
                
                Confirmá amablemente el cambio de búsqueda y mostrá que entendés su nueva intención.
                Mantené un tono positivo y servicial.
                """
                
                fallback = f"Entiendo que quieres hacer una nueva búsqueda de {new_search_type}s. ¡Procedamos!"
                self._generate_response_with_fallback(prompt, fallback, tracker, dispatcher)
                
                params_text = ", ".join([f"{k}: {v}" for k, v in new_params.items()])
                dispatcher.utter_message(
                    text=f"Buscando {new_search_type}s con {params_text}",
                    json_message={
                        "type": "search_results",
                        "search_type": new_search_type,
                        "parameters": new_params,
                        "replaced_previous_suggestion": True,
                        "timestamp": datetime.now().isoformat()
                    }
                )
                
                events.extend([
                    SlotSet("pending_suggestion", None),
                    SlotSet("user_engagement_level", "engaged")
                ])
            else:
                prompt = f"""
                El usuario cambió de tema desde una búsqueda de {old_search_type}s pero no especificó qué quiere ahora.
                Preguntale amablemente qué tipo de búsqueda quiere hacer.
                """
                
                fallback = f"¿Qué tipo de búsqueda quieres hacer ahora?"
                self._generate_response_with_fallback(prompt, fallback, tracker, dispatcher)
                
                events.extend([
                    SlotSet("pending_suggestion", None),
                    SlotSet("user_engagement_level", "redirecting")
                ])
        else:
            dispatcher.utter_message("Entendido, sigamos con tu nueva consulta.")
            events.append(SlotSet("pending_suggestion", None))
        
        return events
    
    def _handle_out_of_scope(self, context: Dict[str, Any], entity_analysis: Dict, 
                           dispatcher: CollectingDispatcher, tracker: Tracker) -> List[EventType]:
        """Maneja mensajes fuera del contexto"""
        logger.info("[Action] Manejando mensaje fuera de contexto")
        
        if entity_analysis['has_product_related'] or entity_analysis['has_commercial_intent']:
            entities_mentioned = []
            if entity_analysis['product_entities']:
                entities_mentioned.extend([e['value'] for e in entity_analysis['product_entities']])
            if entity_analysis['commercial_entities']:
                entities_mentioned.extend([e['value'] for e in entity_analysis['commercial_entities']])
            
            prompt = f"""
            El usuario mencionó: {', '.join(entities_mentioned)} pero su mensaje no fue claro.
            Reconocé que entendés algo de lo que dijo, pero pedile que sea más específico.
            Sugerí que puede buscar por nombre de producto, animal, síntoma, o proveedor.
            Mantené un tono amigable y alentador.
            """
            
            fallback = "Parece que mencionas algo relacionado con productos, pero no entiendo completamente. ¿Podrías ser más específico?"
            self._generate_response_with_fallback(prompt, fallback, tracker, dispatcher)
            
            return [SlotSet("user_engagement_level", "confused_but_interested")]
        else:
            prompt = """
            El usuario dijo algo que no está relacionado con buscar productos veterinarios.
            Redirigilo suavemente explicando tu especialidad (productos y ofertas veterinarias).
            Preguntá si hay algún producto que necesite. Tono cordial pero firme.
            """
            
            fallback = "Me especializo en ayudarte a buscar productos y ofertas. ¿Hay algún producto específico que necesites?"
            self._generate_response_with_fallback(prompt, fallback, tracker, dispatcher)
            
            return [SlotSet("user_engagement_level", "redirecting")]
    
    def _handle_ambiguity(self, context: Dict[str, Any], entity_analysis: Dict,
                         dispatcher: CollectingDispatcher, tracker: Tracker) -> List[EventType]:
        """Maneja mensajes ambiguos"""
        logger.info("[Action] Manejando ambigüedad")
        user_msg = context.get('user_message', '')
        
        if entity_analysis['entity_count'] == 0:
            prompt = f"""
            El usuario dijo: "{user_msg}" pero no mencionó nada específico.
            Pedile amablemente más detalles sugiriendo ejemplos concretos:
            - Nombre del producto
            - Animal (perro, gato, etc.)
            - Tipo de oferta
            Mantené el tono cordial y alentador.
            """
            
            fallback = "Tu mensaje no es claro. ¿Puedes ser más específico? Por ejemplo, dime el nombre del producto o para qué animal es."
            self._generate_response_with_fallback(prompt, fallback, tracker, dispatcher)
            
            return [SlotSet("user_engagement_level", "needs_clarification")]
            
        elif entity_analysis['has_product_related']:
            products = [e['value'] for e in entity_analysis['product_entities']]
            
            prompt = f"""
            El usuario mencionó: {', '.join(products)} pero necesitamos más contexto.
            Preguntá qué quiere hacer exactamente:
            - ¿Buscar el producto?
            - ¿Comparar precios?
            - ¿Ver ofertas?
            Sé específico y útil.
            """
            
            fallback = f"Mencionas {', '.join(products)}, pero necesito más detalles. ¿Buscas el producto, comparar precios, o ver ofertas?"
            self._generate_response_with_fallback(prompt, fallback, tracker, dispatcher)
            
            return [SlotSet("user_engagement_level", "clarifying_product")]
            
        else:
            return self._handle_general_fallback(context, entity_analysis, dispatcher, tracker)
    
    def _handle_rejection(self, context: Dict[str, Any], dispatcher: CollectingDispatcher, 
                         tracker: Tracker) -> List[EventType]:
        """Maneja rechazo del usuario"""
        logger.info("[Action] Manejando rechazo")
        events = []
        
        if context.get('pending_search') or context.get('pedido_incompleto'):
            events.extend([
                SlotSet("pending_search", None),
                SlotSet("pedido_incompleto", None)
            ])
        
        prompt = """
        El usuario rechazó la ayuda o está molesto.
        Disculpate cordialmente sin ser excesivo.
        Dejá en claro que estás disponible si cambia de opinión.
        Tono empático pero profesional.
        """
        
        fallback = "Entiendo, disculpa si no pude ayudarte. Si cambias de opinión, estaré aquí para asistirte."
        self._generate_response_with_fallback(prompt, fallback, tracker, dispatcher)
        
        events.append(SlotSet("user_engagement_level", "disengaged"))
        return events
    
    def _handle_negative_feedback(self, context: Dict[str, Any], dispatcher: CollectingDispatcher,
                                 tracker: Tracker) -> List[EventType]:
        """Maneja feedback negativo"""
        logger.info("[Action] Manejando feedback negativo")
        
        prompt = """
        El usuario está insatisfecho con el servicio.
        Disculpate genuinamente y pedí detalles específicos de qué necesita.
        Mostrá disposición a mejorar. Tono empático y profesional.
        """
        
        fallback = "Lamento que la experiencia no haya sido la esperada. ¿Podrías decirme qué producto o información necesitas específicamente?"
        self._generate_response_with_fallback(prompt, fallback, tracker, dispatcher)
        
        return [SlotSet("user_engagement_level", "needs_help")]
    
    def _handle_implicit_search(self, context: Dict[str, Any], entity_analysis: Dict,
                              dispatcher: CollectingDispatcher, tracker: Tracker) -> List[EventType]:
        """Maneja intención implícita de búsqueda"""
        logger.info("[Action] Manejando búsqueda implícita")
        
        if entity_analysis['has_product_related']:
            products = [e['value'] for e in entity_analysis['product_entities']]
            
            prompt = f"""
            El usuario mencionó: {', '.join(products)} con intención de búsqueda.
            Confirmá que entendés su interés y ofrecé opciones claras:
            - Ver productos disponibles
            - Comparar precios
            - Buscar ofertas
            Sé específico y accionable.
            """
            
            fallback = f"Veo que te interesa {', '.join(products)}. ¿Quieres ver productos, comparar precios, o buscar ofertas?"
            self._generate_response_with_fallback(prompt, fallback, tracker, dispatcher)
            
            return [SlotSet("user_engagement_level", "product_focused")]
            
        else:
            prompt = """
            El usuario tiene intención comercial pero sin especificar producto.
            Preguntá qué producto específico le interesa.
            Sugerí ejemplos si es necesario. Tono servicial.
            """
            
            fallback = "Parece que quieres buscar algo. ¿Qué producto específico te interesa?"
            self._generate_response_with_fallback(prompt, fallback, tracker, dispatcher)
            
            return [SlotSet("user_engagement_level", "search_interested")]
    
    def _handle_help_request(self, context: Dict[str, Any], dispatcher: CollectingDispatcher,
                            tracker: Tracker) -> List[EventType]:
        """Maneja solicitud de ayuda"""
        logger.info("[Action] Manejando solicitud de ayuda")
        
        prompt = """
        El usuario pidió ayuda.
        Explicá claramente qué podés hacer (buscar productos y ofertas).
        Listá ejemplos de información útil que puede darte:
        - Nombre del producto
        - Animal
        - Proveedor
        - Síntomas
        Tono educativo pero accesible.
        """
        
        fallback = "Puedo ayudarte a buscar productos y ofertas. Dime: nombre del producto, animal, proveedor, o cualquier detalle que tengas."
        self._generate_response_with_fallback(prompt, fallback, tracker, dispatcher)
        
        return [SlotSet("user_engagement_level", "needs_guidance")]
    
    def _handle_pending_search_fallback(self, context: Dict[str, Any], entity_analysis: Dict,
                                      dispatcher: CollectingDispatcher, tracker: Tracker) -> List[EventType]:
        """Maneja fallback con búsqueda pendiente"""
        logger.info("[Action] Manejando fallback con búsqueda pendiente")
        
        pending_search = context.get('pending_search')
        
        if entity_analysis['entity_count'] > 0:
            entities = [e.get('value', '') for e in 
                       entity_analysis['product_entities'] + entity_analysis['commercial_entities']]
            
            prompt = f"""
            El usuario mencionó: {', '.join(entities)} pero tiene una búsqueda pendiente.
            Preguntá qué quiere hacer:
            - Modificar búsqueda actual
            - Empezar nueva búsqueda
            - Continuar con la anterior
            Sé claro sobre las opciones.
            """
            
            fallback = f"Mencionas {', '.join(entities)} pero tienes una búsqueda pendiente. ¿Quieres modificarla, empezar nueva, o continuar?"
            self._generate_response_with_fallback(prompt, fallback, tracker, dispatcher)
            
            return [SlotSet("user_engagement_level", "modifying_search")]
        
        if pending_search:
            search_type = pending_search.get('search_type', 'búsqueda')
            current_params = pending_search.get('parameters', {})
            
            if current_params:
                params_str = ", ".join([f"{k}: {v}" for k, v in current_params.items()])
                
                prompt = f"""
                El usuario no fue claro. Tiene búsqueda de {search_type}s con: {params_str}
                Preguntá si quiere:
                - Continuar
                - Modificar
                - Cancelar
                Sé conciso y directo.
                """
                
                fallback = f"Tu búsqueda de {search_type}s tiene: {params_str}. ¿Quieres continuarla, modificarla o cancelarla?"
                self._generate_response_with_fallback(prompt, fallback, tracker, dispatcher)
        
        return [SlotSet("user_engagement_level", "pending_decision")]
    
    def _handle_general_fallback(self, context: Dict[str, Any], entity_analysis: Dict,
                               dispatcher: CollectingDispatcher, tracker: Tracker) -> List[EventType]:
        """Maneja fallback general"""
        logger.info("[Action] Manejando fallback general")
        user_msg = context.get('user_message', '')
        
        if entity_analysis['entity_count'] > 0:
            entities = context.get('latest_message', {}).get('entities', [])
            entity_types = list(set([e.get('entity', '') for e in entities]))
            
            prompt = f"""
            El usuario dijo: "{user_msg}" y mencionó: {', '.join(entity_types)}
            No está claro qué necesita exactamente.
            Pedí más especificidad de forma amigable.
            Sugerí que diga qué producto busca o qué información necesita.
            """
            
            fallback = f"Veo que mencionas {', '.join(entity_types)}, pero no estoy seguro qué necesitas. ¿Puedes ser más específico?"
            self._generate_response_with_fallback(prompt, fallback, tracker, dispatcher)
            
            return [SlotSet("user_engagement_level", "entity_confused")]
        
        # Respuesta completamente general
        prompt = f"""
        El usuario dijo: "{user_msg}" pero no está claro qué quiere.
        Ofrecé ayuda de forma amigable mencionando tus especialidades:
        - Buscar productos veterinarios
        - Encontrar ofertas
        Preguntá qué puede ayudarlo a encontrar específicamente.
        """
        
        fallback = "No estoy seguro de entender. ¿Buscas productos, ofertas, o tienes otra consulta específica?"
        self._generate_response_with_fallback(prompt, fallback, tracker, dispatcher)
        
        return [SlotSet("user_engagement_level", "general_confused")]