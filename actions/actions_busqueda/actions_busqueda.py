# actions/actions_busqueda.py - REFACTORIZADO
# ✅ CAMBIO PRINCIPAL: _handle_search_intent ya NO ejecuta búsquedas directamente
# Ahora solo hace PRE-ANÁLISIS y delega al LLM (search_engine)

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import re

import actions
from actions.functions.search_engine_cpu import get_cpu_search_engine
from actions.logger import log_message
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, EventType

from actions.config import (
    config_manager,
    get_intent_config,
    get_lookup_tables,
    get_entities_for_intent,
    validate_entity_value,
    get_entity_suggestions
)
from actions.models.model_manager import get_search_engine
from ..conversation_state import ConversationState, SuggestionManager, create_smart_suggestion, get_improved_suggestions
from .comparison_detector import ComparisonDetector
from .modification_detector import ModificationDetector
from ..helpers import validate_entities_for_intent, validate_entity_detection

logger = logging.getLogger(__name__)

class ActionBusquedaSituacion(Action):
    """
    ✅ REFACTORIZADO: Ahora actúa como "Cerebro A" (Pre-análisis)
    Su trabajo es PREPARAR información para el LLM, no ejecutar búsquedas
    """
    
    def __init__(self):
        try:
            # Motor GPU (prioritario) - TU CÓDIGO ORIGINAL
            self.search_engine = get_search_engine()
            
            # ✅ NUEVO: Motor CPU (fallback optimizado)
            self.search_engine_cpu = get_cpu_search_engine()
            
            # Detectores (sin cambios)
            from .comparison_detector import ComparisonDetector
            from .modification_detector import ModificationDetector
            self.comparison_detector = ComparisonDetector()
            self.modification_detector = ModificationDetector()
            
            logger.info("[ActionBusquedaSituacion] Motores inicializados (GPU + CPU)")
            logger.info(f"    GPU disponible: {self.search_engine.is_gpu_available()}")
            logger.info(f"    CPU disponible: {self.search_engine_cpu.is_available()}")
            
        except Exception as e:
            logger.error(f"[ActionBusquedaSituacion] Error inicializando: {e}")
            self.comparison_detector = None
            self.modification_detector = None
    
    def name(self) -> str:
        return "action_busqueda_situacion"
    
    # ============== NORMALIZACIÓN DE ENTIDADES (Sin cambios) ==============
    
    def _normalize_regex_entities(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normaliza entidades específicas de regex a formato genérico
        """
        try:
            normalized = []
            
            for entity in entities:
                entity_type = entity.get('entity')
                entity_value = entity.get('value')
                
                # CASO 1: Comparadores con contexto
                if entity_type.startswith('comparador_'):
                    parts = entity_type.split('_')
                    
                    if len(parts) >= 3:
                        operator_role = parts[1]
                        context = parts[2]
                        
                        group_map = {
                            'descuento': 'descuento_filter',
                            'precio': 'precio_filter',
                            'stock': 'stock_filter',
                            'bonificacion': 'bonificacion_filter'
                        }
                        
                        normalized_entity = {
                            **entity,
                            'entity': 'comparador',
                            'value': operator_role,
                            'role': operator_role,
                            'group': group_map.get(context, f"{context}_filter"),
                            '_original_entity': entity_type
                        }
                        
                        logger.debug(f"[Normalize] {entity_type} → comparador (role={operator_role}, group={group_map.get(context)})")
                        normalized.append(normalized_entity)
                    
                    elif len(parts) == 2:
                        operator_role = parts[1].replace('generico', '').strip()
                        
                        normalized_entity = {
                            **entity,
                            'entity': 'comparador',
                            'value': operator_role,
                            'role': operator_role,
                            '_original_entity': entity_type
                        }
                        
                        logger.debug(f"[Normalize] {entity_type} → comparador (role={operator_role})")
                        normalized.append(normalized_entity)
                    
                    else:
                        normalized.append(entity)
                
                # CASO 2: Estados específicos
                elif entity_type.startswith('estado_'):
                    estado_role = entity_type.replace('estado_', '')
                    
                    normalized_entity = {
                        **entity,
                        'entity': 'estado',
                        'value': entity_value or estado_role,
                        'role': estado_role,
                        '_original_entity': entity_type
                    }
                    
                    logger.debug(f"[Normalize] {entity_type} → estado (role={estado_role})")
                    normalized.append(normalized_entity)
                
                # CASO 3: Dosis específicas
                elif entity_type.startswith('dosis_'):
                    dosis_type = entity_type.replace('dosis_', '')
                    
                    normalized_entity = {
                        **entity,
                        'entity': 'dosis',
                        'value': entity_value,
                        'dosis_type': dosis_type,
                        '_original_entity': entity_type
                    }
                    
                    logger.debug(f"[Normalize] {entity_type} → dosis (type={dosis_type})")
                    normalized.append(normalized_entity)
                
                # CASO 4: Animales específicos
                elif entity_type.startswith('animal_'):
                    animal_value = entity_type.replace('animal_', '')
                    
                    normalized_entity = {
                        **entity,
                        'entity': 'animal',
                        'value': entity_value or animal_value,
                        '_original_entity': entity_type
                    }
                    
                    logger.debug(f"[Normalize] {entity_type} → animal")
                    normalized.append(normalized_entity)
                
                # CASO 5: Mantener genéricas
                else:
                    normalized.append(entity)
            
            if len(normalized) != len(entities):
                logger.warning(f"[Normalize] ⚠️ Perdida de entidades: {len(entities)} → {len(normalized)}")
            else:
                logger.info(f"[Normalize] ✅ {len(normalized)} entidades normalizadas")
            
            return normalized
            
        except Exception as e:
            logger.error(f"[Normalize] Error: {e}", exc_info=True)
            return entities

    # ============== RUN (Sin cambios mayores) ==============
    
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[str, Any]) -> List[EventType]:
        """
        Ejecuta búsquedas y formatea resultados
        """
        try:
            context = ConversationState.get_conversation_context(tracker)
            intent_name = context['current_intent']
            user_message = context.get('user_message', '')
            
            logger.info(f"[ActionBusquedaSituacion] Procesando intent: {intent_name}")
            
            events = []
            log_message(tracker, nlu_conf_threshold=0.6)
            
            # Detectar sugerencias ignoradas
            ignored_suggestion_cleanup = self._handle_ignored_suggestions(context, intent_name, dispatcher)
            events.extend(ignored_suggestion_cleanup['events'])
            
            if ignored_suggestion_cleanup['suggestion_was_ignored']:
                context['pending_suggestion'] = None
                context['awaiting_suggestion_response'] = False
            
            # Validar intent
            intent_config = get_intent_config()
            if intent_name not in intent_config.get("intents", {}):
                logger.warning(f"[ActionBusquedaSituacion] Intent desconocido: {intent_name}")
                dispatcher.utter_message("Lo siento, no pude entender tu solicitud.")
                return events
            
            # Actualizar sentimiento
            if context['detected_sentiment'] != context['current_sentiment_slot']:
                events.append(SlotSet("user_sentiment", context['detected_sentiment']))
            
            # ✅ LÓGICA DE PROCESAMIENTO
            
            # 1. INTENTS DE MODIFICACIÓN
            if intent_name.startswith('modificar_busqueda'):
                result = self._handle_modification_intent(context, tracker, dispatcher)
            
            # 2. INTENTS DE BÚSQUEDA
            elif self._is_search_intent(intent_name):
                comparison_info = self._analyze_comparison_with_groups(tracker)
                logger.debug(f"[ActionBusquedaSituacion] Comparación: {comparison_info}")
                
                result = self._handle_search_intent(context, tracker, dispatcher, comparison_info)
            
            # 3. INTENTS GENÉRICOS
            else:
                if intent_name in ['afirmar', 'denegar', 'agradecer']:
                    result = {'type': 'generic_response'}
                else:
                    dispatcher.utter_message("¿En qué puedo ayudarte hoy?")
                    result = {'type': 'generic_response'}
            
            # ✅ Formatear y enviar resultados
            if result.get('type') == 'search_success':
                self._send_search_results(result, dispatcher)
            
            events.extend(self._process_result(result, context))
            logger.info(f"[ActionBusquedaSituacion] Completado. Eventos: {len(events)}")
            
            return events
            
        except Exception as e:
            logger.error(f"[ActionBusquedaSituacion] Error crítico: {e}", exc_info=True)
            dispatcher.utter_message("Ocurrió un error procesando tu solicitud.")
            return []

    # ============== ✅ REFACTORIZADO: _handle_search_intent ==============
        
    def _handle_search_intent(
            self, 
            context: Dict[str, Any], 
            tracker: Tracker, 
            dispatcher: CollectingDispatcher,
            comparison_info: Dict[str, Any]
        ) -> Dict[str, Any]:
            """
            ✅ NUEVO FLUJO CON TRIAGE:
            1. Pre-análisis (Cerebro A) - SIEMPRE
            2. Triage: GPU vs CPU Simple vs CPU Complejo
            3. Ejecución según ruta elegida
            4. Procesamiento de resultados
            """
            try:
                intent_name = context['current_intent']
                entities = context['entities']
                user_message = context.get('user_message', '')
                
                # ============== PASO 1: VALIDAR ENTIDADES ==============
                # (Tu código original, sin cambios)
                validation_result = self._validate_entities_with_helper(
                    tracker, 
                    intent_name, 
                    dispatcher
                )
                
                if validation_result.get('has_suggestions') or validation_result.get('has_errors'):
                    logger.warning(f"[HandleSearch] Búsqueda frenada por validación.")
                    return {
                        'type': 'entity_suggestion',
                        'suggestion_data': validation_result.get('suggestion_data'),
                        'slot_cleanup_events': []
                    }
                
                # ============== PASO 2: PRE-ANÁLISIS (Cerebro A) ==============
                # (Tu código original, sin cambios)
                
                normalized_entities = self._normalize_regex_entities(entities)
                
                pre_analyzed_params = self._build_search_params(
                    normalized_entities, 
                    context, 
                    comparison_info
                )
                
                search_type = self._determine_search_type(intent_name)
                
                logger.info(f"[HandleSearch] 🧠 Pre-análisis (Cerebro A): {pre_analyzed_params}")
                logger.info(f"[HandleSearch] 📝 Tipo sugerido: {search_type}")
                
                # ============== PASO 3: TRIAGE (LÓGICA NUEVA) ==============
                
                is_gpu = self.search_engine.is_gpu_available()
                is_complex = self._is_query_complex(tracker, pre_analyzed_params, user_message)
                
                logger.info(f"[HandleSearch] 🎯 Triage: GPU={is_gpu}, Complejo={is_complex}")
                
                # --- RUTA 1: GPU (FLUJO ORIGINAL - SIN CAMBIOS) ---
                if is_gpu:
                    logger.info("[HandleSearch] 🚀 Ruta: GPU (flujo original preservado)")
                    
                    llm_result = self.search_engine.execute_search(
                        search_params=pre_analyzed_params,
                        search_type=search_type,
                        user_message=user_message,
                        is_modification=False,
                        previous_params=None
                    )
                
                # --- RUTA 2: CPU SIMPLE (BYPASS DIRECTO) ---
                elif not is_complex:
                    logger.info("[HandleSearch] ⚡️ Ruta: CPU Bypass (pre-análisis directo, <1s)")
                    
                    # Ejecutar búsqueda directa sin LLM
                    direct_result = self.search_engine.execute_direct(
                        pre_analyzed_params, search_type
                    )
                    
                    # Empaquetar resultado en formato estándar
                    llm_result = {
                        "success": direct_result.get("success"),
                        "results": direct_result.get("results"),
                        "total_results": direct_result.get("total_results"),
                        "llm_used": "none (bypass)",
                        "llm_time": 0.0,
                        "final_params": pre_analyzed_params,
                        "final_search_type": search_type
                    }
                    
                    logger.info(f"[HandleSearch] ✅ Bypass completado: {llm_result['total_results']} resultados")
                
                # --- RUTA 3: CPU COMPLEJO (LLM CON TIMEOUT) ---
                else:
                    logger.info("[HandleSearch] 🐢 Ruta: CPU con LLM (timeout 40s + fallback)")
                    
                    # Intentar con LLM CPU (timeout 40s)
                    cpu_result = self.search_engine_cpu.execute_with_timeout(
                        pre_analyzed_params=pre_analyzed_params,
                        search_type=search_type,
                        user_message=user_message,
                        timeout=40
                    )
                    
                    # Si LLM CPU tuvo éxito
                    if cpu_result and cpu_result.get("success"):
                        logger.info("[HandleSearch] ✅ CPU LLM exitoso, ejecutando búsqueda")
                        
                        final_params = cpu_result["params"]
                        final_action = cpu_result["action"]
                        final_search_type = "ofertas" if final_action == "search_offers" else "productos"
                        
                        # Ejecutar búsqueda con parámetros del LLM
                        direct_result = self.search_engine.execute_direct(
                            final_params, final_search_type
                        )
                        
                        llm_result = {
                            "success": direct_result.get("success"),
                            "results": direct_result.get("results"),
                            "total_results": direct_result.get("total_results"),
                            "llm_used": "cpu",
                            "llm_time": cpu_result.get("llm_time", 0.0),
                            "final_params": final_params,
                            "final_search_type": final_search_type
                        }
                    
                    # Si LLM CPU falló (timeout/error) → FALLBACK al pre-análisis
                    else:
                        logger.warning("[HandleSearch] ⚠️ CPU LLM falló/timeout, usando fallback (pre-análisis)")
                        
                        direct_result = self.search_engine.execute_direct(
                            pre_analyzed_params, search_type
                        )
                        
                        llm_result = {
                            "success": direct_result.get("success"),
                            "results": direct_result.get("results"),
                            "total_results": direct_result.get("total_results"),
                            "llm_used": "fallback (pre-análisis)",
                            "llm_time": 40.0,  # Timeout alcanzado
                            "final_params": pre_analyzed_params,
                            "final_search_type": search_type,
                            "fallback_reason": "CPU LLM timeout/error"
                        }
                
                # ============== PASO 4: PROCESAR RESULTADO ==============
                # (Tu código original, sin cambios)
                
                if not llm_result.get("success"):
                    logger.error(f"[HandleSearch] ❌ Error: {llm_result.get('error')}")
                    return {
                        'type': 'search_error',
                        'error': llm_result.get('error'),
                        'parameters': pre_analyzed_params
                    }
                
                # Extraer resultados finales
                final_results = llm_result.get('results', {})
                total_results = llm_result.get('total_results', 0)
                
                logger.info(
                    f"[HandleSearch] ✅ {total_results} resultados "
                    f"(ruta: {llm_result.get('llm_used')}, tiempo: {llm_result.get('llm_time', 0):.2f}s)"
                )
                
                return {
                    'type': 'search_success',
                    'search_type': llm_result.get('final_search_type', search_type),
                    'parameters': llm_result.get('final_params', pre_analyzed_params),
                    'search_results': final_results,
                    'comparison_info': comparison_info,
                    'llm_used': llm_result.get('llm_used'),
                    'llm_time': llm_result.get('llm_time', 0.0)
                }
            
            except Exception as e:
                logger.error(f"[HandleSearch] Error: {e}", exc_info=True)
                return {'type': 'search_error', 'error': str(e)}
    # ============== ✅ REFACTORIZADO: _handle_modification_intent ==============
    
    def _handle_modification_intent(
        self, 
        context: Dict[str, Any], 
        tracker: Tracker, 
        dispatcher: CollectingDispatcher
    ) -> Dict[str, Any]:
        """
        ✅ NUEVO FLUJO: Pre-análisis de modificaciones → LLM → Búsqueda
        """
        try:
            user_message = context.get('user_message', '')
            entities = tracker.latest_message.get("entities", [])
            previous_params = self._extract_previous_search_parameters(context)
            search_type = previous_params.get('_previous_search_type', 'productos')
            intent_name = context['current_intent']

            # ============== PASO 1: VALIDAR NUEVAS ENTIDADES ==============
            validation_result = self._validate_entities_with_helper(
                tracker, 
                intent_name, 
                dispatcher
            )
            
            if validation_result.get('has_suggestions') or validation_result.get('has_errors'):
                logger.warning(f"[ModifyIntent] Modificación frenada por validación.")
                return {
                    'type': 'entity_suggestion',
                    'suggestion_data': validation_result.get('suggestion_data'),
                    'slot_cleanup_events': []
                }

            # ============== PASO 2: PRE-ANÁLISIS DE CAMBIOS (Cerebro A) ==============
            
            # 2.1 Normalizar nuevas entidades
            normalized_entities = self._normalize_regex_entities(entities)
            
            # 2.2 Construir parámetros de los CAMBIOS detectados
            current_params = self._build_search_params(normalized_entities, context, {})
            
            logger.info(f"[ModifyIntent] 🧠 Pre-análisis de cambios (Cerebro A): {current_params}")
            logger.info(f"[ModifyIntent] 📋 Parámetros previos: {previous_params}")
            
            # ============== PASO 3: LLAMAR AL LLM (Cerebro B) ==============
            
            llm_result = self.search_engine.execute_search(
                search_params=current_params,  # ← Cambios detectados
                search_type=search_type,
                user_message=user_message,
                is_modification=True,  # ← Activar modo modificación
                previous_params=previous_params,
                chat_history=context.get('chat_history', [])
            )
            
            # ============== PASO 4: PROCESAR RESULTADO ==============
            
            if not llm_result.get("success"):
                logger.error(f"[ModifyIntent] ❌ Error: {llm_result.get('error')}")
                return {
                    'type': 'modify_error',
                    'error': llm_result.get('error')
                }
            
            final_results = llm_result.get('results', {})
            total_results = llm_result.get('total_results', 0)
            
            logger.info(f"[ModifyIntent] ✅ {total_results} resultados después de modificar")
            
            return {
                'type': 'search_success',
                'search_type': llm_result.get('final_search_type', search_type),
                'parameters': llm_result.get('final_params', current_params),
                'search_results': final_results,
                'modification_applied': True,
                'llm_used': llm_result.get('llm_used'),
                'llm_time': llm_result.get('llm_time', 0.0)
            }
                
        except Exception as e:
            logger.error(f"[ModifyIntent] Error: {e}", exc_info=True)
            return {'type': 'modify_error', 'error': str(e)}
        
    def _is_query_complex(
        self, 
        tracker: Tracker, 
        pre_params: Dict[str, Any],
        user_message: str
    ) -> bool:
        """
        ✅ NUEVA FUNCIÓN: Determina si una query es "compleja" y necesita LLM.
        
        SIMPLE (bypass directo):
        - 1-2 filtros claros del NLU (ej: {"proveedor": "holliday"})
        - Query corta sin ambigüedad
        
        COMPLEJA (necesita LLM):
        - Más de 3 filtros
        - Mensaje largo con contexto ambiguo
        - Comparaciones numéricas (descuentos, stock)
        - Intents de modificación
        - Pre-análisis vacío pero mensaje largo (NLU falló)
        
        Args:
            tracker: Tracker de Rasa
            pre_params: Parámetros del pre-análisis
            user_message: Mensaje original del usuario
        
        Returns:
            True si es compleja (necesita LLM), False si es simple (bypass)
        """
        try:
            intent = tracker.get_intent_of_latest_message()
            
            # REGLA 1: Modificaciones SIEMPRE son complejas
            if intent.startswith('modificar_busqueda'):
                logger.debug("[IsComplex] Modificación → COMPLEJO")
                return True
            
            # REGLA 2: Pre-análisis vacío + mensaje largo = ambigüedad
            if not pre_params and len(user_message) > 15:
                logger.debug("[IsComplex] Pre-análisis vacío + mensaje largo → COMPLEJO")
                return True
            
            # REGLA 3: Muchos filtros = complejo
            num_filters = len([v for v in pre_params.values() if v])
            if num_filters > 3:
                logger.debug(f"[IsComplex] {num_filters} filtros → COMPLEJO")
                return True
            
            # REGLA 4: Comparaciones numéricas = complejo
            numeric_filters = ['descuento_min', 'descuento_max', 'stock_min', 'stock_max', 
                             'bonificacion_min', 'bonificacion_max']
            has_numeric = any(k in pre_params for k in numeric_filters)
            if has_numeric:
                logger.debug("[IsComplex] Filtros numéricos detectados → COMPLEJO")
                return True
            
            # REGLA 5: Múltiples estados = complejo
            estado_value = pre_params.get('estado', '')
            if isinstance(estado_value, str) and ',' in estado_value:
                logger.debug("[IsComplex] Múltiples estados → COMPLEJO")
                return True
            
            # REGLA 6: Dosis con múltiples componentes = complejo
            dosis_fields = ['dosis_gramaje', 'dosis_volumen', 'dosis_forma']
            num_dosis = sum(1 for k in dosis_fields if k in pre_params and pre_params[k])
            if num_dosis >= 2:
                logger.debug(f"[IsComplex] {num_dosis} campos de dosis → COMPLEJO")
                return True
            
            # REGLA 7: Mensaje muy largo (>50 chars) con contexto = complejo
            if len(user_message) > 50 and num_filters > 0:
                logger.debug("[IsComplex] Mensaje largo con contexto → COMPLEJO")
                return True
            
            # POR DEFECTO: Query simple (1-2 filtros básicos)
            logger.debug(f"[IsComplex] Query simple ({num_filters} filtros) → BYPASS")
            return False
            
        except Exception as e:
            logger.error(f"[IsComplex] Error: {e}, asumiendo COMPLEJO por seguridad")
            return True  # En caso de error, asumir complejo (usar LLM o fallback)
    

    # ============== BUILD SEARCH PARAMS (Cerebro A - LÓGICA COMPLETA) ==============
    
    def _build_search_params(
        self, 
        entities: List[Dict[str, Any]], 
        context: Dict[str, Any],
        comparison_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        ✅ CONSERVADO: Esta es la lógica de "Cerebro A"
        Construye el pre-análisis estructurado que el LLM usará
        """
        params = {}
        
        # Mapeo de entidades
        entity_mapping = {
            'producto': 'nombre',
            'empresa': 'proveedor',
            'categoria': 'categoria',
            'estado': 'estado'
        }
        
        for entity in entities:
            entity_type = entity.get('entity')
            entity_value = entity.get('value')
            entity_role = entity.get('role')
            
            # Mapeo directo
            if entity_type in entity_mapping:
                param_name = entity_mapping[entity_type]
                
                if param_name:
                    if entity_role and entity_type == 'empresa':
                        params[entity_role] = entity_value
                    else:
                        params[param_name] = entity_value
            
            # Dosis
            elif entity_type == 'dosis':
                dosis_type = entity.get('dosis_type', 'forma')
                params[f'dosis_{dosis_type}'] = entity_value
            
            # Comparadores con grupos
            elif entity_type == 'comparador':
                group = entity.get('group')
                operator = entity.get('role', entity_value)
                
                if group == 'descuento_filter':
                    if operator in ['gt', 'gte']:
                        params['descuento_min'] = self._get_quantity_from_entities(entities, group)
                    elif operator in ['lt', 'lte']:
                        params['descuento_max'] = self._get_quantity_from_entities(entities, group)
                
                elif group == 'stock_filter':
                    if operator in ['gt', 'gte']:
                        params['stock_min'] = self._get_quantity_from_entities(entities, group)
                    elif operator in ['lt', 'lte']:
                        params['stock_max'] = self._get_quantity_from_entities(entities, group)
        
        # Procesar estados múltiples
        estado_entities = [e for e in entities if e.get('entity') == 'estado']
        if estado_entities:
            self._process_multiple_estados(
                [{'entity': e} for e in estado_entities], 
                params
            )
        
        logger.debug(f"[BuildParams] Construidos: {params}")
        return params

    def _process_multiple_estados(self, estado_entities: List[Dict[str, Any]], 
                              search_params: Dict[str, Any]) -> None:
        """
        Procesa múltiples estados y los combina
        """
        try:
            estados_validos = []
            
            for item in estado_entities:
                entity_obj = item['entity']
                estado_role = entity_obj.get('role')
                estado_value = entity_obj.get('value')
                
                estado = estado_role if estado_role else estado_value
                
                if estado:
                    estado_normalizado = estado.lower().replace(' ', '_')
                    
                    estado_map = {
                        'nuevas': 'nuevo',
                        'novedades': 'nuevo',
                        'no_vistas': 'nuevo',
                        'stock_limitado': 'poco_stock',
                        'ultimas_unidades': 'poco_stock',
                        'proximo_a_vencer': 'vence_pronto',
                        'por_vencer': 'vence_pronto'
                    }
                    
                    estado_final = estado_map.get(estado_normalizado, estado_normalizado)
                    
                    if estado_final not in estados_validos:
                        estados_validos.append(estado_final)
            
            if estados_validos:
                search_params['estado'] = ','.join(estados_validos)
                logger.info(f"[MultiEstados] {len(estados_validos)} estados procesados: {estados_validos}")
            
        except Exception as e:
            logger.error(f"[MultiEstados] Error: {e}")

    def _get_quantity_from_entities(self, entities: List[Dict], group: str) -> Optional[float]:
        """
        Extrae cantidad de entidades asociadas al grupo
        """
        try:
            for entity in entities:
                if entity.get('group') == group and entity.get('entity') in ['cantidad_descuento', 'cantidad_stock', 'cantidad']:
                    return float(entity.get('value', 0))
            return None
        except:
            return None

    # ============== HELPERS (Conservados sin cambios) ==============
    
    def _determine_search_type(self, intent_name: str) -> str:
        """Determina si buscar productos u ofertas"""
        if 'oferta' in intent_name.lower():
            return 'ofertas'
        return 'productos'
    
    def _is_search_intent(self, intent_name: str) -> bool:
        search_intents = ['buscar_producto', 'buscar_oferta', 'consultar_novedades_producto', 
                         'consultar_novedades_oferta', 'consultar_recomendaciones_producto',
                         'consultar_recomendaciones_oferta']
        return intent_name in search_intents
    
    def _analyze_comparison_with_groups(self, tracker: Tracker) -> Dict[str, Any]:
        """Analiza comparaciones extrayendo grupos del NLU"""
        try:
            if not self.comparison_detector:
                return {}
            
            text = tracker.latest_message.get("text", "")
            entities = tracker.latest_message.get("entities", [])
            
            if not text:
                return {}
            
            logger.debug(f"[Comparison] Analizando con {len(entities)} entidades")
            
            entity_groups = self._extract_entity_groups(entities)
            comparison_result = self.comparison_detector.detect_comparison(text, entities)
            
            if not comparison_result.detected:
                return {}
            
            comparison_info = {
                'detected': True,
                'operator': comparison_result.operator.value if comparison_result.operator else None,
                'operator_role': self._map_operator_to_role(comparison_result.operator),
                'quantity': comparison_result.quantity,
                'type': comparison_result.comparison_type.value if comparison_result.comparison_type else None,
                'entities': comparison_result.entities,
                'groups': comparison_result.groups_detected,
                'roles': comparison_result.roles_detected,
                'confidence': comparison_result.confidence,
                'temporal_filters': comparison_result.temporal_filters,
                'normalized_dates': comparison_result.normalized_dates,
                'nlu_groups': entity_groups,
                'grouped_entities': self._group_entities_by_filter(entity_groups)
            }
            
            logger.info(
                f"[Comparison] Detectada con grupos: {list(entity_groups.keys())}, "
                f"confianza: {comparison_result.confidence:.2f}"
            )
            
            return comparison_info
            
        except Exception as e:
            logger.error(f"[Comparison] Error: {e}", exc_info=True)
            return {}

    def _extract_entity_groups(self, entities: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Extrae grupos de entidades del NLU"""
        try:
            groups = {}
            
            for entity in entities:
                group = entity.get('group')
                if group:
                    if group not in groups:
                        groups[group] = []
                    
                    groups[group].append({
                        'entity': entity.get('entity'),
                        'value': entity.get('value'),
                        'role': entity.get('role'),
                        'confidence': entity.get('confidence', 0.0)
                    })
            
            if groups:
                logger.debug(f"[Groups] Extraídos {len(groups)} grupos: {list(groups.keys())}")
            
            return groups
            
        except Exception as e:
            logger.error(f"[Groups] Error extrayendo: {e}")
            return {}

    def _group_entities_by_filter(self, entity_groups: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
        """Agrupa entidades por tipo de filtro"""
        try:
            grouped = {}
            
            for group_name, entities in entity_groups.items():
                if 'descuento' in group_name:
                    filter_type = 'descuento'
                elif 'precio' in group_name:
                    filter_type = 'precio'
                elif 'stock' in group_name:
                    filter_type = 'stock'
                elif 'bonificacion' in group_name:
                    filter_type = 'bonificacion'
                else:
                    filter_type = group_name
                
                filter_data = {}
                for entity in entities:
                    entity_type = entity['entity']
                    role = entity.get('role')
                    
                    if entity_type == 'comparador':
                        filter_data['operator'] = role
                        filter_data['operator_text'] = entity['value']
                    else:
                        filter_data['value'] = entity['value']
                        filter_data['entity_type'] = entity_type
                
                grouped[filter_type] = filter_data
            
            if grouped:
                logger.debug(f"[GroupedFilters] {len(grouped)} filtros agrupados")
            
            return grouped
            
        except Exception as e:
            logger.error(f"[GroupedFilters] Error: {e}")
            return {}

    def _map_operator_to_role(self, operator) -> Optional[str]:
        """Mapea operador de comparación a role del NLU"""
        try:
            from .comparison_detector import ComparisonOperator
            
            mapping = {
                ComparisonOperator.GREATER_THAN: 'gt',
                ComparisonOperator.LESS_THAN: 'lt',
                ComparisonOperator.EQUAL_TO: 'eq',
                ComparisonOperator.DIFFERENT_FROM: 'neq'
            }
            
            return mapping.get(operator)
            
        except Exception as e:
            logger.error(f"[OperatorMap] Error: {e}")
            return None

    def _extract_previous_search_parameters(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Extrae parámetros de búsqueda previa"""
        try:
            search_history = context.get('search_history', [])
            
            if not search_history:
                return {}
            
            latest_search = search_history[-1]
            previous_params = latest_search.get('parameters', {})
            search_type = latest_search.get('type', 'productos')
            
            enriched_params = previous_params.copy()
            enriched_params['_previous_search_type'] = search_type
            enriched_params['_previous_timestamp'] = latest_search.get('timestamp')
            
            if previous_params:
                logger.info(f"[PrevParams] {len(previous_params)} parámetros de búsqueda anterior ({search_type})")
            
            return enriched_params
            
        except Exception as e:
            logger.error(f"[PrevParams] Error: {e}")
            return {}

    # ============== SEND RESULTS ==============
    
    def _send_search_results(self, result: Dict[str, Any], dispatcher: CollectingDispatcher) -> None:
        """
        Envía un solo mensaje con 'text' (resumen) y 'custom' (JSON)
        """
        try:
            search_results = result.get('search_results', {})
            search_type = result.get('search_type', 'productos')
            total_results = search_results.get('total_results', 0)
            
            # Mensaje de texto
            if total_results == 0:
                params_display = self._format_parameters_for_display(result.get('parameters', {}))
                params_str = ", ".join([f"{k}: {v}" for k, v in params_display.items()])
                text_message = f"❌ No encontré {search_type} con los parámetros:\n{params_str}"
            else:
                item_type = "ofertas" if search_type == "ofertas" else "productos"
                text_message = f"✅ Encontré {total_results} {item_type}."
            
            # Payload custom
            custom_payload = {
                "type": "search_results",
                "search_type": search_type,
                "validated": True,
                "timestamp": datetime.now().isoformat(),
                "parameters": result.get('parameters', {}),
                "search_results": search_results,
                "comparison_analysis": result.get('comparison_info')
            }
            
            dispatcher.utter_message(
                text=text_message,
                custom=custom_payload
            )
            
            logger.info(f"[SearchResults] Enviado 1 mensaje con 'text' y 'custom' (JSON)")

        except Exception as e:
            logger.error(f"[SearchResults] Error: {e}", exc_info=True)
            dispatcher.utter_message("Encontré resultados pero hubo un error al mostrarlos.")

    def _format_parameters_for_display(self, parameters: Dict[str, Any]) -> Dict[str, str]:
        """Formatea parámetros para mostrar al usuario"""
        try:
            formatted = {}
            
            for key, value in parameters.items():
                if isinstance(value, dict):
                    if 'value' in value and 'role' in value:
                        role = value['role']
                        val = value['value']
                        
                        if key == 'estado':
                            role_display = {
                                'nuevo': 'productos nuevos',
                                'poco_stock': 'poco stock',
                                'vence_pronto': 'vence pronto',
                                'en_oferta': 'en oferta'
                            }.get(role, val)
                            formatted[key] = role_display
                        
                        elif key == 'empresa':
                            formatted[key] = f"{val}" if role == 'proveedor' else f"{val} ({role})"
                        
                        else:
                            formatted[key] = val
                    
                    elif 'value' in value and 'type' in value:
                        dosis_type = value['type']
                        val = value['value']
                        
                        type_display = {
                            'gramaje': 'mg/g',
                            'volumen': 'ml/l',
                            'forma': ''
                        }.get(dosis_type, '')
                        
                        formatted[key] = f"{val} {type_display}".strip()
                    
                    elif 'operator' in value and 'value' in value:
                        operator = value['operator']
                        val = value['value']
                        
                        op_display = {
                            'lt': 'menor a',
                            'gt': 'mayor a',
                            'lte': 'hasta',
                            'gte': 'al menos',
                            'eq': 'igual a'
                        }.get(operator, operator)
                        
                        formatted[key] = f"{op_display} {val}"
                    
                    else:
                        formatted[key] = str(value.get('value', value))
                
                else:
                    formatted[key] = str(value)
            
            return formatted
            
        except Exception as e:
            logger.error(f"[FormatDisplay] Error: {e}")
            return parameters

    # ============== VALIDACIÓN DE ENTIDADES ==============
    
    def _validate_entities_with_helper(self, tracker: Tracker, intent_name: str, 
                                   dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """
        Valida entidades y genera sugerencias si es necesario
        """
        try:
            entities = tracker.latest_message.get("entities", [])
            
            # Ordenar por confianza
            entities_with_confidence = []
            for entity in entities:
                confidence = entity.get("confidence_entity", entity.get("confidence", 0.0))
                entities_with_confidence.append({
                    **entity,
                    "confidence_score": confidence
                })
            
            entities_sorted = sorted(entities_with_confidence, key=lambda x: x["confidence_score"], reverse=True)
            
            logger.debug(f"[EntityValidation] Validando {len(entities_sorted)} entidades")
            
            helper_result = validate_entities_for_intent(entities_sorted, intent_name, min_length=2, check_fragments=True)
            
            # Acumular todos los mensajes
            all_messages = []
            enhanced_suggestions = []
            cross_entity_suggestions = []
            
            if helper_result['has_suggestions']:
                for suggestion_item in helper_result['suggestions']:
                    try:
                        entity_type = suggestion_item.get('entity_type')
                        raw_value = suggestion_item.get('raw_value')
                        suggestions_list = suggestion_item.get('suggestions', [])
                        
                        original_confidence = 0.0
                        for original_ent in entities_sorted:
                            if original_ent.get('value') == raw_value and original_ent.get('entity') == entity_type:
                                original_confidence = original_ent['confidence_score']
                                break
                        
                        if suggestions_list:
                            suggestion_text = suggestions_list[0]
                            message = f"'{raw_value}' no es válido. ¿Te refieres a '{suggestion_text}'?"
                            all_messages.append(message)
                            
                            suggestion_data = SuggestionManager.create_entity_suggestion(
                                raw_value, entity_type, suggestion_text, 
                                {
                                    'intent': tracker.get_intent_of_latest_message(),
                                    'original_confidence': original_confidence
                                }
                            )
                            enhanced_suggestions.append(suggestion_data)
                            logger.info(f"[EntityValidation] Sugerencia normal: '{raw_value}' → '{suggestion_text}'")
                        else:
                            # Validación cruzada
                            cross_matches = self.validate_and_suggest_entities(raw_value, entity_type)
                            
                            if cross_matches:
                                cross_message = self.format_cross_entity_suggestions(cross_matches)
                                message = f"'{raw_value}' no es válido como {entity_type}. {cross_message}"
                                all_messages.append(message)
                                
                                best_match = cross_matches[0]
                                cross_suggestion_data = SuggestionManager.create_entity_suggestion(
                                    raw_value, best_match['entity_type'], best_match['suggestion'],
                                    {
                                        'intent': tracker.get_intent_of_latest_message(), 
                                        'cross_entity': True,
                                        'original_confidence': original_confidence
                                    }
                                )
                                cross_entity_suggestions.append(cross_suggestion_data)
                                logger.info(f"[EntityValidation] Sugerencia cruzada: '{raw_value}' → '{best_match['suggestion']}'")
                            else:
                                message = f"'{raw_value}' no es válido como {entity_type}."
                                all_messages.append(message)
                    
                    except Exception as suggestion_error:
                        logger.error(f"[EntityValidation] Error en sugerencia: {suggestion_error}")
                        continue
            
            # Enviar UN SOLO mensaje consolidado
            if all_messages:
                consolidated_message = "\n".join(all_messages)
                dispatcher.utter_message(consolidated_message)
            
            all_suggestions = enhanced_suggestions + cross_entity_suggestions
            all_suggestions.sort(key=lambda x: -x.get('metadata', {}).get('original_confidence', 0.0))
            
            return {
                'valid_params': helper_result['valid_params'],
                'has_suggestions': len(all_suggestions) > 0,
                'suggestion_data': all_suggestions[0] if all_suggestions else None,
                'has_errors': helper_result['has_errors'] and len(all_suggestions) == 0,
                'errors': helper_result['errors'] if len(all_suggestions) == 0 else []
            }
            
        except Exception as e:
            logger.error(f"[EntityValidation] Error: {e}", exc_info=True)
            dispatcher.utter_message("Error validando entidades")
            return {
                'valid_params': {},
                'has_suggestions': False,
                'suggestion_data': None,
                'has_errors': True,
                'errors': ["Error validando entidades"]
            }

    def validate_and_suggest_entities(self, invalid_value: str, original_entity_type: str) -> List[Dict[str, Any]]:
        """Usa sistema avanzado de similitud"""
        try:
            logger.debug(f"[CrossValidation] Para '{invalid_value}' (tipo: {original_entity_type})")
            
            suggestions = get_improved_suggestions(
                invalid_value, 
                original_entity_type, 
                max_suggestions=5
            )
            
            if not suggestions:
                return []
            
            formatted_suggestions = []
            for suggestion in suggestions:
                formatted_suggestions.append({
                    'entity_type': suggestion['entity_type'],
                    'suggestion': suggestion['suggestion'],
                    'similarity': suggestion['similarity'],
                    'original_value': suggestion['original_input'],
                    'match_confidence': suggestion['match_confidence'],
                    'priority': 1,
                    'match_type': 'advanced_similarity'
                })
            
            formatted_suggestions.sort(key=lambda x: x['similarity'], reverse=True)
            
            logger.info(f"[CrossValidation] {len(formatted_suggestions)} sugerencias para '{invalid_value}'")
            return formatted_suggestions
            
        except Exception as e:
            logger.error(f"[CrossValidation] Error: {e}", exc_info=True)
            return []

    def format_cross_entity_suggestions(self, matches: List[Dict[str, Any]]) -> str:
        """Formatea sugerencias priorizando spelling"""
        try:
            if not matches:
                return "No se encontraron sugerencias alternativas."
            
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
            logger.error(f"[CrossFormat] Error: {e}")
            return "¿Podrías intentar con otro término?"

    def _get_entity_display_name(self, entity_type: str) -> str:
        """Convierte nombres técnicos a legibles"""
        display_names = {
            'categoria': 'categoría',
            'empresa': 'empresa', 
            'ingrediente_activo': 'ingrediente activo',
            'animal': 'animal',
            'producto': 'producto',
            'accion_terapeutica': 'acción terapéutica'
        }
        return display_names.get(entity_type, entity_type)

    # ============== MANEJO DE SUGERENCIAS IGNORADAS ==============
    
    def _handle_ignored_suggestions(self, context: Dict[str, Any], current_intent: str, 
                                   dispatcher: CollectingDispatcher) -> Dict[str, Any]:
        """Detecta y limpia sugerencias ignoradas automáticamente"""
        try:
            pending_suggestion = context.get('pending_suggestion')
            if not pending_suggestion:
                return {'suggestion_was_ignored': False, 'events': []}
            
            suggestion_ignored = SuggestionManager.check_if_suggestion_ignored(
                current_intent, pending_suggestion, context.get('is_small_talk', False)
            )
            
            if suggestion_ignored:
                suggestion_type = pending_suggestion.get('suggestion_type', 'unknown')
                original_search_type = pending_suggestion.get('search_type', 'unknown')
                
                logger.info(f"[IgnoredSugg] Detectada - Tipo: {suggestion_type}")
                
                if suggestion_type == 'entity_correction':
                    original_value = pending_suggestion.get('original_value', '')
                    message = f"Entiendo que prefieres hacer una nueva búsqueda en lugar de corregir '{original_value}'."
                elif suggestion_type == 'type_correction':
                    message = "Perfecto, te ayudo con esta nueva búsqueda."
                else:
                    message = "Perfecto, te ayudo con tu nueva búsqueda."
                
                current_search_type = self._determine_search_type(current_intent)
                if original_search_type != 'unknown' and current_search_type != original_search_type:
                    try:
                        dispatcher.utter_message(message)
                    except Exception as msg_error:
                        logger.error(f"[IgnoredSugg] Error enviando mensaje: {msg_error}")
                
                cleanup_events = [
                    SlotSet("pending_suggestion", None),
                    SlotSet("suggestion_context", None),
                    SlotSet("user_engagement_level", "engaged"),
                ]
                
                return {
                    'suggestion_was_ignored': True,
                    'events': cleanup_events,
                    'cleanup_reason': 'user_changed_search_type'
                }
            
            return {'suggestion_was_ignored': False, 'events': []}
            
        except Exception as e:
            logger.error(f"[IgnoredSugg] Error: {e}", exc_info=True)
            return {
                'suggestion_was_ignored': True,
                'events': [SlotSet("pending_suggestion", None)],
                'cleanup_reason': 'error_recovery'
            }

    # ============== PROCESAR RESULTADOS ==============
    
    def _process_result(self, result: Dict[str, Any], context: Dict[str, Any]) -> List[EventType]:
        """Genera eventos de slot apropiados"""
        try:
            events = []
            result_type = result.get('type')
            
            logger.debug(f"[ProcessResult] Tipo: {result_type}")
            
            if result_type == 'entity_suggestion':
                suggestion_data = result['suggestion_data']
                events.extend([
                    SlotSet("pending_suggestion", suggestion_data),
                    SlotSet("user_engagement_level", "awaiting_confirmation")
                ])
            
            elif result_type == 'parameter_suggestion':
                suggestion_data = result.get('suggestion_data', {})
                events.extend([
                    SlotSet("pending_suggestion", suggestion_data),
                    SlotSet("user_engagement_level", "awaiting_parameters")
                ])
            
            elif result_type == 'search_success':
                search_history = context.get('search_history', [])
                
                history_entry = {
                    'timestamp': datetime.now().isoformat(),
                    'type': result['search_type'],
                    'parameters': result['parameters'],
                    'status': 'completed'
                }
                
                if result.get('comparison_info'):
                    history_entry['comparison_info'] = {
                        'detected': result['comparison_info'].get('detected', False),
                        'type': result['comparison_info'].get('type'),
                        'operator': result['comparison_info'].get('operator')
                    }
                
                search_history.append(history_entry)
                
                events.extend([
                    SlotSet("search_history", search_history),
                    SlotSet("pending_suggestion", None),
                    SlotSet("user_engagement_level", "satisfied")
                ])
                
                logger.info(f"[ProcessResult] Búsqueda exitosa. Historial: {len(search_history)} entradas")
            
            elif result_type in ['validation_error', 'configuration_error', 'search_error', 'modify_error']:
                events.append(SlotSet("user_engagement_level", "needs_help"))
            
            if 'slot_cleanup_events' in result:
                cleanup_events = result['slot_cleanup_events']
                events.extend(cleanup_events)
            
            logger.info(f"[ProcessResult] {len(events)} eventos generados")
            return events
            
        except Exception as e:
            logger.error(f"[ProcessResult] Error: {e}", exc_info=True)
            return [SlotSet("user_engagement_level", "needs_help")]