
from asyncio.log import logger
import difflib
from random import random, choice
from typing import Any, Dict, List
from xml.dom.minidom import Text

from actions.helpers import get_intent_info
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, EventType


class ActionSmallTalkSituacion(Action):
    """Small talk mejorado usando responses del config y chistes reales"""
    
    def name(self) -> Text:
        return "action_smalltalk_situacion"
    
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[EventType]:
        try:
            # Obtener contexto de manera segura
            current_intent = tracker.latest_message.get("intent", {}).get("name", "")
            
            # Obtener slots de manera segura
            def get_slot_safe(slot_name, default=None):
                try:
                    value = tracker.get_slot(slot_name)
                    return value if value is not None else default
                except:
                    return default
            
            pending_search = get_slot_safe("pending_search_data")
            pedido_incompleto = get_slot_safe("pedido_incompleto", False)
            
            logger.info(f"[SmallTalkSituacion] Intent: {current_intent}, PendingSearch: {pending_search is not None}, PedidoIncompleto: {pedido_incompleto}")
            
            # MANEJO ESPECIAL PARA CHISTES CON RESPONSES DEL CONFIG
            if current_intent == "pedir_chiste":
                intent_info = get_intent_info(current_intent)
                responses = intent_info.get("responses", [])
                
                if responses:
                    # Usar responses del config si están disponibles
                    if isinstance(responses, list) and responses:
                        chiste_text = choice(responses).get("text", "") if isinstance(responses[0], dict) else choice(responses)
                    elif isinstance(responses, dict) and "text" in responses:
                        chiste_text = responses["text"]
                    else:
                        chiste_text = str(responses)
                    
                    if chiste_text:
                        dispatcher.utter_message(text=chiste_text)
                        logger.info(f"[SmallTalkSituacion] Chiste fallback enviado: {chiste_text[:30]}...")
                return []
            
            # RESPUESTAS CONTEXTUALIZADAS ESPECÍFICAS (prioritarias)
            elif pending_search and current_intent == "saludo":
                search_type = pending_search.get('search_type', 'búsqueda') if isinstance(pending_search, dict) else 'búsqueda'
                message = f"¡Hola otra vez! Recuerdo que estabas buscando {search_type}s. ¿Seguimos con eso?"
                dispatcher.utter_message(text=message)
                logger.info(f"[SmallTalkSituacion] Respuesta contextual con pending_search")
                return []
                
            elif pedido_incompleto and current_intent == "saludo":
                message = "¡Hola otra vez! Recuerdo que estabas buscando algo. ¿Seguimos?"
                dispatcher.utter_message(text=message)
                logger.info(f"[SmallTalkSituacion] Respuesta contextual con pedido_incompleto")
                return []
                
            elif pending_search and current_intent == "preguntar_como_estas":
                message = "¡Muy bien, gracias! ¿Y tú? ¿Quieres continuar con tu búsqueda?"
                dispatcher.utter_message(text=message)
                logger.info(f"[SmallTalkSituacion] Respuesta contextual cómo estás con pending")
                return []
                
            elif pedido_incompleto and current_intent == "preguntar_como_estas":
                message = "¡Muy bien! ¿Y tú? ¿Quieres continuar con tu búsqueda?"
                dispatcher.utter_message(text=message)
                logger.info(f"[SmallTalkSituacion] Respuesta contextual cómo estás con pedido")
                return []
            
            # USAR RESPONSES DEL CONFIG (principal)
            intent_info = get_intent_info(current_intent)
            responses = intent_info.get("responses", [])
            
            if responses:
                # Seleccionar response del config
                if isinstance(responses, list) and responses:
                    if isinstance(responses[0], dict) and "text" in responses[0]:
                        message = choice(responses)["text"]
                    else:
                        message = choice(responses) if isinstance(responses[0], str) else str(responses[0])
                elif isinstance(responses, dict) and "text" in responses:
                    message = responses["text"]
                else:
                    message = str(responses)
                
                dispatcher.utter_message(text=message)
                logger.info(f"[SmallTalkSituacion] Response del config usado para {current_intent}")
                return []
            
            # FALLBACK: Intentar usar response del domain.yml
            response_name = f"utter_{current_intent}"
            if domain and response_name in domain.get("responses", {}):
                logger.info(f"[SmallTalkSituacion] Usando response del domain: {response_name}")
                try:
                    dispatcher.utter_message(response=response_name)
                    logger.info(f"[SmallTalkSituacion] Domain response enviado: {response_name}")
                    return []
                except Exception as e:
                    logger.warning(f"[SmallTalkSituacion] Error usando domain response '{response_name}': {e}")
            
            # FALLBACK FINAL: Respuestas hardcodeadas
            responses_fallback = {
                "saludo": [
                    "¡Hola! ¿En qué puedo ayudarte hoy?",
                    "¡Hola! Estoy aquí para ayudarte a encontrar lo que necesites.",
                    "¡Hola! ¿Buscas algún producto en particular?"
                ],
                "preguntar_como_estas": [
                    "¡Muy bien, gracias por preguntar! ¿Y tú cómo estás?",
                    "¡Excelente! Listo para ayudarte. ¿Cómo andas?",
                    "¡Todo perfecto! ¿Cómo te encuentras?"
                ],
                "responder_como_estoy": [
                    "Me alegra escuchar eso. ¿En qué puedo ayudarte?",
                    "¡Qué bueno! ¿Hay algo que necesites buscar?",
                    "Perfecto. ¿Te puedo ayudar con alguna búsqueda?"
                ],
                "responder_estoy_bien": [
                    "¡Excelente! ¿Qué puedo hacer por ti?",
                    "¡Me alegra saberlo! ¿En qué te ayudo?",
                    "¡Qué bueno! ¿Necesitas buscar algo?"
                ],
                "despedida": [
                    "¡Hasta luego! Que tengas un excelente día.",
                    "¡Nos vemos! Siempre estaré aquí si me necesitas.",
                    "¡Adiós! Fue un placer ayudarte."
                ],
                "reirse_chiste": [
                    "¡Me alegra que te haya gustado! ¿Quieres que busquemos algo?",
                    "¡Jajaja! ¿Te ayudo con alguna búsqueda ahora?",
                    "¡Qué bueno que te divirtió! ¿En qué más puedo ayudarte?"
                ]
            }
            
            if current_intent in responses_fallback:
                message = choice(responses_fallback[current_intent])
                dispatcher.utter_message(text=message)
                logger.info(f"[SmallTalkSituacion] Respuesta fallback para {current_intent}")
            else:
                logger.warning(f"[SmallTalkSituacion] No se encontró response para '{current_intent}', usando fallback genérico")
                dispatcher.utter_message(text="¡Hola! ¿En qué puedo ayudarte?")
            
            return []
            
        except Exception as e:
            logger.error(f"[SmallTalkSituacion] ERROR CRÍTICO: {e}", exc_info=True)
            # Respuesta de emergencia mínima
            dispatcher.utter_message(text="¡Hola! ¿En qué puedo ayudarte?")
            return []


