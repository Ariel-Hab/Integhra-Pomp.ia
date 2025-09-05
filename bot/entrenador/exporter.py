import re
import yaml
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Any, Tuple
import unidecode

def validar_yaml(path: str = "data/nlu.yml") -> bool:
    """Valida sintaxis YAML de un archivo"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            yaml.safe_load(f)
        print(f"✅ YAML válido: {Path(path).name}")
        return True
    except yaml.YAMLError as e:
        print(f"❌ Error en YAML {Path(path).name}: {e}")
        return False
    except FileNotFoundError:
        print(f"❌ Archivo no encontrado: {path}")
        return False

def limpiar_yaml(ejemplo: str) -> str:
    """Limpia texto para exportación YAML segura"""
    ejemplo = ejemplo.replace('"', '\\"')
    ejemplo = ejemplo.replace('\n', ' ').replace('\r', '')
    ejemplo = re.sub(r'\s{2,}', ' ', ejemplo)
    return ejemplo.strip()

class UnifiedExporter:
    """
    Exportador que genera TODOS los archivos necesarios para Rasa
    usando el sistema unificado de entidades
    """
    
    @staticmethod
    def _get_project_root() -> Path:
        """Obtiene la ruta raíz del proyecto dinámicamente"""
        # Desde bot/entrenador/exporter.py ir a la raíz
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent  # bot/entrenador/ -> bot/ -> raíz/
        return project_root
    
    @staticmethod
    def exportar_nlu_completo(
        ejemplos: List[Tuple[str, str]],
        lookup_tables: Dict[str, List[str]],
        pattern_entities: Dict[str, List[str]], 
        dynamic_entities_info: Dict[str, Dict[str, Any]],
        output_path: str = "data/nlu.yml"
    ) -> bool:
        """
        Exporta NLU completo: ejemplos + lookup tables + regex patterns
        TODO EN UN SOLO ARCHIVO para que Rasa tenga acceso a todo
        """
        try:
            # Convertir output_path a absoluto si es necesario
            if not Path(output_path).is_absolute():
                project_root = UnifiedExporter._get_project_root()
                output_file = project_root / output_path
            else:
                output_file = Path(output_path)
            
            # Crear directorio padre si no existe
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, "w", encoding="utf-8") as f:
                f.write('version: "3.1"\n\nnlu:\n')
                
                # 1. EJEMPLOS DE INTENTS
                if ejemplos:
                    f.write("# ============================================================================\n")
                    f.write("# 🔹 TRAINING EXAMPLES POR INTENT\n") 
                    f.write("# ============================================================================\n\n")
                    
                    intents = defaultdict(list)
                    for texto, intent in ejemplos:
                        if texto is None:
                            continue
                        texto = str(texto).strip()
                        if texto:
                            intents[intent].append(texto)

                    for intent, ejemplos_intent in intents.items():
                        f.write(f'- intent: {intent}\n  examples: |\n')
                        for ejemplo in ejemplos_intent:
                            clean = limpiar_yaml(str(ejemplo))
                            f.write(f'    - "{clean}"\n')
                        f.write("\n")
                
                # 2. LOOKUP TABLES (desde CSV)
                if lookup_tables:
                    f.write("# ============================================================================\n")
                    f.write("# 🔹 LOOKUP TABLES (desde CSV y entidades core)\n")
                    f.write("# ============================================================================\n\n")
                    
                    for entity, valores in lookup_tables.items():
                        if not valores:
                            continue
                        f.write(f'- lookup: {entity}\n  examples: |\n')
                        for valor in sorted(set(valores)):
                            valor = str(valor).strip()
                            valor = valor.replace('\n', ' ').replace('\r', '')
                            valor = valor.replace('"', "'")
                            valor = re.sub(r"\s{2,}", " ", valor)

                            if ":" in valor:
                                print(f"⚠️ Posible problema en lookup '{entity}': {valor}")
                                continue

                            if valor:
                                f.write(f'    - {valor}\n')
                        f.write('\n')
                
                # 3. LOOKUP TABLES para PATTERN ENTITIES (ejemplos estáticos)
                if pattern_entities:
                    f.write("# ============================================================================\n")
                    f.write("# 🔹 PATTERN ENTITIES como LOOKUP TABLES\n")
                    f.write("# ============================================================================\n\n")
                    
                    for entity, patterns in pattern_entities.items():
                        if not patterns:
                            continue
                        f.write(f'- lookup: {entity}\n  examples: |\n')
                        for pattern in patterns:
                            pattern = str(pattern).strip()
                            if pattern:
                                f.write(f'    - {pattern}\n')
                        f.write('\n')
                
                # 4. REGEX PATTERNS para DYNAMIC ENTITIES
                if dynamic_entities_info:
                    f.write("# ============================================================================\n")
                    f.write("# 🔹 REGEX PATTERNS para ENTIDADES DINÁMICAS\n")
                    f.write("# ============================================================================\n\n")
                    
                    # Cargar patterns desde entities_regex.yml
                    regex_patterns = UnifiedExporter._cargar_regex_patterns()
                    
                    for entity_name, entity_info in dynamic_entities_info.items():
                        regex_name = entity_info.get("regex_name", entity_name)
                        if regex_name in regex_patterns:
                            patterns = regex_patterns[regex_name]
                            f.write(f'- regex: {entity_name}\n  examples: |\n')
                            for pattern in patterns:
                                f.write(f'    - {pattern}\n')
                            f.write('\n')
                
                # 5. LOOKUP TABLES para EJEMPLOS de DYNAMIC ENTITIES
                # Esto permite al NLU reconocer ejemplos comunes incluso sin regex
                if dynamic_entities_info:
                    f.write("# ============================================================================\n")
                    f.write("# 🔹 EJEMPLOS de ENTIDADES DINÁMICAS (para mejor training)\n")
                    f.write("# ============================================================================\n\n")
                    
                    from bot.entrenador.importer import UnifiedEntityManager
                    dynamic_examples = UnifiedEntityManager.generar_dynamic_entities_examples()
                    
                    for entity_name, entity_info in dynamic_entities_info.items():
                        examples_lookup_name = entity_info.get("examples_lookup")
                        if examples_lookup_name and entity_name in dynamic_examples:
                            examples = dynamic_examples[entity_name]
                            f.write(f'- lookup: {examples_lookup_name}\n  examples: |\n')
                            for example in examples:
                                f.write(f'    - {example}\n')
                            f.write('\n')

            print(f"✅ [NLU] Archivo completo exportado: {output_file}")
            return True
            
        except Exception as e:
            print(f"❌ [NLU] Error exportando: {e}")
            return False

    @staticmethod
    def _cargar_regex_patterns() -> Dict[str, List[str]]:
        """Carga patterns de regex desde entities_regex.yml con búsqueda dinámica"""
        try:
            project_root = UnifiedExporter._get_project_root()
            
            # Buscar en múltiples ubicaciones posibles
            possible_paths = [
                project_root / "bot" / "data" / "entities_regex.yml",
                project_root / "context" / "entities_regex.yml",
                Path("bot/data/entities_regex.yml"),
                Path("context/entities_regex.yml"),
                Path("entities_regex.yml")
            ]
            
            regex_file = None
            for path in possible_paths:
                if path.exists():
                    regex_file = path
                    break
            
            if not regex_file:
                print(f"⚠️ [REGEX] No se encuentra entities_regex.yml en ubicaciones:")
                for path in possible_paths:
                    print(f"    • {path}")
                return {}
                
            with open(regex_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            
            patterns = {}
            nlu_data = data.get("nlu", [])
            
            for item in nlu_data:
                if isinstance(item, dict) and "regex" in item:
                    regex_name = item["regex"]
                    examples_text = item.get("examples", "")
                    
                    if isinstance(examples_text, str):
                        regex_patterns = []
                        for line in examples_text.split('\n'):
                            line = line.strip()
                            if line.startswith('- '):
                                pattern = line[2:].strip()
                                if pattern:
                                    regex_patterns.append(pattern)
                        
                        if regex_patterns:
                            patterns[regex_name] = regex_patterns
            
            print(f"✅ [REGEX] Cargados {len(patterns)} regex patterns desde {regex_file}")
            return patterns
            
        except Exception as e:
            print(f"❌ [REGEX] Error cargando patterns: {e}")
            return {}

    @staticmethod
    def exportar_synonyms_desde_lookup(
        lookup_tables: Dict[str, List[str]], 
        output_path: str = "data/synonyms.yml"
    ) -> bool:
        """
        Genera sinónimos automáticos desde lookup tables
        """
        try:
            # Convertir output_path a absoluto si es necesario
            if not Path(output_path).is_absolute():
                project_root = UnifiedExporter._get_project_root()
                output_file = project_root / output_path
            else:
                output_file = Path(output_path)
            
            # Crear directorio padre si no existe
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            synonyms_data = {"version": "3.1", "nlu": []}
            
            for entity_name, valores in lookup_tables.items():
                if not valores:
                    continue
                    
                # Generar sinónimos para cada valor
                for valor_original in valores:
                    if not valor_original or len(valor_original) < 2:
                        continue
                        
                    variantes = set()
                    variantes.add(valor_original)  # Original
                    variantes.add(valor_original.lower())  # Lowercase
                    variantes.add(unidecode.unidecode(valor_original.lower()))  # Sin acentos
                    
                    # Generar variantes adicionales
                    if " " in valor_original:
                        # Para nombres multi-palabra, agregar sin espacios
                        variantes.add(valor_original.replace(" ", ""))
                        # Agregar primera palabra sola
                        primera_palabra = valor_original.split()[0]
                        if len(primera_palabra) > 2:
                            variantes.add(primera_palabra)
                    
                    # Filtrar el valor original para obtener solo las variantes
                    ejemplos = [v for v in variantes if v != valor_original and v.strip()]
                    
                    if ejemplos:
                        ejemplos_str = "\n".join(f"    - {e}" for e in ejemplos)
                        synonyms_data["nlu"].append({
                            "synonym": valor_original,
                            "examples": ejemplos_str
                        })
            
            with open(output_file, "w", encoding="utf-8") as f:
                yaml.dump(synonyms_data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
            
            print(f"✅ [SYNONYMS] Generados sinónimos automáticos: {output_file}")
            return True
            
        except Exception as e:
            print(f"❌ [SYNONYMS] Error generando sinónimos: {e}")
            return False

    @staticmethod
    def exportar_archivos_separados(
        lookup_tables: Dict[str, List[str]],
        pattern_entities: Dict[str, List[str]],
        dynamic_entities_info: Dict[str, Dict[str, Any]],
        output_dir: str = "data"
    ) -> Dict[str, bool]:
        """
        Exporta archivos separados para casos donde se necesiten
        (lookup_tables.yml, regex_entities.yml, etc.)
        """
        results = {}
        
        # Convertir output_dir a absoluto si es necesario
        if not Path(output_dir).is_absolute():
            project_root = UnifiedExporter._get_project_root()
            output_path = project_root / output_dir
        else:
            output_path = Path(output_dir)
            
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 1. Exportar lookup tables separadas
        lookup_path = output_path / "lookup_tables.yml"
        try:
            with open(lookup_path, "w", encoding="utf-8") as f:
                f.write('version: "3.1"\n\nnlu:\n')
                
                # Lookup tables desde CSV
                for entity, valores in lookup_tables.items():
                    if not valores:
                        continue
                    f.write(f'- lookup: {entity}\n  examples: |\n')
                    for valor in sorted(set(valores)):
                        valor = str(valor).strip()
                        if valor:
                            f.write(f'    - {valor}\n')
                    f.write('\n')
                
                # Pattern entities como lookup tables
                for entity, patterns in pattern_entities.items():
                    if not patterns:
                        continue
                    f.write(f'- lookup: {entity}\n  examples: |\n')
                    for pattern in patterns:
                        if pattern:
                            f.write(f'    - {pattern}\n')
                    f.write('\n')
            
            results["lookup_tables"] = True
            print(f"✅ [SEPARATE] Lookup tables: {lookup_path}")
            
        except Exception as e:
            print(f"❌ [SEPARATE] Error exportando lookup tables: {e}")
            results["lookup_tables"] = False
        
        # 2. Exportar regex entities separadas
        regex_path = output_path / "regex_entities.yml"
        try:
            regex_patterns = UnifiedExporter._cargar_regex_patterns()
            
            with open(regex_path, "w", encoding="utf-8") as f:
                f.write('version: "3.1"\n\nnlu:\n')
                
                for entity_name, entity_info in dynamic_entities_info.items():
                    regex_name = entity_info.get("regex_name", entity_name)
                    if regex_name in regex_patterns:
                        patterns = regex_patterns[regex_name]
                        f.write(f'- regex: {entity_name}\n  examples: |\n')
                        for pattern in patterns:
                            f.write(f'    - {pattern}\n')
                        f.write('\n')
            
            results["regex_entities"] = True
            print(f"✅ [SEPARATE] Regex entities: {regex_path}")
            
        except Exception as e:
            print(f"❌ [SEPARATE] Error exportando regex entities: {e}")
            results["regex_entities"] = False
        
        return results

# Funciones de compatibilidad con sistema anterior
def exportar_yaml(ejemplos: List[Tuple[str, str]], output_path: str = "data/nlu.yml") -> bool:
    """Función de compatibilidad - solo ejemplos"""
    try:
        # Convertir a ruta absoluta
        if not Path(output_path).is_absolute():
            project_root = UnifiedExporter._get_project_root()
            output_file = project_root / output_path
        else:
            output_file = Path(output_path)
        
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        intents = defaultdict(list)
        for texto, intent in ejemplos:
            if texto is None:
                continue
            texto = str(texto).strip()
            if not texto:
                continue
            intents[intent].append(texto)

        with open(output_file, "w", encoding="utf-8") as f:
            f.write('version: "3.1"\n\nnlu:\n')
            for intent, ejemplos_intent in intents.items():
                f.write(f'- intent: {intent}\n  examples: |\n')
                for ejemplo in ejemplos_intent:
                    clean = limpiar_yaml(str(ejemplo))
                    f.write(f'    - "{clean}"\n')
                f.write("\n")
        
        print(f"✅ [COMPAT] Ejemplos exportados: {output_file}")
        return True
        
    except Exception as e:
        print(f"❌ [COMPAT] Error exportando ejemplos: {e}")
        return False

def exportar_lookup_tables(lookup_tables: Dict[str, List[str]], output_path: str = "data/lookup_tables.yml") -> bool:
    """Función de compatibilidad - solo lookup tables"""
    try:
        # Convertir a ruta absoluta
        if not Path(output_path).is_absolute():
            project_root = UnifiedExporter._get_project_root()
            output_file = project_root / output_path
        else:
            output_file = Path(output_path)
        
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write('version: "3.1"\n\nnlu:\n')
            for entity, ejemplos in lookup_tables.items():
                if not ejemplos:
                    continue
                f.write(f'- lookup: {entity}\n  examples: |\n')
                for e in ejemplos:
                    e = str(e).strip()
                    e = e.replace('\n', ' ').replace('\r', '')
                    e = e.replace('"', "'")
                    e = re.sub(r"\s{2,}", " ", e)

                    if ":" in e:
                        print(f"⚠️ Posible problema en entidad '{entity}': {e}")
                        continue

                    if e:
                        f.write(f'    - {e}\n')
                f.write('\n')
        
        print(f"✅ [COMPAT] Lookup tables exportadas: {output_file}")
        return True
        
    except Exception as e:
        print(f"❌ [COMPAT] Error exportando lookup tables: {e}")
        return False

def generar_synonyms_from_list(canonicos: List[str]) -> Dict[str, Any]:
    """Función de compatibilidad para generar sinónimos"""
    synonyms = {"version": "3.1", "nlu": []}
    for item in canonicos:
        variantes = set()
        variantes.add(item)
        variantes.add(item.lower())
        variantes.add(unidecode.unidecode(item.lower()))

        ejemplos = [v for v in variantes if v != item]

        if ejemplos:
            ejemplos_str = "\n".join(f"- {e}" for e in ejemplos)
            synonyms["nlu"].append({
                "synonym": item,
                "examples": ejemplos_str
            })
    return synonyms

def exportar_synonyms_a_yaml(synonyms: Dict[str, Any], path: str = "data/synonyms.yml") -> bool:
    """Función de compatibilidad para exportar sinónimos"""
    try:
        # Convertir a ruta absoluta
        if not Path(path).is_absolute():
            project_root = UnifiedExporter._get_project_root()
            output_file = project_root / path
        else:
            output_file = Path(path)
        
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(synonyms, f, allow_unicode=True, sort_keys=False)
        print(f"✅ [COMPAT] Sinónimos exportados: {output_file}")
        return True
    except Exception as e:
        print(f"❌ [COMPAT] Error exportando sinónimos: {e}")
        return False

# Testing y ejemplos
if __name__ == "__main__":
    print("🚀 TESTING EXPORTADOR UNIFICADO")
    print("="*50)
    
    # Datos de ejemplo
    ejemplos_test = [
        ("necesito [antibiótico](producto) para [perros](animal)", "buscar_producto"),
        ("hay [ofertas](intencion_buscar) de [bayer](proveedor)?", "buscar_oferta")
    ]
    
    lookup_test = {
        "producto": ["antibiótico", "vitamina", "desparasitante"],
        "proveedor": ["bayer", "zoetis", "merial"]
    }
    
    pattern_test = {
        "animal": ["perro", "gato", "caballo"],
        "sentimiento_positivo": ["genial", "perfecto", "excelente"]
    }
    
    dynamic_test = {
        "cantidad_descuento": {
            "regex_name": "cantidad_descuento",
            "examples_lookup": "cantidad_descuento_ejemplos"
        }
    }
    
    # Test exportación completa
    print("📝 Exportando NLU completo...")
    success = UnifiedExporter.exportar_nlu_completo(
        ejemplos_test, lookup_test, pattern_test, dynamic_test,
        "test_nlu_completo.yml"
    )
    
    if success:
        validar_yaml("test_nlu_completo.yml")
    
    # Test sinónimos automáticos
    print("📝 Generando sinónimos automáticos...")
    UnifiedExporter.exportar_synonyms_desde_lookup(lookup_test, "test_synonyms.yml")
    
    print("✅ Testing completado")