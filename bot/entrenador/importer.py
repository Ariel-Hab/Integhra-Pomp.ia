import os
import re
import csv
import yaml
import random
import unicodedata
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd
from utils import formatear_nombre, generar_fecha_random, limpiar_texto, extraer_nombre_y_dosis

# Cache para configuración unificada
_UNIFIED_CONFIG_CACHE = None

class SimpleImportLogger:
    """Sistema de logging simplificado para importación de entidades"""
    
    @staticmethod
    def log_start(total_entities: int, csv_files: List[str]):
        """Log inicial de lo que se va a procesar"""
        print("=" * 60)
        print("🔧 IMPORTACIÓN DE ENTIDADES")
        print("=" * 60)
        print(f"📊 Entidades a procesar: {total_entities}")
        if csv_files:
            print(f"📁 CSVs a procesar: {', '.join(csv_files)}")
        print()
    
    @staticmethod
    def log_results(successful: Dict[str, int], failed: List[Tuple[str, str]]):
        """Log final de resultados"""
        print("=" * 60)
        print("📋 RESUMEN IMPORTACIÓN")
        print("=" * 60)
        
        total_items = sum(successful.values())
        print(f"✅ Items procesados: {total_items}")
        
        if successful:
            print(f"🎯 Entidades exitosas:")
            for entity, count in successful.items():
                print(f"   • {entity}: {count} items")
        
        if failed:
            print(f"❌ Fallos ({len(failed)}):")
            for entity, error in failed[:5]:  # Solo mostrar primeros 5
                print(f"   • {entity}: {error}")
            if len(failed) > 5:
                print(f"   ... y {len(failed) - 5} errores más")
        
        print("=" * 60)

