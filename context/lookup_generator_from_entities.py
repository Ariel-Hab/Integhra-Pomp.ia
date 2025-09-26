#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lookup Tables Generator - Genera lookup tables automáticamente desde entity loaders
Versión: 1.0 - Integración completa con entity_loaders.py
"""

import yaml
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass
from collections import defaultdict

# Importar el sistema de entity loaders existente
from entity_loaders import (
    EntityDefinition, PatternEntityLoader, CSVEntityLoader, 
    RegexEntityLoader, AliasEntityLoader, EntityManager,
    ConfigValidationError, MissingDataError
)

logger = logging.getLogger(__name__)

@dataclass
class LookupTableConfig:
    """Configuración para generación de lookup tables"""
    max_values_per_lookup: int = 50
    min_values_for_lookup: int = 5
    exclude_entities: Set[str] = None
    include_entity_patterns: List[str] = None
    generate_synonyms: bool = True
    generate_regex: bool = True
    
    def __post_init__(self):
        if self.exclude_entities is None:
            self.exclude_entities = {'sentimiento', 'tiempo', 'indicador_temporal'}
        if self.include_entity_patterns is None:
            self.include_entity_patterns = [
                'producto*', 'proveedor*', 'categoria*', 'animal*', 
                'dosis*', 'estado*', 'ingrediente_activo*'
            ]

class EntityBasedLookupGenerator:
    """Generador de lookup tables basado en entity loaders"""
    
    def __init__(self, data_dir: Path, config_dir: Path, config: LookupTableConfig = None):
        self.data_dir = data_dir
        self.config_dir = config_dir
        self.config = config or LookupTableConfig()
        
        # Integrar con el EntityManager existente
        self.entity_manager = EntityManager(data_dir, config_dir)
        
        # Datos generados
        self.lookup_tables: Dict[str, List[str]] = {}
        self.regex_patterns: Dict[str, str] = {}
        self.synonyms: Dict[str, List[str]] = {}
        
    def load_entities_and_generate_lookups(self):
        """Carga entidades y genera lookup tables automáticamente"""
        logger.info("Cargando entidades y generando lookup tables...")
        
        # Usar el EntityManager existente para cargar todas las entidades
        self.entity_manager.load_all_entities()
        
        # Generar lookup tables desde entidades cargadas
        self._generate_lookup_tables_from_entities()
        
        # Generar regex patterns
        if self.config.generate_regex:
            self._generate_regex_patterns()
        
        # Generar synonyms
        if self.config.generate_synonyms:
            self._generate_synonyms_from_segments()
        
        logger.info(f"Generadas {len(self.lookup_tables)} lookup tables, "
                   f"{len(self.regex_patterns)} regex patterns, "
                   f"{len(self.synonyms)} synonyms")
    
    def _generate_lookup_tables_from_entities(self):
        """Genera lookup tables desde las entidades cargadas"""
        logger.info("Generando lookup tables desde entidades...")
        
        for entity_name, values in self.entity_manager.entity_values.items():
            # Filtrar entidades excluidas
            if entity_name in self.config.exclude_entities:
                logger.debug(f"Saltando entidad excluida: {entity_name}")
                continue
            
            # Verificar si cumple con los patrones incluidos
            if not self._should_include_entity(entity_name):
                logger.debug(f"Saltando entidad no incluida: {entity_name}")
                continue
            
            # Verificar cantidad mínima de valores
            if len(values) < self.config.min_values_for_lookup:
                logger.debug(f"Saltando entidad con pocos valores: {entity_name} ({len(values)})")
                continue
            
            # Limpiar y limitar valores
            cleaned_values = self._clean_entity_values(values, entity_name)
            
            if cleaned_values:
                # Usar nombre limpio para la lookup table
                lookup_name = self._get_lookup_name(entity_name)
                self.lookup_tables[lookup_name] = cleaned_values[:self.config.max_values_per_lookup]
                logger.debug(f"Lookup table '{lookup_name}': {len(self.lookup_tables[lookup_name])} valores")
    
    def _should_include_entity(self, entity_name: str) -> bool:
        """Verifica si una entidad debe incluirse en lookup tables"""
        # Entidades que empiezan con 'segment_' generalmente no son para lookup
        if entity_name.startswith('segment_'):
            return False
        
        # Verificar patrones incluidos
        for pattern in self.config.include_entity_patterns:
            if pattern.endswith('*'):
                if entity_name.startswith(pattern[:-1]):
                    return True
            elif pattern == entity_name:
                return True
        
        return False
    
    def _clean_entity_values(self, values: List[str], entity_name: str) -> List[str]:
        """Limpia y normaliza valores de entidades"""
        cleaned = []
        seen = set()
        
        for value in values:
            if not value or not isinstance(value, str):
                continue
            
            # Limpiar valor
            clean_value = value.strip().lower()
            
            # Evitar duplicados
            if clean_value in seen:
                continue
            
            # Filtros específicos por tipo de entidad
            if self._is_valid_value(clean_value, entity_name):
                cleaned.append(value.strip())  # Mantener capitalización original
                seen.add(clean_value)
        
        return cleaned
    
    def _is_valid_value(self, value: str, entity_name: str) -> bool:
        """Valida si un valor es apropiado para lookup table"""
        # Filtros básicos
        if len(value) < 2 or len(value) > 50:
            return False
        
        # No incluir valores que parecen códigos o IDs
        if value.isdigit() or (len(value) < 4 and any(c.isdigit() for c in value)):
            return False
        
        # Filtros específicos por entidad
        if entity_name in ['producto', 'categoria']:
            # Para productos, evitar valores muy genéricos
            generic_terms = {'producto', 'medicamento', 'droga', 'medicina'}
            if value in generic_terms:
                return False
        
        return True
    
    def _get_lookup_name(self, entity_name: str) -> str:
        """Obtiene nombre limpio para lookup table"""
        # Remover prefijos comunes
        name = entity_name
        prefixes_to_remove = ['segment_', 'entity_']
        
        for prefix in prefixes_to_remove:
            if name.startswith(prefix):
                name = name[len(prefix):]
        
        return name
    
    def _generate_regex_patterns(self):
        """Genera patterns regex para entidades numéricas"""
        logger.info("Generando patterns regex...")
        
        # Patterns para entidades numéricas comunes
        regex_definitions = {
            'cantidad_descuento': r'\d{1,2}%|\d{1,2}\s*por\s*ciento|\d{1,2}\s*porciento',
            'cantidad_bonificacion': r'\d+\s*x\s*\d+|lleva\s+\d+\s+paga\s+\d+|\d+\s*por\s*\d+',
            'cantidad_stock': r'\d{1,6}|\d{1,3}\.?\d{0,3}|más\s+de\s+\d+|menos\s+de\s+\d+',
            'precio_monto': r'\$\d{1,6}|\d{1,6}\s*pesos?|\d{1,6}\s*pe|\d{1,6}\.\d{2}',
            'fecha_especifica': r'\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}-\d{1,2}-\d{2,4}|\d{1,2}\s+de\s+\w+'
        }
        
        # Verificar si tenemos entidades correspondientes
        for pattern_name, pattern_regex in regex_definitions.items():
            if pattern_name in self.entity_manager.entity_values or any(
                name.startswith(pattern_name) for name in self.entity_manager.entity_values
            ):
                self.regex_patterns[pattern_name] = pattern_regex
                logger.debug(f"Pattern regex '{pattern_name}': {pattern_regex}")
    
    def _generate_synonyms_from_segments(self):
        """Genera synonyms desde los segmentos de conversación"""
        logger.info("Generando synonyms desde segmentos...")
        
        # Usar segmentos del EntityManager
        for segment_name, segment_values in self.entity_manager.segments.items():
            if len(segment_values) >= 2:  # Solo crear synonym si hay múltiples valores
                # Limpiar nombre del synonym
                synonym_name = segment_name.replace('_', ' ').replace('-', ' ')
                self.synonyms[synonym_name] = segment_values[:15]  # Limitar cantidad
                logger.debug(f"Synonym '{synonym_name}': {len(segment_values)} valores")
        
        # Synonyms adicionales basados en entidades
        self._generate_entity_based_synonyms()
    
    def _generate_entity_based_synonyms(self):
        """Genera synonyms adicionales basados en patrones de entidades"""
        # Synonyms para acciones de búsqueda
        search_actions = []
        if 'intencion_buscar' in self.entity_manager.entity_values:
            search_actions = self.entity_manager.entity_values['intencion_buscar'][:10]
        
        if not search_actions:
            search_actions = ['buscar', 'necesitar', 'querer', 'mostrar', 'conseguir']
        
        self.synonyms['buscar_accion'] = search_actions
        
        # Synonyms para confirmaciones (si no existen desde segmentos)
        if 'confirmacion_positiva' not in self.synonyms:
            self.synonyms['confirmacion_positiva'] = [
                'sí', 'dale', 'perfecto', 'está bien', 'genial', 'bárbaro'
            ]
        
        if 'confirmacion_negativa' not in self.synonyms:
            self.synonyms['confirmacion_negativa'] = [
                'no', 'no me sirve', 'no me convence', 'prefiero otra cosa'
            ]
    
    def export_to_yaml(self, output_file: Path) -> Path:
        """Exporta lookup tables, regex y synonyms a archivo YAML"""
        logger.info(f"Exportando lookup tables a {output_file}...")
        
        nlu_data = {
            'version': '3.1',
            'nlu': []
        }
        
        # Agregar lookup tables
        for lookup_name, values in self.lookup_tables.items():
            lookup_entry = {
                'lookup': lookup_name,
                'examples': self._format_values_as_yaml(values)
            }
            nlu_data['nlu'].append(lookup_entry)
        
        # Agregar regex patterns
        for regex_name, pattern in self.regex_patterns.items():
            regex_entry = {
                'regex': regex_name,
                'examples': f"- {pattern}"
            }
            nlu_data['nlu'].append(regex_entry)
        
        # Agregar synonyms
        for synonym_name, values in self.synonyms.items():
            synonym_entry = {
                'synonym': synonym_name,
                'examples': self._format_values_as_yaml(values)
            }
            nlu_data['nlu'].append(synonym_entry)
        
        # Guardar archivo
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            yaml.dump(nlu_data, f, default_flow_style=False, 
                     allow_unicode=True, sort_keys=False)
        
        logger.info(f"Lookup tables exportadas exitosamente: {output_file}")
        return output_file
    
    def _format_values_as_yaml(self, values: List[str]) -> str:
        """Formatea valores como string YAML multilínea"""
        formatted_values = []
        for value in values:
            formatted_values.append(f"- {value}")
        return '\n'.join(formatted_values)
    
    def get_lookup_values(self, entity_name: str, limit: int = 20) -> List[str]:
        """Obtiene valores de una lookup table generada"""
        values = self.lookup_tables.get(entity_name, [])
        if not values:
            # Intentar variaciones del nombre
            alt_names = [
                f"{entity_name}s",
                entity_name.rstrip('s'),
                entity_name.replace('_', ''),
                entity_name.replace('-', '_')
            ]
            for alt_name in alt_names:
                values = self.lookup_tables.get(alt_name, [])
                if values:
                    break
        
        return values[:limit] if values else []
    
    def generate_stats(self) -> Dict[str, Any]:
        """Genera estadísticas de lookup tables generadas"""
        return {
            'total_lookup_tables': len(self.lookup_tables),
            'total_regex_patterns': len(self.regex_patterns),
            'total_synonyms': len(self.synonyms),
            'lookup_table_stats': {
                name: {
                    'total_values': len(values),
                    'sample_values': values[:5]
                }
                for name, values in self.lookup_tables.items()
            },
            'entity_coverage': {
                'entities_loaded': len(self.entity_manager.entity_values),
                'entities_converted_to_lookup': len(self.lookup_tables),
                'conversion_rate': len(self.lookup_tables) / len(self.entity_manager.entity_values) if self.entity_manager.entity_values else 0
            },
            'source_breakdown': {
                'from_csv_entities': len([
                    name for name, entity in self.entity_manager.entities.items() 
                    if entity.source == 'csv'
                ]),
                'from_pattern_entities': len([
                    name for name, entity in self.entity_manager.entities.items() 
                    if entity.source == 'pattern'
                ]),
                'from_segments': len(self.entity_manager.segments)
            }
        }

def main():
    """Función principal para generar lookup tables"""
    config_dir = Path("config")
    data_dir = Path("data")
    output_dir = Path("generated")
    
    # Configuración
    config = LookupTableConfig(
        max_values_per_lookup=40,
        min_values_for_lookup=3,
        exclude_entities={'sentimiento', 'tiempo'},
        generate_synonyms=True,
        generate_regex=True
    )
    
    # Crear generador
    generator = EntityBasedLookupGenerator(data_dir, config_dir, config)
    
    try:
        # Cargar entidades y generar lookup tables
        generator.load_entities_and_generate_lookups()
        
        # Exportar lookup tables
        lookup_file = generator.export_to_yaml(output_dir / "lookup_tables_generated.yml")
        
        # Generar estadísticas
        stats = generator.generate_stats()
        import json
        with open(output_dir / "lookup_generation_stats.json", 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        
        print(f"\nLookup Tables generadas exitosamente!")
        print(f"Archivo: {lookup_file}")
        print(f"Lookup tables: {stats['total_lookup_tables']}")
        print(f"Regex patterns: {stats['total_regex_patterns']}")
        print(f"Synonyms: {stats['total_synonyms']}")
        print(f"Cobertura: {stats['entity_coverage']['conversion_rate']:.1%}")
        
    except Exception as e:
        logger.error(f"Error generando lookup tables: {e}")
        raise

if __name__ == "__main__":
    main()