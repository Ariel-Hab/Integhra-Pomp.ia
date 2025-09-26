import logging
from typing import Any, Dict, List
from datetime import datetime, timedelta
import re

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, EventType

# Import actualizado - usa el nuevo sistema
from actions.config import (
    config_manager,
    get_intent_config,
    get_lookup_tables,
    get_entities_for_intent,
    validate_entity_value,
    get_entity_suggestions
)
from ..conversation_state import ConversationState, SuggestionManager, create_smart_suggestion, get_improved_suggestions

# Import del nuevo detector de comparaciones
from .comparison_detector import ComparisonDetector

# ✅ NUEVO: Import de las funciones del helper para validación
from ..helpers import validate_entities_for_intent, validate_entity_detection

logger = logging.getLogger(__name__)

class ActionBusquedaSituacion(Action):
    """Action optimizada usando el nuevo sistema de configuración con mejor manejo de sugerencias ignoradas"""
    
    def __init__(self):
        # Inicializar el detector de comparaciones
        try:
            self.comparison_detector = ComparisonDetector()
            logger.info("[ActionBusquedaSituacion] Detector de comparaciones inicializado correctamente")
        except Exception as e:
            logger.error(f"[ActionBusquedaSituacion] Error inicializando detector de comparaciones: {e}")
            self.comparison_detector = None
    
    def name(self) -> str:
        return "action_busqueda_situacion"
    
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[str, Any]) -> List[EventType]:
        """Punto de entrada principal con manejo robusto de errores y limpieza automática de sugerencias ignoradas"""
        try:
            context = ConversationState.get_conversation_context(tracker)
            intent_name = context['current_intent']
            user_message = context.get('user_message', '')
            
            logger.info(f"[ActionBusquedaSituacion] Procesando intent: {intent_name}, mensaje: '{user_message[:100]}...'")
            
            events = []
            
            # 🆕 NUEVA FUNCIONALIDAD: Detectar y limpiar sugerencias ignoradas AL INICIO
            ignored_suggestion_cleanup = self._handle_ignored_suggestions(context, intent_name, dispatcher)
            events.extend(ignored_suggestion_cleanup['events'])
            
            # Si se detectó una sugerencia ignorada, actualizar el contexto
            if ignored_suggestion_cleanup['suggestion_was_ignored']:
                logger.info("[ActionBusquedaSituacion] Sugerencia ignorada detectada - contexto actualizado")
                # Actualizar el contexto para reflejar la limpieza
                context['pending_suggestion'] = None
                context['awaiting_suggestion_response'] = False
            
            # Validar que el intent existe en la configuración
            intent_config = get_intent_config()
            if intent_name not in intent_config.get("intents", {}):
                logger.warning(f"[ActionBusquedaSituacion] Intent desconocido: {intent_name}")
                dispatcher.utter_message("Lo siento, no pude entender tu solicitud.")
                return events  # Retornar eventos de limpieza si los hay
            
            # NUEVA FUNCIONALIDAD: Detectar comparaciones para enriquecer la búsqueda
            comparison_info = None
            if self._is_search_intent(intent_name):
                comparison_info = self._analyze_comparison_for_search(tracker)
                logger.debug(f"[ActionBusquedaSituacion] Información de comparación: {comparison_info}")
            
            # Actualizar sentimiento si cambió
            if context['detected_sentiment'] != context['current_sentiment_slot']:
                events.append(SlotSet("user_sentiment", context['detected_sentiment']))
                logger.debug(f"[ActionBusquedaSituacion] Actualizando sentimiento: {context['detected_sentiment']}")
            
            # Procesar según el tipo de intent
            if self._is_search_or_modify_intent(intent_name):
                result = self._handle_search_intent(context, tracker, dispatcher, comparison_info)
                logger.info(f"[ActionBusquedaSituacion] Intent de búsqueda/modificación procesado: {result.get('type', 'unknown')}")
            else:
                dispatcher.utter_message("¿En qué puedo ayudarte hoy?")
                logger.debug("[ActionBusquedaSituacion] Intent no clasificado, enviando saludo genérico")

            
            # Procesar resultado y generar eventos
            events.extend(self._process_result(result, context))
            logger.info(f"[ActionBusquedaSituacion] Procesamiento completado. Eventos generados: {len(events)}")
            
            return events
            
        except Exception as e:
            logger.error(f"[ActionBusquedaSituacion] Error crítico en run(): {e}", exc_info=True)
            try:
                dispatcher.utter_message("Ocurrió un error procesando tu solicitud. ¿Puedes intentar nuevamente?")
            except Exception as disp_error:
                logger.error(f"[ActionBusquedaSituacion] Error adicional enviando mensaje de error: {disp_error}")
            return []
    
    def _handle_ignored_suggestions(self, context: Dict[str, Any], current_intent: str, 
                                   dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """
        🆕 NUEVA FUNCIÓN CLAVE: Detecta y limpia sugerencias ignoradas automáticamente
        """
        try:
            pending_suggestion = context.get('pending_suggestion')
            if not pending_suggestion:
                return {'suggestion_was_ignored': False, 'events': []}
            
            # Verificar si el usuario ignoró la sugerencia
            suggestion_ignored = SuggestionManager.check_if_suggestion_ignored(
                current_intent, pending_suggestion, context.get('is_small_talk', False)
            )
            
            if suggestion_ignored:
                suggestion_type = pending_suggestion.get('suggestion_type', 'unknown')
                original_search_type = pending_suggestion.get('search_type', 'unknown')
                
                logger.info(f"[ActionBusquedaSituacion] Sugerencia ignorada detectada - Tipo: {suggestion_type}, Búsqueda original: {original_search_type}")
                
                # Determinar mensaje apropiado según el tipo de sugerencia ignorada
                if suggestion_type == 'entity_correction':
                    original_value = pending_suggestion.get('original_value', '')
                    entity_type = pending_suggestion.get('entity_type', '')
                    message = f"Entiendo que prefieres hacer una nueva búsqueda en lugar de corregir '{original_value}'. Te ayudo con tu nueva consulta."
                    
                elif suggestion_type == 'type_correction':
                    original_value = pending_suggestion.get('original_value', '')
                    message = f"Perfecto, te ayudo con esta nueva búsqueda en lugar de corregir '{original_value}'."
                    
                elif suggestion_type == 'missing_parameters':
                    message = f"Entiendo que quieres hacer una nueva búsqueda. Te ayudo con esta consulta."
                    
                else:
                    message = "Perfecto, te ayudo con tu nueva búsqueda."
                
                # Solo enviar mensaje si realmente cambió el tipo de búsqueda
                current_search_type = self._get_search_type(current_intent)
                if original_search_type != 'unknown' and current_search_type != original_search_type:
                    try:
                        dispatcher.utter_message(message)
                        logger.debug(f"[ActionBusquedaSituacion] Mensaje de cambio de búsqueda enviado")
                    except Exception as msg_error:
                        logger.error(f"[ActionBusquedaSituacion] Error enviando mensaje de cambio: {msg_error}")
                
                # Eventos de limpieza
                cleanup_events = [
                    SlotSet("pending_suggestion", None),
                    SlotSet("suggestion_context", None),
                    SlotSet("user_engagement_level", "engaged"),  # Usuario está activamente buscando
                ]
                
                logger.info("[ActionBusquedaSituacion] Sugerencia limpiada automáticamente - usuario cambió de tema")
                
                return {
                    'suggestion_was_ignored': True,
                    'events': cleanup_events,
                    'cleanup_reason': 'user_changed_search_type',
                    'original_suggestion_type': suggestion_type
                }
            
            # Si hay sugerencia pendiente pero no fue ignorada, verificar si la está siguiendo
            suggestion_followed = SuggestionManager.check_if_suggestion_followed(current_intent, pending_suggestion)
            
            if suggestion_followed:
                logger.debug("[ActionBusquedaSituacion] Usuario está siguiendo la sugerencia pendiente")
                return {
                    'suggestion_was_ignored': False, 
                    'events': [],
                    'suggestion_being_followed': True
                }
            
            # Sugerencia aún pendiente, no ignorada ni seguida claramente
            logger.debug("[ActionBusquedaSituacion] Sugerencia aún pendiente, no hay acción de limpieza")
            return {'suggestion_was_ignored': False, 'events': []}
            
        except Exception as e:
            logger.error(f"[ActionBusquedaSituacion] Error manejando sugerencias ignoradas: {e}", exc_info=True)
            # En caso de error, limpiar sugerencias para evitar estados inconsistentes
            return {
                'suggestion_was_ignored': True,
                'events': [SlotSet("pending_suggestion", None)],
                'cleanup_reason': 'error_recovery'
            }
    
    def _analyze_comparison_for_search(self, tracker: Tracker) -> Dict[str, Any]:
        """
        Analiza comparaciones para enriquecer la búsqueda
        """
        try:
            # Verificar que el detector esté disponible
            if not self.comparison_detector:
                logger.warning("[ActionBusquedaSituacion] Detector de comparaciones no disponible")
                return {}
            
            # Obtener texto del mensaje y entidades
            text = tracker.latest_message.get("text", "")
            entities = tracker.latest_message.get("entities", [])
            
            if not text:
                logger.debug("[ActionBusquedaSituacion] No hay texto para analizar comparación")
                return {}
            
            logger.debug(f"[ActionBusquedaSituacion] Analizando comparación en: '{text[:100]}...' con {len(entities)} entidades")
            
            # Ejecutar detección de comparación
            comparison_result = self.comparison_detector.detect_comparison(text, entities)
            
            if not comparison_result.detected:
                logger.debug("[ActionBusquedaSituacion] No se detectaron comparaciones")
                return {}
            
            # Extraer información relevante para la búsqueda
            comparison_info = {
                'detected': True,
                'operator': comparison_result.operator.value if comparison_result.operator else None,
                'quantity': comparison_result.quantity,
                'type': comparison_result.comparison_type.value if comparison_result.comparison_type else None,
                'entities': comparison_result.entities,
                'groups': comparison_result.groups_detected,
                'roles': comparison_result.roles_detected,
                'confidence': comparison_result.confidence,
                'temporal_filters': comparison_result.temporal_filters,
                'normalized_dates': comparison_result.normalized_dates
            }
            
            logger.info(f"[ActionBusquedaSituacion] Comparación detectada exitosamente: {comparison_result.comparison_type.value if comparison_result.comparison_type else 'None'} con confianza {comparison_result.confidence:.2f}")
            
            return comparison_info
            
        except Exception as e:
            logger.error(f"[ActionBusquedaSituacion] Error en análisis de comparaciones: {e}", exc_info=True)
            return {}
    
    def _extract_temporal_filters(self, text: str, comparison_info: Dict[str, Any] = None) -> Dict[str, Any]:
        """Extrae filtros temporales del texto"""
        try:
            temporal_filters = {}
            text_lower = text.lower()
            
            logger.debug(f"[ActionBusquedaSituacion] Extrayendo filtros temporales de: '{text[:100]}...'")
            
            # Si ya hay filtros temporales de comparación, usarlos como base
            if comparison_info and comparison_info.get('temporal_filters'):
                temporal_filters.update(comparison_info['temporal_filters'])
                logger.debug(f"[ActionBusquedaSituacion] Usando filtros temporales de comparación: {temporal_filters}")
            
            # Detectar términos temporales adicionales
            now = datetime.now()
            
            # Detectar "recientes" si no está en comparación
            if not temporal_filters and any(word in text_lower for word in ["reciente", "nuevo", "últimos"]):
                temporal_filters["date_from"] = (now - timedelta(weeks=2)).strftime("%Y-%m-%d")
                temporal_filters["date_to"] = now.strftime("%Y-%m-%d")
                temporal_filters["period"] = "recent"
                logger.debug("[ActionBusquedaSituacion] Filtro temporal 'recientes' aplicado")
            
            # Detectar "vigentes" o "válidos"
            if any(word in text_lower for word in ["vigente", "válido", "activo"]):
                if not temporal_filters.get("date_from"):
                    temporal_filters["date_from"] = now.strftime("%Y-%m-%d")
                temporal_filters["status"] = "active"
                logger.debug("[ActionBusquedaSituacion] Filtro temporal 'vigentes' aplicado")
            
            # Detectar "que vencen pronto"
            if any(phrase in text_lower for phrase in ["que vencen", "próximos a vencer", "por vencer"]):
                temporal_filters["date_to"] = (now + timedelta(days=30)).strftime("%Y-%m-%d")
                temporal_filters["status"] = "expiring_soon"
                logger.debug("[ActionBusquedaSituacion] Filtro temporal 'que vencen pronto' aplicado")
            
            if temporal_filters:
                logger.info(f"[ActionBusquedaSituacion] Filtros temporales extraídos: {temporal_filters}")
            else:
                logger.debug("[ActionBusquedaSituacion] No se encontraron filtros temporales")
            
            return temporal_filters
            
        except Exception as e:
            logger.error(f"[ActionBusquedaSituacion] Error extrayendo filtros temporales: {e}", exc_info=True)
            return {}
    
    def _format_temporal_description(self, temporal_filters: Dict[str, Any]) -> str:
        """Formatea descripción legible de filtros temporales"""
        try:
            if not temporal_filters:
                return ""
            
            descriptions = []
            
            if temporal_filters.get("period"):
                period_descriptions = {
                    "current_week": "de esta semana",
                    "current_month": "de este mes",
                    "recent": "recientes",
                    "current_and_future": "vigentes"
                }
                period = temporal_filters["period"]
                if period in period_descriptions:
                    descriptions.append(period_descriptions[period])
            
            if temporal_filters.get("date_from") and temporal_filters.get("date_to"):
                if temporal_filters["date_from"] == temporal_filters["date_to"]:
                    descriptions.append(f"del {temporal_filters['date_from']}")
                else:
                    descriptions.append(f"desde {temporal_filters['date_from']} hasta {temporal_filters['date_to']}")
            elif temporal_filters.get("date_from"):
                descriptions.append(f"desde {temporal_filters['date_from']}")
            elif temporal_filters.get("date_to"):
                descriptions.append(f"hasta {temporal_filters['date_to']}")
            
            if temporal_filters.get("status") == "expiring_soon":
                descriptions.append("que vencen pronto")
            elif temporal_filters.get("status") == "active":
                descriptions.append("activos")
            
            result = " ".join(descriptions) if descriptions else ""
            logger.debug(f"[ActionBusquedaSituacion] Descripción temporal formateada: '{result}'")
            return result
            
        except Exception as e:
            logger.error(f"[ActionBusquedaSituacion] Error formateando descripción temporal: {e}")
            return ""
    
    def _is_search_intent(self, intent_name: str) -> bool:
        """Determina si es un intent de búsqueda"""
        search_intents = ['buscar_producto', 'buscar_oferta', 'consultar_novedades_producto', 
                         'consultar_novedades_oferta', 'consultar_recomendaciones_producto',
                         'consultar_recomendaciones_oferta']
        return intent_name in search_intents
    
    def _is_search_or_modify_intent(self, intent_name: str) -> bool:
        """Determina si es un intent de búsqueda o modificación"""
        search_intents = ['buscar_producto', 'buscar_oferta', 'consultar_novedades_producto', 
                        'consultar_novedades_oferta', 'consultar_recomendaciones_producto',
                        'consultar_recomendaciones_oferta', 'modificar_busqueda']
        return intent_name in search_intents
    # def _is_completion_intent(self, intent_name: str) -> bool:
    #     """Determina si es un intent de completar pedido"""
    #     return intent_name == 'completar_pedido'
    

    def _extract_search_parameters_from_entities(self, tracker: Tracker) -> Dict[str, Any]:
        """
        ✅ Extrae parámetros validando contra lookup tables.
        Para 'empresa' y 'dosis' incluye también el role detectado.
        """
        try:
            search_params = {}
            
            # Obtener entidades del mensaje actual solamente
            current_entities = tracker.latest_message.get("entities", [])
            
            if not current_entities:
                logger.debug("[EntityParams] No hay entidades en el mensaje actual")
                return {}
            
            logger.info(f"[EntityParams] === VALIDANDO {len(current_entities)} ENTIDADES CONTRA LOOKUP TABLES ===")
            
            # Mapeo de entidades a parámetros de búsqueda
            entity_to_param = {
                'producto': 'nombre',
                'empresa': 'empresa',
                'categoria': 'categoria',
                'animal': 'animal',
                'sintoma': 'sintoma',
                'dosis': 'dosis',
                'estado': 'estado',
                'cantidad': 'cantidad',
                'precio': 'precio',
                'descuento': 'descuento',
                'bonificacion': 'bonificacion',
                'stock': 'stock',
                'tiempo': 'tiempo',
                'fecha': 'fecha'
            }
            
            # ✅ VALIDAR cada entidad antes de incluirla en search_params
            for i, entity in enumerate(current_entities):
                entity_type = entity.get("entity")
                entity_value = entity.get("value", "").strip()
                entity_confidence = entity.get("confidence", 0.0)
                
                if not entity_type or not entity_value:
                    continue
                    
                if entity_type not in entity_to_param:
                    logger.debug(f"[EntityParams] [{i+1}] Tipo de entidad '{entity_type}' no mapeado, ignorando")
                    continue
                
                param_name = entity_to_param[entity_type]
                
                logger.info(f"[EntityParams] [{i+1}] Validando {entity_type}='{entity_value}' (conf: {entity_confidence:.2f})")
                
                from ..helpers import validate_entity_detection
                validation_result = validate_entity_detection(
                    entity_type=entity_type,
                    entity_value=entity_value,
                    min_length=2,
                    check_fragments=True
                )
                
                if validation_result.get("valid"):
                    normalized_value = validation_result.get("normalized", entity_value)
                    
                    # 🔹 Si es empresa o dosis → guardamos value + role
                    if entity_type in ["empresa", "dosis"]:
                        search_params[param_name] = {
                            "value": normalized_value,
                            "role": entity.get("role") or "unspecified"
                        }
                    else:
                        search_params[param_name] = normalized_value
                    
                    logger.info(f"[EntityParams] ✅ [{i+1}] {entity_type}='{entity_value}' -> {param_name}='{normalized_value}' VÁLIDO")
                    
                else:
                    reason = validation_result.get("reason", "unknown")
                    suggestions = validation_result.get("suggestions", [])
                    
                    logger.warning(f"[EntityParams] ❌ [{i+1}] {entity_type}='{entity_value}' RECHAZADO ({reason})")
                    
                    if suggestions:
                        logger.info(f"[EntityParams] 💡 [{i+1}] Sugerencias disponibles: {suggestions[:3]}")
                    else:
                        logger.info(f"[EntityParams] 🚫 [{i+1}] No hay sugerencias para '{entity_value}'")
            
            logger.info(f"[EntityParams] === RESULTADO: {len(search_params)} parámetros válidos de {len(current_entities)} entidades ===")
            
            if search_params:
                for param, value in search_params.items():
                    logger.info(f"[EntityParams]   ✅ {param}: '{value}'")
            else:
                logger.warning("[EntityParams]   ❌ Ninguna entidad pasó la validación")
            
            return search_params
            
        except Exception as e:
            logger.error(f"[EntityParams] Error crítico extrayendo parámetros validados: {e}", exc_info=True)
            return {}


    def _extract_previous_search_parameters(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        ✅ CORREGIDO: Extrae parámetros de búsqueda anterior con información de tipo
        """
        try:
            search_history = context.get('search_history', [])
            
            if not search_history:
                logger.debug("[PrevParams] No hay historial de búsquedas")
                return {}
            
            # Obtener la búsqueda más reciente
            latest_search = search_history[-1]
            previous_params = latest_search.get('parameters', {})
            search_type = latest_search.get('type', 'producto')
            
            # ✅ NUEVA FUNCIONALIDAD: Incluir información del tipo de búsqueda
            enriched_params = previous_params.copy()
            enriched_params['_previous_search_type'] = search_type  # Metadata interna
            enriched_params['_previous_timestamp'] = latest_search.get('timestamp')
            
            if previous_params:
                logger.info(f"[PrevParams] Extraídos {len(previous_params)} parámetros de búsqueda anterior ({search_type}): {list(previous_params.keys())}")
            else:
                logger.debug("[PrevParams] Búsqueda anterior sin parámetros")
            
            return enriched_params
            
        except Exception as e:
            logger.error(f"[PrevParams] Error extrayendo parámetros anteriores: {e}")
            return {}
    def _generate_slot_cleanup_events(self, tracker: Tracker, intent_name: str = None) -> List[EventType]:
        """
        ✅ CORREGIDO: Limpieza inteligente que preserva contexto para modificar_busqueda
        """
        try:
            cleanup_events = []
            
            # Obtener entidades del mensaje actual
            current_entities = tracker.latest_message.get("entities", [])
            current_entity_types = {entity.get("entity") for entity in current_entities if entity.get("entity")}
            
            # Lista de slots de búsqueda
            search_slots = [
                'producto', 'empresa', 'categoria', 'animal', 'sintoma', 'dosis',
                'estado', 'cantidad', 'precio', 'descuento', 'bonificacion', 
                'stock', 'tiempo', 'fecha'
            ]
            
            # ✅ NUEVA LÓGICA: Para modificar_busqueda, SER MUY CONSERVADOR
            if intent_name == 'modificar_busqueda':
                logger.info("[SlotCleanup] Modo conservador para modificar_busqueda - solo limpiar slots explícitamente reemplazados")
                
                # Solo limpiar slots que tienen entidades correspondientes en el mensaje actual
                # (esto significa que el usuario quiere cambiar específicamente esos valores)
                slots_to_replace = []
                for slot_name in search_slots:
                    current_slot_value = tracker.get_slot(slot_name)
                    
                    # Si hay entidad correspondiente en el mensaje actual, será reemplazada
                    if current_slot_value and slot_name in current_entity_types:
                        # No limpiamos aquí, el sistema de extracción de slots lo actualizará
                        logger.debug(f"[SlotCleanup] '{slot_name}' será reemplazado por nueva entidad")
                        # No agregar cleanup_events - dejar que el valor se actualice naturalmente
                
                logger.info(f"[SlotCleanup] Modo conservador: manteniendo contexto existente para modificar_busqueda")
                
            else:
                # ✅ LÓGICA ORIGINAL: Para búsquedas nuevas, limpiar slots no utilizados
                slots_cleaned = []
                for slot_name in search_slots:
                    current_slot_value = tracker.get_slot(slot_name)
                    
                    # Si el slot tiene valor pero no hay entidad correspondiente en el mensaje actual
                    if current_slot_value and slot_name not in current_entity_types:
                        cleanup_events.append(SlotSet(slot_name, None))
                        slots_cleaned.append(slot_name)
                        logger.debug(f"[SlotCleanup] Limpiando slot '{slot_name}': '{current_slot_value}'")
                
                if slots_cleaned:
                    logger.info(f"[SlotCleanup] Limpiados {len(slots_cleaned)} slots de búsquedas anteriores: {slots_cleaned}")
                else:
                    logger.debug("[SlotCleanup] No se requiere limpieza de slots")
            
            return cleanup_events
            
        except Exception as e:
            logger.error(f"[SlotCleanup] Error generando eventos de limpieza: {e}")
            return []

    # ====================================================================
    # CAMBIO 3: Modificar _handle_search_intent() - Solo la sección que cambia
    # ====================================================================
    def _handle_modify_search_intent(self, context: Dict[str, Any], tracker: Tracker, 
                                dispatcher: CollectingDispatcher, search_type: str,
                                comparison_info: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        ✅ NUEVO MÉTODO: Maneja modificar_busqueda preservando contexto inteligentemente
        """
        try:
            user_message = context.get('user_message', '')
            
            logger.info(f"[ModifySearch] Procesando modificación de búsqueda (tipo inferido: {search_type})")
            
            # ✅ PASO 1: Extraer parámetros nuevos del mensaje actual
            current_params = self._extract_search_parameters_from_entities(tracker)
            
            # ✅ PASO 2: Obtener parámetros de la búsqueda anterior
            previous_params = self._extract_previous_search_parameters(context)
            
            # ✅ PASO 3: Combinar parámetros inteligentemente
            # Estrategia: previous_params como base + current_params como override
            combined_params = {}
            
            # Empezar con parámetros anteriores (excluyendo metadata interna)
            for key, value in previous_params.items():
                if not key.startswith('_'):  # Excluir metadata como _previous_search_type
                    combined_params[key] = value
            
            # Sobrescribir con parámetros actuales (cambios específicos del usuario)
            combined_params.update(current_params)
            
            # ✅ PASO 4: Log detallado del proceso de combinación
            logger.info(f"[ModifySearch] Combinación de parámetros:")
            logger.info(f"[ModifySearch]   Anteriores: {len(previous_params)} → {[k for k in previous_params.keys() if not k.startswith('_')]}")
            logger.info(f"[ModifySearch]   Nuevos: {len(current_params)} → {list(current_params.keys())}")
            logger.info(f"[ModifySearch]   Combinados: {len(combined_params)} → {list(combined_params.keys())}")
            
            # ✅ PASO 5: Validar que tenemos parámetros válidos
            if not combined_params:
                logger.warning("[ModifySearch] Sin parámetros combinados válidos")
                dispatcher.utter_message("No pude determinar qué modificar en tu búsqueda. ¿Puedes ser más específico?")
                return {'type': 'modify_error', 'reason': 'no_combined_parameters'}
            
            # ✅ PASO 6: Ejecutar búsqueda modificada
            temporal_filters = self._extract_temporal_filters(user_message, comparison_info)
            
            logger.info(f"[ModifySearch] Ejecutando búsqueda modificada de {search_type}")
            result = self._execute_search(search_type, combined_params, dispatcher, comparison_info, temporal_filters)
            
            # ✅ PASO 7: Marcar resultado como modificación
            result['modification_applied'] = True
            result['previous_params'] = {k: v for k, v in previous_params.items() if not k.startswith('_')}
            result['new_params'] = current_params
            result['combined_params'] = combined_params
            
            return result
            
        except Exception as e:
            logger.error(f"[ModifySearch] Error procesando modificación: {e}", exc_info=True)
            dispatcher.utter_message("Hubo un error modificando tu búsqueda. ¿Puedes intentar de nuevo?")
            return {'type': 'modify_error', 'error': str(e)}
    
    def _handle_search_intent(self, context: Dict[str, Any], tracker: Tracker, 
                         dispatcher: CollectingDispatcher, comparison_info: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        ✅ CORREGIDO: Manejo inteligente de modificar_busqueda con preservación de contexto
        """
        try:
            intent_name = context['current_intent']
            user_message = context.get('user_message', '')
            
            logger.info(f"[ActionBusquedaSituacion] Manejando intent: {intent_name}")
            
            # ✅ PASO 1: Determinar tipo de búsqueda con contexto inteligente
            search_type = self._get_search_type(intent_name, context)
            
            # ✅ PASO 2: Manejo especial para modificar_busqueda
            if intent_name == 'modificar_busqueda':
                return self._handle_modify_search_intent(context, tracker, dispatcher, search_type, comparison_info)
            
            # ✅ PASO 3: Manejo normal para otros intents (lógica existente)
            # Limpiar slots de búsquedas anteriores (con limpieza inteligente)
            slot_cleanup_events = self._generate_slot_cleanup_events(tracker, intent_name)
            search_params = self._extract_search_parameters_from_entities(tracker)
            
            # Resto de la lógica existente...
            if search_params:
                temporal_filters = self._extract_temporal_filters(user_message, comparison_info)
                
                logger.info(f"[ActionBusquedaSituacion] Ejecutando búsqueda de {search_type} con parámetros: {search_params}")
                result = self._execute_search(search_type, search_params, dispatcher, comparison_info, temporal_filters)
                result['slot_cleanup_events'] = slot_cleanup_events
                return result
            else:
                # Validación con helper...
                valid_entities = get_entities_for_intent(intent_name)
                if not valid_entities:
                    logger.warning(f"[ActionBusquedaSituacion] No hay entidades configuradas para intent: {intent_name}")
                    dispatcher.utter_message("Lo siento, hay un problema con la configuración de búsqueda.")
                    return {'type': 'configuration_error', 'slot_cleanup_events': slot_cleanup_events}
                
                validation_result = self._validate_entities_with_helper(tracker, intent_name, dispatcher)
                # ... resto de la lógica de validación existente
                
        except Exception as e:
            logger.error(f"[ActionBusquedaSituacion] Error manejando intent de búsqueda: {e}", exc_info=True)
            dispatcher.utter_message("Ocurrió un error procesando tu búsqueda.")
            return {'type': 'search_error', 'error': str(e)}

    
    def _validate_entities_with_helper(self, tracker: Tracker, intent_name: str, dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Valida entidades priorizando las de mayor confianza"""
        try:
            entities = tracker.latest_message.get("entities", [])
            
            # Ordenar entidades por confianza descendente
            entities_with_confidence = []
            for entity in entities:
                confidence = entity.get("confidence_entity", entity.get("confidence", 0.0))
                entities_with_confidence.append({
                    **entity,
                    "confidence_score": confidence
                })
            
            entities_sorted = sorted(entities_with_confidence, key=lambda x: x["confidence_score"], reverse=True)
            
            logger.debug(f"[ActionBusquedaSituacion] Validando {len(entities_sorted)} entidades ordenadas por confianza para intent: {intent_name}")
            
            # ✅ CORREGIDO: Usar validación menos restrictiva para términos médicos
            # Reducir min_length para permitir unidades médicas como "mg", "ml"
            helper_result = validate_entities_for_intent(entities_sorted, intent_name, min_length=2, check_fragments=True)
            
            logger.debug(f"[ActionBusquedaSituacion] Resultado del helper: {helper_result}")
            
            # Aplicar validación cruzada a entidades con errores (priorizando por confianza)
            enhanced_suggestions = []
            cross_entity_suggestions = []
            
            if helper_result['has_suggestions']:
                for suggestion_item in helper_result['suggestions']:
                    try:
                        entity_type = suggestion_item.get('entity_type')
                        raw_value = suggestion_item.get('raw_value')
                        suggestions_list = suggestion_item.get('suggestions', [])
                        
                        # Encontrar la confianza de esta entidad específica
                        original_confidence = 0.0
                        for original_ent in entities_sorted:
                            if original_ent.get('value') == raw_value and original_ent.get('entity') == entity_type:
                                original_confidence = original_ent['confidence_score']
                                break
                        
                        if suggestions_list:
                            # Usar sugerencia normal del helper
                            suggestion_text = suggestions_list[0]
                            message = f"'{raw_value}' no es válido. ¿Te refieres a '{suggestion_text}'? (confianza original: {original_confidence:.2f})"
                            
                            suggestion_data = SuggestionManager.create_entity_suggestion(
                                raw_value, entity_type, suggestion_text, 
                                {
                                    'intent': tracker.get_intent_of_latest_message(),
                                    'original_confidence': original_confidence
                                }
                            )
                            enhanced_suggestions.append(suggestion_data)
                            dispatcher.utter_message(message)
                            logger.info(f"[ActionBusquedaSituacion] Sugerencia normal enviada para '{raw_value}': '{suggestion_text}' (conf: {original_confidence:.2f})")
                        
                        else:
                            # Si no hay sugerencias normales, aplicar validación cruzada
                            logger.info(f"[ActionBusquedaSituacion] No hay sugerencias normales para '{raw_value}' (conf: {original_confidence:.2f}), aplicando validación cruzada...")
                            
                            cross_matches = self.validate_and_suggest_entities(raw_value, entity_type)
                            
                            if cross_matches:
                                cross_message = self.format_cross_entity_suggestions(cross_matches)
                                dispatcher.utter_message(f"'{raw_value}' no es válido como {entity_type}. {cross_message} (confianza original: {original_confidence:.2f})")
                                
                                best_match = cross_matches[0]
                                cross_suggestion_data = SuggestionManager.create_entity_suggestion(
                                    raw_value, best_match['entity_type'], best_match['suggestion'],
                                    {
                                        'intent': tracker.get_intent_of_latest_message(), 
                                        'cross_entity': True,
                                        'original_confidence': original_confidence,
                                        'cross_similarity': best_match.get('similarity', 0.0)
                                    }
                                )
                                cross_entity_suggestions.append(cross_suggestion_data)
                                
                                logger.info(f"[ActionBusquedaSituacion] Sugerencia cruzada enviada: '{raw_value}' -> '{best_match['suggestion']}' ({best_match['entity_type']}) conf: {original_confidence:.2f}")
                            else:
                                dispatcher.utter_message(f"'{raw_value}' no es válido como {entity_type}. (confianza: {original_confidence:.2f})")
                                logger.warning(f"[ActionBusquedaSituacion] Sin sugerencias para '{raw_value}' conf: {original_confidence:.2f}")
                            
                    except Exception as suggestion_error:
                        logger.error(f"[ActionBusquedaSituacion] Error procesando sugerencia individual: {suggestion_error}")
                        continue
            
            # Combinar sugerencias y ordenar por confianza
            all_suggestions = enhanced_suggestions + cross_entity_suggestions
            all_suggestions.sort(key=lambda x: (
                -x.get('metadata', {}).get('original_confidence', 0.0),
                -x.get('metadata', {}).get('cross_similarity', 0.0)
            ))
            
            # Adaptar resultado del helper al formato esperado
            adapted_result = {
                'valid_params': helper_result['valid_params'],
                'has_suggestions': len(all_suggestions) > 0,
                'suggestion_data': all_suggestions[0] if all_suggestions else None,
                'has_errors': helper_result['has_errors'] and len(all_suggestions) == 0,
                'errors': helper_result['errors'] if len(all_suggestions) == 0 else [],
                'confidence_info': {
                    'total_entities': len(entities),
                    'highest_confidence': entities_sorted[0]['confidence_score'] if entities_sorted else 0.0,
                    'lowest_confidence': entities_sorted[-1]['confidence_score'] if entities_sorted else 0.0,
                    'average_confidence': sum(e['confidence_score'] for e in entities_sorted) / len(entities_sorted) if entities_sorted else 0.0
                }
            }
            
            logger.info(f"[ActionBusquedaSituacion] Validación completada con priorización por confianza: {len(helper_result['valid_params'])} válidos, {len(all_suggestions)} sugerencias totales")
            
            return adapted_result
            
        except Exception as e:
            logger.error(f"[ActionBusquedaSituacion] Error crítico en validación con helper: {e}", exc_info=True)
            return {
                'valid_params': {},
                'has_suggestions': False,
                'suggestion_data': None,
                'has_errors': True,
                'errors': ["Error interno validando entidades con helper"],
                'confidence_info': {'total_entities': 0, 'highest_confidence': 0.0, 'lowest_confidence': 0.0, 'average_confidence': 0.0}
            }



    def validate_and_suggest_entities(self, invalid_value: str, original_entity_type: str) -> List[Dict[str, Any]]:
        """
        ✅ VERSIÓN MEJORADA: Usa el sistema avanzado de similitud
        """
        try:
            logger.debug(f"[ActionBusquedaSituacion] Validación mejorada para '{invalid_value}' (tipo: {original_entity_type})")
 
            
            # Usar el sistema avanzado de similitud
            suggestions = get_improved_suggestions(
                invalid_value, 
                original_entity_type, 
                max_suggestions=5  # Más sugerencias para mejor selección
            )
            
            if not suggestions:
                logger.debug(f"[ActionBusquedaSituacion] No se encontraron sugerencias mejoradas para '{invalid_value}'")
                return []
            
            # Convertir al formato esperado por el resto del código
            formatted_suggestions = []
            for suggestion in suggestions:
                formatted_suggestions.append({
                    'entity_type': suggestion['entity_type'],
                    'suggestion': suggestion['suggestion'],
                    'similarity': suggestion['similarity'],
                    'original_value': suggestion['original_input'],
                    'match_confidence': suggestion['match_confidence'],
                    'priority': 1,  # Alta prioridad para todas las sugerencias mejoradas
                    'match_type': 'advanced_similarity',
                    'metadata': suggestion.get('metadata', {})
                })
            
            # Ordenar por similitud (ya viene ordenado, pero por seguridad)
            formatted_suggestions.sort(key=lambda x: x['similarity'], reverse=True)
            
            logger.info(f"[ActionBusquedaSituacion] Sistema mejorado encontró {len(formatted_suggestions)} sugerencias para '{invalid_value}'")
            for i, sug in enumerate(formatted_suggestions[:3]):
                logger.info(f"  {i+1}. {sug['suggestion']} (sim: {sug['similarity']:.3f}, conf: {sug['match_confidence']})")
            
            return formatted_suggestions
            
        except ImportError:
            logger.warning("[ActionBusquedaSituacion] Sistema mejorado no disponible, usando fallback")
            return self._fallback_validation_and_suggest(invalid_value, original_entity_type)
        except Exception as e:
            logger.error(f"[ActionBusquedaSituacion] Error en validación mejorada: {e}", exc_info=True)
            return self._fallback_validation_and_suggest(invalid_value, original_entity_type)

    def _fallback_validation_and_suggest(self, invalid_value: str, original_entity_type: str) -> List[Dict[str, Any]]:
        """Método de fallback si el sistema mejorado falla"""
        try:
            # Tu código original como fallback
            from actions.config import get_lookup_tables
            import difflib
            
            all_lookups = get_lookup_tables()
            if not all_lookups or original_entity_type not in all_lookups:
                return []
            
            lookup_values = all_lookups[original_entity_type]
            suggestions = difflib.get_close_matches(invalid_value, lookup_values, n=3, cutoff=0.6)
            
            return [
                {
                    'entity_type': original_entity_type,
                    'suggestion': suggestion,
                    'similarity': 0.7,  # Score estimado
                    'original_value': invalid_value,
                    'match_confidence': 'medium',
                    'priority': 2,
                    'match_type': 'basic_difflib'
                }
                for suggestion in suggestions
            ]
            
        except Exception as e:
            logger.error(f"[ActionBusquedaSituacion] Error en fallback: {e}")
            return []

   

    def _create_basic_suggestion(self, raw_value: str, entity_type: str, suggestion: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Crea sugerencia básica cuando el sistema mejorado no está disponible"""
        return {
            'suggestion_type': 'entity_correction',
            'original_value': raw_value,
            'entity_type': entity_type,
            'suggestions': [suggestion],
            'metadata': {
                'similarity_scores': [0.7],  # Score estimado
                'match_confidences': ['medium'],
                'search_method': 'basic_fallback'
            },
            'timestamp': datetime.now().isoformat(),
            'search_context': context,
            'awaiting_response': True,
            'version': '1.5',  # Híbrido básico-mejorado
            'clarification_attempts': 0,
            'created_at': datetime.now().timestamp()
        }

    def format_cross_entity_suggestions(self, matches: List[Dict[str, Any]]) -> str:
        """Formatea sugerencias priorizando correcciones de spelling"""
        try:
            if not matches:
                return "No se encontraron sugerencias alternativas."
            
            # Separar por tipo de match
            spelling_matches = [m for m in matches if m.get('match_type') == 'spelling']
            cross_entity_matches = [m for m in matches if m.get('match_type') == 'cross_entity']
            
            if spelling_matches:
                best_spelling = spelling_matches[0]
                return f"¿Te refieres a '{best_spelling['suggestion']}'? (corrección de ortografía)"
            
            elif len(cross_entity_matches) == 1:
                match = cross_entity_matches[0]
                entity_display = self._get_entity_display_name(match['entity_type'])
                return f"¿Te refieres a '{match['suggestion']}' como {entity_display}?"
            
            elif cross_entity_matches:
                suggestions = []
                for match in cross_entity_matches[:3]:
                    entity_display = self._get_entity_display_name(match['entity_type'])
                    suggestions.append(f"'{match['suggestion']}' ({entity_display})")
                
                if len(suggestions) == 2:
                    return f"¿Te refieres a {suggestions[0]} o {suggestions[1]}?"
                else:
                    return f"¿Te refieres a {', '.join(suggestions[:-1])} o {suggestions[-1]}?"
            
            return "¿Podrías intentar con otro término?"
                    
        except Exception as e:
            logger.error(f"[ActionBusquedaSituacion] Error formateando sugerencias cruzadas: {e}")
            return "¿Podrías intentar con otro término?"

    def _get_entity_display_name(self, entity_type: str) -> str:
        """Convierte nombres técnicos de entidades a nombres legibles"""
        display_names = {
            'categoria': 'categoría',
            'empresa': 'empresa', 
            'ingrediente_activo': 'ingrediente activo',
            'animal': 'animal',
            'producto': 'producto',
            'accion_terapeutica': 'acción terapéutica'
        }
        return display_names.get(entity_type, entity_type)
    def _execute_search(self, search_type: str, parameters: Dict[str, str], dispatcher: CollectingDispatcher, 
                       comparison_info: Dict[str, Any] = None, temporal_filters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Ejecuta búsqueda con parámetros validados"""
        
        try:
            logger.info(f"[ActionBusquedaSituacion] Ejecutando búsqueda de {search_type} con {len(parameters)} parámetros")
            
            # Construir mensaje básico
            if parameters:
                criteria_text = ", ".join([f"{k}: {v}" for k, v in parameters.items()])
                base_message = f"Buscando {search_type}s con {criteria_text}"
            else:
                base_message = f"Mostrando {search_type}s disponibles"
            
            # Enriquecer mensaje con información de comparación
            enriched_message = self._enrich_message_with_comparison(base_message, parameters, comparison_info)
            
            # Enriquecer mensaje con filtros temporales
            if temporal_filters:
                temporal_description = self._format_temporal_description(temporal_filters)
                if temporal_description:
                    enriched_message += f" {temporal_description}"
            
            logger.debug(f"[ActionBusquedaSituacion] Mensaje enriquecido: '{enriched_message}'")
            
            # Preparar JSON message
            json_message = {
                "type": "search_results",
                "search_type": search_type,
                "parameters": parameters,
                "validated": True,
                "timestamp": datetime.now().isoformat()
            }
            
            # Agregar información de comparación al JSON si está disponible
            if comparison_info and comparison_info.get('detected'):
                # ✅ CORREGIDO: Convertir objetos complejos a diccionarios serializables
                serializable_entities = []
                for entity in comparison_info.get('entities', []):
                    if hasattr(entity, 'entity_type'):  # Es un objeto ComparisonEntity
                        serializable_entities.append({
                            "type": entity.entity_type,
                            "value": entity.entity_value,
                            "role": entity.role if hasattr(entity, 'role') else None
                        })
                    elif isinstance(entity, dict):  # Ya es un diccionario
                        serializable_entities.append(entity)
                    else:  # Convertir a string por seguridad
                        serializable_entities.append(str(entity))
                
                json_message["comparison_analysis"] = {
                    "detected": True,
                    "operator": comparison_info.get('operator'),
                    "quantity": comparison_info.get('quantity'),
                    "type": comparison_info.get('type'),
                    "confidence": comparison_info.get('confidence', 0.0),
                    "entities": serializable_entities,
                    "groups": comparison_info.get('groups', []),
                    "usage": self._determine_quantity_usage(parameters, comparison_info)
                }
            
            # Agregar filtros temporales al JSON
            if temporal_filters:
                json_message["comparative_dates"] = {
                    "filters": temporal_filters,
                    "description": self._format_temporal_description(temporal_filters)
                }
            
            # Enviar respuesta estructurada
            dispatcher.utter_message(
                text=enriched_message,
                json_message=json_message
            )
            
            logger.info(f"[ActionBusquedaSituacion] Respuesta de búsqueda enviada exitosamente")
            
            return {
                'type': 'search_success',
                'search_type': search_type,
                'parameters': parameters,
                'message': enriched_message,
                'comparison_info': comparison_info,
                'temporal_filters': temporal_filters
            }
            
        except Exception as e:
            logger.error(f"[ActionBusquedaSituacion] Error ejecutando búsqueda: {e}", exc_info=True)
            dispatcher.utter_message("Ocurrió un error ejecutando la búsqueda. ¿Puedes intentar con otros términos?")
            return {'type': 'search_execution_error', 'error': str(e)}
    
    def _enrich_message_with_comparison(self, base_message: str, parameters: Dict[str, str], comparison_info: Dict[str, Any]) -> str:
        """Enriquece el mensaje con información de comparación"""
        try:
            if not comparison_info or not comparison_info.get('detected'):
                return base_message
            
            operator = comparison_info.get('operator')
            quantity = comparison_info.get('quantity')
            
            if operator and quantity:
                operator_text = self._get_operator_text(operator)
                comparison_detail = f" (buscando {operator_text} {quantity})"
            else:
                comparison_type = comparison_info.get('type', '')
                if comparison_type:
                    comparison_detail = f" (con filtros de {comparison_type})"
                else:
                    comparison_detail = " (con comparación aplicada)"
            
            result = base_message + comparison_detail
            logger.debug(f"[ActionBusquedaSituacion] Mensaje enriquecido con comparación: '{result}'")
            return result
            
        except Exception as e:
            logger.error(f"[ActionBusquedaSituacion] Error enriqueciendo mensaje con comparación: {e}")
            return base_message
    
    def _get_operator_text(self, operator: str) -> str:
        """Convierte el operador a texto legible"""
        operator_mapping = {
            'greater_than': 'más de',
            'less_than': 'menos de',
            'equal_to': 'igual a',
            'different_from': 'diferente de'
        }
        return operator_mapping.get(operator, operator)
    
    def _determine_quantity_usage(self, parameters: Dict[str, str], comparison_info: Dict[str, Any]) -> str:
        """Determina si la cantidad se usa para comparación o como valor exacto"""
        try:
            operator = comparison_info.get('operator')
            
            if operator in ['greater_than', 'less_than']:
                return 'comparison'
            elif operator in ['equal_to']:
                return 'exact_value'
            else:
                return 'exact_value'
                    
        except Exception as e:
            logger.error(f"[ActionBusquedaSituacion] Error determinando uso de cantidad: {e}")
            return 'exact_value'
    
    def _get_search_type(self, intent_name: str, context: Dict[str, Any] = None) -> str:
        """
        ✅ CORREGIDO: Extrae tipo de búsqueda inteligentemente desde historial para modificar_busqueda
        """
        try:
            if intent_name == "modificar_busqueda":
                # Para modificar_busqueda, inferir tipo desde el historial más reciente
                if context:
                    search_history = context.get('search_history', [])
                    if search_history:
                        latest_search = search_history[-1]
                        latest_type = latest_search.get('type', 'producto')
                        logger.info(f"[SearchType] modificar_busqueda: inferido '{latest_type}' desde historial")
                        return latest_type
                        
                # Fallback si no hay historial
                logger.warning("[SearchType] modificar_busqueda sin historial, usando fallback 'producto'")
                return "producto"
                
            # Lógica original para otros intents
            elif "oferta" in intent_name:
                return "oferta"
            elif "producto" in intent_name:
                return "producto"
            elif "recomendacion" in intent_name:
                return "recomendacion"
            elif "novedad" in intent_name:
                return "novedad"
            else:
                return "producto"
                
        except Exception as e:
            logger.error(f"[SearchType] Error determinando tipo de búsqueda: {e}")
            return "producto"

    def _process_result(self, result: Dict[str, Any], context: Dict[str, Any]) -> List[EventType]:
        """Genera eventos de slot apropiados"""
        try:
            events = []
            result_type = result.get('type')
            
            logger.debug(f"[ActionBusquedaSituacion] Procesando resultado de tipo: {result_type}")
            
            confidence_info = result.get('confidence_info', {})
            if confidence_info.get('average_confidence', 0.0) > 0:
                logger.info(f"[ActionBusquedaSituacion] Confianza promedio: {confidence_info['average_confidence']:.2f}")
            
            if result_type == 'entity_suggestion':
                suggestion_data = result['suggestion_data']
                
                if confidence_info:
                    suggestion_data['confidence_info'] = confidence_info
                
                events.extend([
                    SlotSet("pending_suggestion", suggestion_data),
                    SlotSet("user_engagement_level", "awaiting_confirmation")
                ])
                logger.debug("[ActionBusquedaSituacion] Eventos de sugerencia de entidad generados")
            
            elif result_type == 'parameter_suggestion':
                suggestion_data = result.get('suggestion_data', {})
                
                if confidence_info:
                    suggestion_data['confidence_info'] = confidence_info
                
                events.extend([
                    SlotSet("pending_suggestion", suggestion_data),
                    SlotSet("user_engagement_level", "awaiting_parameters")
                ])
                logger.debug("[ActionBusquedaSituacion] Eventos de sugerencia de parámetros generados")
            
            elif result_type == 'search_success':
                # Actualizar historial
                search_history = context.get('search_history', [])
                
                history_entry = {
                    'timestamp': datetime.now().isoformat(),
                    'type': result['search_type'],
                    'parameters': result['parameters'],
                    'status': 'completed'
                }
                
                if confidence_info:
                    history_entry['confidence_info'] = confidence_info
                
                if result.get('comparison_info'):
                    history_entry['comparison_info'] = {
                        'detected': result['comparison_info'].get('detected', False),
                        'type': result['comparison_info'].get('type'),
                        'operator': result['comparison_info'].get('operator'),
                        'confidence': result['comparison_info'].get('confidence', 0.0)
                    }
                
                if result.get('temporal_filters'):
                    history_entry['temporal_filters'] = result['temporal_filters']
                
                search_history.append(history_entry)
                
                events.extend([
                    SlotSet("search_history", search_history),
                    SlotSet("pending_suggestion", None),
                    SlotSet("user_engagement_level", "satisfied")
                ])
                
                logger.info(f"[ActionBusquedaSituacion] Eventos de búsqueda exitosa generados. Historial: {len(search_history)} entradas")
            
            elif result_type in ['validation_error', 'configuration_error', 'search_error', 'completion_error', 'search_execution_error']:
                events.append(SlotSet("user_engagement_level", "needs_help"))
                logger.debug(f"[ActionBusquedaSituacion] Eventos de error generados para: {result_type}")
            
            logger.info(f"[ActionBusquedaSituacion] Procesamiento de resultado completado. {len(events)} eventos generados")

            if 'slot_cleanup_events' in result:
                cleanup_events = result['slot_cleanup_events']
                events.extend(cleanup_events)
                logger.debug(f"[ActionBusquedaSituacion] Agregados {len(cleanup_events)} eventos de limpieza de slots")

            logger.info(f"[ActionBusquedaSituacion] Procesamiento de resultado completado. {len(events)} eventos generados")
            return events
            
        except Exception as e:
            logger.error(f"[ActionBusquedaSituacion] Error procesando resultado: {e}", exc_info=True)
            try:
                return [SlotSet("user_engagement_level", "needs_help")]
            except Exception as slot_error:
                logger.error(f"[ActionBusquedaSituacion] Error crítico generando eventos de fallback: {slot_error}")
                return []