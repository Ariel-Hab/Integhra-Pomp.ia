#!/usr/bin/env python3
"""
exporter_optimized.py - Exportador Optimizado para NLU
Soluciona problemas de exportación y asegura que Rasa tenga acceso completo a todas las entidades.
"""

import re
import yaml
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
import unidecode
from datetime import datetime

class ExportError(Exception):
    """Excepción específica para errores de exportación"""
    pass

def validar_yaml_robusto(path: str) -> Tuple[bool, Optional[str]]:
    """Validador YAML robusto que retorna detalle del error"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Verificar contenido no vacío
        if not content.strip():
            return False, "Archivo vacío"
            
        # Validar sintaxis YAML
        data = yaml.safe_load(content)
        
        # Verificar estructura básica para NLU
        if path.endswith('nlu.yml'):
            if not isinstance(data, dict) or 'nlu' not in data:
                return False, "Estructura NLU inválida: falta sección 'nlu'"
                
        print(f"✅ YAML válido: {Path(path).name}")
        return True, None
        
    except yaml.YAMLError as e:
        error_msg = f"Error YAML: {str(e)[:200]}"
        print(f"❌ {Path(path).name}: {error_msg}")
        return False, error_msg
    except FileNotFoundError:
        error_msg = f"Archivo no encontrado"
        print(f"❌ {Path(path).name}: {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = f"Error inesperado: {str(e)[:200]}"
        print(f"❌ {Path(path).name}: {error_msg}")
        return False, error_msg

def limpiar_texto_yaml(texto: str) -> str:
    """Limpia texto para exportación YAML segura y robusta"""
    if not isinstance(texto, str):
        texto = str(texto)
    
    # Remover caracteres problemáticos
    texto = texto.replace('"', '\\"')
    texto = texto.replace('\n', ' ').replace('\r', '')
    texto = re.sub(r'\s{2,}', ' ', texto)
    texto = texto.strip()
    
    # Manejar caracteres especiales
    texto = re.sub(r'[^\w\s\-.,!?áéíóúñü]', '', texto, flags=re.IGNORECASE)
    
    return texto

class OptimizedExporter:
    """
    Exportador optimizado que garantiza que Rasa tenga acceso completo
    a todas las entidades y datos necesarios para el NLU.
    """
    
    @staticmethod
    def _get_project_root() -> Path:
        """Obtiene la ruta raíz del proyecto de forma robusta"""
        current_file = Path(__file__).resolve()
        
        # Buscar hacia arriba hasta encontrar estructura del proyecto
        for parent in current_file.parents:
            if (parent / "context").exists() or (parent / "bot").exists():
                return parent
                
        # Fallback: usar tres niveles arriba desde bot/entrenador/
        return current_file.parent.parent.parent
    
    @staticmethod
    def exportar_nlu_completo_robusto(
        ejemplos: List[Tuple[str, str]],
        lookup_tables: Dict[str, List[str]],
        pattern_entities: Dict[str, List[str]],
        dynamic_entities_info: Dict[str, Dict[str, Any]],
        output_path: str = "data/nlu.yml"
    ) -> Tuple[bool, str]:
        """
        Exporta NLU completo con validación robusta y manejo de errores.
        Retorna (success, error_message)
        """
        try:
            # Preparar ruta de salida
            if not Path(output_path).is_absolute():
                project_root = OptimizedExporter._get_project_root()
                output_file = project_root / output_path
            else:
                output_file = Path(output_path)
            
            # Crear directorio padre
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            
            # Estadísticas para verificación
            stats = {
                'ejemplos': len(ejemplos) if ejemplos else 0,
                'lookup_tables': len(lookup_tables),
                'pattern_entities': len(pattern_entities),
                'dynamic_entities': len(dynamic_entities_info)
            }
            
            print(f"📊 Exportando NLU con:")
            print(f"  • Ejemplos: {stats['ejemplos']}")
            print(f"  • Lookup tables: {stats['lookup_tables']}")
            print(f"  • Pattern entities: {stats['pattern_entities']}")
            print(f"  • Dynamic entities: {stats['dynamic_entities']}")
            
            # Escribir archivo NLU
            with open(output_file, "w", encoding="utf-8") as f:
                # Header
                f.write('# NLU Completo - Generado automáticamente\n')
                f.write(f'# Fecha: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
                f.write('version: "3.1"\n\n')
                f.write('nlu:\n')
                
                # 1. EXPORTAR EJEMPLOS DE ENTRENAMIENTO
                if ejemplos:
                    f.write('\n# ============= EJEMPLOS DE ENTRENAMIENTO =============\n')
                    current_intent = None
                    
                    for ejemplo, intent in ejemplos:
                        if intent != current_intent:
                            f.write(f'\n- intent: {intent}\n')
                            f.write('  examples: |\n')
                            current_intent = intent
                        
                        ejemplo_limpio = limpiar_texto_yaml(ejemplo)
                        f.write(f'    - {ejemplo_limpio}\n')
                
                # 2. EXPORTAR LOOKUP TABLES (CSV)
                if lookup_tables:
                    f.write('\n# ============= LOOKUP TABLES (CSV) =============\n')
                    for entity_name, values in lookup_tables.items():
                        if values:  # Solo exportar si tiene valores
                            f.write(f'\n- lookup: {entity_name}\n')
                            f.write('  examples: |\n')
                            
                            # Limpiar y deduplicar valores
                            clean_values = list(set([
                                limpiar_texto_yaml(v) for v in values 
                                if v and str(v).strip()
                            ]))
                            
                            for value in sorted(clean_values)[:500]:  # Limitar a 500 por performance
                                f.write(f'    - {value}\n')
                
                # 3. EXPORTAR PATTERN ENTITIES (estáticas)
                if pattern_entities:
                    f.write('\n# ============= PATTERN ENTITIES (ESTÁTICAS) =============\n')
                    for entity_name, values in pattern_entities.items():
                        if values:
                            f.write(f'\n- lookup: {entity_name}\n')
                            f.write('  examples: |\n')
                            
                            clean_values = list(set([
                                limpiar_texto_yaml(v) for v in values 
                                if v and str(v).strip()
                            ]))
                            
                            for value in sorted(clean_values):
                                f.write(f'    - {value}\n')
                
                # 4. EXPORTAR REGEX PATTERNS (dinámicas)
                if dynamic_entities_info:
                    f.write('\n# ============= REGEX PATTERNS (DINÁMICAS) =============\n')
                    for entity_name, entity_config in dynamic_entities_info.items():
                        if 'regex_pattern' in entity_config:
                            pattern = entity_config['regex_pattern']
                            f.write(f'\n- regex: {entity_name}\n')
                            f.write(f'  examples: |\n')
                            f.write(f'    - {pattern}\n')
                
                # 5. FOOTER CON ESTADÍSTICAS
                f.write(f'\n# ============= ESTADÍSTICAS =============\n')
                f.write(f'# Total ejemplos: {stats["ejemplos"]}\n')
                f.write(f'# Total lookup tables: {stats["lookup_tables"]}\n')
                f.write(f'# Total pattern entities: {stats["pattern_entities"]}\n')
                f.write(f'# Total regex patterns: {stats["dynamic_entities"]}\n')
            
            # Validar archivo generado
            is_valid, error_msg = validar_yaml_robusto(str(output_file))
            if not is_valid:
                return False, f"YAML inválido: {error_msg}"
            
            # Verificar contenido mínimo
            with open(output_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if content.count('- intent:') == 0 and content.count('- lookup:') == 0:
                    return False, "Archivo generado no contiene datos válidos"
            
            print(f"✅ NLU completo exportado: {output_file}")
            print(f"📁 Tamaño: {output_file.stat().st_size / 1024:.1f} KB")
            
            return True, ""
            
        except Exception as e:
            error_msg = f"Error exportando NLU: {str(e)}"
            print(f"❌ {error_msg}")
            return False, error_msg
    
    @staticmethod
    def exportar_synonyms_optimizado(
        lookup_tables: Dict[str, List[str]],
        output_path: str = "data/synonyms.yml"
    ) -> Tuple[bool, str]:
        """Exporta sinónimos automáticos desde lookup tables"""
        try:
            if not Path(output_path).is_absolute():
                project_root = OptimizedExporter._get_project_root()
                output_file = project_root / output_path
            else:
                output_file = Path(output_path)
            
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            synonyms_count = 0
            
            with open(output_file, "w", encoding="utf-8") as f:
                f.write('# Sinónimos automáticos - Generado desde lookup tables\n')
                f.write(f'# Fecha: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
                f.write('version: "3.1"\n\n')
                f.write('nlu:\n')
                
                for entity_name, values in lookup_tables.items():
                    if len(values) > 1:  # Solo crear sinónimos si hay múltiples valores
                        # Agrupar valores similares
                        synonym_groups = OptimizedExporter._create_synonym_groups(values)
                        
                        for main_value, synonyms in synonym_groups.items():
                            if len(synonyms) > 1:
                                f.write(f'\n- synonym: {main_value}\n')
                                f.write('  examples: |\n')
                                for synonym in synonyms:
                                    clean_synonym = limpiar_texto_yaml(synonym)
                                    f.write(f'    - {clean_synonym}\n')
                                synonyms_count += 1
            
            is_valid, error_msg = validar_yaml_robusto(str(output_file))
            if not is_valid:
                return False, f"Synonyms YAML inválido: {error_msg}"
            
            print(f"✅ Sinónimos exportados: {synonyms_count} grupos")
            return True, ""
            
        except Exception as e:
            error_msg = f"Error exportando sinónimos: {str(e)}"
            return False, error_msg
    
    @staticmethod
    def _create_synonym_groups(values: List[str]) -> Dict[str, List[str]]:
        """Crea grupos de sinónimos basados en similitud"""
        groups = defaultdict(list)
        
        for value in values:
            if not value or not str(value).strip():
                continue
                
            clean_value = str(value).strip().lower()
            
            # Usar la primera palabra como clave principal
            main_word = clean_value.split()[0] if clean_value else clean_value
            groups[main_word].append(value)
        
        # Filtrar grupos con solo un elemento
        return {k: v for k, v in groups.items() if len(v) > 1}
    
    @staticmethod
    def exportar_archivos_separados_debug(
        lookup_tables: Dict[str, List[str]],
        pattern_entities: Dict[str, List[str]],
        dynamic_entities_info: Dict[str, Dict[str, Any]],
        output_dir: str = "data"
    ) -> Dict[str, bool]:
        """Exporta archivos separados para debugging"""
        results = {}
        
        try:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            # 1. Lookup tables separadas
            lookup_file = output_path / "debug_lookup_tables.yml"
            try:
                with open(lookup_file, "w", encoding="utf-8") as f:
                    f.write('# DEBUG: Lookup Tables\n')
                    f.write('version: "3.1"\n\nnlu:\n')
                    
                    for entity, values in lookup_tables.items():
                        f.write(f'\n- lookup: {entity}\n')
                        f.write('  examples: |\n')
                        for value in values[:10]:  # Solo primeros 10 para debug
                            f.write(f'    - {limpiar_texto_yaml(value)}\n')
                
                results['lookup_tables'] = validar_yaml_robusto(str(lookup_file))[0]
            except Exception as e:
                print(f"❌ Error exportando lookup tables debug: {e}")
                results['lookup_tables'] = False
            
            # 2. Pattern entities separadas
            pattern_file = output_path / "debug_pattern_entities.yml"
            try:
                with open(pattern_file, "w", encoding="utf-8") as f:
                    f.write('# DEBUG: Pattern Entities\n')
                    f.write('version: "3.1"\n\nnlu:\n')
                    
                    for entity, values in pattern_entities.items():
                        f.write(f'\n- lookup: {entity}\n')
                        f.write('  examples: |\n')
                        for value in values[:10]:
                            f.write(f'    - {limpiar_texto_yaml(value)}\n')
                
                results['pattern_entities'] = validar_yaml_robusto(str(pattern_file))[0]
            except Exception as e:
                print(f"❌ Error exportando pattern entities debug: {e}")
                results['pattern_entities'] = False
            
            # 3. Regex patterns separadas
            regex_file = output_path / "debug_regex_patterns.yml"
            try:
                with open(regex_file, "w", encoding="utf-8") as f:
                    f.write('# DEBUG: Regex Patterns\n')
                    f.write('version: "3.1"\n\nnlu:\n')
                    
                    for entity, config in dynamic_entities_info.items():
                        if 'regex_pattern' in config:
                            f.write(f'\n- regex: {entity}\n')
                            f.write(f'  examples: |\n')
                            f.write(f'    - {config["regex_pattern"]}\n')
                
                results['regex_patterns'] = validar_yaml_robusto(str(regex_file))[0]
            except Exception as e:
                print(f"❌ Error exportando regex patterns debug: {e}")
                results['regex_patterns'] = False
            
            print(f"🔧 Archivos debug exportados en: {output_path}")
            return results
            
        except Exception as e:
            print(f"❌ Error general exportando archivos debug: {e}")
            return {"error": False}

# Funciones de compatibilidad para mantener la interfaz anterior
class UnifiedExporter:
    """Wrapper de compatibilidad para mantener la interfaz anterior"""
    
    @staticmethod
    def exportar_nlu_completo(*args, **kwargs):
        """Wrapper para compatibilidad"""
        success, error = OptimizedExporter.exportar_nlu_completo_robusto(*args, **kwargs)
        return success
    
    @staticmethod
    def exportar_synonyms_desde_lookup(*args, **kwargs):
        """Wrapper para compatibilidad"""
        success, error = OptimizedExporter.exportar_synonyms_optimizado(*args, **kwargs)
        return success
    
    @staticmethod
    def exportar_archivos_separados(*args, **kwargs):
        """Wrapper para compatibilidad"""
        return OptimizedExporter.exportar_archivos_separados_debug(*args, **kwargs)

# Función validar_yaml para compatibilidad
def validar_yaml(path: str) -> bool:
    """Función de compatibilidad para validación YAML"""
    return validar_yaml_robusto(path)[0]