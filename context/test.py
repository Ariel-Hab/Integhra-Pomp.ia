#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Runner para el Generador NLU - Script de ejecución principal
Versión: 1.0
"""

import argparse
import json
import sys
import logging
from pathlib import Path
from typing import Optional
import time

# Importar el generador principal
from nlu_generator import IntegratedNLUGenerator, IntegratedConfig

def setup_logging(verbose: bool = False):
    """Configura el sistema de logging"""
    level = logging.DEBUG if verbose else logging.INFO
    
    # Configurar formato
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # Handler para consola
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Configurar logger raíz
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    
    # Reducir ruido de algunos loggers
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)

def validate_directories(config_dir: Path, data_dir: Path, output_dir: Path) -> bool:
    """Valida que los directorios necesarios existan"""
    errors = []
    
    if not config_dir.exists():
        errors.append(f"Directorio de configuración no encontrado: {config_dir}")
    
    if not data_dir.exists():
        errors.append(f"Directorio de datos no encontrado: {data_dir}")
    
    # Verificar archivos de configuración críticos
    critical_files = [
        config_dir / "examples.yml",
        config_dir / "entities_config.yml",
        config_dir / "nlu_config.yml",
        config_dir / "templates.yml"
    ]
    
    for file_path in critical_files:
        if not file_path.exists():
            errors.append(f"Archivo crítico no encontrado: {file_path}")
    
    if errors:
        print("❌ Errores de validación:")
        for error in errors:
            print(f"   • {error}")
        return False
    
    # Crear directorio de salida si no existe
    output_dir.mkdir(parents=True, exist_ok=True)
    
    return True

def print_header():
    """Imprime el header del programa"""
    print("=" * 70)
    print("🤖 GENERADOR NLU - Sistema Completo de Datos de Entrenamiento")
    print("=" * 70)
    print()

def print_directory_info(config_dir: Path, data_dir: Path, output_dir: Path):
    """Imprime información de directorios"""
    print("📁 Configuración de directorios:")
    print(f"   Config:  {config_dir.absolute()}")
    print(f"   Data:    {data_dir.absolute()}")
    print(f"   Output:  {output_dir.absolute()}")
    print()

def print_generation_summary(stats: dict):
    """Imprime resumen de la generación"""
    print("\n" + "=" * 70)
    print("📊 RESUMEN DE GENERACIÓN")
    print("=" * 70)
    
    print(f"Total de ejemplos generados: {stats['total_examples']:,}")
    print(f"Total de intents: {stats['generation_summary']['total_intents']}")
    print(f"Promedio por intent: {stats['generation_summary']['avg_examples_per_intent']:.1f}")
    
    print("\n📈 Ejemplos por fuente:")
    for source, count in stats['examples_by_source'].items():
        percentage = (count / stats['total_examples']) * 100
        print(f"   {source:12}: {count:5,} ({percentage:5.1f}%)")
    
    print("\n🎯 Top 10 intents por cantidad:")
    sorted_intents = sorted(
        stats['examples_by_intent'].items(), 
        key=lambda x: x[1], 
        reverse=True
    )[:10]
    
    for intent, count in sorted_intents:
        print(f"   {intent:25}: {count:4,} ejemplos")
    
    if stats['entity_usage']:
        print("\n🏷️ Top 10 entidades más usadas:")
        for entity, count in list(stats['entity_usage'].items())[:10]:
            print(f"   {entity:20}: {count:4,} usos")

def main():
    """Función principal integrada"""
    parser = argparse.ArgumentParser(
        description="Generador NLU Integrado - Sistema completo con lookup tables automáticas",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  python run_generator.py
  python run_generator.py --config-dir ./config --data-dir ./data
  python run_generator.py --output-dir ./output --verbose
  python run_generator.py --dry-run
  python run_generator.py --max-examples 20 --similarity-threshold 0.8
        """
    )
    
    # Argumentos de directorios
    parser.add_argument(
        "--config-dir", 
        type=Path, 
        default=Path("config"),
        help="Directorio de archivos de configuración (default: config)"
    )
    
    parser.add_argument(
        "--data-dir", 
        type=Path, 
        default=Path("data"),
        help="Directorio de archivos de datos CSV (default: data)"
    )
    
    parser.add_argument(
        "--output-dir", 
        type=Path, 
        default=Path("generated"),
        help="Directorio de salida (default: generated)"
    )
    
    # Argumentos de configuración de archivos
    parser.add_argument(
        "--nlu-filename",
        type=str,
        default="nlu_complete.yml",
        help="Nombre del archivo NLU de salida (default: nlu_complete.yml)"
    )
    
    parser.add_argument(
        "--lookup-filename",
        type=str,
        default="lookup_tables.yml",
        help="Nombre del archivo de lookup tables (default: lookup_tables.yml)"
    )
    
    # Argumentos de configuración de generación
    parser.add_argument(
        "--max-examples",
        type=int,
        default=25,
        help="Máximo ejemplos por intent (default: 25)"
    )
    
    parser.add_argument(
        "--min-examples",
        type=int,
        default=5,
        help="Mínimo ejemplos por intent (default: 5)"
    )
    
    parser.add_argument(
        "--max-variations",
        type=int,
        default=6,
        help="Máximo variaciones por template (default: 6)"
    )
    
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.80,
        help="Umbral de similitud para deduplicación (default: 0.80)"
    )
    
    parser.add_argument(
        "--variation-probability",
        type=float,
        default=0.6,
        help="Probabilidad de generar variaciones (default: 0.6)"
    )
    
    parser.add_argument(
        "--max-lookup-values",
        type=int,
        default=40,
        help="Máximo valores por lookup table (default: 40)"
    )
    
    # Argumentos de control
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Activar logging detallado"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Ejecutar validación sin generar archivos"
    )
    
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Solo generar estadísticas, sin archivos NLU/lookup"
    )
    
    parser.add_argument(
        "--skip-lookup",
        action="store_true",
        help="Saltar generación de lookup tables"
    )
    
    parser.add_argument(
        "--disable-consolidation",
        action="store_true",
        help="Desactivar consolidación automática de intents"
    )
    
    args = parser.parse_args()
    
    # Configurar logging
    setup_logging(args.verbose)
    
    # Mostrar header
    print_header()
    print_directory_info(args.config_dir, args.data_dir, args.output_dir)
    
    # Validar directorios
    if not validate_directories(args.config_dir, args.data_dir, args.output_dir):
        sys.exit(1)
    
    print("✅ Validación de directorios completada\n")
    
    if args.dry_run:
        print("🔍 Modo dry-run activado - No se generarán archivos")
        print("✅ Validación completada exitosamente")
        return 0
    
    try:
        # Configurar el sistema integrado
        print("⚙️ Configurando sistema integrado...")
        
        # Crear configuración personalizada
        config = IntegratedConfig(
            max_examples_per_intent=args.max_examples,
            min_examples_per_intent=args.min_examples,
            max_variations_per_template=args.max_variations,
            similarity_threshold=args.similarity_threshold,
            variation_probability=args.variation_probability
        )
        
        # Configurar lookup tables
        from lookup_generator_from_entities import LookupTableConfig
        config.lookup_config = LookupTableConfig(
            max_values_per_lookup=args.max_lookup_values,
            min_values_for_lookup=3,
            generate_synonyms=True,
            generate_regex=True
        )
        
        # Desactivar consolidación si se solicita
        if args.disable_consolidation:
            config.intent_consolidation = {}
        
        # Crear generador integrado
        print("🚀 Inicializando generador integrado...")
        generator = IntegratedNLUGenerator(args.config_dir, args.data_dir, args.output_dir, config)
        
        # Medir tiempo de ejecución
        start_time = time.time()
        
        # Generar sistema completo
        print("⚙️ Iniciando generación completa (NLU + Lookup Tables)...")
        generator.generate_complete_nlu()
        
        # Generar estadísticas
        stats = generator.generate_comprehensive_stats()
        
        # Exportar archivos si no es stats-only
        nlu_file = None
        lookup_file = None
        
        if not args.stats_only:
            if args.skip_lookup:
                # Solo generar NLU
                nlu_file = generator._export_nlu_yml(args.output_dir / args.nlu_filename)
                print(f"📄 Archivo NLU generado: {nlu_file}")
            else:
                # Generar ambos archivos
                nlu_file, lookup_file = generator.export_complete_nlu(
                    args.nlu_filename, 
                    args.lookup_filename
                )
                print(f"📄 Archivo NLU generado: {nlu_file}")
                print(f"📋 Lookup Tables generadas: {lookup_file}")
        
        # Guardar estadísticas detalladas
        stats_file = args.output_dir / "comprehensive_stats.json"
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        
        # Calcular tiempo transcurrido
        elapsed_time = time.time() - start_time
        
        # Mostrar resultados
        print_generation_summary(stats)
        
        print(f"\n⏱️  Tiempo total: {elapsed_time:.2f} segundos")
        print(f"📊 Estadísticas: {stats_file}")
        
        # Resumen final
        print(f"\n🎉 Generación integrada completada exitosamente!")
        if not args.stats_only:
            if nlu_file:
                print(f"   📄 NLU: {nlu_file.name}")
            if lookup_file:
                print(f"   📋 Lookups: {lookup_file.name}")
            print(f"   📊 Stats: {stats_file.name}")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Proceso interrumpido por el usuario")
        return 1
        
    except Exception as e:
        logging.error(f"❌ Error durante la generación: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())