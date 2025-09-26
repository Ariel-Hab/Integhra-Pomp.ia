#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Intent Processors Module - Procesadores especializados para intents y segmentos
Versión: 4.1 - Con soporte para roles y grupos
"""

import yaml
from typing import Dict, List, Any, Optional, Set, Tuple
from pathlib import Path
from dataclasses import dataclass, field
import logging
import re
import json

logger = logging.getLogger(__name__)


class ConfigValidationError(Exception):
    """Error crítico de validación de configuración"""
    pass


class MissingDataError(Exception):
    """Error cuando faltan datos requeridos"""
    pass


@dataclass
class IntentDefinition:
    """Definición completa de un intent"""
    name: str
    group: str
    entities: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    templates: List[str] = field(default_factory=list)
    responses: List[str] = field(default_factory=list)
    next_intents: List[str] = field(default_factory=list)
    starter_allowed: bool = True
    action_prefix: str = "action_generica"
    response_prefix: str = "utter_"
    context_switch: bool = False


@dataclass
class SegmentDefinition:
    """Definición de un segmento conversacional"""
    name: str
    examples: List[str] = field(default_factory=list)
    category: str = "general"


class IntentProcessor:
    """Procesador de intents con validación estricta"""
    
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.context_config = {}
        self.examples_config = {}
        self.templates_config = {}
        self.responses_config = {}
        
        # Configuraciones procesadas
        self._flow_groups = {}
        self._intent_templates = {}
    
    def load_configs(self):
        """Carga archivos de configuración de intents"""
        # Cargar context_config.yml - REQUERIDO
        context_file = self.config_dir / "context_config.yml"
        if not context_file.exists():
            raise MissingDataError(f"Archivo REQUERIDO context_config.yml no encontrado: {context_file}")
        
        with open(context_file, 'r', encoding='utf-8') as f:
            self.context_config = yaml.safe_load(f)
        
        # Validar estructura básica
        if 'intents' not in self.context_config:
            raise MissingDataError("context_config.yml debe tener sección 'intents'")
        
        # Cargar examples.yml - REQUERIDO
        examples_file = self.config_dir / "examples.yml"
        if not examples_file.exists():
            raise MissingDataError(f"Archivo REQUERIDO examples.yml no encontrado: {examples_file}")
        
        with open(examples_file, 'r', encoding='utf-8') as f:
            self.examples_config = yaml.safe_load(f)
        
        # Cargar templates.yml - REQUERIDO
        templates_file = self.config_dir / "templates.yml"
        if not templates_file.exists():
            raise MissingDataError(f"Archivo REQUERIDO templates.yml no encontrado: {templates_file}")
        
        with open(templates_file, 'r', encoding='utf-8') as f:
            self.templates_config = yaml.safe_load(f)
        
        # Cargar responses.yml - OPCIONAL pero recomendado
        responses_file = self.config_dir / "responses.yml"
        if responses_file.exists():
            with open(responses_file, 'r', encoding='utf-8') as f:
                self.responses_config = yaml.safe_load(f)
        else:
            logger.warning("responses.yml no encontrado - intents no tendrán responses")
        
        # Procesar configuraciones auxiliares
        self._flow_groups = self.context_config.get('flow_groups', {})
        self._intent_templates = self.context_config.get('intent_templates', {})
        
        logger.info("Archivos de configuración de intents cargados")
    
    def process_intents(self) -> Dict[str, IntentDefinition]:
        """Procesa todos los intents con validación estricta"""
        intents_config = self.context_config.get('intents', {})
        if not intents_config:
            raise MissingDataError("No se encontraron intents en context_config.yml")
        
        intents = {}
        validation_errors = []
        
        for intent_name, intent_config in intents_config.items():
            try:
                # Aplicar template si existe
                processed_config = self._apply_intent_template(intent_config, intent_name)
                
                # Obtener ejemplos
                examples = self._get_intent_examples(intent_name)
                
                # Obtener templates
                templates = self._get_intent_templates(intent_name)
                
                # VALIDACIÓN CRÍTICA: debe tener ejemplos O templates
                if not examples and not templates:
                    validation_errors.append(
                        f"Intent '{intent_name}' no tiene ejemplos ni templates definidos. "
                        f"Debe tener al menos uno de los dos."
                    )
                    continue
                
                # Obtener responses
                responses = self._get_intent_responses(intent_name)
                
                # Validar entidades referenciadas
                entities = processed_config.get('entities', [])
                self._validate_intent_entities(intent_name, entities)
                
                intents[intent_name] = IntentDefinition(
                    name=intent_name,
                    group=processed_config.get('grupo', 'general'),
                    entities=entities,
                    examples=examples,
                    templates=templates,
                    responses=responses,
                    next_intents=processed_config.get('next_intents', []),
                    starter_allowed=processed_config.get('starter_allowed', True),
                    action_prefix=processed_config.get('action_prefix', 'action_generica'),
                    response_prefix=processed_config.get('response_prefix', 'utter_'),
                    context_switch=processed_config.get('context_switch', False)
                )
                
            except Exception as e:
                validation_errors.append(f"Error procesando intent '{intent_name}': {e}")
        
        if validation_errors:
            raise ConfigValidationError(f"Errores procesando intents: {validation_errors}")
        
        logger.info(f"Procesados {len(intents)} intents exitosamente")
        return intents
    
    def _apply_intent_template(self, intent_config: Dict[str, Any], intent_name: str) -> Dict[str, Any]:
        """Aplica template de intent si está definido"""
        template_name = intent_config.get('template')
        if template_name and template_name in self._intent_templates:
            base_config = self._intent_templates[template_name].copy()
            # Sobrescribir con configuración específica del intent
            for key, value in intent_config.items():
                if key != 'template':
                    base_config[key] = value
            return base_config
        
        return intent_config
    
    def _get_intent_examples(self, intent_name: str) -> List[str]:
        """Obtiene ejemplos para un intent (solo si existen)"""
        examples = self.examples_config.get(intent_name, [])
        
        if isinstance(examples, str):
            # Ejemplo único - limpiar guion inicial si existe
            clean_example = examples.strip()
            if clean_example.startswith('- '):
                clean_example = clean_example[2:].strip()
            return [clean_example] if clean_example else []
        elif isinstance(examples, list):
            # Lista de ejemplos - limpiar guiones iniciales
            valid_examples = []
            for ex in examples:
                if isinstance(ex, str) and ex.strip():
                    clean_ex = ex.strip()
                    if clean_ex.startswith('- '):
                        clean_ex = clean_ex[2:].strip()
                    if clean_ex:
                        valid_examples.append(clean_ex)
            return valid_examples
        else:
            logger.warning(f"Intent '{intent_name}' tiene ejemplos en formato inválido: {type(examples)}")
            return []
    
    def _get_intent_templates(self, intent_name: str) -> List[str]:
        """Obtiene templates para un intent (solo si existen)"""
        templates = []
        
        # Definir secciones de templates a buscar
        template_sections = [
            'templates_busqueda',
            'templates_confirmacion',
            'templates_con_roles'
        ]
        
        for section in template_sections:
            section_templates = self.templates_config.get(section, {})
            if intent_name in section_templates:
                intent_templates = section_templates[intent_name]
                if isinstance(intent_templates, list):
                    for t in intent_templates:
                        if isinstance(t, str) and t.strip():
                            clean_template = t.strip()
                            # Limpiar guion inicial si existe
                            if clean_template.startswith('- '):
                                clean_template = clean_template[2:].strip()
                            if clean_template:
                                templates.append(clean_template)
                elif isinstance(intent_templates, str) and intent_templates.strip():
                    clean_template = intent_templates.strip()
                    if clean_template.startswith('- '):
                        clean_template = clean_template[2:].strip()
                    if clean_template:
                        templates.append(clean_template)
        
        return templates
    
    def _get_intent_responses(self, intent_name: str) -> List[str]:
        """Obtiene responses para un intent (solo si existen)"""
        response_key = f"utter_{intent_name}"
        responses_data = self.responses_config.get(response_key, [])
        
        responses = []
        for response in responses_data:
            if isinstance(response, dict) and 'text' in response:
                text = response['text'].strip()
                if text:
                    responses.append(text)
            elif isinstance(response, str) and response.strip():
                responses.append(response.strip())
        
        return responses
    
    def _validate_intent_entities(self, intent_name: str, entities: List[str]):
        """Valida que las entidades referenciadas estén bien formadas"""
        for entity in entities:
            if not isinstance(entity, str) or not entity.strip():
                raise ConfigValidationError(f"Intent '{intent_name}' tiene entidad inválida: {entity}")
            
            # Validar formato de entidad (sin caracteres especiales problemáticos)
            if not entity.replace('_', '').replace('-', '').isalnum():
                logger.warning(f"Intent '{intent_name}' tiene entidad con formato inusual: '{entity}'")
    
    def validate_intents(self, intents: Dict[str, IntentDefinition], available_entities: Set[str] = None) -> List[str]:
        """Valida la consistencia de intents procesados"""
        errors = []
        
        # Validar que cada intent tenga contenido suficiente
        for intent_name, intent in intents.items():
            if not intent.examples and not intent.templates:
                errors.append(f"Intent '{intent_name}' no tiene ejemplos ni templates")
            
            # Validar grupos definidos
            if intent.group not in self._flow_groups and intent.group != 'general':
                errors.append(f"Intent '{intent_name}' referencia grupo inexistente: '{intent.group}'")
            
            # Validar entidades si se proporciona lista disponible
            if available_entities:
                for entity in intent.entities:
                    if entity not in available_entities:
                        errors.append(f"Intent '{intent_name}' referencia entidad inexistente: '{entity}'")
            
            # Validar next_intents (solo advertencias)
            for next_intent in intent.next_intents:
                if next_intent not in intents:
                    logger.warning(f"Intent '{intent_name}' referencia next_intent inexistente: '{next_intent}'")
        
        return errors
    
    def get_intent_by_group(self, intents: Dict[str, IntentDefinition], group_name: str) -> List[IntentDefinition]:
        """Obtiene intents por grupo"""
        return [intent for intent in intents.values() if intent.group == group_name]
    
    def get_starter_intents(self, intents: Dict[str, IntentDefinition]) -> List[IntentDefinition]:
        """Obtiene intents que pueden iniciar conversaciones"""
        return [intent for intent in intents.values() if intent.starter_allowed]


class SegmentProcessor:
    """Procesador de segmentos conversacionales"""
    
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.segments_config = {}
    
    def load_config(self):
        """Carga configuración de segmentos desde segments.yml o formato NLU"""
        # Intentar cargar desde segments.yml primero
        segments_file = self.config_dir / "segments.yml"
        if segments_file.exists():
            with open(segments_file, 'r', encoding='utf-8') as f:
                self.segments_config = yaml.safe_load(f)
            logger.info("Configuración de segmentos cargada desde segments.yml")
            return
        
        # Si no existe, intentar cargar desde archivos NLU (formato synonym)
        nlu_files = [
            self.config_dir / "nlu.yml",
            self.config_dir / "segments_nlu.yml",
            self.config_dir / "data" / "nlu.yml"
        ]
        
        for nlu_file in nlu_files:
            if nlu_file.exists():
                logger.info(f"Intentando cargar segmentos desde formato NLU: {nlu_file}")
                if self._load_segments_from_nlu(nlu_file):
                    logger.info(f"Segmentos cargados desde formato NLU: {nlu_file}")
                    return
        
        logger.warning("No se encontraron archivos de segmentos - no se cargarán segmentos")
    
    def _load_segments_from_nlu(self, nlu_file: Path) -> bool:
        """Carga segmentos desde archivo NLU con formato synonym"""
        try:
            with open(nlu_file, 'r', encoding='utf-8') as f:
                nlu_data = yaml.safe_load(f)
            
            if not nlu_data or 'nlu' not in nlu_data:
                return False
            
            segments_found = 0
            self.segments_config = {}
            
            for item in nlu_data['nlu']:
                if 'synonym' in item:
                    synonym_name = item['synonym']
                    examples_text = item.get('examples', '')
                    
                    # Procesar ejemplos del formato "examples: |"
                    if isinstance(examples_text, str):
                        examples = self._process_nlu_examples(examples_text)
                        
                        if examples:
                            self.segments_config[synonym_name] = {
                                'examples': examples,
                                'category': 'conversational'
                            }
                            segments_found += 1
                            logger.debug(f"Segmento '{synonym_name}' cargado con {len(examples)} ejemplos")
            
            if segments_found > 0:
                logger.info(f"Cargados {segments_found} segmentos desde formato NLU")
                return True
            
            return False
            
        except Exception as e:
            logger.warning(f"Error cargando segmentos desde {nlu_file}: {e}")
            return False
    
    def _process_nlu_examples(self, examples_text: str) -> List[str]:
        """Procesa ejemplos en formato NLU (con guiones y saltos de línea)"""
        if not examples_text:
            return []
        
        examples = []
        lines = examples_text.split('\n')
        
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                # Remover guion inicial si existe
                if line.startswith('- '):
                    line = line[2:].strip()
                
                if line:
                    examples.append(line)
        
        return examples
    
    def process_segments(self) -> Dict[str, SegmentDefinition]:
        """Procesa segmentos conversacionales"""
        segments = {}
        
        if not self.segments_config:
            logger.info("No hay segmentos para procesar")
            return segments
        
        for segment_name, segment_config in self.segments_config.items():
            try:
                # Procesar configuración de segmento
                if isinstance(segment_config, dict):
                    examples = segment_config.get('examples', [])
                    category = segment_config.get('category', 'general')
                    
                    # Procesar ejemplos multi-línea si es un string
                    if isinstance(examples, str):
                        examples = self._process_multiline_examples(examples)
                elif isinstance(segment_config, list):
                    # Lista directa de ejemplos
                    examples = segment_config
                    category = 'general'
                else:
                    logger.warning(f"Segmento '{segment_name}' tiene formato inválido: {type(segment_config)}")
                    continue
                
                # Validar ejemplos
                valid_examples = self._validate_examples(examples, segment_name)
                
                if valid_examples:  # Solo crear segmento si tiene ejemplos válidos
                    segments[segment_name] = SegmentDefinition(
                        name=segment_name,
                        examples=valid_examples,
                        category=category
                    )
                else:
                    logger.warning(f"Segmento '{segment_name}' no tiene ejemplos válidos")
            
            except Exception as e:
                logger.error(f"Error procesando segmento '{segment_name}': {e}")
        
        logger.info(f"Procesados {len(segments)} segmentos")
        return segments
    
    def _process_multiline_examples(self, examples_str: str) -> List[str]:
        """Procesa ejemplos en formato multi-línea"""
        lines = examples_str.split('\n')
        examples = []
        
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                # Remover prefijo de lista si existe
                if line.startswith('- '):
                    line = line[2:].strip()
                
                if line:
                    examples.append(line)
        
        return examples
    
    def _validate_examples(self, examples: List[str], segment_name: str) -> List[str]:
        """Valida y limpia ejemplos de un segmento"""
        valid_examples = []
        
        for example in examples:
            if isinstance(example, str):
                cleaned = example.strip()
                # Limpiar guion inicial si existe
                if cleaned.startswith('- '):
                    cleaned = cleaned[2:].strip()
                
                if cleaned and len(cleaned) > 1:  # Al menos 2 caracteres
                    valid_examples.append(cleaned)
                else:
                    logger.warning(f"Segmento '{segment_name}' tiene ejemplo muy corto: '{example}'")
            else:
                logger.warning(f"Segmento '{segment_name}' tiene ejemplo no-string: {type(example)}")
        
        return valid_examples
    
    def validate_segments(self, segments: Dict[str, SegmentDefinition]) -> List[str]:
        """Valida segmentos procesados"""
        warnings = []
        
        for segment_name, segment in segments.items():
            if not segment.examples:
                warnings.append(f"Segmento '{segment_name}' no tiene ejemplos")
            elif len(segment.examples) < 3:
                warnings.append(f"Segmento '{segment_name}' tiene muy pocos ejemplos ({len(segment.examples)})")
            
            # Detectar duplicados
            unique_examples = set(segment.examples)
            if len(unique_examples) != len(segment.examples):
                warnings.append(f"Segmento '{segment_name}' tiene ejemplos duplicados")
        
        return warnings


class TemplateExpander:
    """Expansor de templates con entidades, segmentos, roles y grupos"""
    
    def __init__(self, entities: Dict[str, Any], segments: Dict[str, SegmentDefinition], templates_config: Dict[str, Any] = None):
        self.entities = entities
        self.segments = segments
        self.templates_config = templates_config or {}
        
        # Obtener configuración de roles y grupos
        self.entity_roles = self.templates_config.get('entity_roles', {})
        self.entity_groups = self._init_entity_groups()
        
    def _init_entity_groups(self) -> Dict[str, str]:
        """Inicializa grupos de entidades basado en roles y tipos"""
        groups = {}
        
        # Grupos por defecto basados en el ejemplo
        default_groups = {
            'producto': 'search_primary',
            'categoria': 'search_primary', 
            'animal': 'search_secondary',
            'proveedor': 'search_secondary',
            'comparador': 'comparison_filters',
            'estado': 'filters_categorical',
            'dosis': 'filters_categorical',
            'dia': 'temporal_filters',
            'fecha': 'temporal_filters',
            'indicador_temporal': 'temporal_filters',
            'cantidad_descuento': 'numeric_filters',
            'cantidad_bonificacion': 'numeric_filters',
            'cantidad_stock': 'numeric_filters',
            'ingrediente_activo': 'filters_categorical'
        }
        
        # Asignar grupos a entidades existentes
        for entity_name in self.entities.keys():
            if entity_name in default_groups:
                groups[entity_name] = default_groups[entity_name]
            else:
                groups[entity_name] = 'general'
                
        return groups
    
    def expand_templates(self, templates: List[str], max_combinations: int = 100) -> List[str]:
        """Expande templates reemplazando placeholders con valores anotados"""
        expanded = []
        
        for template in templates:
            try:
                # Encontrar placeholders en el template
                placeholders = self._find_placeholders_with_roles(template)
                
                if not placeholders:
                    # Template sin placeholders
                    expanded.append(template)
                    continue
                
                # Generar combinaciones con anotaciones
                combinations = self._generate_annotated_combinations(template, placeholders, max_combinations)
                expanded.extend(combinations)
                
            except Exception as e:
                logger.warning(f"Error expandiendo template '{template}': {e}")
                # Agregar template original como fallback
                expanded.append(template)
        
        return expanded
    
    def _find_placeholders_with_roles(self, template: str) -> List[Tuple[str, str, str]]:
        """Encuentra placeholders con formato {entity} o {entity:role}"""
        placeholder_pattern = r'\{([^}:]+)(?::([^}]+))?\}'
        matches = re.findall(placeholder_pattern, template)
        
        placeholders = []
        for entity, role in matches:
            # Si no hay role específico, usar el primer role disponible o None
            if not role and entity in self.entity_roles:
                role = self.entity_roles[entity][0] if self.entity_roles[entity] else None
            
            placeholders.append((entity, role or '', template))
        
        return placeholders
    
    def _generate_annotated_combinations(self, template: str, placeholders: List[Tuple[str, str, str]], max_combinations: int) -> List[str]:
        """Genera combinaciones con anotaciones JSON completas"""
        combinations = []
        
        # Obtener valores para cada placeholder
        placeholder_data = {}
        for entity, role, _ in placeholders:
            values = self._get_placeholder_values(entity)
            if values:
                placeholder_data[(entity, role)] = values[:5]  # Máximo 5 valores
        
        # Si algún placeholder no tiene valores, usar el template original
        if not all((entity, role) in placeholder_data for entity, role, _ in placeholders):
            return [template]
        
        # Generar combinaciones
        from itertools import product
        
        keys = list(placeholder_data.keys())
        value_lists = [placeholder_data[key] for key in keys]
        
        count = 0
        for combination in product(*value_lists):
            if count >= max_combinations:
                break
            
            expanded_template = template
            
            # Reemplazar cada placeholder con valor anotado
            for i, (entity, role) in enumerate(keys):
                value = combination[i]
                
                # Crear anotación JSON
                annotation = self._create_annotation(entity, role, value)
                annotated_value = f"[{value}]{annotation}"
                
                # Determinar el patrón a reemplazar
                if role:
                    pattern = f"{{{entity}:{role}}}"
                else:
                    pattern = f"{{{entity}}}"
                
                expanded_template = expanded_template.replace(pattern, annotated_value)
            
            combinations.append(expanded_template)
            count += 1
        
        return combinations
    
    def _create_annotation(self, entity: str, role: str, value: str) -> str:
        """Crea anotación JSON para una entidad"""
        annotation = {
            "entity": entity
        }
        
        # Agregar grupo si está definido
        if entity in self.entity_groups:
            annotation["group"] = self.entity_groups[entity]
        
        # Agregar role si está especificado y es válido
        if role and entity in self.entity_roles and role in self.entity_roles[entity]:
            annotation["role"] = role
        
        return json.dumps(annotation, ensure_ascii=False)
    
    def _get_placeholder_values(self, placeholder: str) -> List[str]:
        """Obtiene valores para un placeholder específico"""
        # Primero buscar en entidades
        if placeholder in self.entities:
            entity = self.entities[placeholder]
            if hasattr(entity, 'values') and entity.values:
                return entity.values[:5]  # Primeros 5 valores
            elif hasattr(entity, 'patterns') and entity.patterns:
                return entity.patterns[:5]  # Primeros 5 patterns
        
        # Luego buscar en segmentos
        if placeholder in self.segments:
            segment = self.segments[placeholder]
            return segment.examples[:5]  # Primeros 5 ejemplos
        
        # Valores por defecto para placeholders comunes
        default_values = {
            'cantidad_descuento': ['10%', '15%', '20%', '25%'],
            'cantidad_bonificacion': ['2x1', '3x2', 'lleva 2 paga 1'],
            'dia': ['lunes', 'martes', 'hoy', 'mañana'],
            'fecha': ['esta semana', 'este mes', 'pronto'],
            'comparador': ['mejor que', 'más barato que', 'igual que']
        }
        
        return default_values.get(placeholder, [placeholder])  # Fallback al placeholder mismo