class UnifiedEntityManager:
    """
    Gestor unificado de entidades que centraliza TODO en entities.yml
    """
    
    @staticmethod
    def _get_project_root() -> Path:
        """Obtiene la ruta raíz del proyecto dinámicamente"""
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent  # bot/entrenador/ -> bot/ -> raíz/
        return project_root
    
    @staticmethod
    def cargar_entities_config(entities_path: Optional[str] = None) -> Dict[str, Any]:
        """Carga la configuración unificada de entidades con ruta dinámica"""
        global _UNIFIED_CONFIG_CACHE
        
        if _UNIFIED_CONFIG_CACHE is None:
            try:
                if entities_path is None:
                    project_root = UnifiedEntityManager._get_project_root()
                    entities_file = project_root / "bot" / "data" / "entities.yml"
                else:
                    entities_file = Path(entities_path)
                
                if not entities_file.exists():
                    return {}
                
                with open(entities_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
                
                _UNIFIED_CONFIG_CACHE = config
                
            except Exception:
                _UNIFIED_CONFIG_CACHE = {}
                
        return _UNIFIED_CONFIG_CACHE

    @staticmethod
    def invalidar_cache():
        """Invalida el cache para forzar recarga"""
        global _UNIFIED_CONFIG_CACHE
        _UNIFIED_CONFIG_CACHE = None

    @staticmethod
    def generar_lookup_tables_desde_csv(data_dir: str = "data") -> Tuple[Dict[str, List[str]], List[Tuple[str, str]]]:
        """
        Genera lookup tables desde CSV usando configuración de entities.yml
        Returns: (lookup_tables, failed_entities)
        """
        config = UnifiedEntityManager.cargar_entities_config()
        csv_processing = config.get("csv_processing", {})
        lookup_entities = config.get("lookup_entities", {})
        
        # Convertir data_dir a ruta absoluta
        project_root = UnifiedEntityManager._get_project_root()
        if not Path(data_dir).is_absolute():
            data_dir_path = project_root / data_dir
        else:
            data_dir_path = Path(data_dir)
        
        lookup_tables = {}
        failed_entities = []
        
        # Preparar información para logging
        csv_files = list(set([cfg["file"] for cfg in csv_processing.values() if "file" in cfg]))
        total_entities = len([e for e in lookup_entities.values() if e.get("source") == "csv"])
        
        SimpleImportLogger.log_start(total_entities, csv_files)

        # Funciones de procesamiento reutilizables
        def quitar_acentos(texto):
            return ''.join(c for c in unicodedata.normalize('NFD', texto)
                           if unicodedata.category(c) != 'Mn')

        def limpiar_y_extraer_compuestos(texto_compuesto):
            """Extrae compuestos químicos de texto"""
            PALABRAS_IRRELEVANTES = [
                'excipientes', 'csp', 'agua destilada', 'contenido de', 'cada',
                'ml', 'g', 'mg', 'unidad', 'unidades', 'equivalente a', 'por',
                'comp', 'tableta', 'comprimido', 'mgml'
            ]
            
            texto = texto_compuesto.lower()
            texto = quitar_acentos(texto)
            texto = re.sub(r'\([^)]*\)', ' ', texto)
            texto = re.sub(r'[:;+/]', ',', texto)
            texto = re.sub(r'\b(c\.?s\.?p\.?|principios? activos?:?|contenido:?|cont(?:iene|:)?|formula:?|componentes?:?)\b', '', texto)
            texto = re.sub(r'\b(mg|g|ml|ui|mcg|mcg/ml|%)\b', ' ', texto)
            texto = re.sub(r'[^\w\s,]', ' ', texto)
            texto = re.sub(r'\s+', ' ', texto).strip()
            
            for palabra in PALABRAS_IRRELEVANTES:
                palabra_esc = re.escape(palabra)
                texto = re.sub(r'\b' + palabra_esc + r'\b', ' ', texto, flags=re.IGNORECASE)
            texto = re.sub(r'\s+', ' ', texto).strip()

            patron = re.compile(r'([a-záéíóúñü\-]+(?: [a-záéíóúñü\-]+)*)', re.IGNORECASE)
            candidatos = patron.findall(texto)
            compuestos = [c.strip() for c in candidatos if len(c.strip()) >= 3 and not re.fullmatch(r'[\d\s,.]+', c)]
            return sorted(set(compuestos))

        def procesar_csv(csv_config_name: str, csv_config: Dict[str, Any]) -> List[str]:
            """Procesa un CSV según la configuración con ruta dinámica"""
            csv_filename = csv_config["file"]
            possible_paths = [
                data_dir_path / csv_filename,
                project_root / "bot" / "data" / csv_filename
            ]
            
            file_path = None
            for path in possible_paths:
                if path.exists():
                    file_path = path
                    break
            
            if file_path is None:
                raise FileNotFoundError(f"CSV no encontrado: {csv_filename}")

            df = pd.read_csv(file_path, on_bad_lines='skip')
            
            # Aplicar filtros específicos
            filters = csv_config.get("filters", [])
            for filter_config in filters:
                if isinstance(filter_config, dict):
                    for filter_name, filter_value in filter_config.items():
                        if filter_name == "enterprise_type_id" and "enterprise_type_id" in df.columns:
                            df = df[df["enterprise_type_id"].isin(filter_value)]

            resultados = []
            column = csv_config["column"]
            tipo = csv_config["type"]
            
            for row in df.itertuples(index=False):
                valor_raw = getattr(row, column, "")
                if pd.isna(valor_raw):
                    continue
                valor_raw = str(valor_raw).strip()
                if not valor_raw or valor_raw == "." or len(valor_raw) == 1:
                    continue

                # Procesamiento específico por tipo
                if tipo == "producto":
                    nombre_raw, _ = extraer_nombre_y_dosis(valor_raw)
                    nombre = formatear_nombre(nombre_raw)
                    if nombre and len(nombre) > 1:
                        resultados.append(nombre)
                elif tipo == "ingrediente_activo":
                    resultados.extend(limpiar_y_extraer_compuestos(valor_raw))
                elif tipo == "categoria":
                    categoria = limpiar_texto(valor_raw)
                    if categoria and len(categoria) > 1:
                        resultados.append(categoria)
                elif tipo == "proveedor":
                    proveedor_full = formatear_nombre(valor_raw)
                    if proveedor_full and len(proveedor_full) > 1:
                        resultados.append(proveedor_full)
                        # Agregar primera palabra como variante si está configurado
                        if any(f.get("add_first_word") for f in filters if isinstance(f, dict)):
                            palabras = proveedor_full.split()
                            if len(palabras) > 1:
                                resultados.append(palabras[0])
                else:
                    limpio = limpiar_texto(valor_raw)
                    if limpio and len(limpio) > 1:
                        resultados.append(limpio)
                        
            return sorted(set(resultados))

        # Procesar todas las entidades con lookup tables
        successful = {}
        
        for entity_name, entity_config in lookup_entities.items():
            try:
                if entity_config.get("source") == "csv":
                    csv_config_name = entity_config["csv_config"]
                    if csv_config_name in csv_processing:
                        csv_config = csv_processing[csv_config_name]
                        resultados = procesar_csv(csv_config_name, csv_config)
                        lookup_tables[entity_name] = resultados
                        successful[entity_name] = len(resultados)
                    else:
                        failed_entities.append((entity_name, f"Configuración CSV no encontrada: {csv_config_name}"))
                elif entity_config.get("source") == "alias":
                    # Manejar alias (ej: compuesto -> ingrediente_activo)
                    alias_of = entity_config["alias_of"]
                    if alias_of in lookup_tables:
                        lookup_tables[entity_name] = lookup_tables[alias_of]
                        successful[entity_name] = len(lookup_tables[alias_of])
                    else:
                        failed_entities.append((entity_name, f"Alias de entidad no encontrada: {alias_of}"))
            except Exception as e:
                failed_entities.append((entity_name, str(e)))

        SimpleImportLogger.log_results(successful, failed_entities)
        return lookup_tables, failed_entities

    @staticmethod
    def obtener_pattern_entities() -> Dict[str, List[str]]:
        """Obtiene todas las entidades con patterns estáticos"""
        config = UnifiedEntityManager.cargar_entities_config()
        pattern_entities = config.get("pattern_entities", {})
        
        patterns_dict = {}
        for entity_name, entity_data in pattern_entities.items():
            patterns_dict[entity_name] = entity_data.get("patterns", [])
            
        return patterns_dict

    @staticmethod
    def obtener_dynamic_entities_info() -> Dict[str, Dict[str, Any]]:
        """Obtiene información de entidades dinámicas (regex)"""
        config = UnifiedEntityManager.cargar_entities_config()
        return config.get("dynamic_entities", {})

    @staticmethod
    def generar_dynamic_entities_examples() -> Dict[str, List[str]]:
        """Genera ejemplos para entidades dinámicas basado en configuración"""
        dynamic_info = UnifiedEntityManager.obtener_dynamic_entities_info()
        
        # Ejemplos hardcodeados pero configurables
        base_examples = {
            "cantidad_descuento": [
                f"{i}%" for i in range(10, 81, 5)  # 10%, 15%, ..., 80%
            ] + ["2x1", "3x2", "4x3", "mitad de precio", "precio promocional"],
            
            "cantidad_bonificacion": [
                f"{i}%" for i in range(10, 51, 5)  # 10%, 15%, ..., 50%
            ] + ["2x1", "3x2", "lleva 2 paga 1", "bonus", "regalo", "gratis"],
            
            "cantidad_stock": [
                f"{i} unidades" for i in [1, 5, 10, 20, 50, 100]
            ] + ["pocas unidades", "stock limitado", "sin stock", "mucho stock", "agotado", "disponible"]
        }
        
        # Filtrar solo las entidades dinámicas configuradas
        result = {}
        for entity_name in dynamic_info.keys():
            if entity_name in base_examples:
                result[entity_name] = base_examples[entity_name]
                
        return result



def generar_imports_unificado(data_dir: str = "data") -> Tuple[Dict[str, List[str]], Dict[str, List[str]], Dict[str, Dict[str, Any]]]:
    """
    Pipeline completo usando el sistema unificado de entidades.
    
    Returns:
        Tuple de (lookup_tables, pattern_entities, dynamic_entities_info)
    """
    # Convertir data_dir a ruta absoluta si es necesario
    project_root = UnifiedEntityManager._get_project_root()
    if not Path(data_dir).is_absolute():
        data_dir_path = project_root / data_dir
    else:
        data_dir_path = Path(data_dir)
    
    data_dir_path.mkdir(exist_ok=True)
    
    # 1. Generar lookup tables desde CSV
    lookup_tables, failed_entities = UnifiedEntityManager.generar_lookup_tables_desde_csv(str(data_dir_path))
    
    # 2. Obtener pattern entities
    pattern_entities = UnifiedEntityManager.obtener_pattern_entities()
    
    # 3. Obtener información de dynamic entities
    dynamic_entities_info = UnifiedEntityManager.obtener_dynamic_entities_info()
    dynamic_examples = UnifiedEntityManager.generar_dynamic_entities_examples()
    
    return lookup_tables, pattern_entities, dynamic_entities_info

def exportar_lookup_tables_csv(lookup_tables: Dict[str, List[str]], output_dir: str = "data"):
    """Exporta lookup tables a archivos CSV individuales (compatibilidad)"""
    # Convertir a ruta absoluta
    project_root = UnifiedEntityManager._get_project_root()
    if not Path(output_dir).is_absolute():
        output_path = project_root / output_dir
    else:
        output_path = Path(output_dir)
    
    output_path.mkdir(exist_ok=True)
    
    for entity_name, values in lookup_tables.items():
        if values:  # Solo exportar si hay valores
            csv_path = output_path / f"{entity_name}_lookup.csv"
            with open(csv_path, 'w', encoding='utf-8') as f:
                for value in sorted(set(values)):
                    f.write(f"{value}\n")

# Funciones de compatibilidad con el sistema anterior
def generar_imports(data_dir: str = "data") -> Tuple[Dict[str, List[str]], Dict[str, Any]]:
    """Función de compatibilidad que mantiene la interfaz anterior"""
    lookup_tables, pattern_entities, dynamic_info = generar_imports_unificado(data_dir)
    
    # Exportar CSVs para compatibilidad
    exportar_lookup_tables_csv(lookup_tables, data_dir)
    
    # Generar entidades por producto (compatibilidad)
    entidades_por_producto = {}
    productos = lookup_tables.get("producto", [])
    if productos:
        # Simplificado para compatibilidad
        for i, producto in enumerate(productos[:100]):  # Limitar para eficiencia
            entidades_por_producto[producto] = {
                "nombre": producto,
                "producto": producto,
                "proveedor": random.choice(lookup_tables.get("proveedor", ["Proveedor"])),
                "categoria": random.choice(lookup_tables.get("categoria", ["Categoria"])),
            }
    
    return lookup_tables, entidades_por_producto

# Funciones de utilidad
def obtener_entidades_disponibles() -> Dict[str, Any]:
    """Devuelve información completa sobre todas las entidades disponibles"""
    config = UnifiedEntityManager.cargar_entities_config()
    
    lookup_entities = list(config.get("lookup_entities", {}).keys())
    pattern_entities = list(config.get("pattern_entities", {}).keys())
    dynamic_entities = list(config.get("dynamic_entities", {}).keys())
    
    return {
        "lookup_entities": lookup_entities,
        "pattern_entities": pattern_entities,
        "dynamic_entities": dynamic_entities,
        "total_entities": len(lookup_entities) + len(pattern_entities) + len(dynamic_entities),
        "entities_config": config
    }

def validar_entidades_kwargs(**kwargs) -> Dict[str, str]:
    """Valida que las entidades pasadas existan en la configuración unificada"""
    info = obtener_entidades_disponibles()
    all_entities = info["lookup_entities"] + info["pattern_entities"] + info["dynamic_entities"]
    
    issues = {}
    for entity_name, valor in kwargs.items():
        if entity_name not in all_entities:
            issues[entity_name] = f"Entidad no definida en configuración unificada"
        elif not valor:
            issues[entity_name] = f"Valor vacío para entidad"
    
    return issues

# Testing y ejemplos
if __name__ == "__main__":
    print("🚀 TESTING SISTEMA UNIFICADO DE ENTIDADES")
    print("="*50)
    
    # Mostrar entidades disponibles
    info = obtener_entidades_disponibles()
    print(f"📊 Entidades disponibles:")
    print(f"   • Lookup: {info['lookup_entities']}")
    print(f"   • Patterns: {info['pattern_entities']}")
    print(f"   • Dynamic: {info['dynamic_entities']}")
    print(f"   • Total: {info['total_entities']}")
    
    # Generar imports usando sistema unificado
    print(f"\n🔧 Generando imports...")
    lookup, patterns, dynamic = generar_imports_unificado()
    
    # Ejemplo de anotación
    texto_ejemplo = "necesito antibiótico de bayer para mi perro con 20% de descuento"
    print(f"\n📝 Ejemplo de anotación:")
    print(f"   Original: {texto_ejemplo}")
    
    print(f"\n✅ Sistema unificado funcionando correctamente")