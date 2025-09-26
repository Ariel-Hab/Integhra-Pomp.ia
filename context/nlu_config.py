#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NLU Configuration - Integración con Entity Loaders existente
Versión: 1.0
"""

import yaml
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

# Importar los loaders existentes
from entity_loaders import (
    EntityDefinition, PatternEntityLoader, CSVEntityLoader, 
    RegexEntityLoader, AliasEntityLoader, ValidationResult
)

logger = logging.getLogger(__name__)

@dataclass
class NLUConfig:
    """Configuración completa para generación de NLU"""
    
    # Configuración de entidades y grupos
    entity_groups: Dict[str, str] = field(default_factory=dict)
    
    # Configuración de intents
    intent_settings: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Configuración de generación
    generation_settings: Dict[str, Any] = field(default_factory=dict)

class EntityLoaderIntegration:
    """Integración con los entity loaders existentes"""
    
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.data_dir = config_dir / 'data'
        self.entities_file = config_dir / 'entities.yml'
        self.entities_regex_file = config_dir / 'entities_regex.yml'
        
        # Configuración por defecto
        self.default_config = self._load_default_config()
        
    def _load_default_config(self) -> NLUConfig:
        """Carga configuración por defecto"""
        return NLUConfig(
            entity_groups={
                # Entidades principales de búsqueda
                'producto': 'search_primary',
                'categoria': 'search_primary',
                
                # Entidades secundarias de búsqueda  
                'proveedor': 'search_secondary',
                'ingrediente_activo': 'search_secondary',
                
                # Filtros temporales
                'fecha': 'temporal_filters',
                'dia': 'temporal_filters', 
                'indicador_temporal': 'temporal_filters',
                
                # Filtros numéricos
                'cantidad_descuento': 'numeric_filters',
                'cantidad_bonificacion': 'numeric_filters',
                'cantidad_stock': 'numeric_filters',
                'dosis': 'numeric_filters',
                
                # Filtros comparativos
                'comparador': 'comparative_filters',
                
                # Filtros de contexto
                'animal': 'context_filters',
                'estado': 'context_filters',
            },
            
            intent_settings={
                # Configuración específica por intent
                'buscar_producto': {
                    'max_examples_per_template': 5,
                    'use_entity_combinations': True,
                    'priority_entities': ['producto', 'categoria'],
                    'optional_entities': ['proveedor', 'animal', 'fecha']
                },
                'buscar_oferta': {
                    'max_examples_per_template': 4,
                    'use_entity_combinations': True,
                    'priority_entities': ['cantidad_descuento', 'cantidad_bonificacion'],
                    'required_entities': ['cantidad_descuento', 'cantidad_bonificacion']
                },
                'consultar_novedades': {
                    'max_examples_per_template': 3,
                    'use_entity_combinations': False,
                    'priority_entities': ['indicador_temporal', 'fecha']
                },
                'saludo': {
                    'max_examples_per_template': 0,  # Solo ejemplos estáticos
                    'use_templates': False
                },
                'despedida': {
                    'max_examples_per_template': 0,  # Solo ejemplos estáticos
                    'use_templates': False
                }
            },
            
            generation_settings={
                'avoid_duplicates': True,
                'balance_entity_usage': True,
                'max_total_examples_per_intent': 20,
                'include_empty_entity_variants': True,
                'smart_combination_selection': True
            }
        )
    
    def load_all_entities(self) -> Dict[str, EntityDefinition]:
        """Carga todas las entidades usando los loaders existentes"""
        logger.info("Iniciando carga completa de entidades...")
        
        all_entities = {}
        
        try:
            # 1. Cargar Pattern Entities
            logger.info("Cargando Pattern Entities...")
            pattern_loader = PatternEntityLoader(self.entities_file)
            pattern_entities = pattern_loader.load_entities({})
            
            # Validar pattern entities
            pattern_validation = pattern_loader.validate(pattern_entities)
            if not pattern_validation.is_valid:
                logger.error(f"Errores en pattern entities: {pattern_validation.critical_errors}")
                for error in pattern_validation.critical_errors:
                    logger.error(f"  - {error}")
            
            if pattern_validation.warnings:
                for warning in pattern_validation.warnings:
                    logger.warning(f"  - {warning}")
            
            all_entities.update(pattern_entities)
            logger.info(f"✅ Cargadas {len(pattern_entities)} pattern entities")
            
        except Exception as e:
            logger.error(f"Error cargando pattern entities: {e}")
        
        try:
            # 2. Cargar CSV Entities
            logger.info("Cargando CSV Entities...")
            csv_loader = CSVEntityLoader(self.data_dir, self.entities_file)
            csv_entities = csv_loader.load_entities({})
            
            # Validar CSV entities
            csv_validation = csv_loader.validate(csv_entities)
            if not csv_validation.is_valid:
                logger.error(f"Errores en CSV entities: {csv_validation.critical_errors}")
                for error in csv_validation.critical_errors:
                    logger.error(f"  - {error}")
            
            if csv_validation.warnings:
                for warning in csv_validation.warnings:
                    logger.warning(f"  - {warning}")
            
            all_entities.update(csv_entities)
            logger.info(f"✅ Cargadas {len(csv_entities)} CSV entities")
            
        except Exception as e:
            logger.error(f"Error cargando CSV entities: {e}")
        
        try:
            # 3. Cargar Regex Entities
            logger.info("Cargando Regex Entities...")
            regex_loader = RegexEntityLoader(self.entities_file, self.entities_regex_file)
            regex_entities = regex_loader.load_entities({})
            
            # Validar regex entities
            regex_validation = regex_loader.validate(regex_entities)
            if not regex_validation.is_valid:
                logger.error(f"Errores en regex entities: {regex_validation.critical_errors}")
                for error in regex_validation.critical_errors:
                    logger.error(f"  - {error}")
            
            all_entities.update(regex_entities)
            logger.info(f"✅ Cargadas {len(regex_entities)} regex entities")
            
        except Exception as e:
            logger.error(f"Error cargando regex entities: {e}")
        
        try:
            # 4. Cargar Alias Entities
            logger.info("Cargando Alias Entities...")
            alias_loader = AliasEntityLoader(self.entities_file)
            alias_entities = alias_loader.load_entities({})
            
            # Validar alias entities
            alias_validation = alias_loader.validate(alias_entities)
            if not alias_validation.is_valid:
                logger.error(f"Errores en alias entities: {alias_validation.critical_errors}")
            
            all_entities.update(alias_entities)
            logger.info(f"✅ Cargadas {len(alias_entities)} alias entities")
            
        except Exception as e:
            logger.error(f"Error cargando alias entities: {e}")
        
        # 5. Resolver alias entities
        resolved_entities = self._resolve_aliases(all_entities)
        
        logger.info(f"🎯 TOTAL: {len(resolved_entities)} entidades cargadas y validadas")
        
        # Log resumen por tipo
        by_source = {}
        for entity in resolved_entities.values():
            source = entity.source
            by_source[source] = by_source.get(source, 0) + 1
        
        logger.info("📊 Resumen por tipo:")
        for source, count in by_source.items():
            logger.info(f"   {source}: {count} entidades")
        
        return resolved_entities
    
    def _resolve_aliases(self, entities: Dict[str, EntityDefinition]) -> Dict[str, EntityDefinition]:
        """Resuelve alias entities copiando valores de entidades origen"""
        logger.info("Resolviendo alias entities...")
        
        resolved = {}
        
        # Primero agregar todas las entidades no-alias
        for name, entity in entities.items():
            if entity.source != 'alias':
                resolved[name] = entity
        
        # Luego resolver los alias
        for name, entity in entities.items():
            if entity.source == 'alias':
                if entity.alias_of in resolved:
                    source_entity = resolved[entity.alias_of]
                    
                    # Crear nueva entidad copiando valores de la fuente
                    resolved_entity = EntityDefinition(
                        name=name,
                        source='alias',
                        type=source_entity.type,
                        values=source_entity.values[:] if source_entity.values else [],
                        patterns=source_entity.patterns[:] if source_entity.patterns else [],
                        regex_pattern=source_entity.regex_pattern,
                        alias_of=entity.alias_of,
                        description=f"Alias of {entity.alias_of}"
                    )
                    
                    resolved[name] = resolved_entity
                    logger.debug(f"✅ Alias '{name}' -> '{entity.alias_of}' resuelto")
                else:
                    logger.error(f"❌ Alias '{name}' referencia entidad inexistente: '{entity.alias_of}'")
        
        return resolved
    
    def get_entity_values(self, entity_name: str, entities: Dict[str, EntityDefinition]) -> List[str]:
        """Obtiene valores de una entidad específica"""
        if entity_name not in entities:
            logger.warning(f"Entity '{entity_name}' no encontrada")
            return []
        
        entity = entities[entity_name]
        
        # Priorizar values sobre patterns
        if entity.values:
            return [v for v in entity.values if v and v.strip()]
        elif entity.patterns:
            return [p for p in entity.patterns if p and p.strip()]
        else:
            logger.warning(f"Entity '{entity_name}' sin valores disponibles")
            return []
    
    def save_config(self, config: NLUConfig, config_file: Path):
        """Guarda configuración en archivo YAML"""
        config_data = {
            'entity_groups': config.entity_groups,
            'intent_settings': config.intent_settings,
            'generation_settings': config.generation_settings
        }
        
        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f, default_flow_style=False, 
                     allow_unicode=True, sort_keys=False, indent=2)
        
        logger.info(f"Configuración guardada: {config_file}")
    
    def load_config(self, config_file: Path) -> NLUConfig:
        """Carga configuración desde archivo YAML"""
        if not config_file.exists():
            logger.warning(f"Archivo de configuración no encontrado: {config_file}")
            return self.default_config
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            return NLUConfig(
                entity_groups=config_data.get('entity_groups', {}),
                intent_settings=config_data.get('intent_settings', {}),
                generation_settings=config_data.get('generation_settings', {})
            )
        except Exception as e:
            logger.error(f"Error cargando configuración: {e}")
            return self.default_config

# Función auxiliar para debugging de entidades
def debug_entities(entities: Dict[str, EntityDefinition], entity_name: str = None):
    """Función helper para debuggear entidades cargadas"""
    if entity_name:
        if entity_name in entities:
            entity = entities[entity_name]
            print(f"\n🔍 DEBUG Entity: {entity_name}")
            print(f"   Source: {entity.source}")
            print(f"   Type: {entity.type}")
            print(f"   Values: {len(entity.values) if entity.values else 0}")
            print(f"   Patterns: {len(entity.patterns) if entity.patterns else 0}")
            
            if entity.values:
                print(f"   Sample values: {entity.values[:5]}")
            if entity.patterns:
                print(f"   Sample patterns: {entity.patterns[:5]}")
        else:
            print(f"❌ Entity '{entity_name}' no encontrada")
    else:
        print(f"\n📊 RESUMEN DE ENTIDADES ({len(entities)} total)")
        print("=" * 50)
        
        by_source = {}
        for entity in entities.values():
            source = entity.source
            by_source[source] = by_source.get(source, 0) + 1
        
        for source, count in by_source.items():
            print(f"{source:15}: {count:3} entidades")
        
        print("\n📝 LISTADO COMPLETO:")
        for name, entity in sorted(entities.items()):
            values_count = len(entity.values) if entity.values else 0
            patterns_count = len(entity.patterns) if entity.patterns else 0
            print(f"  {name:20} ({entity.source:8}) - {values_count:3}v/{patterns_count:3}p")

def main():
    """Función para testing de la integración"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    config_dir = Path("config")
    integration = EntityLoaderIntegration(config_dir)
    
    try:
        # Cargar todas las entidades
        entities = integration.load_all_entities()
        
        # Debug general
        debug_entities(entities)
        
        # Debug entidades específicas
        debug_entities(entities, 'producto')
        debug_entities(entities, 'proveedor')
        debug_entities(entities, 'cantidad_descuento')
        
        # Guardar configuración por defecto
        config_file = config_dir / 'nlu_config.yml'
        integration.save_config(integration.default_config, config_file)
        
        print(f"\n✅ Testing completado!")
        print(f"📁 Configuración guardada en: {config_file}")
        
    except Exception as e:
        print(f"\n❌ Error en testing: {e}")
        raise

if __name__ == "__main__":
    main()