#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regex Value Generator - Generador de valores para entidades regex
Convierte patterns regex en valores de ejemplo realistas
Versión: 1.0
"""

import re
import random
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from entity_loaders import EntityDefinition

logger = logging.getLogger(__name__)

@dataclass
class RegexValueMapper:
    """Mapea patterns regex a valores de ejemplo realistas"""
    
    # Valores predefinidos para entidades comunes
    PREDEFINED_VALUES = {
        'cantidad_descuento': [
            "10%", "15%", "20%", "25%", "30%", "40%", "50%",
            "10% de descuento", "20% off", "25% desc", 
            "precio especial", "oferta especial", "precio promocional"
        ],
        
        'cantidad_bonificacion': [
            "2x1", "3x2", "4x3", "lleva 2 paga 1", "lleva 3 paga 2",
            "15% bonificación", "20% bonus", "con regalo", 
            "bonificación especial", "bonus"
        ],
        
        'cantidad_stock': [
            "5 unidades", "10 unidades", "15 unidades", "pocas unidades",
            "últimas unidades", "stock limitado", "stock disponible", 
            "mucho stock", "stock agotado", "disponible", "sin stock"
        ],
        
        'precio_monto': [
            "$1000", "$1500", "$2000", "$2500", "$3000", "$5000",
            "1000 pesos", "1500 pesos", "2000 pesos", "precio bajo",
            "precio alto", "económico", "barato", "caro"
        ],
        
        'fecha_especifica': [
            "15/09/2024", "03/10/2024", "20/12/2024", "5 de enero",
            "10 de marzo", "esta semana", "próxima semana", 
            "este mes", "próximo mes"
        ]
    }

class RegexValueGenerator:
    """Generador de valores de ejemplo para entidades regex"""
    
    def __init__(self):
        self.mapper = RegexValueMapper()
        self.generated_cache = {}
        
    def generate_values_for_regex_entity(self, entity: EntityDefinition, count: int = 10) -> List[str]:
        """Genera valores de ejemplo para una entidad regex"""
        
        if entity.source != 'regex':
            logger.warning(f"Entity '{entity.name}' no es regex, no se pueden generar valores")
            return []
        
        entity_name = entity.name
        
        # Usar cache si ya generamos valores para esta entidad
        cache_key = f"{entity_name}_{count}"
        if cache_key in self.generated_cache:
            return self.generated_cache[cache_key]
        
        # Usar valores predefinidos si existen
        if entity_name in self.mapper.PREDEFINED_VALUES:
            predefined = self.mapper.PREDEFINED_VALUES[entity_name]
            values = random.sample(predefined, min(count, len(predefined)))
            logger.debug(f"Usando valores predefinidos para '{entity_name}': {len(values)} valores")
        else:
            # Generar valores basados en regex pattern
            values = self._generate_from_regex_pattern(entity.regex_pattern, entity_name, count)
            logger.debug(f"Generados valores desde regex para '{entity_name}': {len(values)} valores")
        
        # Guardar en cache
        self.generated_cache[cache_key] = values
        
        return values
    
    def _generate_from_regex_pattern(self, regex_pattern: str, entity_name: str, count: int) -> List[str]:
        """Genera valores basados en el pattern regex"""
        
        if not regex_pattern:
            logger.warning(f"Pattern regex vacío para entity '{entity_name}'")
            return []
        
        try:
            # Intentar generar valores basados en el pattern
            compiled_pattern = re.compile(regex_pattern)
            
            # Valores generados basados en análisis del pattern
            if 'descuento' in regex_pattern.lower() or '%' in regex_pattern:
                return self._generate_discount_values(count)
            elif 'bonificacion' in regex_pattern.lower() or 'x' in regex_pattern:
                return self._generate_bonification_values(count)
            elif 'stock' in regex_pattern.lower() or 'unidad' in regex_pattern:
                return self._generate_stock_values(count)
            elif 'precio' in regex_pattern.lower() or '$' in regex_pattern:
                return self._generate_price_values(count)
            elif 'fecha' in regex_pattern.lower() or '/' in regex_pattern:
                return self._generate_date_values(count)
            else:
                # Fallback genérico
                return self._generate_generic_values(entity_name, count)
                
        except re.error as e:
            logger.error(f"Error compilando regex pattern para '{entity_name}': {e}")
            return self._generate_fallback_values(entity_name, count)
    
    def _generate_discount_values(self, count: int) -> List[str]:
        """Genera valores de descuento"""
        base_values = ["10%", "15%", "20%", "25%", "30%", "40%", "50%"]
        variants = []
        
        for value in base_values[:count]:
            variants.extend([
                value,
                f"{value} descuento",
                f"{value} off",
                value.replace('%', '% desc')
            ])
        
        return variants[:count]
    
    def _generate_bonification_values(self, count: int) -> List[str]:
        """Genera valores de bonificación"""
        values = [
            "2x1", "3x2", "4x3", "lleva 2 paga 1", "lleva 3 paga 2",
            "15% bonificación", "20% bonus", "con regalo"
        ]
        return values[:count]
    
    def _generate_stock_values(self, count: int) -> List[str]:
        """Genera valores de stock"""
        values = [
            "5 unidades", "10 unidades", "pocas unidades", "stock limitado",
            "disponible", "mucho stock", "últimas unidades"
        ]
        return values[:count]
    
    def _generate_price_values(self, count: int) -> List[str]:
        """Genera valores de precio"""
        values = [
            "$1000", "$1500", "$2000", "$3000", 
            "1000 pesos", "precio bajo", "económico", "barato"
        ]
        return values[:count]
    
    def _generate_date_values(self, count: int) -> List[str]:
        """Genera valores de fecha"""
        values = [
            "15/09/2024", "03/10/2024", "esta semana", "próximo mes",
            "5 de enero", "10 de marzo", "mañana"
        ]
        return values[:count]
    
    def _generate_generic_values(self, entity_name: str, count: int) -> List[str]:
        """Genera valores genéricos basados en el nombre de la entidad"""
        logger.warning(f"Generando valores genéricos para entity '{entity_name}'")
        
        if 'descuento' in entity_name.lower():
            return ["20%", "15%", "promoción"][:count]
        elif 'bonificacion' in entity_name.lower():
            return ["2x1", "3x2", "bonus"][:count]
        elif 'stock' in entity_name.lower():
            return ["disponible", "stock limitado", "pocas unidades"][:count]
        elif 'precio' in entity_name.lower():
            return ["$1000", "barato", "económico"][:count]
        elif 'fecha' in entity_name.lower():
            return ["mañana", "esta semana", "próximo mes"][:count]
        else:
            return [f"valor_{i}" for i in range(1, count + 1)]
    
    def _generate_fallback_values(self, entity_name: str, count: int) -> List[str]:
        """Valores de fallback cuando falla todo lo demás"""
        logger.warning(f"Usando valores de fallback para entity '{entity_name}'")
        return [f"[{entity_name}_{i}]" for i in range(1, count + 1)]

class EnhancedEntityContextManager:
    """Manager mejorado que maneja entidades regex y pattern"""
    
    def __init__(self, entities: Dict[str, EntityDefinition], entity_groups: Dict[str, str]):
        self.entities = entities
        self.entity_groups = entity_groups
        self.usage_stats = {}
        self.regex_generator = RegexValueGenerator()
        
        # Pre-generar valores para entidades regex
        self._prepare_regex_entities()
    
    def _prepare_regex_entities(self):
        """Pre-genera valores para todas las entidades regex"""
        logger.info("Pre-generando valores para entidades regex...")
        
        regex_entities_found = 0
        
        for entity_name, entity in self.entities.items():
            if entity.source == 'regex':
                regex_entities_found += 1
                logger.debug(f"Procesando regex entity: {entity_name}")
                
                try:
                    values = self.regex_generator.generate_values_for_regex_entity(entity, 15)
                    
                    if values:
                        # Agregar los valores generados a la entidad
                        entity.values = values
                        logger.info(f"✅ Entity regex '{entity_name}': {len(values)} valores generados")
                        logger.debug(f"    Valores: {values[:3]}...")
                    else:
                        logger.error(f"❌ Entity regex '{entity_name}': Sin valores generados")
                        # Fallback: valores básicos para evitar placeholders
                        fallback_values = [f"{entity_name}_1", f"{entity_name}_2", f"{entity_name}_3"]
                        entity.values = fallback_values
                        logger.warning(f"    Usando fallback: {fallback_values}")
                        
                except Exception as e:
                    logger.error(f"❌ Error generando valores para '{entity_name}': {e}")
                    # Fallback crítico
                    entity.values = [f"{entity_name}_fallback"]
        
        logger.info(f"Pre-generación completada: {regex_entities_found} entidades regex procesadas")
    
    def select_contextual_value(self, entity_name: str, context: Dict[str, str] = None) -> str:
        """Selecciona valor considerando contexto, incluyendo entidades regex"""
        
        # Manejar roles en entity_name (formato: entity_name:role)
        clean_entity_name = entity_name.split(':')[0] if ':' in entity_name else entity_name
        
        if clean_entity_name not in self.entities:
            logger.warning(f"Entity '{clean_entity_name}' no encontrada")
            return f"[{clean_entity_name}]"
        
        entity_def = self.entities[clean_entity_name]
        available_values = self._get_entity_values(entity_def)
        
        if not available_values:
            logger.warning(f"Entity '{clean_entity_name}' sin valores disponibles")
            return f"[{clean_entity_name}]"
        
        # Aplicar balance de uso
        selected_value = self._apply_usage_balance(clean_entity_name, available_values)
        
        # Actualizar estadísticas de uso
        self._update_usage_stats(clean_entity_name, selected_value)
        
        return selected_value
    
    def _get_entity_values(self, entity_def: EntityDefinition) -> List[str]:
        """Extrae valores válidos considerando todos los tipos de entidad"""
        values = []
        
        # Pattern entities
        if entity_def.patterns:
            values.extend([p for p in entity_def.patterns if p and p.strip()])
        
        # CSV entities o valores pre-generados
        if entity_def.values:
            values.extend([v for v in entity_def.values if v and v.strip()])
        
        # Regex entities - generar valores si no existen
        if entity_def.source == 'regex' and not values:
            logger.debug(f"Generando valores on-demand para regex entity '{entity_def.name}'")
            values = self.regex_generator.generate_values_for_regex_entity(entity_def, 10)
        
        return values
    
    def _apply_usage_balance(self, entity_name: str, values: List[str]) -> str:
        """Aplica balance de uso para evitar repetición excesiva"""
        if entity_name not in self.usage_stats:
            self.usage_stats[entity_name] = {}
        
        usage = self.usage_stats[entity_name]
        
        # Preferir valores menos usados
        min_usage = min(usage.values()) if usage else 0
        least_used = [v for v in values if usage.get(v, 0) == min_usage]
        
        if least_used:
            return random.choice(least_used)
        
        return random.choice(values)
    
    def _update_usage_stats(self, entity_name: str, value: str):
        """Actualiza estadísticas de uso"""
        if entity_name not in self.usage_stats:
            self.usage_stats[entity_name] = {}
        
        self.usage_stats[entity_name][value] = self.usage_stats[entity_name].get(value, 0) + 1
    
    def get_entity_group(self, entity_name: str) -> str:
        """Obtiene el grupo de una entidad (manejando roles)"""
        clean_entity_name = entity_name.split(':')[0] if ':' in entity_name else entity_name
        return self.entity_groups.get(clean_entity_name, "default")
    
    def debug_entity_values(self, entity_name: str = None):
        """Debug helper para ver valores de entidades"""
        if entity_name:
            if entity_name in self.entities:
                entity = self.entities[entity_name]
                values = self._get_entity_values(entity)
                print(f"\n🔍 Entity '{entity_name}' ({entity.source}):")
                print(f"   Valores disponibles: {len(values)}")
                print(f"   Muestra: {values[:5]}")
            else:
                print(f"❌ Entity '{entity_name}' no encontrada")
        else:
            print(f"\n📊 RESUMEN DE ENTIDADES:")
            for name, entity in self.entities.items():
                values = self._get_entity_values(entity)
                print(f"   {name:20} ({entity.source:8}): {len(values):3} valores")

def main():
    """Testing del generador de valores regex"""
    logging.basicConfig(level=logging.INFO)
    
    # Test del generador
    generator = RegexValueGenerator()
    
    # Crear entidades regex de ejemplo
    test_entities = {
        'cantidad_descuento': EntityDefinition(
            name='cantidad_descuento',
            source='regex',
            type='text',
            regex_pattern=r'\d{1,2}%\s?(de\s?descuento|off|desc|dto)?'
        ),
        'cantidad_bonificacion': EntityDefinition(
            name='cantidad_bonificacion', 
            source='regex',
            type='text',
            regex_pattern=r'\d+x\d+\s?bonificación|lleva\s?\d+\s?paga\s?\d+'
        )
    }
    
    entity_groups = {
        'cantidad_descuento': 'numeric_filters',
        'cantidad_bonificacion': 'numeric_filters'
    }
    
    # Test del manager mejorado
    manager = EnhancedEntityContextManager(test_entities, entity_groups)
    
    print("🧪 TESTING REGEX VALUE GENERATOR")
    print("=" * 50)
    
    # Debug de entidades
    manager.debug_entity_values()
    
    # Test de selección de valores
    print(f"\n🎯 SELECCIÓN DE VALORES:")
    for entity_name in ['cantidad_descuento', 'cantidad_bonificacion']:
        print(f"\n{entity_name}:")
        for i in range(5):
            value = manager.select_contextual_value(entity_name)
            print(f"  {i+1}: {value}")

if __name__ == "__main__":
    main()