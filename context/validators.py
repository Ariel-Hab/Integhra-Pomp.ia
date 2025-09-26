#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validators Module - Validadores estrictos para configuraciones con soporte completo
Versión: 4.1 - Incluye validación de roles, grupos y segmentos
"""

import re
from typing import Dict, List, Set, Tuple, Any
from pathlib import Path
import logging
import yaml

logger = logging.getLogger(__name__)


class ConfigValidationError(Exception):
    """Error crítico de validación de configuración"""
    pass


class ValidationReport:
    """Reporte detallado de validación"""
    
    def __init__(self):
        self.critical_errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []
        self.stats: Dict[str, Any] = {}
    
    def add_critical(self, message: str, context: str = ""):
        if context:
            message = f"[{context}] {message}"
        self.critical_errors.append(message)
    
    def add_warning(self, message: str, context: str = ""):
        if context:
            message = f"[{context}] {message}"
        self.warnings.append(message)
    
    def add_info(self, message: str, context: str = ""):
        if context:
            message = f"[{context}] {message}"
        self.info.append(message)
    
    @property
    def is_valid(self) -> bool:
        return len(self.critical_errors) == 0
    
    def print_report(self):
        """Imprime reporte de validación"""
        print("\n" + "="*60)
        print("📋 REPORTE DE VALIDACIÓN")
        print("="*60)
        
        if self.critical_errors:
            print("\n🚨 ERRORES CRÍTICOS:")
            for error in self.critical_errors:
                print(f"   ❌ {error}")
        
        if self.warnings:
            print("\n⚠️ ADVERTENCIAS:")
            for warning in self.warnings:
                print(f"   ⚠️  {warning}")
        
        if self.info:
            print("\n📝 INFORMACIÓN:")
            for info in self.info:
                print(f"   ℹ️  {info}")
        
        if self.stats:
            print("\n📊 ESTADÍSTICAS:")
            for key, value in self.stats.items():
                print(f"   • {key}: {value}")
        
        print("\n" + ("✅ VALIDACIÓN EXITOSA" if self.is_valid else "❌ VALIDACIÓN FALLIDA"))
        print("="*60)


class FileValidator:
    """Validador de archivos requeridos"""
    
    def __init__(self, config_dir: Path, data_dir: Path):
        self.config_dir = config_dir
        self.data_dir = data_dir
    
    def validate_required_files(self) -> ValidationReport:
        """Valida que existan todos los archivos requeridos"""
        report = ValidationReport()
        
        # Archivos de configuración requeridos
        required_config_files = [
            "context_config.yml",
            "entities.yml",
            "examples.yml",
            "templates.yml"
        ]
        
        # Archivos opcionales pero recomendados
        optional_config_files = [
            "responses.yml",
            "segments.yml",
            "entities_regex.yml",
            "entities_config.yml",
            "slots_config.yml"
        ]
        
        # Archivos de segmentos (pueden estar en formato NLU)
        segment_files = [
            "segments.yml",
            "nlu.yml",
            "segments_nlu.yml",
            "data/nlu.yml"
        ]
        
        # Validar archivos requeridos
        for filename in required_config_files:
            file_path = self.config_dir / filename
            if not file_path.exists():
                report.add_critical(f"Archivo requerido no encontrado: {filename}")
            else:
                report.add_info(f"Archivo encontrado: {filename}")
        
        # Validar archivos opcionales
        for filename in optional_config_files:
            file_path = self.config_dir / filename
            if not file_path.exists():
                report.add_warning(f"Archivo opcional no encontrado: {filename}")
            else:
                report.add_info(f"Archivo opcional encontrado: {filename}")
        
        # Validar archivos de segmentos (al menos uno debe existir)
        segment_found = False
        for filename in segment_files:
            file_path = self.config_dir / filename
            if file_path.exists():
                segment_found = True
                report.add_info(f"Archivo de segmentos encontrado: {filename}")
                break
        
        if not segment_found:
            report.add_warning("No se encontraron archivos de segmentos (segments.yml o formato NLU)")
        
        # Validar estructura de directorios
        if not self.config_dir.exists():
            report.add_critical(f"Directorio de configuración no existe: {self.config_dir}")
        
        if not self.data_dir.exists():
            report.add_warning(f"Directorio de datos no existe: {self.data_dir}")
        
        return report


class SegmentValidator:
    """Validador especializado para segmentos"""
    
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
    
    def validate_segments(self, segments: Dict[str, Any]) -> ValidationReport:
        """Valida segmentos cargados"""
        report = ValidationReport()
        
        if not segments:
            report.add_warning("No se cargaron segmentos")
            return report
        
        # Estadísticas básicas
        report.stats["total_segments"] = len(segments)
        
        category_counts = {}
        total_examples = 0
        
        for name, segment in segments.items():
            # Validar estructura básica
            if not hasattr(segment, 'examples'):
                report.add_critical(f"Segmento '{name}' no tiene ejemplos")
                continue
            
            examples = getattr(segment, 'examples', [])
            category = getattr(segment, 'category', 'unknown')
            
            # Contar ejemplos y categorías
            total_examples += len(examples)
            category_counts[category] = category_counts.get(category, 0) + 1
            
            # Validar contenido
            if not examples:
                report.add_warning(f"Segmento '{name}' no tiene ejemplos")
            elif len(examples) < 3:
                report.add_warning(f"Segmento '{name}' tiene pocos ejemplos ({len(examples)})")
            else:
                report.add_info(f"Segmento '{name}' tiene {len(examples)} ejemplos")
            
            # Validar calidad de ejemplos
            for i, example in enumerate(examples):
                if not isinstance(example, str):
                    report.add_warning(f"Segmento '{name}' tiene ejemplo no-string en posición {i}")
                elif len(example.strip()) < 2:
                    report.add_warning(f"Segmento '{name}' tiene ejemplo muy corto en posición {i}")
        
        # Estadísticas finales
        report.stats.update({
            "by_category": category_counts,
            "total_examples": total_examples,
            "avg_examples_per_segment": total_examples / len(segments) if segments else 0
        })
        
        # Validaciones adicionales
        if total_examples < 50:
            report.add_warning(f"Pocos ejemplos totales de segmentos ({total_examples}), considera agregar más")
        
        return report


class EntityValidator:
    """Validador especializado para entidades con soporte para roles y grupos"""
    
    def validate_entity_consistency(self, entities: Dict[str, Any], templates_config: Dict[str, Any] = None) -> ValidationReport:
        """Valida consistencia de entidades con roles y grupos"""
        report = ValidationReport()
        
        entity_names = set(entities.keys())
        
        # Estadísticas básicas
        report.stats["total_entities"] = len(entities)
        source_counts = {}
        
        for name, entity in entities.items():
            source = getattr(entity, 'source', 'unknown')
            source_counts[source] = source_counts.get(source, 0) + 1
            
            # Validar estructura básica
            self._validate_entity_structure(name, entity, report)
            
            # Validar contenido según tipo
            self._validate_entity_content(name, entity, report)
        
        report.stats["entities_by_source"] = source_counts
        
        # Validar alias
        self._validate_entity_aliases(entities, report)
        
        # Validar duplicados
        self._validate_entity_duplicates(entities, report)
        
        # Validar roles y grupos si hay configuración de templates
        if templates_config:
            self._validate_entity_roles_and_groups(entities, templates_config, report)
        
        return report
    
    def _validate_entity_structure(self, name: str, entity: Any, report: ValidationReport):
        """Valida estructura básica de una entidad"""
        required_attrs = ['name', 'source', 'type']
        
        for attr in required_attrs:
            if not hasattr(entity, attr):
                report.add_critical(f"Entity '{name}' no tiene atributo requerido: {attr}")
        
        # Validar nombre
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', name):
            report.add_warning(f"Entity '{name}' tiene nombre con formato inusual")
    
    def _validate_entity_content(self, name: str, entity: Any, report: ValidationReport):
        """Valida contenido de entidad según su tipo"""
        source = getattr(entity, 'source', '')
        
        if source == 'csv':
            values = getattr(entity, 'values', [])
            if not values:
                report.add_critical(f"Entity CSV '{name}' no tiene valores")
            elif len(values) < 3:
                report.add_warning(f"Entity CSV '{name}' tiene pocos valores ({len(values)})")
        
        elif source == 'pattern':
            patterns = getattr(entity, 'patterns', [])
            if not patterns:
                report.add_critical(f"Entity pattern '{name}' no tiene patterns")
            else:
                for i, pattern in enumerate(patterns):
                    try:
                        pattern_str = str(pattern).strip()
                    except Exception:
                        pattern_str = ""
                        report.add_warning(
                            f"Entity '{name}' tiene pattern inválido en posición {i}: {pattern} ({type(pattern).__name__})"
                        )

                    if not pattern_str:
                        report.add_warning(f"Entity '{name}' tiene pattern vacío en posición {i}")

        elif source == 'regex':
            regex_pattern = getattr(entity, 'regex_pattern', None)
            if not regex_pattern:
                report.add_critical(f"Entity regex '{name}' no tiene pattern")
            else:
                try:
                    re.compile(regex_pattern)
                except re.error as e:
                    report.add_critical(f"Entity regex '{name}' tiene pattern inválido: {e}")
        
        elif source == 'alias':
            alias_of = getattr(entity, 'alias_of', None)
            if not alias_of:
                report.add_critical(f"Entity alias '{name}' no tiene alias_of")
    
    def _validate_entity_aliases(self, entities: Dict[str, Any], report: ValidationReport):
        """Valida que los alias referencien entidades existentes"""
        for name, entity in entities.items():
            if getattr(entity, 'source', '') == 'alias':
                alias_of = getattr(entity, 'alias_of', None)
                if alias_of and alias_of not in entities:
                    report.add_critical(f"Alias '{name}' referencia entidad inexistente '{alias_of}'")
    
    def _validate_entity_duplicates(self, entities: Dict[str, Any], report: ValidationReport):
        """Detecta posibles duplicados en entidades"""
        csv_entities = {name: entity for name, entity in entities.items() 
                       if getattr(entity, 'source', '') == 'csv'}
        
        for name1, entity1 in csv_entities.items():
            values1 = set(getattr(entity1, 'values', []))
            
            for name2, entity2 in csv_entities.items():
                if name1 >= name2:
                    continue
                
                values2 = set(getattr(entity2, 'values', []))
                
                if values1 and values2:
                    intersection = len(values1 & values2)
                    union = len(values1 | values2)
                    similarity = intersection / union if union > 0 else 0
                    
                    if similarity > 0.8:
                        report.add_warning(f"Entidades '{name1}' y '{name2}' son muy similares ({similarity:.1%})")
    
    def _validate_entity_roles_and_groups(self, entities: Dict[str, Any], templates_config: Dict[str, Any], report: ValidationReport):
        """Valida roles y grupos de entidades"""
        entity_roles = templates_config.get('entity_roles', {})
        
        if not entity_roles:
            report.add_warning("No se encontró configuración de entity_roles en templates.yml")
            return
        
        # Validar que las entidades con roles existan
        entities_with_roles = set()
        total_roles = 0
        
        for entity_name, roles in entity_roles.items():
            if not isinstance(roles, list):
                report.add_critical(f"Entity '{entity_name}' tiene roles en formato inválido (debe ser lista)")
                continue
            
            total_roles += len(roles)
            entities_with_roles.add(entity_name)
            
            if entity_name not in entities:
                report.add_warning(f"Entity '{entity_name}' tiene roles definidos pero no existe")
            else:
                report.add_info(f"Entity '{entity_name}' tiene {len(roles)} roles definidos")
        
        # Estadísticas de roles
        report.stats.update({
            "entities_with_roles": len(entities_with_roles),
            "total_roles_defined": total_roles,
            "role_coverage": len(entities_with_roles) / len(entities) if entities else 0
        })
        
        # Advertencias sobre cobertura
        if len(entities_with_roles) / len(entities) < 0.5:
            report.add_warning(f"Solo {len(entities_with_roles)}/{len(entities)} entidades tienen roles definidos")


class IntentValidator:
    """Validador especializado para intents con soporte para templates con roles"""
    
    def validate_intent_consistency(self, intents: Dict[str, Any], entities: Set[str], templates_config: Dict[str, Any] = None) -> ValidationReport:
        """Valida consistencia de intents"""
        report = ValidationReport()
        
        # Estadísticas básicas
        report.stats["total_intents"] = len(intents)
        
        with_examples = 0
        with_templates = 0
        with_responses = 0
        group_counts = {}
        
        for name, intent in intents.items():
            # Validar estructura
            self._validate_intent_structure(name, intent, report)
            
            # Validar contenido
            self._validate_intent_content(name, intent, entities, report)
            
            # Validar templates con roles
            if templates_config:
                self._validate_intent_templates_with_roles(name, intent, entities, templates_config, report)
            
            # Estadísticas
            if getattr(intent, 'examples', []):
                with_examples += 1
            if getattr(intent, 'templates', []):
                with_templates += 1
            if getattr(intent, 'responses', []):
                with_responses += 1
            
            group = getattr(intent, 'group', 'unknown')
            group_counts[group] = group_counts.get(group, 0) + 1
        
        report.stats.update({
            "with_examples": with_examples,
            "with_templates": with_templates,
            "with_responses": with_responses,
            "by_group": group_counts
        })
        
        # Validaciones específicas
        self._validate_intent_flows(intents, report)
        self._validate_intent_groups(intents, report)
        
        return report
    
    def _validate_intent_structure(self, name: str, intent: Any, report: ValidationReport):
        """Valida estructura básica de un intent"""
        required_attrs = ['name', 'group']
        
        for attr in required_attrs:
            if not hasattr(intent, attr):
                report.add_critical(f"Intent '{name}' no tiene atributo requerido: {attr}")
    
    def _validate_intent_content(self, name: str, intent: Any, entities: Set[str], report: ValidationReport):
        """Valida contenido de un intent"""
        examples = getattr(intent, 'examples', [])
        templates = getattr(intent, 'templates', [])
        
        # Validación crítica: debe tener ejemplos O templates
        if not examples and not templates:
            report.add_critical(f"Intent '{name}' no tiene ejemplos ni templates")
        
        # Validar ejemplos
        if examples:
            for i, example in enumerate(examples):
                if not isinstance(example, str) or len(example.strip()) < 2:
                    report.add_warning(f"Intent '{name}' tiene ejemplo inválido en posición {i}")
        
        # Validar templates
        if templates:
            for i, template in enumerate(templates):
                if not isinstance(template, str):
                    report.add_warning(f"Intent '{name}' tiene template inválido en posición {i}")
                else:
                    # Validar placeholders en templates
                    self._validate_template_placeholders(name, template, entities, report)
        
        # Validar entidades referenciadas
        intent_entities = getattr(intent, 'entities', [])
        for entity in intent_entities:
            if entity not in entities:
                report.add_critical(f"Intent '{name}' referencia entidad inexistente: '{entity}'")
    
    def _validate_template_placeholders(self, intent_name: str, template: str, entities: Set[str], report: ValidationReport):
        """Valida placeholders en templates incluyendo sintaxis con roles"""
        # Detectar placeholders con y sin roles: {entity} y {entity:role}
        placeholder_pattern = r'\{([^}:]+)(?::([^}]+))?\}'
        matches = re.findall(placeholder_pattern, template)
        
        for entity, role in matches:
            if entity not in entities:
                # Verificar si es un placeholder común que debería existir
                common_placeholders = {
                    'producto', 'proveedor', 'categoria', 'animal', 'comparador',
                    'cantidad_descuento', 'cantidad_bonificacion', 'dia', 'fecha'
                }
                
                if entity in common_placeholders:
                    report.add_critical(f"Intent '{intent_name}' usa placeholder común '{entity}' que no existe como entidad")
                else:
                    report.add_warning(f"Intent '{intent_name}' usa placeholder desconocido: '{entity}'")
            
            # Si tiene role, validar que sea válido (esto se puede expandir)
            if role:
                report.add_info(f"Intent '{intent_name}' usa placeholder con role: {entity}:{role}")
    
    def _validate_intent_templates_with_roles(self, intent_name: str, intent: Any, entities: Set[str], templates_config: Dict[str, Any], report: ValidationReport):
        """Valida templates con roles específicos"""
        templates = getattr(intent, 'templates', [])
        entity_roles = templates_config.get('entity_roles', {})
        
        for template in templates:
            # Encontrar placeholders con roles
            placeholder_pattern = r'\{([^}:]+):([^}]+)\}'
            role_matches = re.findall(placeholder_pattern, template)
            
            for entity, role in role_matches:
                if entity in entity_roles:
                    if role not in entity_roles[entity]:
                        report.add_warning(f"Intent '{intent_name}' usa role '{role}' no definido para entity '{entity}'")
                else:
                    report.add_warning(f"Intent '{intent_name}' usa entity '{entity}' con role pero no tiene roles definidos")
    
    def _validate_intent_flows(self, intents: Dict[str, Any], report: ValidationReport):
        """Valida flujos entre intents"""
        intent_names = set(intents.keys())
        
        for name, intent in intents.items():
            next_intents = getattr(intent, 'next_intents', [])
            
            for next_intent in next_intents:
                if next_intent not in intent_names:
                    report.add_warning(f"Intent '{name}' referencia next_intent inexistente: '{next_intent}'")
    
    def _validate_intent_groups(self, intents: Dict[str, Any], report: ValidationReport):
        """Valida grupos de intents"""
        groups = set()
        for intent in intents.values():
            groups.add(getattr(intent, 'group', 'unknown'))
        
        # Verificar que haya grupos balanceados
        group_sizes = {}
        for group in groups:
            group_intents = [i for i in intents.values() if getattr(i, 'group', '') == group]
            group_sizes[group] = len(group_intents)
        
        # Advertir sobre grupos con pocos intents
        for group, size in group_sizes.items():
            if size == 1:
                report.add_warning(f"Grupo '{group}' tiene solo 1 intent")


class ConfigValidator:
    """Validador principal que orquesta todas las validaciones"""
    
    def __init__(self, config_dir: str, data_dir: str):
        self.config_dir = Path(config_dir)
        self.data_dir = Path(data_dir)
        
        self.file_validator = FileValidator(self.config_dir, self.data_dir)
        self.entity_validator = EntityValidator()
        self.intent_validator = IntentValidator()
        self.segment_validator = SegmentValidator(self.config_dir)
    
    def validate_complete_config(self, entities: Dict[str, Any], intents: Dict[str, Any], segments: Dict[str, Any] = None, templates_config: Dict[str, Any] = None) -> ValidationReport:
        """Ejecuta validación completa del sistema incluyendo roles, grupos y segmentos"""
        report = ValidationReport()
        
        # 1. Validar archivos
        file_report = self.file_validator.validate_required_files()
        self._merge_reports(report, file_report, "FILES")
        
        # 2. Validar entidades (con roles y grupos)
        entity_report = self.entity_validator.validate_entity_consistency(entities, templates_config)
        self._merge_reports(report, entity_report, "ENTITIES")
        
        # 3. Validar intents (con templates con roles)
        entity_names = set(entities.keys())
        intent_report = self.intent_validator.validate_intent_consistency(intents, entity_names, templates_config)
        self._merge_reports(report, intent_report, "INTENTS")
        
        # 4. Validar segmentos si existen
        if segments:
            segment_report = self.segment_validator.validate_segments(segments)
            self._merge_reports(report, segment_report, "SEGMENTS")
        
        # 5. Validaciones cruzadas
        self._validate_cross_dependencies(entities, intents, segments, report)
        
        # 6. Validar configuración de templates si existe
        if templates_config:
            self._validate_templates_config(templates_config, entities, report)
        
        # Compilar estadísticas finales
        report.stats["validation_summary"] = {
            "total_critical_errors": len(report.critical_errors),
            "total_warnings": len(report.warnings),
            "validation_passed": report.is_valid
        }
        
        return report
    
    def _merge_reports(self, main_report: ValidationReport, sub_report: ValidationReport, context: str):
        """Combina reportes de validación"""
        for error in sub_report.critical_errors:
            main_report.add_critical(error, context)
        
        for warning in sub_report.warnings:
            main_report.add_warning(warning, context)
        
        for info in sub_report.info:
            main_report.add_info(info, context)
        
        # Combinar estadísticas
        for key, value in sub_report.stats.items():
            main_report.stats[f"{context.lower()}_{key}"] = value
    
    def _validate_cross_dependencies(self, entities: Dict[str, Any], intents: Dict[str, Any], segments: Dict[str, Any], report: ValidationReport):
        """Valida dependencias cruzadas entre componentes"""
        # Verificar que intents de búsqueda tengan entidades relevantes
        search_intents = [name for name, intent in intents.items() 
                         if 'buscar' in name.lower() or getattr(intent, 'group', '') == 'search']
        
        core_entities = {'producto', 'categoria', 'proveedor'}
        available_core = core_entities & set(entities.keys())
        
        if search_intents and len(available_core) < 2:
            report.add_critical(f"Tienes intents de búsqueda pero faltan entidades core: {core_entities - available_core}")
        
        # Verificar que haya intents starter
        starter_intents = [name for name, intent in intents.items() 
                          if getattr(intent, 'starter_allowed', True)]
        
        if len(starter_intents) == 0:
            report.add_critical("No hay intents que puedan iniciar conversaciones")
        elif len(starter_intents) < 3:
            report.add_warning(f"Pocos intents starter ({len(starter_intents)}), considera agregar más")
        
        # Validar que haya segmentos si se usan en templates
        if segments:
            segment_names = set(segments.keys())
            
            # Buscar referencias a segmentos en templates
            used_segments = set()
            for intent in intents.values():
                templates = getattr(intent, 'templates', [])
                for template in templates:
                    placeholders = re.findall(r'\{([^}:]+)', template)
                    for placeholder in placeholders:
                        if placeholder in segment_names:
                            used_segments.add(placeholder)
            
            unused_segments = segment_names - used_segments
            if unused_segments:
                report.add_info(f"Segmentos cargados pero no usados en templates: {list(unused_segments)}")
    
    def _validate_templates_config(self, templates_config: Dict[str, Any], entities: Dict[str, Any], report: ValidationReport):
        """Valida configuración específica de templates"""
        entity_roles = templates_config.get('entity_roles', {})
        generation_config = templates_config.get('generation_config', {})
        
        # Validar entity_roles
        if entity_roles:
            for entity_name, roles in entity_roles.items():
                if entity_name not in entities:
                    report.add_warning(f"Entity_roles define roles para entity inexistente: '{entity_name}'")
                
                if not isinstance(roles, list):
                    report.add_critical(f"Entity_roles para '{entity_name}' debe ser una lista")
        
        # Validar generation_config
        if generation_config:
            template_validation = generation_config.get('template_validation', {})
            if template_validation:
                required_entities = template_validation.get('required_entities', [])
                for entity in required_entities:
                    if entity not in entities:
                        report.add_critical(f"Generation_config requiere entity inexistente: '{entity}'")
            
            entity_roles_config = generation_config.get('entity_roles', {})
            if entity_roles_config:
                for entity_name in entity_roles_config.keys():
                    if entity_name not in entities:
                        report.add_warning(f"Generation_config define roles para entity inexistente: '{entity_name}'")