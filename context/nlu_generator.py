#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integrated NLU Generator - Sistema completo con lookup tables automáticas
Versión: 2.0 - Integración completa con entity_loaders y generación automática de lookups
"""

import yaml
import random
import re
import logging
import json
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, Counter
import hashlib

# Importar componentes del sistema
from entity_loaders import EntityManager
from lookup_generator_from_entities import EntityBasedLookupGenerator, LookupTableConfig

logger = logging.getLogger(__name__)

@dataclass
class IntegratedConfig:
    """Configuración integrada para todo el sistema"""
    # Configuración de lookup tables
    lookup_config: LookupTableConfig = field(default_factory=LookupTableConfig)
    
    # Configuración de generación NLU
    max_examples_per_intent: int = 25
    min_examples_per_intent: int = 5
    max_variations_per_template: int = 6
    
    # Configuración de deduplicación
    similarity_threshold: float = 0.80
    max_duplicates_per_intent: int = 2
    
    # Configuración de variación
    variation_probability: float = 0.6
    use_conversation_markers: bool = True
    
    # Configuración de intents
    intent_consolidation: Dict[str, str] = field(default_factory=lambda: {
        'agradecer': 'agradecimiento',
        'reirse_chiste': 'responder_positivo',
        'responder_como_estoy': 'estado_animo',
        'responder_estoy_bien': 'estado_animo'
    })

@dataclass
class GeneratedNLUExample:
    """Ejemplo NLU generado con metadatos completos"""
    text: str
    intent: str
    entities: List[Dict[str, Any]]
    source: str  # 'hardcoded', 'template', 'variation'
    template_used: Optional[str] = None
    variation_id: Optional[str] = None
    confidence_score: float = 1.0
    
    def __post_init__(self):
        self.hash_key = self._generate_hash()
    
    def _generate_hash(self) -> str:
        """Genera hash único para deduplicación"""
        normalized = re.sub(r'\s+', ' ', self.text.lower().strip())
        normalized = re.sub(r'[^\w\s]', '', normalized)
        return hashlib.md5(normalized.encode()).hexdigest()[:8]

class SmartVariationEngine:
    """Motor de variaciones inteligentes"""
    
    def __init__(self, lookup_generator: EntityBasedLookupGenerator, config: IntegratedConfig):
        self.lookup_generator = lookup_generator
        self.config = config
        
        # Marcadores conversacionales argentinos
        self.conversation_starters = [
            "che", "disculpá", "perdón", "hola", "mirá", "decime", 
            "sabés", "tendrás", "habrá", "por casualidad"
        ]
        
        self.conversation_enders = [
            "por favor", "gracias", "desde ya gracias", "si podés",
            "cuando puedas", "si tenés tiempo", "te agradezco"
        ]
        
        self.filler_words = [
            "bueno", "o sea", "digamos", "ponele", "tipo", "medio que",
            "como que", "viste", "entendés"
        ]
    
    def generate_variations(self, base_text: str, intent: str, 
                          entities: List[Dict], max_variations: int = None) -> List[GeneratedNLUExample]:
        """Genera variaciones inteligentes de un texto base"""
        if max_variations is None:
            max_variations = self.config.max_variations_per_template
        
        variations = []
        
        # Ejemplo base
        base_example = GeneratedNLUExample(
            text=base_text,
            intent=intent,
            entities=entities,
            source='template',
            variation_id='base'
        )
        variations.append(base_example)
        
        # Generar variaciones
        for i in range(max_variations - 1):
            if random.random() > self.config.variation_probability:
                continue
            
            variation_text = self._create_intelligent_variation(base_text, intent)
            
            if variation_text and variation_text != base_text:
                # Ajustar entidades para la nueva variación
                adjusted_entities = self._adjust_entities_positions(
                    entities, base_text, variation_text
                )
                
                variation = GeneratedNLUExample(
                    text=variation_text,
                    intent=intent,
                    entities=adjusted_entities,
                    source='variation',
                    template_used=base_text,
                    variation_id=f'var_{i+1}'
                )
                variations.append(variation)
        
        return variations
    
    def _create_intelligent_variation(self, text: str, intent: str) -> str:
        """Crea variación inteligente del texto"""
        variation = text
        
        # Aplicar diferentes tipos de variación
        variation_types = [
            self._add_conversation_markers,
            self._apply_synonym_substitution,
            self._add_filler_words,
            self._apply_intent_specific_variations
        ]
        
        # Aplicar 1-2 variaciones aleatorias
        selected_variations = random.sample(variation_types, k=random.randint(1, 2))
        
        for variation_func in selected_variations:
            try:
                variation = variation_func(variation, intent)
            except Exception as e:
                logger.debug(f"Error en variación {variation_func.__name__}: {e}")
                continue
        
        return variation.strip()
    
    def _add_conversation_markers(self, text: str, intent: str) -> str:
        """Agrega marcadores conversacionales"""
        if not self.config.use_conversation_markers:
            return text
        
        if random.random() < 0.4:
            if random.random() < 0.6:
                # Agregar al inicio
                starter = random.choice(self.conversation_starters)
                return f"{starter}, {text}"
            else:
                # Agregar al final
                ender = random.choice(self.conversation_enders)
                return f"{text}, {ender}"
        
        return text
    
    def _apply_synonym_substitution(self, text: str, intent: str) -> str:
        """Aplica sustitución de sinónimos"""
        # Usar synonyms generados automáticamente
        words = text.split()
        new_words = []
        
        for word in words:
            clean_word = re.sub(r'[^\w]', '', word.lower())
            
            # Buscar en synonyms generados
            replacement = self._find_synonym_replacement(clean_word, intent)
            
            if replacement and replacement != clean_word:
                # Mantener capitalización
                if word[0].isupper():
                    replacement = replacement.capitalize()
                new_words.append(replacement)
            else:
                new_words.append(word)
        
        return ' '.join(new_words)
    
    def _find_synonym_replacement(self, word: str, intent: str) -> Optional[str]:
        """Busca reemplazo de sinónimo en las tablas generadas"""
        for synonym_name, synonym_values in self.lookup_generator.synonyms.items():
            if word in [v.lower() for v in synonym_values]:
                # Filtrar la palabra original y seleccionar otra
                alternatives = [v for v in synonym_values if v.lower() != word]
                if alternatives and random.random() < 0.3:
                    return random.choice(alternatives)
        return None
    
    def _add_filler_words(self, text: str, intent: str) -> str:
        """Agrega palabras de relleno ocasionalmente"""
        if random.random() < 0.2:  # Baja probabilidad
            filler = random.choice(self.filler_words)
            words = text.split()
            
            if len(words) > 2:
                # Insertar en posición aleatoria (no al inicio ni al final)
                insert_pos = random.randint(1, len(words) - 1)
                words.insert(insert_pos, filler)
                return ' '.join(words)
        
        return text
    
    def _apply_intent_specific_variations(self, text: str, intent: str) -> str:
        """Aplica variaciones específicas por tipo de intent"""
        if intent.startswith('buscar_'):
            return self._vary_search_intent(text)
        elif intent in ['afirmar', 'denegar']:
            return self._vary_confirmation_intent(text, intent)
        elif intent == 'agradecimiento':
            return self._vary_thanks_intent(text)
        
        return text
    
    def _vary_search_intent(self, text: str) -> str:
        """Variaciones para intents de búsqueda"""
        search_variations = {
            'necesito': ['busco', 'quiero', 'me hace falta', 'precisaría'],
            'busco': ['necesito', 'ando buscando', 'estoy buscando'],
            'quiero': ['necesito', 'me interesa', 'quisiera'],
            'tenés': ['hay', 'manejás', 'vendés', 'conseguís']
        }
        
        for original, replacements in search_variations.items():
            if original in text.lower():
                replacement = random.choice(replacements)
                return text.replace(original, replacement)
        
        return text
    
    def _vary_confirmation_intent(self, text: str, intent: str) -> str:
        """Variaciones para confirmaciones"""
        if intent == 'afirmar':
            affirmative_variations = {
                'sí': ['dale', 'perfecto', 'está bien'],
                'perfecto': ['genial', 'bárbaro', 'excelente'],
                'está bien': ['me sirve', 'me parece bien']
            }
            
            for original, replacements in affirmative_variations.items():
                if original in text.lower():
                    return text.replace(original, random.choice(replacements))
        
        return text
    
    def _vary_thanks_intent(self, text: str) -> str:
        """Variaciones para agradecimientos"""
        thanks_variations = {
            'gracias': ['muchas gracias', 'mil gracias', 'te agradezco'],
            'muchas gracias': ['gracias', 'muy amable'],
            'excelente': ['genial', 'perfecto', 'buenísimo']
        }
        
        for original, replacements in thanks_variations.items():
            if original in text.lower():
                return text.replace(original, random.choice(replacements))
        
        return text
    
    def _adjust_entities_positions(self, entities: List[Dict], 
                                 original_text: str, new_text: str) -> List[Dict]:
        """Ajusta posiciones de entidades en texto modificado"""
        if not entities or original_text == new_text:
            return entities
        
        adjusted = []
        
        for entity in entities:
            value = entity['value']
            
            # Buscar nueva posición
            start_pos = new_text.find(value)
            if start_pos != -1:
                adjusted_entity = entity.copy()
                adjusted_entity['start'] = start_pos
                adjusted_entity['end'] = start_pos + len(value)
                adjusted.append(adjusted_entity)
            else:
                # Si no se encuentra, mantener entidad original
                adjusted.append(entity)
        
        return adjusted

class AdvancedDeduplicator:
    """Deduplicador avanzado con análisis semántico"""
    
    def __init__(self, config: IntegratedConfig):
        self.config = config
        self.seen_examples: Dict[str, Set[str]] = defaultdict(set)
        self.seen_hashes: Set[str] = set()
    
    def is_duplicate(self, example: GeneratedNLUExample) -> bool:
        """Verifica si un ejemplo es duplicado"""
        # Hash exacto
        if example.hash_key in self.seen_hashes:
            return True
        
        # Preservar ejemplos hardcodeados siempre
        if example.source == 'hardcoded':
            return False
        
        # Verificar similitud por intent
        intent_examples = self.seen_examples[example.intent]
        
        # Contar similares
        similar_count = 0
        for seen_hash in intent_examples:
            if self._calculate_similarity(example.hash_key, seen_hash) > self.config.similarity_threshold:
                similar_count += 1
        
        return similar_count >= self.config.max_duplicates_per_intent
    
    def add_example(self, example: GeneratedNLUExample):
        """Registra ejemplo como visto"""
        self.seen_hashes.add(example.hash_key)
        self.seen_examples[example.intent].add(example.hash_key)
    
    def _calculate_similarity(self, hash1: str, hash2: str) -> float:
        """Calcula similitud entre hashes"""
        if hash1 == hash2:
            return 1.0
        
        # Similitud por caracteres comunes
        common_chars = sum(1 for a, b in zip(hash1, hash2) if a == b)
        return common_chars / max(len(hash1), len(hash2))

class IntegratedNLUGenerator:
    """Generador NLU integrado completo"""
    
    def __init__(self, config_dir: Path, data_dir: Path, output_dir: Path, 
                 config: IntegratedConfig = None):
        self.config_dir = config_dir
        self.data_dir = data_dir
        self.output_dir = output_dir
        self.config = config or IntegratedConfig()
        
        # Componentes principales
        self.lookup_generator = EntityBasedLookupGenerator(
            data_dir, config_dir, self.config.lookup_config
        )
        self.variation_engine = SmartVariationEngine(self.lookup_generator, self.config)
        self.deduplicator = AdvancedDeduplicator(self.config)
        
        # Datos generados
        self.all_examples: List[GeneratedNLUExample] = []
        self.examples_by_intent: Dict[str, List[GeneratedNLUExample]] = defaultdict(list)
        
        # Templates optimizados
        self.core_templates = {
            'saludo': [
                "hola", "buen día", "qué tal", "cómo va", "buenas"
            ],
            'despedida': [
                "chau", "hasta luego", "nos vemos", "que tengas buen día"
            ],
            'agradecimiento': [
                "gracias", "muchas gracias", "excelente atención", "muy amable"
            ],
            'buscar_producto': [
                "necesito {producto}",
                "busco {producto} de {proveedor}",
                "tenés {producto} para {animal}",
                "me mostrás {producto} en {dosis}",
                "{producto} hay disponible",
                "quiero comprar {producto}"
            ],
            'buscar_oferta': [
                "qué ofertas hay",
                "hay descuentos en {categoria}",
                "promociones de {proveedor}",
                "{producto} con descuento",
                "ofertas en {categoria}"
            ],
            'consultar_novedades': [
                "qué novedades hay",
                "productos nuevos de {proveedor}",
                "qué llegó nuevo",
                "últimos productos"
            ],
            'afirmar': [
                "sí, está bien", "perfecto", "dale", "me sirve"
            ],
            'denegar': [
                "no me sirve", "prefiero otra cosa", "no es lo que busco"
            ],
            'completar_pedido': [
                "confirmo el pedido", "está bien así", "dale, hacemos el pedido"
            ]
        }
    
    def generate_complete_nlu(self):
        """Genera NLU completo con lookup tables automáticas"""
        logger.info("Iniciando generación completa de NLU...")
        
        start_time = time.time()
        
        # 1. Cargar entidades y generar lookup tables
        logger.info("Paso 1: Generando lookup tables automáticas...")
        self.lookup_generator.load_entities_and_generate_lookups()
        
        # 2. Cargar ejemplos hardcodeados si existen
        logger.info("Paso 2: Cargando ejemplos hardcodeados...")
        self._load_hardcoded_examples()
        
        # 3. Generar ejemplos desde templates
        logger.info("Paso 3: Generando ejemplos desde templates...")
        self._generate_from_templates()
        
        # 4. Aplicar deduplicación y límites
        logger.info("Paso 4: Aplicando deduplicación y límites...")
        self._apply_deduplication_and_limits()
        
        # 5. Organizar por intent
        self._organize_by_intent()
        
        elapsed_time = time.time() - start_time
        
        logger.info(f"Generación completada en {elapsed_time:.2f}s: "
                   f"{len(self.all_examples)} ejemplos únicos en "
                   f"{len(self.examples_by_intent)} intents")
    
    def _load_hardcoded_examples(self):
        """Carga ejemplos hardcodeados desde examples.yml"""
        examples_file = self.config_dir / "examples.yml"
        
        if not examples_file.exists():
            logger.info("No se encontró examples.yml, solo se usarán templates")
            return
        
        try:
            with open(examples_file, 'r', encoding='utf-8') as f:
                examples_data = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Error cargando examples.yml: {e}")
            return
        
        hardcoded_count = 0
        
        for intent_name, examples_list in examples_data.items():
            if intent_name == 'version' or not isinstance(examples_list, list):
                continue
            
            # Aplicar consolidación de intents
            final_intent = self.config.intent_consolidation.get(intent_name, intent_name)
            
            for example_text in examples_list[:10]:  # Límite de hardcodeados
                if isinstance(example_text, str):
                    text, entities = self._parse_hardcoded_example(example_text)
                    
                    example = GeneratedNLUExample(
                        text=text,
                        intent=final_intent,
                        entities=entities,
                        source='hardcoded'
                    )
                    
                    self.all_examples.append(example)
                    self.deduplicator.add_example(example)
                    hardcoded_count += 1
        
        logger.info(f"Cargados {hardcoded_count} ejemplos hardcodeados")
    
    def _parse_hardcoded_example(self, example_text: str) -> Tuple[str, List[Dict]]:
        """Parsea ejemplo hardcodeado con anotaciones"""
        # Pattern para anotaciones [valor](entidad) o [valor](entidad:role)
        entity_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
        
        text = example_text
        entities = []
        offset = 0
        
        for match in entity_pattern.finditer(example_text):
            value = match.group(1)
            entity_spec = match.group(2)
            
            # Parsear especificación de entidad
            entity_parts = entity_spec.split(':')
            entity_name = entity_parts[0]
            entity_role = entity_parts[1] if len(entity_parts) > 1 else None
            
            # Calcular posiciones
            start_pos = match.start() + offset
            end_pos = start_pos + len(value)
            
            # Reemplazar anotación con valor
            text = text[:match.start() + offset] + value + text[match.end() + offset:]
            
            # Crear entidad
            entity = {
                'entity': entity_name,
                'start': start_pos,
                'end': end_pos,
                'value': value
            }
            
            if entity_role:
                entity['role'] = entity_role
            
            entities.append(entity)
            
            # Ajustar offset
            offset += len(value) - len(match.group(0))
        
        return text, entities
    
    def _generate_from_templates(self):
        """Genera ejemplos desde templates"""
        template_count = 0
        
        for intent, templates in self.core_templates.items():
            # Aplicar consolidación de intents
            final_intent = self.config.intent_consolidation.get(intent, intent)
            
            for template in templates:
                if '{' in template:
                    # Template con entidades
                    examples = self._generate_from_entity_template(template, final_intent)
                else:
                    # Template simple
                    examples = self.variation_engine.generate_variations(
                        template, final_intent, []
                    )
                
                # Aplicar deduplicación
                for example in examples:
                    if not self.deduplicator.is_duplicate(example):
                        self.all_examples.append(example)
                        self.deduplicator.add_example(example)
                        template_count += 1
        
        logger.info(f"Generados {template_count} ejemplos desde templates")
    
    def _generate_from_entity_template(self, template: str, intent: str) -> List[GeneratedNLUExample]:
        """Genera ejemplos desde template con entidades"""
        placeholders = re.findall(r'\{(\w+)\}', template)
        
        if not placeholders:
            return []
        
        examples = []
        
        # Generar múltiples combinaciones
        for _ in range(8):  # Máximo 8 combinaciones por template
            text = template
            entities = []
            offset = 0
            
            for placeholder in placeholders:
                # Obtener valores de lookup tables generadas
                values = self.lookup_generator.get_lookup_values(placeholder, limit=25)
                
                if not values:
                    continue
                
                selected_value = random.choice(values)
                placeholder_text = f"{{{placeholder}}}"
                
                # Encontrar y reemplazar placeholder
                start_pos = text.find(placeholder_text)
                if start_pos != -1:
                    start_pos += offset
                    text = text.replace(placeholder_text, selected_value, 1)
                    
                    # Crear entidad
                    entities.append({
                        'entity': placeholder,
                        'start': start_pos,
                        'end': start_pos + len(selected_value),
                        'value': selected_value
                    })
                    
                    # Ajustar offset
                    offset += len(selected_value) - len(placeholder_text)
            
            if entities:
                # Generar variaciones de este ejemplo
                variations = self.variation_engine.generate_variations(
                    text, intent, entities, max_variations=3
                )
                examples.extend(variations)
        
        return examples
    
    def _apply_deduplication_and_limits(self):
        """Aplica deduplicación final y límites"""
        # Agrupar por intent
        by_intent = defaultdict(list)
        for example in self.all_examples:
            by_intent[example.intent].append(example)
        
        filtered_examples = []
        
        for intent, examples in by_intent.items():
            # Aplicar límite máximo
            if len(examples) > self.config.max_examples_per_intent:
                # Priorizar hardcodeados y diversidad
                hardcoded = [e for e in examples if e.source == 'hardcoded']
                others = [e for e in examples if e.source != 'hardcoded']
                
                selected = hardcoded[:]
                remaining_slots = self.config.max_examples_per_intent - len(hardcoded)
                
                if remaining_slots > 0 and others:
                    # Seleccionar con diversidad
                    selected.extend(random.sample(others, min(remaining_slots, len(others))))
                
                examples = selected
            
            # Verificar mínimo
            if len(examples) < self.config.min_examples_per_intent:
                logger.warning(f"Intent '{intent}' tiene solo {len(examples)} ejemplos")
            
            filtered_examples.extend(examples)
        
        self.all_examples = filtered_examples
    
    def _organize_by_intent(self):
        """Organiza ejemplos por intent"""
        self.examples_by_intent.clear()
        for example in self.all_examples:
            self.examples_by_intent[example.intent].append(example)
    
    def export_complete_nlu(self, nlu_filename: str = "nlu_complete.yml", 
                           lookup_filename: str = "lookup_tables.yml") -> Tuple[Path, Path]:
        """Exporta NLU completo y lookup tables"""
        # Exportar lookup tables
        lookup_file = self.lookup_generator.export_to_yaml(
            self.output_dir / lookup_filename
        )
        
        # Exportar NLU
        nlu_file = self._export_nlu_yml(self.output_dir / nlu_filename)
        
        return nlu_file, lookup_file
    
    def _export_nlu_yml(self, output_file: Path) -> Path:
        """Exporta ejemplos NLU a formato YAML con formato consistente de objetos"""
        nlu_data = []
        
        for intent, examples in self.examples_by_intent.items():
            if not examples:
                continue
            
            intent_data = {
                'intent': intent,
                'examples': []
            }
            
            for example in examples:
                # SIEMPRE crear ejemplo como diccionario con 'text' explícito
                example_dict = {
                    'text': example.text
                }
                
                # Agregar 'entities' solo si el ejemplo tiene entidades
                if example.entities:
                    # Formatear entidades para el nuevo formato
                    formatted_entities = []
                    for entity in example.entities:
                        formatted_entity = {
                            'entity': entity['entity'],
                            'value': entity['value'],
                            'start': entity['start'],
                            'end': entity['end']
                        }
                        # Preservar role si existe
                        if 'role' in entity:
                            formatted_entity['role'] = entity['role']
                        
                        formatted_entities.append(formatted_entity)
                    
                    example_dict['entities'] = formatted_entities
                
                # Agregar ejemplo como objeto (nunca como string)
                intent_data['examples'].append(example_dict)
            
            nlu_data.append(intent_data)
        
        # Guardar archivo
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            # Usar dump personalizado para mejor formato
            yaml.dump(nlu_data, f, 
                     default_flow_style=False, 
                     allow_unicode=True, 
                     sort_keys=False,
                     indent=2,
                     width=200)
        
        return output_file
    
    def _create_rasa_annotation(self, example: GeneratedNLUExample) -> str:
        """Crea anotación válida para Rasa"""
        text = example.text
        
        # Ordenar entidades por posición (reversa)
        sorted_entities = sorted(example.entities, key=lambda e: e['start'], reverse=True)
        
        for entity in sorted_entities:
            start = entity['start']
            end = entity['end']
            entity_name = entity['entity']
            value = entity['value']
            role = entity.get('role')
            
            # Crear anotación simple sin roles para mejor compatibilidad
            annotation = f"[{value}]({entity_name})"
            text = text[:start] + annotation + text[end:]
        
        return text
    
    def generate_comprehensive_stats(self) -> Dict[str, Any]:
        """Genera estadísticas comprensivas"""
        lookup_stats = self.lookup_generator.generate_stats()
        
        return {
            'generation_summary': {
                'total_examples': len(self.all_examples),
                'total_intents': len(self.examples_by_intent),
                'avg_examples_per_intent': len(self.all_examples) / len(self.examples_by_intent) if self.examples_by_intent else 0,
                'deduplication_enabled': True,
                'lookup_tables_generated': lookup_stats['total_lookup_tables']
            },
            'examples_by_intent': {
                intent: len(examples) 
                for intent, examples in self.examples_by_intent.items()
            },
            'examples_by_source': dict(Counter(e.source for e in self.all_examples)),
            'entity_usage': dict(Counter(
                entity['entity'] 
                for example in self.all_examples 
                for entity in example.entities
            ).most_common(15)),
            'lookup_table_stats': lookup_stats,
            'quality_metrics': {
                'unique_examples_ratio': len(set(e.hash_key for e in self.all_examples)) / len(self.all_examples) if self.all_examples else 0,
                'avg_entities_per_example': sum(len(e.entities) for e in self.all_examples) / len(self.all_examples) if self.all_examples else 0,
                'intents_with_min_examples': len([
                    intent for intent, examples in self.examples_by_intent.items() 
                    if len(examples) >= self.config.min_examples_per_intent
                ])
            }
        }

def main():
    """Función principal integrada"""
    config_dir = Path("config")
    data_dir = Path("data")
    output_dir = Path("generated")
    
    # Configuración personalizada
    config = IntegratedConfig(
        max_examples_per_intent=30,
        min_examples_per_intent=5,
        max_variations_per_template=6,
        similarity_threshold=0.75,
        variation_probability=0.7
    )
    
    # Crear generador integrado
    generator = IntegratedNLUGenerator(config_dir, data_dir, output_dir, config)
    
    try:
        print("Iniciando generación completa de NLU...")
        
        # Generar todo el NLU
        generator.generate_complete_nlu()
        
        # Exportar archivos
        nlu_file, lookup_file = generator.export_complete_nlu()
        
        # Generar estadísticas
        stats = generator.generate_comprehensive_stats()
        stats_file = output_dir / "comprehensive_stats.json"
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        
        # Mostrar resultados
        print(f"\n✅ Generación completa exitosa!")
        print(f"📄 Archivo NLU: {nlu_file}")
        print(f"📋 Lookup Tables: {lookup_file}")
        print(f"📊 Estadísticas: {stats_file}")
        print(f"\n📈 Resumen:")
        print(f"   Ejemplos totales: {stats['generation_summary']['total_examples']}")
        print(f"   Intents: {stats['generation_summary']['total_intents']}")
        print(f"   Lookup tables: {stats['generation_summary']['lookup_tables_generated']}")
        print(f"   Ratio de únicos: {stats['quality_metrics']['unique_examples_ratio']:.2%}")
        
    except Exception as e:
        logger.error(f"Error en generación integrada: {e}")
        raise

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()