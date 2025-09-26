#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Entity Loaders Module - Con logging mejorado para debug
Versión: 4.2 - Enhanced logging
"""

import yaml
import pandas as pd
import re
from typing import Dict, List, Any, Optional, Union
from pathlib import Path
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import logging

# Configurar logger específico para este módulo
logger = logging.getLogger(__name__)

class ConfigValidationError(Exception):
    """Error crítico de validación de configuración"""
    pass

class MissingDataError(Exception):
    """Error cuando faltan datos requeridos"""
    pass

@dataclass
class ValidationResult:
    """Resultado de validación con errores críticos y warnings"""
    critical_errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    @property
    def is_valid(self) -> bool:
        return len(self.critical_errors) == 0
    
    def add_critical(self, error: str):
        self.critical_errors.append(error)
        
    def add_warning(self, warning: str):
        self.warnings.append(warning)

@dataclass
class EntityDefinition:
    """Definición completa de una entidad"""
    name: str
    source: str  # 'csv', 'pattern', 'regex', 'alias'
    type: str
    values: List[str] = field(default_factory=list)
    patterns: List[str] = field(default_factory=list)
    regex_pattern: Optional[str] = None
    csv_config: Optional[str] = None
    alias_of: Optional[str] = None
    description: Optional[str] = None

def safe_str_conversion(value: Any, context: str = "") -> str:
    """Convierte cualquier valor a string de forma segura"""
    if value is None:
        return ""
    
    if isinstance(value, bool):
        # Convertir booleanos a string lowercase
        return str(value).lower()
    
    if isinstance(value, (int, float)):
        return str(value)
    
    if isinstance(value, str):
        return value.strip()
    
    # Para cualquier otro tipo, intentar conversión
    try:
        result = str(value).strip()
        if context:
            logger.debug(f"Conversión no estándar en {context}: {type(value).__name__} -> string")
        return result
    except Exception as e:
        if context:
            logger.warning(f"Error convirtiendo valor en {context}: {value} ({type(value).__name__}): {e}")
        return ""

def validate_and_clean_patterns(patterns: List[Any], entity_name: str) -> List[str]:
    """Valida y limpia una lista de patterns, manejando diferentes tipos de datos"""
    logger.debug(f"[{entity_name}] Validando {len(patterns)} patterns")
    cleaned_patterns = []
    
    for i, pattern in enumerate(patterns):
        try:
            # Convertir a string de forma segura
            pattern_str = safe_str_conversion(pattern, f"entity '{entity_name}' pattern {i}")
            
            if pattern_str:  # Solo agregar si no está vacío
                cleaned_patterns.append(pattern_str)
                logger.debug(f"[{entity_name}] Pattern {i}: '{pattern_str}' (OK)")
            else:
                logger.warning(f"[{entity_name}] Pattern {i}: VACIO - {pattern} ({type(pattern).__name__})")
                
        except Exception as e:
            logger.error(f"[{entity_name}] Error procesando pattern {i}: {e}")
            continue
    
    logger.debug(f"[{entity_name}] Resultado: {len(cleaned_patterns)}/{len(patterns)} patterns válidos")
    return cleaned_patterns

class EntityLoader(ABC):
    """Clase base para cargadores de entidades"""
    
    @abstractmethod
    def load_entities(self, config: Dict[str, Any]) -> Dict[str, EntityDefinition]:
        pass
    
    @abstractmethod
    def validate(self, entities: Dict[str, EntityDefinition]) -> ValidationResult:
        pass

class PatternEntityLoader(EntityLoader):
    """Cargador de entidades basadas en patterns estáticos"""
    
    def __init__(self, entities_file: Path):
        self.entities_file = entities_file
        logger.debug(f"[PatternEntityLoader] Inicializado con archivo: {entities_file}")
        
    def load_entities(self, config: Dict[str, Any]) -> Dict[str, EntityDefinition]:
        """Carga entidades con patterns desde entities.yml"""
        logger.info(f"[PatternEntityLoader] Iniciando carga desde {self.entities_file}")
        
        if not self.entities_file.exists():
            logger.error(f"[PatternEntityLoader] Archivo no encontrado: {self.entities_file}")
            raise MissingDataError(f"Archivo entities.yml no encontrado: {self.entities_file}")
        
        try:
            with open(self.entities_file, 'r', encoding='utf-8') as f:
                entities_data = yaml.safe_load(f)
            logger.debug(f"[PatternEntityLoader] Archivo YAML parseado correctamente")
        except yaml.YAMLError as e:
            logger.error(f"[PatternEntityLoader] Error parseando YAML: {e}")
            raise ConfigValidationError(f"Error parseando YAML en {self.entities_file}: {e}")
        except Exception as e:
            logger.error(f"[PatternEntityLoader] Error leyendo archivo: {e}")
            raise MissingDataError(f"Error leyendo archivo {self.entities_file}: {e}")
        
        if not entities_data:
            logger.warning(f"[PatternEntityLoader] Archivo YAML vacío")
            raise MissingDataError(f"Archivo entities.yml está vacío: {self.entities_file}")
        
        pattern_entities = entities_data.get('pattern_entities', {})
        logger.info(f"[PatternEntityLoader] Encontradas {len(pattern_entities)} entidades pattern")
        
        entities = {}
        
        for entity_name, entity_config in pattern_entities.items():
            logger.debug(f"[PatternEntityLoader] Procesando entity: {entity_name}")
            
            if not isinstance(entity_config, dict):
                logger.warning(f"[PatternEntityLoader] Configuración inválida para '{entity_name}': {entity_config}")
                continue
                
            raw_patterns = entity_config.get('patterns', [])
            logger.debug(f"[PatternEntityLoader] Entity '{entity_name}' tiene {len(raw_patterns)} patterns raw")
            
            if not raw_patterns:
                logger.error(f"[PatternEntityLoader] Entity '{entity_name}' sin patterns")
                raise MissingDataError(f"Entity '{entity_name}' no tiene patterns definidos")
            
            # Validar y limpiar patterns
            cleaned_patterns = validate_and_clean_patterns(raw_patterns, entity_name)
            
            if not cleaned_patterns:
                logger.error(f"[PatternEntityLoader] Entity '{entity_name}' sin patterns válidos después de limpieza")
                raise MissingDataError(f"Entity '{entity_name}' no tiene patterns válidos después de limpieza")
            
            entities[entity_name] = EntityDefinition(
                name=entity_name,
                source='pattern',
                type='text',
                patterns=cleaned_patterns,
                description=entity_config.get('description', f"Pattern entity: {entity_name}")
            )
            logger.debug(f"[PatternEntityLoader] Entity '{entity_name}' cargada exitosamente")
        
        logger.info(f"[PatternEntityLoader] COMPLETADO: {len(entities)} entidades pattern cargadas")
        return entities
    
    def validate(self, entities: Dict[str, EntityDefinition]) -> ValidationResult:
        """Valida entidades con patterns"""
        result = ValidationResult()
        
        for name, entity in entities.items():
            if entity.source == 'pattern':
                if not entity.patterns:
                    result.add_critical(f"Entity '{name}' no tiene patterns")
                
                # Validar que los patterns no estén vacíos
                empty_patterns = [p for p in entity.patterns if not p.strip()]
                if empty_patterns:
                    result.add_warning(f"Entity '{name}' tiene patterns vacíos")
                
                # Validar que no haya duplicados
                if len(entity.patterns) != len(set(entity.patterns)):
                    result.add_warning(f"Entity '{name}' tiene patterns duplicados")
        
        return result

class CSVEntityLoader(EntityLoader):
    """Cargador de entidades desde archivos CSV"""
    
    def __init__(self, data_dir: Path, entities_file: Path):
        self.data_dir = data_dir
        self.entities_file = entities_file
        logger.debug(f"[CSVEntityLoader] Inicializado - data_dir: {data_dir}, entities_file: {entities_file}")
        
    def load_entities(self, config: Dict[str, Any]) -> Dict[str, EntityDefinition]:
        """Carga entidades desde CSVs según configuración en entities.yml"""
        logger.info(f"[CSVEntityLoader] Iniciando carga desde CSVs")
        
        if not self.entities_file.exists():
            logger.error(f"[CSVEntityLoader] Archivo entities.yml no encontrado: {self.entities_file}")
            raise MissingDataError(f"Archivo entities.yml no encontrado: {self.entities_file}")
        
        try:
            with open(self.entities_file, 'r', encoding='utf-8') as f:
                entities_data = yaml.safe_load(f)
            logger.debug(f"[CSVEntityLoader] Archivo YAML parseado correctamente")
        except yaml.YAMLError as e:
            logger.error(f"[CSVEntityLoader] Error parseando YAML: {e}")
            raise ConfigValidationError(f"Error parseando YAML en {self.entities_file}: {e}")
        
        if not entities_data:
            logger.warning(f"[CSVEntityLoader] Archivo YAML vacío, no hay entidades CSV para cargar")
            return {}
        
        lookup_entities = entities_data.get('lookup_entities', {})
        csv_processing = entities_data.get('csv_processing', {})
        
        logger.info(f"[CSVEntityLoader] Configuración encontrada - lookup_entities: {len(lookup_entities)}, csv_processing: {len(csv_processing)}")
        
        entities = {}
        
        for entity_name, entity_config in lookup_entities.items():
            logger.debug(f"[CSVEntityLoader] Evaluando entity: {entity_name}")
            
            if not isinstance(entity_config, dict):
                logger.warning(f"[CSVEntityLoader] Configuración inválida para '{entity_name}': {entity_config}")
                continue
                
            if entity_config.get('source') == 'csv':
                logger.info(f"[CSVEntityLoader] Procesando CSV entity: {entity_name}")
                
                csv_config_name = entity_config.get('csv_config')
                if not csv_config_name:
                    logger.error(f"[CSVEntityLoader] Entity '{entity_name}' sin csv_config")
                    raise MissingDataError(f"Entity '{entity_name}' no tiene csv_config definido")
                
                logger.debug(f"[CSVEntityLoader] Entity '{entity_name}' usa csv_config: {csv_config_name}")
                
                if csv_config_name not in csv_processing:
                    logger.error(f"[CSVEntityLoader] csv_config '{csv_config_name}' no encontrado en csv_processing")
                    logger.debug(f"[CSVEntityLoader] csv_processing disponibles: {list(csv_processing.keys())}")
                    raise MissingDataError(f"CSV config '{csv_config_name}' no encontrado para entity '{entity_name}'")
                
                try:
                    values = self._load_csv_values(csv_config_name, csv_processing[csv_config_name])
                    logger.info(f"[CSVEntityLoader] Entity '{entity_name}' cargada con {len(values)} valores desde CSV")
                    
                    entities[entity_name] = EntityDefinition(
                        name=entity_name,
                        source='csv',
                        type='text',
                        values=values,
                        csv_config=csv_config_name,
                        description=entity_config.get('description', f"CSV entity: {entity_name}")
                    )
                    
                except Exception as e:
                    logger.error(f"[CSVEntityLoader] Error cargando entity '{entity_name}': {e}")
                    raise
            else:
                logger.debug(f"[CSVEntityLoader] Entity '{entity_name}' no es CSV (source: {entity_config.get('source', 'undefined')})")
        
        logger.info(f"[CSVEntityLoader] COMPLETADO: {len(entities)} entidades CSV cargadas")
        return entities
    
    def _load_csv_values(self, config_name: str, csv_config: Dict[str, Any]) -> List[str]:
        """Carga valores desde un CSV específico"""
        logger.debug(f"[CSVEntityLoader] Cargando CSV con config: {config_name}")
        
        filename = csv_config.get('file')
        if not filename:
            logger.error(f"[CSVEntityLoader] Config '{config_name}' sin archivo definido")
            raise MissingDataError(f"CSV config '{config_name}' no tiene archivo definido")
        
        csv_path = self.data_dir / filename
        logger.debug(f"[CSVEntityLoader] Buscando archivo CSV: {csv_path}")
        
        if not csv_path.exists():
            logger.error(f"[CSVEntityLoader] Archivo CSV no encontrado: {csv_path}")
            raise MissingDataError(f"Archivo CSV no encontrado: {csv_path}")
        
        column = csv_config.get('column')
        if not column:
            logger.error(f"[CSVEntityLoader] Config '{config_name}' sin columna definida")
            raise MissingDataError(f"CSV config '{config_name}' no tiene columna definida")
        
        logger.debug(f"[CSVEntityLoader] Leyendo columna '{column}' del archivo {filename}")
        
        try:
            # Leer CSV con tipos como object para evitar conversiones automáticas
            df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
            logger.debug(f"[CSVEntityLoader] CSV leído exitosamente: {df.shape[0]} filas, {df.shape[1]} columnas")
        except Exception as e:
            logger.warning(f"[CSVEntityLoader] Error leyendo CSV {csv_path}: {e}")
            logger.info(f"[CSVEntityLoader] Intentando lectura con skip de líneas problemáticas...")
            
            try:
                # Intentar con manejo de líneas problemáticas
                df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, on_bad_lines='skip')
                logger.warning(f"[CSVEntityLoader] CSV leído con líneas saltadas: {df.shape[0]} filas, {df.shape[1]} columnas")
            except Exception as e2:
                logger.error(f"[CSVEntityLoader] Error crítico leyendo CSV {csv_path}: {e2}")
                raise MissingDataError(f"Error leyendo CSV {csv_path}: {e2}")
        
        if column not in df.columns:
            logger.error(f"[CSVEntityLoader] Columna '{column}' no encontrada en {filename}")
            logger.debug(f"[CSVEntityLoader] Columnas disponibles: {list(df.columns)}")
            raise MissingDataError(f"Columna '{column}' no encontrada en {filename}. Columnas disponibles: {list(df.columns)}")
        
        # Obtener valores y convertir a string de forma segura
        raw_values = df[column].tolist()
        logger.debug(f"[CSVEntityLoader] Extraídos {len(raw_values)} valores raw de la columna")
        
        values = []
        for i, value in enumerate(raw_values):
            cleaned_value = safe_str_conversion(value, f"CSV {filename}:{column} row {i}")
            if cleaned_value:  # Solo agregar valores no vacíos
                values.append(cleaned_value)
        
        logger.debug(f"[CSVEntityLoader] Después de limpieza: {len(values)} valores válidos")
        
        # Aplicar filtros si existen
        filters = csv_config.get('filters', [])
        if filters:
            logger.debug(f"[CSVEntityLoader] Aplicando {len(filters)} filtros")
            values = self._apply_filters(values, filters, config_name)
            logger.debug(f"[CSVEntityLoader] Después de filtros: {len(values)} valores")
        
        if not values:
            logger.error(f"[CSVEntityLoader] Sin valores válidos después de procesamiento")
            raise MissingDataError(f"No se obtuvieron valores válidos del CSV {filename}, columna {column}")
        
        logger.debug(f"[CSVEntityLoader] Carga completada para config '{config_name}': {len(values)} valores finales")
        return values
    
    def _apply_filters(self, values: List[str], filters: List[Dict[str, Any]], config_name: str) -> List[str]:
        """Aplica filtros a los valores extraídos del CSV"""
        filtered_values = values[:]
        original_count = len(filtered_values)
        
        for i, filter_config in enumerate(filters):
            if not isinstance(filter_config, dict):
                logger.warning(f"[CSVEntityLoader] Filtro {i} inválido en config '{config_name}': {filter_config}")
                continue
                
            logger.debug(f"[CSVEntityLoader] Aplicando filtro {i}: {filter_config}")
            
            if 'min_length' in filter_config:
                min_len = filter_config['min_length']
                before_count = len(filtered_values)
                filtered_values = [v for v in filtered_values if len(v) >= min_len]
                logger.debug(f"[CSVEntityLoader] Filtro min_length={min_len}: {before_count} -> {len(filtered_values)}")
            
            if 'clean_text' in filter_config and filter_config['clean_text']:
                # Asegurar que todos los valores son strings válidos
                cleaned_values = []
                for v in filtered_values:
                    cleaned_v = safe_str_conversion(v, f"clean_text filter in {config_name}")
                    if cleaned_v:
                        cleaned_values.append(cleaned_v.title())
                filtered_values = cleaned_values
                logger.debug(f"[CSVEntityLoader] Filtro clean_text aplicado: {len(filtered_values)} valores")
            
            if 'extract_name_and_dose' in filter_config and filter_config['extract_name_and_dose']:
                before_count = len(filtered_values)
                filtered_values = self._extract_name_and_dose(filtered_values)
                logger.debug(f"[CSVEntityLoader] Filtro extract_name_and_dose: {before_count} -> {len(filtered_values)}")
            
            if 'extract_compounds' in filter_config and filter_config['extract_compounds']:
                before_count = len(filtered_values)
                filtered_values = self._extract_compounds(filtered_values)
                logger.debug(f"[CSVEntityLoader] Filtro extract_compounds: {before_count} -> {len(filtered_values)}")
            
            if 'format_name' in filter_config and filter_config['format_name']:
                filtered_values = self._format_enterprise_names(filtered_values)
                logger.debug(f"[CSVEntityLoader] Filtro format_name aplicado")
            
            if 'add_first_word' in filter_config and filter_config['add_first_word']:
                before_count = len(filtered_values)
                filtered_values = self._add_first_word_variants(filtered_values)
                logger.debug(f"[CSVEntityLoader] Filtro add_first_word: {before_count} -> {len(filtered_values)}")
        
        logger.debug(f"[CSVEntityLoader] Filtros completados: {original_count} -> {len(filtered_values)} valores")
        return filtered_values
    
    def _extract_name_and_dose(self, values: List[str]) -> List[str]:
        """Extrae nombres de productos y dosis"""
        extracted = []
        for value in values:
            # Asegurar que el valor es string
            value_str = safe_str_conversion(value, "extract_name_and_dose")
            if not value_str:
                continue
                
            # Extraer nombre base del producto
            base_name = re.sub(r'\d+\s*(mg|ml|g|%)', '', value_str, flags=re.IGNORECASE).strip()
            if base_name and base_name not in extracted:
                extracted.append(base_name)
            
            # Mantener también el nombre completo
            if value_str not in extracted:
                extracted.append(value_str)
        
        return extracted
    
    def _extract_compounds(self, values: List[str]) -> List[str]:
        """Extrae compuestos químicos de nombres de productos"""
        compounds = []
        # Patrones comunes de ingredientes activos
        compound_patterns = [
            r'([A-Za-z]+cina)', # terminaciones en -cina
            r'([A-Za-z]+zol)',  # terminaciones en -zol  
            r'([A-Za-z]+micina)', # terminaciones en -micina
            r'([A-Za-z]+cilina)', # terminaciones en -cilina
        ]
        
        for value in values:
            value_str = safe_str_conversion(value, "extract_compounds")
            if not value_str:
                continue
                
            for pattern in compound_patterns:
                matches = re.findall(pattern, value_str, re.IGNORECASE)
                for match in matches:
                    if match.lower() not in [c.lower() for c in compounds]:
                        compounds.append(match.lower())
        
        return compounds + values  # Mantener valores originales también
    
    def _format_enterprise_names(self, values: List[str]) -> List[str]:
        """Formatea nombres de empresas"""
        formatted = []
        for value in values:
            value_str = safe_str_conversion(value, "format_enterprise_names")
            if not value_str:
                continue
                
            # Limpiar y formatear nombre
            clean_name = re.sub(r'[^\w\s]', ' ', value_str).strip()
            clean_name = ' '.join(clean_name.split())  # Normalizar espacios
            
            if clean_name and clean_name not in formatted:
                formatted.append(clean_name)
        
        return formatted
    
    def _add_first_word_variants(self, values: List[str]) -> List[str]:
        """Agrega variantes usando la primera palabra"""
        variants = values[:]
        
        for value in values:
            value_str = safe_str_conversion(value, "add_first_word_variants")
            if not value_str:
                continue
                
            words = value_str.split()
            if len(words) > 1:
                first_word = words[0].strip()
                if first_word and len(first_word) > 2 and first_word not in variants:
                    variants.append(first_word)
        
        return variants
    
    def validate(self, entities: Dict[str, EntityDefinition]) -> ValidationResult:
        """Valida entidades CSV"""
        result = ValidationResult()
        
        for name, entity in entities.items():
            if entity.source == 'csv':
                if not entity.values:
                    result.add_critical(f"Entity CSV '{name}' no tiene valores")
                
                if not entity.csv_config:
                    result.add_critical(f"Entity CSV '{name}' no tiene csv_config")
                
                # Validar cantidad mínima de valores
                if len(entity.values) < 2:
                    result.add_warning(f"Entity CSV '{name}' tiene muy pocos valores ({len(entity.values)})")
                
                # Detectar duplicados
                unique_values = set(entity.values)
                if len(unique_values) != len(entity.values):
                    result.add_warning(f"Entity CSV '{name}' tiene valores duplicados")
        
        return result

class RegexEntityLoader(EntityLoader):
    """Cargador de entidades con patterns regex"""
    
    def __init__(self, entities_file: Path, regex_file: Path):
        self.entities_file = entities_file
        self.regex_file = regex_file
        logger.debug(f"[RegexEntityLoader] Inicializado - entities: {entities_file}, regex: {regex_file}")
        
    def load_entities(self, config: Dict[str, Any]) -> Dict[str, EntityDefinition]:
        """Carga entidades regex desde entities.yml y entities_regex.yml"""
        logger.info(f"[RegexEntityLoader] Iniciando carga de entidades regex")
        
        if not self.entities_file.exists():
            logger.error(f"[RegexEntityLoader] Archivo entities.yml no encontrado: {self.entities_file}")
            raise MissingDataError(f"Archivo entities.yml no encontrado: {self.entities_file}")
        
        if not self.regex_file.exists():
            logger.warning(f"[RegexEntityLoader] Archivo entities_regex.yml no encontrado: {self.regex_file}")
            logger.info(f"[RegexEntityLoader] Sin entidades regex para cargar")
            return {}
        
        try:
            with open(self.entities_file, 'r', encoding='utf-8') as f:
                entities_data = yaml.safe_load(f)
            
            with open(self.regex_file, 'r', encoding='utf-8') as f:
                regex_data = yaml.safe_load(f)
                
            logger.debug(f"[RegexEntityLoader] Archivos YAML parseados correctamente")
        except yaml.YAMLError as e:
            logger.error(f"[RegexEntityLoader] Error parseando YAML: {e}")
            raise ConfigValidationError(f"Error parseando YAML: {e}")
        
        if not entities_data or not regex_data:
            logger.warning(f"[RegexEntityLoader] Archivos YAML vacíos")
            return {}
        
        dynamic_entities = entities_data.get('dynamic_entities', {})
        logger.info(f"[RegexEntityLoader] Encontradas {len(dynamic_entities)} entidades dinámicas")
        
        entities = {}
        
        for entity_name, entity_config in dynamic_entities.items():
            logger.debug(f"[RegexEntityLoader] Procesando entity: {entity_name}")
            
            if not isinstance(entity_config, dict):
                logger.warning(f"[RegexEntityLoader] Configuración inválida para '{entity_name}': {entity_config}")
                continue
                
            if entity_config.get('source') == 'regex':
                logger.debug(f"[RegexEntityLoader] Entity '{entity_name}' es tipo regex")
                
                regex_name = entity_config.get('regex_name')
                if not regex_name:
                    logger.error(f"[RegexEntityLoader] Entity '{entity_name}' sin regex_name")
                    raise MissingDataError(f"Entity '{entity_name}' no tiene regex_name definido")
                
                if regex_name not in regex_data:
                    logger.error(f"[RegexEntityLoader] Regex pattern '{regex_name}' no encontrado")
                    logger.debug(f"[RegexEntityLoader] Patrones disponibles: {list(regex_data.keys())}")
                    raise MissingDataError(f"Regex pattern '{regex_name}' no encontrado para entity '{entity_name}'")
                
                regex_pattern = regex_data[regex_name]
                
                # Validar que el pattern es string
                regex_pattern_str = safe_str_conversion(regex_pattern, f"regex pattern '{regex_name}'")
                
                entities[entity_name] = EntityDefinition(
                    name=entity_name,
                    source='regex',
                    type='text',
                    regex_pattern=regex_pattern_str,
                    description=entity_config.get('description', f"Regex entity: {entity_name}")
                )
                logger.debug(f"[RegexEntityLoader] Entity '{entity_name}' cargada exitosamente")
        
        logger.info(f"[RegexEntityLoader] COMPLETADO: {len(entities)} entidades regex cargadas")
        return entities
    
    def validate(self, entities: Dict[str, EntityDefinition]) -> ValidationResult:
        """Valida entidades regex"""
        result = ValidationResult()
        
        for name, entity in entities.items():
            if entity.source == 'regex':
                if not entity.regex_pattern:
                    result.add_critical(f"Entity regex '{name}' no tiene pattern")
                else:
                    # Validar que el regex sea válido
                    try:
                        re.compile(entity.regex_pattern)
                    except re.error as e:
                        result.add_critical(f"Entity regex '{name}' tiene pattern inválido: {e}")
        
        return result

class AliasEntityLoader(EntityLoader):
    """Cargador de entidades alias"""
    
    def __init__(self, entities_file: Path):
        self.entities_file = entities_file
        logger.debug(f"[AliasEntityLoader] Inicializado con archivo: {entities_file}")
        
    def load_entities(self, config: Dict[str, Any]) -> Dict[str, EntityDefinition]:
        """Carga entidades alias desde entities.yml"""
        logger.info(f"[AliasEntityLoader] Iniciando carga de entidades alias")
        
        if not self.entities_file.exists():
            logger.error(f"[AliasEntityLoader] Archivo no encontrado: {self.entities_file}")
            raise MissingDataError(f"Archivo entities.yml no encontrado: {self.entities_file}")
        
        try:
            with open(self.entities_file, 'r', encoding='utf-8') as f:
                entities_data = yaml.safe_load(f)
            logger.debug(f"[AliasEntityLoader] Archivo YAML parseado correctamente")
        except yaml.YAMLError as e:
            logger.error(f"[AliasEntityLoader] Error parseando YAML: {e}")
            raise ConfigValidationError(f"Error parseando YAML en {self.entities_file}: {e}")
        
        if not entities_data:
            logger.warning(f"[AliasEntityLoader] Archivo YAML vacío")
            return {}
        
        lookup_entities = entities_data.get('lookup_entities', {})
        logger.info(f"[AliasEntityLoader] Evaluando {len(lookup_entities)} lookup entities para alias")
        
        entities = {}
        
        for entity_name, entity_config in lookup_entities.items():
            logger.debug(f"[AliasEntityLoader] Evaluando entity: {entity_name}")
            
            if not isinstance(entity_config, dict):
                logger.warning(f"[AliasEntityLoader] Configuración inválida para '{entity_name}': {entity_config}")
                continue
                
            if entity_config.get('source') == 'alias':
                logger.debug(f"[AliasEntityLoader] Entity '{entity_name}' es alias")
                
                alias_of = entity_config.get('alias_of')
                if not alias_of:
                    logger.error(f"[AliasEntityLoader] Alias '{entity_name}' sin alias_of")
                    raise MissingDataError(f"Entity alias '{entity_name}' no tiene alias_of definido")
                
                # Validar que alias_of es string
                alias_of_str = safe_str_conversion(alias_of, f"alias_of for '{entity_name}'")
                
                entities[entity_name] = EntityDefinition(
                    name=entity_name,
                    source='alias',
                    type='text',
                    alias_of=alias_of_str,
                    description=entity_config.get('description', f"Alias of {alias_of_str}")
                )
                logger.debug(f"[AliasEntityLoader] Alias '{entity_name}' -> '{alias_of_str}' cargado")
        
        logger.info(f"[AliasEntityLoader] COMPLETADO: {len(entities)} entidades alias cargadas")
        return entities
    
    def validate(self, entities: Dict[str, EntityDefinition]) -> ValidationResult:
        """Valida entidades alias"""
        result = ValidationResult()
        
        for name, entity in entities.items():
            if entity.source == 'alias':
                if not entity.alias_of:
                    result.add_critical(f"Entity alias '{name}' no tiene alias_of")
        
        return result
    
class EntityManager:
    """Gestiona la carga y provisión de valores de entidades"""
    
    def __init__(self, data_dir: Path, config_dir: Path):
        self.data_dir = data_dir
        self.config_dir = config_dir
        self.entities: Dict[str, EntityDefinition] = {}
        self.entity_values: Dict[str, List[str]] = {}
        self.entity_config: Dict[str, Any] = {}
        self.segments: Dict[str, List[str]] = {}
        
    def load_all_entities(self):
        """Carga todas las entidades usando los loaders existentes"""
        logger.info("🔄 Iniciando carga de entidades...")
        
        # Archivos de configuración
        entities_file = self.config_dir / "entities.yml"
        regex_file = self.config_dir / "entities_regex.yml"
        entities_config_file = self.config_dir / "entities_config.yml"
        segments_file = self.config_dir / "segments.yml"
        
        # Cargar configuración de entidades
        if entities_config_file.exists():
            with open(entities_config_file, 'r', encoding='utf-8') as f:
                self.entity_config = yaml.safe_load(f) or {}
        
        # Cargar segmentos
        if segments_file.exists():
            with open(segments_file, 'r', encoding='utf-8') as f:
                segments_data = yaml.safe_load(f) or {}
                nlu_data = segments_data.get('nlu', [])
                for item in nlu_data:
                    if 'synonym' in item:
                        synonym_name = item['synonym']
                        examples = item.get('examples', '').strip()
                        if examples:
                            # Parsear ejemplos (formato "- ejemplo")
                            values = []
                            for line in examples.split('\n'):
                                line = line.strip()
                                if line.startswith('- '):
                                    values.append(line[2:].strip())
                            self.segments[synonym_name] = values
        
        logger.info(f"📂 Cargados {len(self.segments)} segmentos de conversación")
        
        # Inicializar loaders
        pattern_loader = PatternEntityLoader(entities_file)
        csv_loader = CSVEntityLoader(self.data_dir, entities_file)
        regex_loader = RegexEntityLoader(entities_file, regex_file)
        alias_loader = AliasEntityLoader(entities_file)
        
        config = {}  # Configuración base
        
        try:
            # Cargar entidades de cada tipo
            pattern_entities = pattern_loader.load_entities(config)
            csv_entities = csv_loader.load_entities(config)
            regex_entities = regex_loader.load_entities(config)
            alias_entities = alias_loader.load_entities(config)
            
            # Combinar todas las entidades
            self.entities.update(pattern_entities)
            self.entities.update(csv_entities)
            self.entities.update(regex_entities)
            self.entities.update(alias_entities)
            
            logger.info(f"✅ Entidades cargadas:")
            logger.info(f"   📋 Pattern: {len(pattern_entities)}")
            logger.info(f"   📊 CSV: {len(csv_entities)}")
            logger.info(f"   🔍 Regex: {len(regex_entities)}")
            logger.info(f"   🔗 Alias: {len(alias_entities)}")
            
            # Convertir definiciones a valores utilizables
            self._process_entity_values()
            
        except Exception as e:
            logger.error(f"❌ Error cargando entidades: {e}")
            raise
    
    def _process_entity_values(self):
        """Procesa las definiciones de entidades para obtener valores utilizables"""
        logger.info("🔄 Procesando valores de entidades...")
        
        for name, entity in self.entities.items():
            values = []
            
            if entity.source == 'csv' and entity.values:
                values = entity.values[:50]  # Limitar para eficiencia
            elif entity.source == 'pattern' and entity.patterns:
                values = entity.patterns[:30]  # Limitar patterns
            elif entity.source == 'alias' and entity.alias_of:
                # Resolver alias
                if entity.alias_of in self.entity_values:
                    values = self.entity_values[entity.alias_of][:20]
            elif entity.source == 'regex':
                # Para regex, generar algunos ejemplos básicos
                values = self._generate_regex_examples(entity.regex_pattern)
            
            if values:
                self.entity_values[name] = values
                logger.debug(f"   📝 {name}: {len(values)} valores")
        
        # Agregar segmentos como entidades especiales
        for segment_name, segment_values in self.segments.items():
            entity_name = f"segment_{segment_name}"
            self.entity_values[entity_name] = segment_values[:20]
        
        logger.info(f"✅ Procesadas {len(self.entity_values)} entidades con valores")
    
    def _generate_regex_examples(self, pattern: str) -> List[str]:
        """Genera ejemplos básicos para patterns regex"""
        # Ejemplos simplificados para patterns comunes
        examples = []
        
        if pattern and isinstance(pattern, str):
            if 'cantidad' in pattern.lower():
                examples = ['5', '10', '25', '100', '500']
            elif 'precio' in pattern.lower() or 'descuento' in pattern.lower():
                examples = ['15%', '20%', '25%', '30%', '50%']
            elif 'fecha' in pattern.lower():
                examples = ['mañana', 'la semana que viene', 'el mes próximo']
            else:
                examples = ['ejemplo1', 'ejemplo2', 'ejemplo3']
        
        return examples
    
    def get_entity_values(self, entity_name: str, role: Optional[str] = None, 
                         group: Optional[str] = None, limit: int = 10) -> List[str]:
        """Obtiene valores para una entidad específica"""
        values = self.entity_values.get(entity_name, [])
        
        if not values:
            # Intentar con segmentos
            segment_key = f"segment_{entity_name}"
            values = self.entity_values.get(segment_key, [])
        
        if not values:
            logger.warning(f"⚠️ No se encontraron valores para entidad '{entity_name}'")
            return [f"ejemplo_{entity_name}"]
        
        # Aplicar filtros por role/group si es necesario
        # (implementación simplificada)
        
        return values[:limit]