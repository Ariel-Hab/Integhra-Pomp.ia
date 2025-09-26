# actions/recomendaciones.py - Version Unificada (Fase 1 Implementada)

import logging
from typing import Any, Dict, List
from datetime import datetime

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, EventType

logger = logging.getLogger(__name__)

class ActionRecomendaciones(Action):
    """
    Action unificado para manejar TODAS las recomendaciones.
    Detecta automáticamente si el usuario busca recomendaciones de:
    - Productos específicos
    - Ofertas/promociones
    - Combinación de ambos
    
    Basado en las entidades detectadas en el mensaje.
    """
    
    def name(self) -> str:
        return "action_recomendaciones"
    
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[str, Any]) -> List[EventType]:
        """
        Maneja solicitudes de recomendaciones unificadas con detección inteligente
        del tipo de recomendación basada en entidades
        """
        try:
            # Obtener información del intent y mensaje
            current_intent = tracker.latest_message.get("intent", {}).get("name", "")
            user_message = tracker.latest_message.get("text", "")
            entities = tracker.latest_message.get("entities", [])
            
            logger.info(f"[ActionRecomendaciones] Procesando {current_intent}: '{user_message[:100]}...'")
            
            # 🎯 NUEVA FUNCIONALIDAD: Detectar tipo de recomendación por entidades y palabras clave
            recommendation_analysis = self._analyze_recommendation_request(user_message, entities)
            
            # Generar respuesta personalizada según el análisis
            response_message = self._generate_unified_response(recommendation_analysis, entities)
            
            # Enviar respuesta al usuario
            try:
                dispatcher.utter_message(text=response_message)
                logger.info(f"[ActionRecomendaciones] Respuesta enviada para {recommendation_analysis['primary_type']}")
            except Exception as disp_error:
                logger.error(f"[ActionRecomendaciones] Error enviando respuesta: {disp_error}")
                # Fallback a respuesta simple
                dispatcher.utter_message("La funcionalidad de recomendaciones no está disponible por el momento.")
            
            # Generar eventos de slot
            events = [
                SlotSet("user_engagement_level", "informed_limitation"),
                SlotSet("last_intent_flow", user_message),
                SlotSet("pending_suggestion", None)  # Limpiar sugerencias pendientes
            ]
            
            # Agregar al historial con información del análisis
            search_history = tracker.get_slot("search_history") or []
            history_entry = {
                'timestamp': datetime.now().isoformat(),
                'type': 'recommendation_request',
                'recommendation_analysis': recommendation_analysis,
                'status': 'not_available',
                'intent': current_intent
            }
            search_history.append(history_entry)
            events.append(SlotSet("search_history", search_history))
            
            logger.info(f"[ActionRecomendaciones] Procesamiento completado. {len(events)} eventos generados")
            
            return events
            
        except Exception as e:
            logger.error(f"[ActionRecomendaciones] Error crítico: {e}", exc_info=True)
            try:
                dispatcher.utter_message(
                    "Disculpa, hubo un problema procesando tu solicitud de recomendaciones. "
                    "¿Puedo ayudarte a buscar algo específico?"
                )
            except Exception as disp_error:
                logger.error(f"[ActionRecomendaciones] Error adicional enviando mensaje de error: {disp_error}")
            
            return [SlotSet("user_engagement_level", "needs_help")]
    
    def _analyze_recommendation_request(self, user_message: str, entities: List[Dict]) -> Dict[str, Any]:
        """
        🆕 NUEVA FUNCIÓN: Analiza el tipo de recomendación solicitada
        
        Detecta automáticamente si el usuario busca:
        - Recomendaciones de productos
        - Recomendaciones de ofertas/promociones  
        - Recomendaciones mixtas
        
        Args:
            user_message: Texto del mensaje del usuario
            entities: Lista de entidades detectadas
            
        Returns:
            Dict con análisis completo del tipo de recomendación
        """
        try:
            analysis = {
                'primary_type': 'general',  # general, product, offer, mixed
                'secondary_type': None,
                'has_commercial_terms': False,
                'has_product_terms': False,
                'commercial_terms': [],
                'product_entities': [],
                'category_entities': [],
                'animal_entities': [],
                'provider_entities': [],
                'price_entities': [],
                'discount_entities': [],
                'confidence': 0.0
            }
            
            message_lower = user_message.lower()
            
            # 🔍 DETECTAR TÉRMINOS COMERCIALES (indican recomendación de ofertas)
            commercial_keywords = [
                'oferta', 'ofertas', 'promo', 'promos', 'promoción', 'promociones',
                'descuento', 'descuentos', 'rebaja', 'rebajas', 'liquidación',
                'bonificación', 'bonificaciones', '2x1', '3x2', 'flash',
                'clearance', 'outlet', 'barato', 'económico', 'precio',
                'costo', 'vale la pena', 'conviene', 'ahorro'
            ]
            
            detected_commercial = [term for term in commercial_keywords if term in message_lower]
            analysis['commercial_terms'] = detected_commercial
            analysis['has_commercial_terms'] = len(detected_commercial) > 0
            
            # 🔍 DETECTAR TÉRMINOS DE PRODUCTO
            product_keywords = [
                'producto', 'productos', 'medicamento', 'medicamentos',
                'tratamiento', 'tratamientos', 'medicina', 'medicinas',
                'fármaco', 'fármacos', 'droga', 'drogas'
            ]
            
            detected_product = [term for term in product_keywords if term in message_lower]
            analysis['has_product_terms'] = len(detected_product) > 0
            
            # 🔍 CATEGORIZAR ENTIDADES
            for entity in entities:
                entity_type = entity.get("entity", "")
                entity_value = entity.get("value", "").strip()
                
                if not entity_value or len(entity_value) < 2:
                    continue
                
                if entity_type == "producto":
                    analysis['product_entities'].append(entity_value)
                elif entity_type == "categoria":
                    analysis['category_entities'].append(entity_value)
                elif entity_type == "animal":
                    analysis['animal_entities'].append(entity_value)
                elif entity_type == "empresa":
                    analysis['provider_entities'].append(entity_value)
                elif entity_type in ["precio", "cantidad_descuento", "cantidad_bonificacion"]:
                    if entity_type == "precio":
                        analysis['price_entities'].append(entity_value)
                    else:
                        analysis['discount_entities'].append(entity_value)
            
            # 🎯 DETERMINAR TIPO PRINCIPAL DE RECOMENDACIÓN
            
            # Puntuación para ofertas
            offer_score = 0
            if analysis['has_commercial_terms']:
                offer_score += 3 * len(analysis['commercial_terms'])
            if analysis['price_entities']:
                offer_score += 2 * len(analysis['price_entities'])
            if analysis['discount_entities']:
                offer_score += 3 * len(analysis['discount_entities'])
            
            # Puntuación para productos
            product_score = 0
            if analysis['has_product_terms']:
                product_score += 2
            if analysis['product_entities']:
                product_score += 3 * len(analysis['product_entities'])
            if analysis['category_entities']:
                product_score += 2 * len(analysis['category_entities'])
            if analysis['animal_entities']:
                product_score += 1 * len(analysis['animal_entities'])
            
            # 🏆 DECISIÓN FINAL
            if offer_score > product_score and offer_score >= 3:
                analysis['primary_type'] = 'offer'
                analysis['confidence'] = min(0.9, 0.6 + (offer_score * 0.1))
                if product_score >= 2:
                    analysis['secondary_type'] = 'product'
            elif product_score > offer_score and product_score >= 2:
                analysis['primary_type'] = 'product'
                analysis['confidence'] = min(0.9, 0.6 + (product_score * 0.1))
                if offer_score >= 2:
                    analysis['secondary_type'] = 'offer'
            elif offer_score >= 2 and product_score >= 2:
                analysis['primary_type'] = 'mixed'
                analysis['confidence'] = min(0.8, 0.5 + ((offer_score + product_score) * 0.05))
            else:
                analysis['primary_type'] = 'general'
                analysis['confidence'] = 0.3
            
            logger.debug(f"[ActionRecomendaciones] Análisis: {analysis['primary_type']} (confianza: {analysis['confidence']:.2f})")
            logger.debug(f"[ActionRecomendaciones] Scores - Oferta: {offer_score}, Producto: {product_score}")
            
            return analysis
            
        except Exception as e:
            logger.error(f"[ActionRecomendaciones] Error en análisis de recomendación: {e}")
            return {
                'primary_type': 'general',
                'confidence': 0.0,
                'has_commercial_terms': False,
                'has_product_terms': False
            }
    
    def _generate_unified_response(self, analysis: Dict[str, Any], entities: List[Dict]) -> str:
        """
        🆕 NUEVA FUNCIÓN: Genera respuesta personalizada según el análisis unificado
        
        Args:
            analysis: Resultado del análisis de tipo de recomendación
            entities: Lista de entidades detectadas
            
        Returns:
            Mensaje de respuesta personalizado
        """
        try:
            # Extraer entidades relevantes para personalizar
            entity_mentions = []
            for entity in entities:
                entity_value = entity.get("value", "").strip()
                if entity_value and len(entity_value) > 2:
                    entity_mentions.append(entity_value)
            
            # Limitar a máximo 3 entidades para no saturar el mensaje
            entity_mentions = entity_mentions[:3]
            
            primary_type = analysis.get('primary_type', 'general')
            
            # 🎯 MENSAJES SEGÚN TIPO DETECTADO
            
            if primary_type == 'offer':
                if entity_mentions:
                    entities_text = ", ".join(entity_mentions)
                    base_message = f"Entiendo que buscás recomendaciones de ofertas relacionadas con {entities_text}"
                else:
                    base_message = "Perfecto, capturo que querés recomendaciones de ofertas y promociones"
                
                alternative = "buscar ofertas específicas filtrando por producto, descuento o proveedor"
                
            elif primary_type == 'product':
                if entity_mentions:
                    entities_text = ", ".join(entity_mentions)
                    base_message = f"Entiendo que buscás recomendaciones de productos relacionados con {entities_text}"
                else:
                    base_message = "Perfecto, capturo que querés recomendaciones de productos"
                
                alternative = "buscar productos específicos por nombre, categoría o animal"
                
            elif primary_type == 'mixed':
                if entity_mentions:
                    entities_text = ", ".join(entity_mentions)
                    base_message = f"Entiendo que buscás recomendaciones tanto de productos como ofertas relacionadas con {entities_text}"
                else:
                    base_message = "Perfecto, capturo que querés recomendaciones de productos y ofertas"
                
                alternative = "buscar productos específicos o ver ofertas disponibles"
                
            else:  # general
                if entity_mentions:
                    entities_text = ", ".join(entity_mentions)
                    base_message = f"Claro, te entiendo, buscás que te recomiende algo relacionado con {entities_text}"
                else:
                    base_message = "Claro, te entiendo, buscás que te recomiende algo"
                
                alternative = "buscar productos específicos o ver ofertas disponibles"
            
            # 🎨 CONSTRUIR MENSAJE COMPLETO
            full_message = (
                f"{base_message}. "
                f"Por el momento esta funcionalidad no está disponible, pero puedo ayudarte a {alternative}. "
                f"¿Te interesa que busquemos algo en particular?"
            )
            
            logger.debug(f"[ActionRecomendaciones] Mensaje generado para tipo '{primary_type}': '{full_message[:100]}...'")
            
            return full_message
            
        except Exception as e:
            logger.error(f"[ActionRecomendaciones] Error generando mensaje unificado: {e}")
            # Fallback a mensaje genérico
            return (
                "Entiendo que buscás recomendaciones. "
                "Por el momento esta funcionalidad no está disponible, pero puedo ayudarte a "
                "buscar productos específicos o ver ofertas actuales. "
                "¿Qué te interesa encontrar?"
            )