# conversation_state.py - Sistema Unificado de Sugerencias con Mejoras Integradas
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json
import re
import difflib

from rasa_sdk import Tracker
from .helpers import (
    is_search_intent, is_small_talk_intent, detect_sentiment_in_message,
    detect_implicit_intentions, get_intent_info, get_search_type_from_intent
)

logger = logging.getLogger(__name__)

def normalize_pending_suggestion(value):
    """Asegura que pending_suggestion sea un dict o None."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)  # si viene como JSON string
        except Exception:
            return None
    return None

def get_next_expected_intents(intent_name: str) -> List[str]:
    """Obtiene los intents que pueden seguir según la configuración"""
    intent_info = get_intent_info(intent_name)
    return intent_info.get("next_intents", [])

def get_slot_safely(tracker: Tracker, slot_name: str, default_value: Any = None) -> Any:
    """
    Obtiene un slot de forma segura, manejando casos donde el slot no existe
    """
    try:
        value = tracker.get_slot(slot_name)
        return value if value is not None else default_value
    except Exception as e:
        logger.warning(f"Slot '{slot_name}' no existe o no se puede acceder: {e}")
        return default_value

# ESTADO DE CONVERSACION (mantenido igual)
class ConversationState:
    @staticmethod
    def get_conversation_context(tracker: Tracker) -> Dict[str, Any]:
        """Extrae contexto completo usando la configuración centralizada de forma robusta"""
        try:
            current_intent = tracker.latest_message.get("intent", {}).get("name", "")
            confidence = tracker.latest_message.get("intent", {}).get("confidence", 0.0)
            user_message = tracker.latest_message.get("text", "")
            
            # Detectar sentimiento y intenciones implícitas
            sentiment = detect_sentiment_in_message(user_message)
            implicit_intentions = detect_implicit_intentions(user_message)
            
            # Obtener slots de forma segura
            previous_intent = get_slot_safely(tracker, "last_intent_flow")
            user_sentiment = get_slot_safely(tracker, "user_sentiment", "neutral")
            engagement_level = get_slot_safely(tracker, "user_engagement_level", "neutral")
            
            # Slots del sistema de sugerencias unificado
            pending_suggestion = normalize_pending_suggestion(
                get_slot_safely(tracker, "pending_suggestion")
            )
            suggestion_context = get_slot_safely(tracker, "suggestion_context")
            
            # Slots de historial y contexto
            search_history = get_slot_safely(tracker, "search_history", [])
            context_decision_pending = get_slot_safely(tracker, "context_decision_pending", False)
            current_search_params = get_slot_safely(tracker, "current_search_params")
            validation_errors = get_slot_safely(tracker, "validation_errors", [])
            
            # Slots obsoletos - Con manejo graceful
            pedido_incompleto = get_slot_safely(tracker, "pedido_incompleto", False)
            
            # Si pending_suggestion no existe pero pedido_incompleto sí, migrar el concepto
            if not pending_suggestion and pedido_incompleto:
                logger.info("Detectado sistema obsoleto de pedido_incompleto, usando como fallback")
                pending_suggestion = {
                    'suggestion_type': 'missing_parameters',
                    'search_type': 'producto',  # Asumir producto por defecto
                    'awaiting_response': True,
                    'migrated_from_obsolete': True
                }
            
            # Construir contexto completo
            context = {
                'current_intent': current_intent,
                'intent_confidence': confidence,
                'previous_intent': previous_intent,
                'search_history': search_history,
                'entities': tracker.latest_message.get("entities", []),
                'is_search_intent': is_search_intent(current_intent),
                'is_small_talk': is_small_talk_intent(current_intent),
                'is_completion_intent': current_intent == "completar_pedido",
                'expected_next_intents': get_next_expected_intents(previous_intent or ""),
                'context_decision_pending': context_decision_pending,
                'user_message': user_message,
                'detected_sentiment': sentiment,
                'implicit_intentions': implicit_intentions,
                'current_sentiment_slot': user_sentiment,
                'engagement_level': engagement_level,
                
                # Sistema unificado de sugerencias
                'pending_suggestion': pending_suggestion,
                'suggestion_context': suggestion_context,
                'is_confirmation_intent': current_intent in ["afirmar", "denegar"],
                'awaiting_suggestion_response': bool(pending_suggestion),
                
                # Contexto de búsqueda actual
                'current_search_params': current_search_params,
                'validation_errors': validation_errors,
                
                # Información de migración
                'has_obsolete_slots': pedido_incompleto and not pending_suggestion,
                'system_migrated': bool(pending_suggestion and pending_suggestion.get('migrated_from_obsolete')),
            }
            
            logger.debug(f"Contexto extraído - Intent: {current_intent}, Pending: {bool(pending_suggestion)}, Engagement: {engagement_level}")
            
            return context
            
        except Exception as e:
            logger.error(f"Error extrayendo contexto de conversación: {e}", exc_info=True)
            # Retornar contexto mínimo en caso de error
            return {
                'current_intent': tracker.latest_message.get("intent", {}).get("name", ""),
                'intent_confidence': 0.0,
                'previous_intent': None,
                'search_history': [],
                'entities': [],
                'is_search_intent': False,
                'is_small_talk': False,
                'is_completion_intent': False,
                'expected_next_intents': [],
                'context_decision_pending': False,
                'user_message': tracker.latest_message.get("text", ""),
                'detected_sentiment': "neutral",
                'implicit_intentions': [],
                'current_sentiment_slot': "neutral",
                'engagement_level': "neutral",
                'pending_suggestion': None,
                'suggestion_context': None,
                'is_confirmation_intent': False,
                'awaiting_suggestion_response': False,
                'current_search_params': None,
                'validation_errors': [],
                'has_obsolete_slots': False,
                'system_migrated': False,
                'error_in_context_extraction': True
            }

# SISTEMA AVANZADO DE SIMILITUD INTEGRADO
class AdvancedSimilarityMatcher:
    """
    Sistema avanzado de comparación de similitud para términos médicos/veterinarios
    INTEGRADO en conversation_state.py
    """
    
    def __init__(self):
        # Pesos para diferentes algoritmos de similitud
        self.algorithm_weights = {
            'exact_match': 1.0,
            'case_insensitive': 0.95,
            'sequence_matcher': 0.7,
            'substring_match': 0.6,
            'levenshtein_distance': 0.8,
            'soundex_like': 0.5,
            'medical_abbreviation': 0.9
        }
        
        # Patrones especiales para términos médicos
        self.medical_patterns = {
            # Expansiones de abreviaciones
            'iv': ['intravenoso', 'intravenosa', 'endovenoso'],
            'im': ['intramuscular', 'via intramuscular'],
            'po': ['por via oral', 'oral', 'via oral'],
            'sc': ['subcutaneo', 'subcutánea', 'hipodermico'],
            'id': ['intradermal', 'intradermico'],
            'ip': ['intraperitoneal'],
            'ic': ['intracardaco', 'intracardiaco'],
            
            # Unidades de medida
            'mg': ['miligramo', 'miligramos'],
            'ml': ['mililitro', 'mililitros'],
            'kg': ['kilogramo', 'kilogramos'],
            'gr': ['gramo', 'gramos'],
            'ui': ['unidad internacional', 'unidades internacionales'],
            
            # Términos veterinarios comunes
            'felv': ['leucemia felina', 'virus leucemia felina'],
            'fiv': ['inmunodeficiencia felina', 'virus inmunodeficiencia felina'],
            'pif': ['peritonitis infecciosa felina']
        }
    
    def calculate_similarity(self, input_term: str, lookup_term: str, entity_type: str = "") -> float:
        """
        Calcula similitud usando múltiples algoritmos y devuelve score ponderado
        """
        try:
            if not input_term or not lookup_term:
                return 0.0
            
            input_clean = self._normalize_term(input_term)
            lookup_clean = self._normalize_term(lookup_term)
            
            scores = {}
            
            # 1. Coincidencia exacta
            if input_clean == lookup_clean:
                scores['exact_match'] = 1.0
            
            # 2. Coincidencia insensible a mayúsculas
            if input_clean.lower() == lookup_clean.lower():
                scores['case_insensitive'] = 1.0
            
            # 3. SequenceMatcher de difflib
            scores['sequence_matcher'] = difflib.SequenceMatcher(
                None, input_clean.lower(), lookup_clean.lower()
            ).ratio()
            
            # 4. Coincidencia de substring
            scores['substring_match'] = self._substring_similarity(input_clean, lookup_clean)
            
            # 5. Distancia de Levenshtein normalizada
            scores['levenshtein_distance'] = self._levenshtein_similarity(input_clean, lookup_clean)
            
            # 6. Similitud fonética (soundex-like)
            scores['soundex_like'] = self._phonetic_similarity(input_clean, lookup_clean)
            
            # 7. Abreviaciones médicas
            scores['medical_abbreviation'] = self._medical_abbreviation_similarity(input_clean, lookup_clean)
            
            # Calcular score final ponderado
            final_score = 0.0
            total_weight = 0.0
            
            for algorithm, score in scores.items():
                if score > 0:
                    weight = self.algorithm_weights.get(algorithm, 0.1)
                    final_score += score * weight
                    total_weight += weight
            
            # Normalizar por peso total
            if total_weight > 0:
                final_score = final_score / total_weight
            
            # Bonificación por tipo de entidad específico
            if entity_type:
                final_score += self._entity_type_bonus(input_clean, lookup_clean, entity_type)
            
            return min(final_score, 1.0)
            
        except Exception as e:
            logger.error(f"Error calculando similitud entre '{input_term}' y '{lookup_term}': {e}")
            return 0.0
    
    def _normalize_term(self, term: str) -> str:
        """Normaliza términos para comparación"""
        if not term:
            return ""
        
        # Remover acentos y caracteres especiales
        import unicodedata
        normalized = unicodedata.normalize('NFKD', term).encode('ascii', 'ignore').decode('utf-8')
        
        # Limpiar espacios extra
        normalized = re.sub(r'\s+', ' ', normalized.strip())
        
        return normalized
    
    def _substring_similarity(self, term1: str, term2: str) -> float:
        """Calcula similitud basada en substrings"""
        t1_lower = term1.lower()
        t2_lower = term2.lower()
        
        if t1_lower in t2_lower:
            return len(t1_lower) / len(t2_lower)
        elif t2_lower in t1_lower:
            return len(t2_lower) / len(t1_lower)
        
        # Buscar substring común más largo
        longest_common = self._longest_common_substring(t1_lower, t2_lower)
        if longest_common:
            return len(longest_common) / max(len(t1_lower), len(t2_lower))
        
        return 0.0
    
    def _longest_common_substring(self, s1: str, s2: str) -> str:
        """Encuentra la subcadena común más larga"""
        m, n = len(s1), len(s2)
        longest = ""
        
        for i in range(m):
            for j in range(n):
                k = 0
                while (i + k < m and j + k < n and s1[i + k] == s2[j + k]):
                    k += 1
                if k > len(longest):
                    longest = s1[i:i + k]
        
        return longest
    
    def _levenshtein_similarity(self, s1: str, s2: str) -> float:
        """Calcula similitud basada en distancia de Levenshtein"""
        if not s1 or not s2:
            return 0.0
        
        # Implementación simple de distancia de Levenshtein
        m, n = len(s1), len(s2)
        
        # Crear matriz
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        
        # Inicializar primera fila y columna
        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j
        
        # Llenar matriz
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if s1[i-1] == s2[j-1]:
                    dp[i][j] = dp[i-1][j-1]
                else:
                    dp[i][j] = 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
        
        # Convertir distancia a similitud
        max_len = max(m, n)
        if max_len == 0:
            return 1.0
        
        return 1.0 - (dp[m][n] / max_len)
    
    def _phonetic_similarity(self, s1: str, s2: str) -> float:
        """Similitud fonética simple (soundex-like)"""
        def simple_soundex(s):
            if not s:
                return ""
            
            # Convertir a mayúsculas y tomar primera letra
            s = s.upper()
            soundex = s[0]
            
            # Mapeo simple de consonantes
            mapping = {'B': '1', 'F': '1', 'P': '1', 'V': '1',
                      'C': '2', 'G': '2', 'J': '2', 'K': '2', 'Q': '2', 'S': '2', 'X': '2', 'Z': '2',
                      'D': '3', 'T': '3',
                      'L': '4',
                      'M': '5', 'N': '5',
                      'R': '6'}
            
            for char in s[1:]:
                if char in mapping:
                    code = mapping[char]
                    if len(soundex) == 0 or soundex[-1] != code:
                        soundex += code
                if len(soundex) >= 4:
                    break
            
            return soundex.ljust(4, '0')[:4]
        
        try:
            soundex1 = simple_soundex(s1)
            soundex2 = simple_soundex(s2)
            
            if soundex1 == soundex2:
                return 0.8
            elif soundex1[0] == soundex2[0]:  # Misma primera letra
                return 0.4
            else:
                return 0.0
        except:
            return 0.0
    
    def _medical_abbreviation_similarity(self, input_term: str, lookup_term: str) -> float:
        """Similitud específica para abreviaciones médicas"""
        input_lower = input_term.lower()
        lookup_lower = lookup_term.lower()
        
        # Verificar si input es abreviación conocida
        if input_lower in self.medical_patterns:
            expansions = self.medical_patterns[input_lower]
            for expansion in expansions:
                if expansion.lower() in lookup_lower or lookup_lower in expansion.lower():
                    return 0.9
        
        # Verificar lo contrario
        if lookup_lower in self.medical_patterns:
            expansions = self.medical_patterns[lookup_lower]
            for expansion in expansions:
                if expansion.lower() in input_lower or input_lower in expansion.lower():
                    return 0.9
        
        return 0.0
    
    def _entity_type_bonus(self, input_term: str, lookup_term: str, entity_type: str) -> float:
        """Bonificación específica por tipo de entidad"""
        bonus = 0.0
        
        # Bonificaciones específicas para dosis
        if entity_type == 'dosis':
            # Si ambos contienen números y unidades
            input_has_unit = bool(re.search(r'\d+\s*(mg|ml|kg|gr|ui|cc)', input_term.lower()))
            lookup_has_unit = bool(re.search(r'\d+\s*(mg|ml|kg|gr|ui|cc)', lookup_term.lower()))
            
            if input_has_unit and lookup_has_unit:
                bonus += 0.1
        
        # Bonificaciones para empresas/laboratorios
        elif entity_type == 'empresa':
            # Si ambos contienen palabras clave de empresas farmacéuticas
            pharma_keywords = ['lab', 'laboratorio', 'pharma', 'farm', 'medicine', 'vet']
            input_pharma = any(keyword in input_term.lower() for keyword in pharma_keywords)
            lookup_pharma = any(keyword in lookup_term.lower() for keyword in pharma_keywords)
            
            if input_pharma and lookup_pharma:
                bonus += 0.05
        
        return bonus

# MANEJADOR UNIFICADO DE SUGERENCIAS - VERSIÓN MEJORADA INTEGRADA
class SuggestionManager:
    """
    Maneja el estado y flujo unificado de sugerencias con sistema de similitud avanzado integrado
    """
    
    def __init__(self):
        self.similarity_matcher = AdvancedSimilarityMatcher()
        self.confirmation_patterns = self._load_confirmation_patterns()
    
    def _load_confirmation_patterns(self) -> Dict[str, List[str]]:
        """Carga patrones de confirmación/negación más precisos"""
        return {
            'affirmative_high': [
                'sí', 'si', 'yes', 'correcto', 'exacto', 'perfecto', 'ese', 'esa', 'eso es',
                'así es', 'confirmo', 'acepto', 'está bien', 'ok', 'dale', 'afirmativo'
            ],
            'affirmative_medium': [
                'bueno', 'muy bien', 'claro', 'por supuesto', 'desde luego',
                'efectivamente', 'cierto', 'verdad', 'genial', 'excelente', 'bien'
            ],
            'negative_high': [
                'no', 'nada', 'incorrecto', 'mal', 'error', 'equivocado', 
                'rechazar', 'cancelar', 'para nada', 'jamás', 'nunca', 'negativo'
            ],
            'negative_medium': [
                'otro', 'diferente', 'cambiar', 'distinto', 'no es eso',
                'no es correcto', 'de ninguna manera', 'ni loco'
            ],
            'ambiguous': [
                'tal vez', 'quizás', 'puede que', 'no estoy seguro', 'no sé',
                'mmm', 'eh', 'bueno', 'a ver', 'depende', 'más o menos'
            ]
        }
    
    @staticmethod
    def create_entity_suggestion(entity_value: str, entity_type: str, suggestion: str, 
                               search_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Crea una sugerencia para entidad mal escrita"""
        return {
            'suggestion_type': 'entity_correction',
            'original_value': entity_value,
            'entity_type': entity_type,
            'suggestions': [suggestion] if isinstance(suggestion, str) else suggestion,
            'timestamp': datetime.now().isoformat(),
            'search_context': search_context or {},
            'awaiting_response': True,
            'version': '2.0',  # Version mejorada
            'clarification_attempts': 0,
            'created_at': datetime.now().timestamp()
        }
    
    @staticmethod
    def create_type_correction(entity_value: str, wrong_type: str, correct_type: str,
                              search_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Crea una sugerencia para corrección de tipo de entidad"""
        return {
            'suggestion_type': 'type_correction',
            'original_value': entity_value,
            'wrong_type': wrong_type,
            'correct_type': correct_type,
            'timestamp': datetime.now().isoformat(),
            'search_context': search_context or {},
            'awaiting_response': True,
            'version': '2.0',
            'clarification_attempts': 0,
            'created_at': datetime.now().timestamp()
        }
    
    @staticmethod
    def create_parameter_suggestion(search_type: str, intent_name: str, criteria: str,
                                  current_parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Crea una sugerencia para parámetros faltantes"""
        return {
            'suggestion_type': 'missing_parameters',
            'search_type': search_type,
            'intent_name': intent_name,
            'required_criteria': criteria,
            'current_parameters': current_parameters or {},
            'timestamp': datetime.now().isoformat(),
            'search_context': {
                'search_type': search_type,
                'intent': intent_name
            },
            'awaiting_response': True,
            'version': '2.0',
            'clarification_attempts': 0,
            'created_at': datetime.now().timestamp()
        }
    
    def find_similar_terms(self, input_value: str, entity_type: str, max_suggestions: int = 3,
                          min_similarity: float = 0.6) -> List[Dict[str, Any]]:
        """
        NUEVA FUNCIÓN INTEGRADA: Encuentra términos similares usando el sistema avanzado de similitud
        """
        try:
            # Intentar usar ConfigManager
            try:
                from actions.config import get_lookup_tables
                lookup_tables = get_lookup_tables()
                _has_config = True
            except ImportError:
                logger.warning("ConfigManager no disponible, usando fallback básico")
                lookup_tables = {}
                _has_config = False
            
            if not lookup_tables or entity_type not in lookup_tables:
                logger.debug(f"No hay lookup table para entidad '{entity_type}'")
                return self._fallback_similarity_search(input_value, entity_type, max_suggestions)
            
            candidates = []
            lookup_values = lookup_tables[entity_type]
            
            logger.debug(f"Buscando términos similares a '{input_value}' en {len(lookup_values)} valores de '{entity_type}'")
            
            for lookup_value in lookup_values:
                try:
                    similarity_score = self.similarity_matcher.calculate_similarity(
                        input_value, lookup_value, entity_type
                    )
                    
                    if similarity_score >= min_similarity:
                        candidates.append({
                            'suggestion': lookup_value,
                            'similarity': similarity_score,
                            'entity_type': entity_type,
                            'original_input': input_value,
                            'match_confidence': self._classify_match_confidence(similarity_score)
                        })
                        
                        logger.debug(f"Candidato encontrado: '{lookup_value}' (similitud: {similarity_score:.3f})")
                        
                except Exception as e:
                    logger.error(f"Error calculando similitud para '{lookup_value}': {e}")
                    continue
            
            # Ordenar por similitud descendente
            candidates.sort(key=lambda x: x['similarity'], reverse=True)
            
            # Aplicar post-procesamiento
            processed_candidates = self._post_process_suggestions(candidates, input_value, entity_type)
            
            result = processed_candidates[:max_suggestions]
            
            logger.info(f"Encontradas {len(result)} sugerencias para '{input_value}' ({entity_type})")
            for i, candidate in enumerate(result):
                logger.info(f"  {i+1}. {candidate['suggestion']} (sim: {candidate['similarity']:.3f})")
            
            return result
            
        except Exception as e:
            logger.error(f"Error buscando términos similares para '{input_value}': {e}", exc_info=True)
            return []
    
    def _classify_match_confidence(self, similarity_score: float) -> str:
        """Clasifica la confianza del match"""
        if similarity_score >= 0.9:
            return 'very_high'
        elif similarity_score >= 0.8:
            return 'high'
        elif similarity_score >= 0.7:
            return 'medium'
        elif similarity_score >= 0.6:
            return 'low'
        else:
            return 'very_low'
    
    def _post_process_suggestions(self, candidates: List[Dict[str, Any]], 
                                 input_value: str, entity_type: str) -> List[Dict[str, Any]]:
        """Post-procesa sugerencias para mejorar relevancia"""
        if not candidates:
            return candidates
        
        # Filtrar duplicados muy similares
        filtered_candidates = []
        for candidate in candidates:
            is_duplicate = False
            for existing in filtered_candidates:
                if self.similarity_matcher.calculate_similarity(
                    candidate['suggestion'], existing['suggestion']
                ) > 0.95:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                filtered_candidates.append(candidate)
        
        # Boost para términos que empiezan igual
        input_lower = input_value.lower()
        for candidate in filtered_candidates:
            suggestion_lower = candidate['suggestion'].lower()
            if suggestion_lower.startswith(input_lower[:3]) and len(input_lower) >= 3:
                candidate['similarity'] += 0.05
                candidate['boost_reason'] = 'prefix_match'
        
        # Re-ordenar después de boosts
        filtered_candidates.sort(key=lambda x: x['similarity'], reverse=True)
        
        return filtered_candidates
    
    def _fallback_similarity_search(self, input_value: str, entity_type: str, 
                                   max_suggestions: int) -> List[Dict[str, Any]]:
        """Búsqueda de fallback cuando no hay ConfigManager"""
        try:
            # Usar difflib básico como fallback
            sample_values = {
                'empresa': ['Bayer', 'Merial', 'Zoetis', 'Virbac', 'Boehringer'],
                'categoria': ['antibiotico', 'antiparasitario', 'vacuna', 'analgesico'],
                'animal': ['perro', 'gato', 'bovino', 'equino', 'ovino'],
                'dosis': ['10mg', '5ml', '2.5mg/kg', '1 comprimido']
            }
            
            lookup_values = sample_values.get(entity_type, [])
            if not lookup_values:
                return []
            
            suggestions = difflib.get_close_matches(
                input_value, lookup_values, n=max_suggestions, cutoff=0.6
            )
            
            return [
                {
                    'suggestion': suggestion,
                    'similarity': 0.7,  # Score estimado
                    'entity_type': entity_type,
                    'original_input': input_value,
                    'match_confidence': 'medium',
                    'fallback_mode': True
                }
                for suggestion in suggestions
            ]
            
        except Exception as e:
            logger.error(f"Error en búsqueda de fallback: {e}")
            return []
    
    def analyze_confirmation_response(self, user_message: str, current_intent: str, 
                                    pending_suggestion: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        NUEVA FUNCIÓN INTEGRADA: Analiza respuesta del usuario para determinar confirmación/negación con mayor precisión
        """
        try:
            user_lower = user_message.lower().strip()
            
            analysis = {
                'is_affirmative': False,
                'is_negative': False,
                'is_ambiguous': False,
                'confidence': 0.0,
                'detected_patterns': [],
                'intent_boost': 0.0,
                'context_clues': []
            }
            
            # Boost por intent explícito (prioridad máxima)
            if current_intent == "afirmar":
                analysis['is_affirmative'] = True
                analysis['confidence'] = 0.95
                analysis['intent_boost'] = 0.95
                analysis['detected_patterns'].append('intent_afirmar')
                logger.debug("Confirmación detectada por intent 'afirmar'")
                return analysis
                
            elif current_intent == "denegar":
                analysis['is_negative'] = True
                analysis['confidence'] = 0.95
                analysis['intent_boost'] = 0.95
                analysis['detected_patterns'].append('intent_denegar')
                logger.debug("Negación detectada por intent 'denegar'")
                return analysis
            
            # Análisis de patrones en el texto
            affirmative_score = 0.0
            negative_score = 0.0
            ambiguous_score = 0.0
            
            # Verificar patrones afirmativos
            for pattern in self.confirmation_patterns['affirmative_high']:
                if pattern in user_lower:
                    affirmative_score = max(affirmative_score, 0.9)
                    analysis['detected_patterns'].append(f'aff_high_{pattern}')
            
            for pattern in self.confirmation_patterns['affirmative_medium']:
                if pattern in user_lower:
                    affirmative_score = max(affirmative_score, 0.75)
                    analysis['detected_patterns'].append(f'aff_med_{pattern}')
            
            # Verificar patrones negativos
            for pattern in self.confirmation_patterns['negative_high']:
                if pattern in user_lower:
                    negative_score = max(negative_score, 0.9)
                    analysis['detected_patterns'].append(f'neg_high_{pattern}')
            
            for pattern in self.confirmation_patterns['negative_medium']:
                if pattern in user_lower:
                    negative_score = max(negative_score, 0.75)
                    analysis['detected_patterns'].append(f'neg_med_{pattern}')
            
            # Verificar patrones ambiguos
            for pattern in self.confirmation_patterns['ambiguous']:
                if pattern in user_lower:
                    ambiguous_score = max(ambiguous_score, 0.8)
                    analysis['detected_patterns'].append(f'ambig_{pattern}')
            
            # Análisis contextual específico para sugerencias
            if pending_suggestion:
                context_analysis = self._analyze_suggestion_context(user_message, pending_suggestion)
                affirmative_score += context_analysis['affirmative_bonus']
                negative_score += context_analysis['negative_bonus']
                analysis['context_clues'] = context_analysis['clues']
            
            # Determinar resultado final
            if ambiguous_score >= 0.6:
                analysis['is_ambiguous'] = True
                analysis['confidence'] = ambiguous_score
            elif affirmative_score > negative_score and affirmative_score >= 0.5:
                analysis['is_affirmative'] = True
                analysis['confidence'] = min(affirmative_score, 1.0)
            elif negative_score > affirmative_score and negative_score >= 0.5:
                analysis['is_negative'] = True
                analysis['confidence'] = min(negative_score, 1.0)
            else:
                analysis['is_ambiguous'] = True
                analysis['confidence'] = 0.3
            
            logger.debug(f"Análisis de confirmación: {analysis}")
            return analysis
            
        except Exception as e:
            logger.error(f"Error analizando respuesta de confirmación: {e}")
            return {
                'is_affirmative': False,
                'is_negative': False,
                'is_ambiguous': True,
                'confidence': 0.0,
                'detected_patterns': [],
                'intent_boost': 0.0,
                'context_clues': [],
                'error': str(e)
            }
    
    def _analyze_suggestion_context(self, user_message: str, 
                                   pending_suggestion: Dict[str, Any]) -> Dict[str, Any]:
        """Analiza el contexto específico de la sugerencia para mejorar detección"""
        try:
            clues = []
            affirmative_bonus = 0.0
            negative_bonus = 0.0
            
            user_lower = user_message.lower()
            suggestion_type = pending_suggestion.get('suggestion_type', '')
            
            if suggestion_type == 'entity_correction':
                # Buscar si menciona la sugerencia específica
                suggestions = pending_suggestion.get('suggestions', [])
                original_value = pending_suggestion.get('original_value', '')
                
                for suggestion in suggestions:
                    suggestion_lower = suggestion.lower()
                    # Coincidencia exacta con la sugerencia
                    if suggestion_lower in user_lower:
                        affirmative_bonus += 0.3
                        clues.append(f'mentions_suggestion: {suggestion}')
                    # Coincidencia parcial significativa
                    elif len(suggestion_lower) > 3 and suggestion_lower[:4] in user_lower:
                        affirmative_bonus += 0.15
                        clues.append(f'partial_suggestion_match: {suggestion}')
                
                # Si menciona el valor original, puede estar reafirmando o negando
                if original_value.lower() in user_lower:
                    # Contexto indica negación
                    if any(neg in user_lower for neg in ['no es', 'no se llama', 'no quiero']):
                        negative_bonus += 0.2
                        clues.append('rejects_original_with_negation')
                    else:
                        # Solo menciona original, probablemente confundido
                        clues.append('mentions_original_ambiguous')
                
                # Patrones de aceptación de corrección
                acceptance_patterns = ['ese sí', 'esa es', 'correcto', 'exacto', 'ese producto', 'esa empresa']
                for pattern in acceptance_patterns:
                    if pattern in user_lower:
                        affirmative_bonus += 0.25
                        clues.append(f'acceptance_pattern: {pattern}')
            
            elif suggestion_type == 'type_correction':
                correct_type = pending_suggestion.get('correct_type', '')
                original_value = pending_suggestion.get('original_value', '')
                
                # Si menciona el tipo correcto explícitamente
                if correct_type.lower() in user_lower:
                    affirmative_bonus += 0.25
                    clues.append(f'mentions_correct_type: {correct_type}')
                
                # Patrones de confirmación de tipo
                if any(pattern in user_lower for pattern in ['es una empresa', 'es un laboratorio', 'es marca']):
                    affirmative_bonus += 0.3
                    clues.append('confirms_entity_type')
            
            elif suggestion_type == 'missing_parameters':
                # Para parámetros faltantes, buscar si está proporcionando información
                search_type = pending_suggestion.get('search_type', '')
                
                # Patrones de provisión de información
                info_patterns = ['quiero', 'busco', 'necesito', 'me interesa', 'para', 'con']
                for pattern in info_patterns:
                    if pattern in user_lower:
                        affirmative_bonus += 0.1
                        clues.append(f'provides_info_pattern: {pattern}')
                
                # Si menciona criterios de búsqueda específicos
                search_criteria = ['producto', 'categoria', 'empresa', 'laboratorio', 'dosis', 'animal']
                mentioned_criteria = [criteria for criteria in search_criteria if criteria in user_lower]
                if mentioned_criteria:
                    affirmative_bonus += 0.2
                    clues.append(f'mentions_search_criteria: {mentioned_criteria}')
            
            return {
                'clues': clues,
                'affirmative_bonus': affirmative_bonus,
                'negative_bonus': negative_bonus
            }
            
        except Exception as e:
            logger.error(f"Error analizando contexto de sugerencia: {e}")
            return {'clues': [], 'affirmative_bonus': 0.0, 'negative_bonus': 0.0}
    
    def create_enhanced_suggestion(self, entity_value: str, entity_type: str, 
                                 search_context: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """
        NUEVA FUNCIÓN INTEGRADA: Crea una sugerencia mejorada con múltiples opciones y metadata
        """
        try:
            # Buscar términos similares usando el sistema avanzado
            similar_terms = self.find_similar_terms(
                entity_value, entity_type, max_suggestions=3, min_similarity=0.6
            )
            
            if not similar_terms:
                logger.debug(f"No se encontraron términos similares para '{entity_value}' ({entity_type})")
                return None
            
            # Crear sugerencia con metadata enriquecida
            suggestion = {
                'suggestion_type': 'entity_correction',
                'original_value': entity_value,
                'entity_type': entity_type,
                'suggestions': [term['suggestion'] for term in similar_terms],
                'metadata': {
                    'similarity_scores': [term['similarity'] for term in similar_terms],
                    'match_confidences': [term['match_confidence'] for term in similar_terms],
                    'search_method': 'advanced_similarity_integrated',
                    'total_candidates_found': len(similar_terms)
                },
                'timestamp': datetime.now().isoformat(),
                'search_context': search_context or {},
                'awaiting_response': True,
                'version': '2.0',  # Versión integrada mejorada
                'clarification_attempts': 0,
                'created_at': datetime.now().timestamp(),
                
                # Información para generar mensaje más inteligente
                'best_match': similar_terms[0] if similar_terms else None,
                'confidence_level': similar_terms[0]['match_confidence'] if similar_terms else 'low'
            }
            
            logger.info(f"Sugerencia integrada mejorada creada para '{entity_value}': {suggestion['suggestions']}")
            return suggestion
            
        except Exception as e:
            logger.error(f"Error creando sugerencia integrada mejorada: {e}", exc_info=True)
            return None
    
    def format_suggestion_message(self, suggestion: Dict[str, Any]) -> str:
        """
        NUEVA FUNCIÓN INTEGRADA: Genera mensaje de sugerencia más inteligente basado en confianza y contexto
        """
        try:
            original_value = suggestion.get('original_value', '')
            suggestions_list = suggestion.get('suggestions', [])
            entity_type = suggestion.get('entity_type', '')
            confidence_level = suggestion.get('confidence_level', 'medium')
            
            if not suggestions_list:
                return f"No encontré '{original_value}' como {entity_type} válido. ¿Podrías verificar la ortografía?"
            
            best_suggestion = suggestions_list[0]
            
            # Personalizar mensaje según confianza
            if confidence_level == 'very_high':
                return f"'{original_value}' no es exacto. ¿Te refieres a '{best_suggestion}'?"
            
            elif confidence_level == 'high':
                return f"No encontré '{original_value}'. ¿Querías decir '{best_suggestion}'?"
            
            elif confidence_level == 'medium':
                if len(suggestions_list) == 1:
                    return f"'{original_value}' no está en mis registros. ¿Te refieres a '{best_suggestion}'?"
                else:
                    return f"'{original_value}' no es válido. ¿Te refieres a '{best_suggestion}' o '{suggestions_list[1]}'?"
            
            else:  # low confidence
                if len(suggestions_list) > 1:
                    suggestions_text = "', '".join(suggestions_list[:2])
                    return f"No encontré '{original_value}'. ¿Podrías elegir entre '{suggestions_text}' o escribir el nombre correcto?"
                else:
                    return f"No encontré '{original_value}'. ¿Te refieres a '{best_suggestion}' o podrías especificar mejor?"
            
        except Exception as e:
            logger.error(f"Error formateando mensaje de sugerencia: {e}")
            return f"No encontré '{original_value}'. ¿Podrías verificar la ortografía?"
    
    # === FUNCIONES ORIGINALES MANTENIDAS ===
    
    @staticmethod
    def check_if_suggestion_ignored(current_intent: str, pending_suggestion: Dict[str, Any], 
                                   is_small_talk: bool = False) -> bool:
        """
        Verifica si el usuario ignoró la sugerencia con lógica más sofisticada
        """
        if not pending_suggestion:
            return False
        
        try:
            suggestion_type = pending_suggestion.get('suggestion_type', '')
            
            # Small talk definitivamente ignora cualquier sugerencia
            if is_small_talk:
                logger.debug("[SuggestionManager] Sugerencia ignorada: usuario cambió a small talk")
                return True
             
            # Verificar timeout automático (sugerencias muy antiguas)
            created_at = pending_suggestion.get('created_at', 0)
            if created_at > 0:
                age_minutes = (datetime.now().timestamp() - created_at) / 60
                if age_minutes > 15:  # Sugerencias de más de 15 minutos se consideran ignoradas
                    logger.debug(f"[SuggestionManager] Sugerencia ignorada por timeout: {age_minutes:.1f} minutos de antigüedad")
                    return True
            
            # Lógica específica por tipo de sugerencia
            if suggestion_type == 'missing_parameters':
                suggested_search_type = pending_suggestion.get('search_type', '')
                
                # Si es completar_pedido, NO está ignorando
                if current_intent == 'completar_pedido':
                    return False
                
                # Si es una búsqueda del mismo tipo, NO está ignorando
                if current_intent.startswith('buscar_'):
                    current_search_type = get_search_type_from_intent(current_intent)
                    if current_search_type == suggested_search_type:
                        logger.debug(f"[SuggestionManager] Usuario sigue la sugerencia: mismo tipo de búsqueda ({current_search_type})")
                        return False
                    else:
                        logger.debug(f"[SuggestionManager] Sugerencia ignorada: cambio de tipo de búsqueda {suggested_search_type} -> {current_search_type}")
                        return True
                
                # Si es un intent de consulta relacionado, probablemente NO está ignorando
                consultation_intents = ['consultar_novedades_producto', 'consultar_novedades_oferta', 
                                      'consultar_recomendaciones_producto', 'consultar_recomendaciones_oferta']
                if current_intent in consultation_intents:
                    # Verificar si es el mismo dominio (producto/oferta)
                    if 'producto' in current_intent and suggested_search_type == 'producto':
                        return False
                    elif 'oferta' in current_intent and suggested_search_type == 'oferta':
                        return False
                    else:
                        logger.debug(f"[SuggestionManager] Sugerencia ignorada: consulta de diferente dominio")
                        return True
                
                # Si el usuario hace preguntas genéricas, NO está ignorando necesariamente
                generic_intents = ['saludar', 'preguntar_capacidades', 'solicitar_ayuda']
                if current_intent in generic_intents:
                    return False
            
            elif suggestion_type in ['entity_correction', 'type_correction']:
                suggested_search_context = pending_suggestion.get('search_context', {})
                suggested_search_type = suggested_search_context.get('search_type', '')
                
                # Si es una búsqueda de diferente tipo, está ignorando la sugerencia
                if current_intent.startswith('buscar_'):
                    current_search_type = get_search_type_from_intent(current_intent)
                    if current_search_type != suggested_search_type and suggested_search_type:
                        logger.debug(f"[SuggestionManager] Sugerencia de corrección ignorada: cambio de búsqueda {suggested_search_type} -> {current_search_type}")
                        return True
                    else:
                        # Mismo tipo de búsqueda, pero ¿es con diferentes parámetros completamente nuevos?
                        return SuggestionManager._check_if_completely_new_search(pending_suggestion, current_intent)
                
                # Si empieza una consulta diferente, probablemente está ignorando
                consultation_intents = ['consultar_novedades_producto', 'consultar_novedades_oferta']
                if current_intent in consultation_intents:
                    return True
                
                # Si hace una pregunta genérica, NO está ignorando
                generic_intents = ['saludar', 'preguntar_capacidades', 'solicitar_ayuda']
                if current_intent in generic_intents:
                    return False
            
            # Por defecto, si no es un intent relacionado, probablemente está ignorando
            related_intents = ['afirmar', 'denegar', 'completar_pedido', 'saludar', 'preguntar_capacidades', 'solicitar_ayuda']
            if current_intent not in related_intents and not current_intent.startswith('buscar_') and not current_intent.startswith('consultar_'):
                logger.debug(f"[SuggestionManager] Sugerencia probablemente ignorada: intent no relacionado ({current_intent})")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"[SuggestionManager] Error verificando si se ignoró la sugerencia: {e}")
            return False
    
    @staticmethod
    def _check_if_completely_new_search(pending_suggestion: Dict[str, Any], current_intent: str) -> bool:
        """Verifica si es una búsqueda completamente nueva ignorando la corrección"""
        try:
            # Esta función necesitaría acceso a las entidades actuales para comparar
            # Por ahora, asumimos que si es el mismo tipo de búsqueda, no está ignorando
            # En una implementación más completa, compararías las entidades actuales con las de la sugerencia
            
            suggestion_type = pending_suggestion.get('suggestion_type', '')
            
            # Para correcciones de entidad/tipo, si el usuario hace la misma búsqueda pero con
            # entidades completamente diferentes, podría estar ignorando
            # Esta lógica se puede refinar con acceso a las entidades actuales
            
            return False  # Por seguridad, asumir que no está ignorando
            
        except Exception as e:
            logger.error(f"[SuggestionManager] Error verificando si es búsqueda nueva: {e}")
            return False
    
    @staticmethod
    def check_if_suggestion_followed(current_intent: str, pending_suggestion: Dict[str, Any]) -> bool:
        """Verifica si el usuario está siguiendo una sugerencia"""
        if not pending_suggestion:
            return False
        
        try:
            suggestion_type = pending_suggestion.get('suggestion_type', '')
            
            if suggestion_type == 'missing_parameters':
                suggested_search_type = pending_suggestion.get('search_type', '')
                
                # Si es completar_pedido, definitivamente está siguiendo la sugerencia
                if current_intent == 'completar_pedido':
                    logger.debug("[SuggestionManager] Usuario sigue sugerencia: completar_pedido")
                    return True
                
                # Si es una búsqueda del mismo tipo, está siguiendo la sugerencia
                if current_intent.startswith('buscar_'):
                    current_search_type = get_search_type_from_intent(current_intent)
                    if current_search_type == suggested_search_type:
                        logger.debug(f"[SuggestionManager] Usuario sigue sugerencia: misma búsqueda ({current_search_type})")
                        return True
                
                # Si es una consulta relacionada del mismo dominio
                if current_intent.startswith('consultar_'):
                    if 'producto' in current_intent and suggested_search_type == 'producto':
                        return True
                    elif 'oferta' in current_intent and suggested_search_type == 'oferta':
                        return True
            
            elif suggestion_type in ['entity_correction', 'type_correction']:
                # Para correcciones, si hace la misma búsqueda, probablemente la está siguiendo
                suggested_search_context = pending_suggestion.get('search_context', {})
                suggested_search_type = suggested_search_context.get('search_type', '')
                
                if current_intent.startswith('buscar_'):
                    current_search_type = get_search_type_from_intent(current_intent)
                    if current_search_type == suggested_search_type:
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"[SuggestionManager] Error verificando si se siguió la sugerencia: {e}")
            return False
    
    @staticmethod
    def should_auto_cleanup_suggestion(pending_suggestion: Dict[str, Any], 
                                     current_context: Dict[str, Any]) -> Dict[str, Any]:
        """Determina si una sugerencia debe limpiarse automáticamente y por qué"""
        try:
            if not pending_suggestion:
                return {'should_cleanup': False, 'reason': 'no_suggestion'}
            
            cleanup_reasons = []
            should_cleanup = False
            
            # 1. Verificar timeout
            created_at = pending_suggestion.get('created_at', 0)
            if created_at > 0:
                age_minutes = (datetime.now().timestamp() - created_at) / 60
                if age_minutes > 15:
                    cleanup_reasons.append(f'timeout_exceeded_{age_minutes:.1f}min')
                    should_cleanup = True
            
            # 2. Verificar intentos de clarificación excesivos
            clarification_attempts = pending_suggestion.get('clarification_attempts', 0)
            if clarification_attempts >= 3:
                cleanup_reasons.append(f'excessive_clarification_attempts_{clarification_attempts}')
                should_cleanup = True
            
            # 3. Verificar si fue ignorada según el contexto actual
            is_ignored = SuggestionManager.check_if_suggestion_ignored(
                current_context.get('current_intent', ''),
                pending_suggestion,
                current_context.get('is_small_talk', False)
            )
            if is_ignored:
                cleanup_reasons.append('suggestion_ignored')
                should_cleanup = True
            
            # 4. Verificar inconsistencias en los datos de la sugerencia
            validation_result = SuggestionManager.validate_suggestion_data(pending_suggestion)
            if not validation_result['valid']:
                cleanup_reasons.append(f'invalid_data_{validation_result.get("reason", "unknown")}')
                should_cleanup = True
            
            return {
                'should_cleanup': should_cleanup,
                'reasons': cleanup_reasons,
                'primary_reason': cleanup_reasons[0] if cleanup_reasons else None,
                'suggestion_age_minutes': (datetime.now().timestamp() - created_at) / 60 if created_at > 0 else 0,
                'clarification_attempts': clarification_attempts
            }
            
        except Exception as e:
            logger.error(f"[SuggestionManager] Error determinando limpieza automática: {e}")
            return {
                'should_cleanup': True,
                'reasons': ['error_in_analysis'],
                'primary_reason': 'error_in_analysis'
            }
    
    @staticmethod
    def get_cleanup_message(cleanup_analysis: Dict[str, Any], suggestion_type: str) -> Optional[str]:
        """Genera mensaje apropiado para la limpieza de sugerencia"""
        try:
            if not cleanup_analysis.get('should_cleanup'):
                return None
            
            primary_reason = cleanup_analysis.get('primary_reason', '')
            
            # Mensajes específicos por razón de limpieza
            if 'timeout_exceeded' in primary_reason:
                if suggestion_type == 'missing_parameters':
                    return "Entiendo que quieres hacer una nueva búsqueda. Te ayudo con tu nueva consulta."
                elif suggestion_type in ['entity_correction', 'type_correction']:
                    return "Perfecto, te ayudo con tu nueva búsqueda."
                else:
                    return "Te ayudo con tu nueva consulta."
            
            elif 'excessive_clarification' in primary_reason:
                return "Empecemos de nuevo con tu búsqueda."
            
            elif primary_reason == 'suggestion_ignored':
                if suggestion_type == 'missing_parameters':
                    return "Te ayudo con esta nueva búsqueda."
                elif suggestion_type == 'entity_correction':
                    return "Entiendo que prefieres hacer una nueva búsqueda. Te ayudo con tu nueva consulta."
                elif suggestion_type == 'type_correction':
                    return "Perfecto, te ayudo con esta nueva búsqueda."
                else:
                    return "Te ayudo con tu nueva consulta."
            
            elif 'invalid_data' in primary_reason:
                return None  # No enviar mensaje para problemas técnicos
            
            # Mensaje genérico de fallback
            return "Te ayudo con tu nueva consulta."
            
        except Exception as e:
            logger.error(f"[SuggestionManager] Error generando mensaje de limpieza: {e}")
            return None
    
    @staticmethod
    def handle_suggestion_response(context: Dict[str, Any], user_response: str) -> Dict[str, Any]:
        """Procesa la respuesta del usuario a cualquier tipo de sugerencia"""
        pending = context.get('pending_suggestion')
        if not pending:
            return {'handled': False, 'reason': 'no_pending_suggestion'}
        
        try:
            suggestion_type = pending.get('suggestion_type', '')
            response_lower = user_response.lower().strip()
            
            # Detectar respuestas afirmativas y negativas con más patrones
            affirmative_patterns = [
                "sí", "si", "ok", "dale", "perfecto", "correcto", "exacto", "ese", "esa", 
                "claro", "muy bien", "está bien", "bueno", "ya", "confirmo", "acepto"
            ]
            negative_patterns = [
                "no", "nada", "incorrecto", "otro", "diferente", "mal", "error", 
                "cancelar", "salir", "cambiar", "rechazar"
            ]
            
            is_affirmative = any(pattern in response_lower for pattern in affirmative_patterns)
            is_negative = any(pattern in response_lower for pattern in negative_patterns)
            
            result = {
                'handled': True,
                'is_affirmative': is_affirmative,
                'is_negative': is_negative,
                'suggestion_data': pending,
                'suggestion_type': suggestion_type,
                'processing_timestamp': datetime.now().isoformat()
            }
            
            if suggestion_type == 'entity_correction':
                if is_affirmative:
                    result['action'] = 'accept_suggestion'
                    suggestions = pending.get('suggestions', [])
                    result['corrected_entity'] = {
                        'value': suggestions[0] if suggestions else pending.get('original_value'),
                        'type': pending['entity_type']
                    }
                elif is_negative:
                    result['action'] = 'reject_suggestion'
                else:
                    result['action'] = 'unclear_response'
            
            elif suggestion_type == 'type_correction':
                if is_affirmative:
                    result['action'] = 'accept_type_correction'
                    result['corrected_entity'] = {
                        'value': pending['original_value'],
                        'type': pending['correct_type']
                    }
                elif is_negative:
                    result['action'] = 'reject_suggestion'
                else:
                    result['action'] = 'unclear_response'
            
            elif suggestion_type == 'missing_parameters':
                # Para parámetros faltantes, cualquier intent de búsqueda o completar_pedido
                # del mismo tipo se considera como "siguiendo la sugerencia"
                result['action'] = 'parameters_being_provided'
            
            return result
            
        except Exception as e:
            logger.error(f"[SuggestionManager] Error procesando respuesta a sugerencia: {e}", exc_info=True)
            return {
                'handled': False, 
                'reason': 'processing_error',
                'error': str(e)
            }
    
    @staticmethod
    def validate_suggestion_data(suggestion_data: Dict[str, Any]) -> Dict[str, Any]:
        """Valida que los datos de sugerencia sean correctos"""
        if not suggestion_data:
            return {'valid': False, 'reason': 'empty_suggestion'}
        
        required_fields = ['suggestion_type', 'timestamp', 'awaiting_response']
        missing_fields = [field for field in required_fields if field not in suggestion_data]
        
        if missing_fields:
            return {
                'valid': False, 
                'reason': 'missing_required_fields',
                'missing_fields': missing_fields
            }
        
        suggestion_type = suggestion_data.get('suggestion_type')
        valid_types = ['entity_correction', 'type_correction', 'missing_parameters']
        
        if suggestion_type not in valid_types:
            return {
                'valid': False,
                'reason': 'invalid_suggestion_type',
                'provided_type': suggestion_type,
                'valid_types': valid_types
            }
        
        # Validaciones específicas por tipo
        if suggestion_type == 'entity_correction':
            required_entity_fields = ['original_value', 'entity_type', 'suggestions']
            missing_entity_fields = [field for field in required_entity_fields if field not in suggestion_data]
            if missing_entity_fields:
                return {
                    'valid': False,
                    'reason': 'missing_entity_correction_fields',
                    'missing_fields': missing_entity_fields
                }
            
            # Validar que suggestions no esté vacío
            suggestions = suggestion_data.get('suggestions', [])
            if not suggestions or (isinstance(suggestions, list) and len(suggestions) == 0):
                return {
                    'valid': False,
                    'reason': 'empty_suggestions_list'
                }
        
        elif suggestion_type == 'type_correction':
            required_type_fields = ['original_value', 'wrong_type', 'correct_type']
            missing_type_fields = [field for field in required_type_fields if field not in suggestion_data]
            if missing_type_fields:
                return {
                    'valid': False,
                    'reason': 'missing_type_correction_fields',
                    'missing_fields': missing_type_fields
                }
        
        elif suggestion_type == 'missing_parameters':
            required_param_fields = ['search_type', 'required_criteria']
            missing_param_fields = [field for field in required_param_fields if field not in suggestion_data]
            if missing_param_fields:
                return {
                    'valid': False,
                    'reason': 'missing_parameter_suggestion_fields',
                    'missing_fields': missing_param_fields
                }
        
        # Validar timestamp
        timestamp = suggestion_data.get('timestamp')
        try:
            datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return {
                'valid': False,
                'reason': 'invalid_timestamp_format',
                'timestamp': timestamp
            }
        
        return {'valid': True}
    
    @staticmethod
    def migrate_from_obsolete_system(tracker: Tracker) -> Optional[Dict[str, Any]]:
        """Migra desde el sistema obsoleto de pedido_incompleto al nuevo sistema unificado"""
        try:
            pedido_incompleto = get_slot_safely(tracker, "pedido_incompleto", False)
            
            if pedido_incompleto:
                logger.info("[SuggestionManager] Migrando desde sistema obsoleto pedido_incompleto")
                
                # Crear sugerencia equivalente
                return SuggestionManager.create_parameter_suggestion(
                    search_type="producto",  # Asumir producto por defecto
                    intent_name="buscar_producto",
                    criteria="producto, categoría o proveedor",
                    current_parameters={}
                )
            
            return None
            
        except Exception as e:
            logger.error(f"[SuggestionManager] Error migrando desde sistema obsoleto: {e}")
            return None
    
    @staticmethod
    def get_suggestion_summary(pending_suggestion: Dict[str, Any]) -> str:
        """Genera un resumen legible de la sugerencia pendiente"""
        try:
            if not pending_suggestion:
                return "Sin sugerencia pendiente"
            
            suggestion_type = pending_suggestion.get('suggestion_type', 'unknown')
            created_at = pending_suggestion.get('created_at', 0)
            clarification_attempts = pending_suggestion.get('clarification_attempts', 0)
            
            age_minutes = (datetime.now().timestamp() - created_at) / 60 if created_at > 0 else 0
            
            if suggestion_type == 'entity_correction':
                original = pending_suggestion.get('original_value', '')
                suggestions = pending_suggestion.get('suggestions', [])
                suggestion_text = suggestions[0] if suggestions else ''
                return f"Corrección de entidad: '{original}' -> '{suggestion_text}' (edad: {age_minutes:.1f}min, intentos: {clarification_attempts})"
            
            elif suggestion_type == 'type_correction':
                original = pending_suggestion.get('original_value', '')
                correct_type = pending_suggestion.get('correct_type', '')
                return f"Corrección de tipo: '{original}' como {correct_type} (edad: {age_minutes:.1f}min, intentos: {clarification_attempts})"
            
            elif suggestion_type == 'missing_parameters':
                search_type = pending_suggestion.get('search_type', '')
                criteria = pending_suggestion.get('required_criteria', '')
                return f"Parámetros faltantes: {search_type} - {criteria} (edad: {age_minutes:.1f}min, intentos: {clarification_attempts})"
            
            else:
                return f"Sugerencia tipo {suggestion_type} (edad: {age_minutes:.1f}min, intentos: {clarification_attempts})"
                
        except Exception as e:
            logger.error(f"[SuggestionManager] Error generando resumen de sugerencia: {e}")
            return "Error generando resumen"

# Instancia global del SuggestionManager mejorado
suggestion_manager = SuggestionManager()

# Funciones de conveniencia para compatibilidad
def get_improved_suggestions(entity_value: str, entity_type: str, max_suggestions: int = 3) -> List[Dict[str, Any]]:
    """Función de conveniencia para obtener sugerencias mejoradas"""
    return suggestion_manager.find_similar_terms(entity_value, entity_type, max_suggestions)

def analyze_user_confirmation(user_message: str, current_intent: str, pending_suggestion: Dict[str, Any] = None) -> Dict[str, Any]:
    """Función de conveniencia para analizar confirmaciones"""
    return suggestion_manager.analyze_confirmation_response(user_message, current_intent, pending_suggestion)

def create_smart_suggestion(entity_value: str, entity_type: str, search_context: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
    """Función de conveniencia para crear sugerencias inteligentes"""
    return suggestion_manager.create_enhanced_suggestion(entity_value, entity_type, search_context)