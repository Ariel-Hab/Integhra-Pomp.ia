# #!/usr/bin/env python3
# # -*- coding: utf-8 -*-
# """
# Example Usage - Ejemplo completo de uso del sistema modular con roles, grupos y segmentos
# Versión: 4.2 - Incluye StoryGenerator y validación completa
# """

# import logging
# from pathlib import Path

# # Importar módulos del sistema
# from nlu_generator import NLUGenerator
# from validators import ConfigValidator, ValidationReport
# from data_generator import StoryGenerator


# def setup_logging(level=logging.INFO):
#     """Configura logging para el ejemplo"""
#     logging.basicConfig(
#         level=level,
#         format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
#         handlers=[
#             logging.StreamHandler(),
#             logging.FileHandler('nlu_generation.log', mode='w', encoding='utf-8')
#         ]
#     )


# def validate_before_generation(config_dir: str, data_dir: str) -> bool:
#     """Ejecuta validación completa antes de generar incluyendo segmentos y roles"""
#     print("🔍 Ejecutando validación previa completa...")
    
#     # Crear generador temporal solo para obtener entidades, intents y segmentos
#     temp_generator = NLUGenerator(config_dir, data_dir)
    
#     try:
#         # Cargar configuraciones
#         temp_generator.load_all()
        
#         # Obtener configuración de templates para validar roles
#         templates_config = temp_generator.intent_processor.templates_config
        
#         # Ejecutar validación completa
#         validator = ConfigValidator(config_dir, data_dir)
#         report = validator.validate_complete_config(
#             temp_generator.entities, 
#             temp_generator.intents,
#             temp_generator.segments,
#             templates_config
#         )
        
#         # Mostrar reporte
#         report.print_report()
        
#         return report.is_valid
        
#     except Exception as e:
#         print(f"❌ Error durante validación: {e}")
#         return False


# def generate_nlu_with_options(config_dir: str, data_dir: str, output_dir: str):
#     """Genera NLU con diferentes opciones incluyendo expansión con roles"""
#     print("📝 Generando archivos NLU con soporte para roles y grupos...")
    
#     # Crear directorios de salida
#     output_path = Path(output_dir)
#     output_path.mkdir(parents=True, exist_ok=True)
    
#     # Inicializar generador
#     generator = NLUGenerator(config_dir, data_dir)
#     generator.load_all()
    
#     # Generar versión básica (templates sin expandir)
#     print("   • Generando NLU básico...")
#     generator.export_nlu(f"{output_dir}/nlu_basic.yml", expand_templates=False)
    
#     # Generar versión expandida (templates expandidos con entidades y roles)
#     print("   • Generando NLU expandido con anotaciones de roles...")
#     generator.export_nlu(f"{output_dir}/nlu_expanded.yml", expand_templates=True)
    
#     # Generar domain
#     print("   • Generando domain...")
#     generator.export_domain(f"{output_dir}/domain.yml")
    
#     # Mostrar resumen final
#     generator.print_summary()
    
#     return generator


# def generate_stories_and_rules(config_dir: str, output_dir: str):
#     """Genera stories, rules y domain usando StoryGenerator"""
#     print("📚 Generando stories, rules y domain...")
    
#     try:
#         # Crear generador de stories
#         story_gen = StoryGenerator(config_dir)
#         story_gen.load_all_configs()
        
#         # Generar contenido
#         story_gen.generate_stories()
#         story_gen.generate_rules()
        
#         # Exportar archivos
#         story_gen.export_stories(f"{output_dir}/stories.yml")
#         story_gen.export_rules(f"{output_dir}/rules.yml")
#         story_gen.export_domain(f"{output_dir}/domain_complete.yml")
        
#         # Mostrar resumen
#         story_gen.print_summary()
        
#         return story_gen
        
#     except Exception as e:
#         print(f"⚠️ Error generando stories: {e}")
#         print("   Continuando sin stories...")
#         return None


# def demonstrate_intent_expansion_with_roles(generator: NLUGenerator):
#     """Demuestra la expansión de templates con roles y grupos"""
#     print("\n🎭 DEMOSTRACIÓN DE EXPANSIÓN CON ROLES Y GRUPOS")
#     print("="*55)
    
#     # Obtener intents con templates
#     intents_with_templates = [
#         name for name, intent in generator.intents.items() 
#         if intent.templates
#     ]
    
#     if not intents_with_templates:
#         print("No hay intents con templates para demostrar")
#         return
    
#     # Mostrar expansión para los primeros 2 intents
#     for intent_name in intents_with_templates[:2]:
#         intent = generator.intents[intent_name]
        
#         print(f"\n🎯 Intent: {intent_name}")
#         print(f"   Grupo: {intent.group}")
#         print(f"   Templates originales: {len(intent.templates)}")
        
#         # Mostrar algunos templates originales
#         for i, template in enumerate(intent.templates[:2]):
#             print(f"   Template {i+1}: {template}")
        
#         # Expandir templates
#         expanded = generator.expand_intent_templates(intent_name, max_combinations=5)
#         print(f"   Ejemplos expandidos: {len(expanded)}")
        
#         # Mostrar algunos ejemplos expandidos con anotaciones
#         for i, example in enumerate(expanded[:3]):
#             print(f"   Expandido {i+1}: {example}")
#             # Verificar si contiene anotaciones JSON
#             if '{"entity"' in example:
#                 print(f"                   ✓ Con anotaciones de roles/grupos")
        
#         print("-" * 50)


# def demonstrate_segments_loading(generator: NLUGenerator):
#     """Demuestra la carga de segmentos desde formato NLU"""
#     print("\n🧩 DEMOSTRACIÓN DE SEGMENTOS CARGADOS")
#     print("="*45)
    
#     if not generator.segments:
#         print("No se cargaron segmentos")
#         return
    
#     print(f"Total segmentos cargados: {len(generator.segments)}")
    
#     # Mostrar algunos segmentos
#     for i, (name, segment) in enumerate(list(generator.segments.items())[:5]):
#         print(f"\n🔹 Segmento: {name}")
#         print(f"   Categoría: {segment.category}")
#         print(f"   Ejemplos: {len(segment.examples)}")
        
#         # Mostrar algunos ejemplos
#         for j, example in enumerate(segment.examples[:3]):
#             print(f"   - {example}")
        
#         if len(segment.examples) > 3:
#             print(f"   ... y {len(segment.examples) - 3} más")
    
#     if len(generator.segments) > 5:
#         print(f"\n... y {len(generator.segments) - 5} segmentos más")


# def analyze_configuration_quality_extended(generator: NLUGenerator):
#     """Analiza la calidad de la configuración incluyendo roles y grupos"""
#     print("\n📊 ANÁLISIS EXTENDIDO DE CALIDAD")
#     print("="*45)
    
#     # Obtener resumen detallado
#     summary = generator.get_detailed_summary()
    
#     # Analizar entidades
#     entities_info = summary["entities"]
#     print(f"Entidades: {entities_info['total']}")
    
#     # Encontrar entidades con pocos valores
#     sparse_entities = []
#     for name, details in entities_info["details"].items():
#         if details["source"] == "csv" and details["values_count"] < 5:
#             sparse_entities.append((name, details["values_count"]))
    
#     if sparse_entities:
#         print("⚠️ Entidades con pocos valores:")
#         for name, count in sparse_entities:
#             print(f"   • {name}: {count} valores")
    
#     # Analizar intents
#     intents_info = summary["intents"]
#     print(f"\nIntents: {intents_info['total']}")
    
#     incomplete_intents = intents_info['total'] - intents_info['with_examples'] - intents_info['with_templates']
#     if incomplete_intents > 0:
#         print(f"⚠️ Intents sin ejemplos ni templates: {incomplete_intents}")
    
#     no_response_intents = intents_info['total'] - intents_info['with_responses']
#     if no_response_intents > 0:
#         print(f"ℹ️ Intents sin responses: {no_response_intents}")
    
#     # Mostrar distribución por grupos
#     print("\nDistribución por grupos:")
#     for group, count in intents_info['by_group'].items():
#         print(f"   • {group}: {count}")
    
#     # Analizar roles y grupos (nuevo)
#     roles_info = summary.get("roles", {})
#     if roles_info:
#         print(f"\n🎭 ROLES:")
#         print(f"   • Entidades con roles: {roles_info.get('entities_with_roles', 0)}")
#         print(f"   • Total roles definidos: {roles_info.get('total_roles_defined', 0)}")
        
#         if roles_info.get('roles_by_entity'):
#             print("   • Roles por entidad:")
#             for entity, count in list(roles_info['roles_by_entity'].items())[:5]:
#                 print(f"     - {entity}: {count} roles")
    
#     groups_info = summary.get("groups", {})
#     if groups_info.get("groups_distribution"):
#         print(f"\n🏷️ GRUPOS:")
#         for group, count in groups_info["groups_distribution"].items():
#             print(f"   • {group}: {count} entidades")
    
#     # Analizar segmentos
#     segments_info = summary["segments"]
#     if segments_info["total"] > 0:
#         print(f"\n🧩 SEGMENTOS: {segments_info['total']}")
#         if segments_info.get("by_category"):
#             print("   Por categoría:")
#             for category, count in segments_info["by_category"].items():
#                 print(f"   • {category}: {count}")


# def run_complete_example():
#     """Ejecuta ejemplo completo del sistema con todas las funcionalidades"""
#     print("🚀 INICIANDO GENERACIÓN COMPLETA DE NLU + STORIES + RULES")
#     print("="*70)
    
#     BASE_DIR = Path(__file__).parent.resolve()
#     # Configuración
#     config_dir = BASE_DIR / "config"
#     data_dir = BASE_DIR / "data"
#     output_dir = BASE_DIR / "output"
    
#     # 1. Validación previa completa
#     if not validate_before_generation(config_dir, data_dir):
#         print("❌ Validación falló. Corrige los errores antes de continuar.")
#         return None
    
#     print("✅ Validación exitosa, procediendo con generación...")
    
#     # 2. Generación de NLU
#     try:
#         generator = generate_nlu_with_options(config_dir, data_dir, output_dir)
        
#         # 3. Generación de Stories y Rules
#         story_gen = generate_stories_and_rules(config_dir, output_dir)
        
#         # 4. Demostraciones específicas
#         demonstrate_intent_expansion_with_roles(generator)
#         demonstrate_segments_loading(generator)
#         analyze_configuration_quality_extended(generator)
        
#         print("\n🎉 GENERACIÓN COMPLETADA EXITOSAMENTE")
#         print("📁 Archivos generados en:", Path(output_dir).absolute())
#         print("   • nlu_basic.yml - Templates sin expandir")
#         print("   • nlu_expanded.yml - Templates expandidos con roles y grupos")
#         print("   • domain.yml - Domain básico de Rasa")
#         if story_gen:
#             print("   • stories.yml - Stories de conversación")
#             print("   • rules.yml - Rules deterministas")
#             print("   • domain_complete.yml - Domain completo con slots")
#         print("   • nlu_generation.log - Log detallado de la ejecución")
        
#         return generator
        
#     except Exception as e:
#         print(f"❌ Error durante generación: {e}")
#         logging.error(f"Error en generación: {e}", exc_info=True)
#         return None


# def quick_validation_only():
#     """Ejecuta solo validación completa sin generar archivos"""
#     print("🔍 VALIDACIÓN COMPLETA")
#     print("="*35)
    
#     config_dir = "config/"
#     data_dir = "data/"
    
#     success = validate_before_generation(config_dir, data_dir)
    
#     if success:
#         print("\n✅ Configuración válida - incluye roles, grupos y segmentos")
#     else:
#         print("\n❌ Se encontraron problemas en la configuración")
    
#     return success


# def generate_nlu_only():
#     """Genera solo NLU sin validación previa"""
#     print("📝 GENERACIÓN RÁPIDA DE NLU")
#     print("="*35)
    
#     try:
#         generator = NLUGenerator("config/", "data/")
#         generator.load_all()
        
#         # Exportar con templates expandidos y roles
#         generator.export_nlu("output/nlu.yml", expand_templates=True)
#         generator.export_domain("output/domain.yml")
        
#         # Mostrar resumen de lo generado
#         generator.print_summary()
        
#         # Mostrar estadísticas de roles si están disponibles
#         summary = generator.get_detailed_summary()
#         roles_info = summary.get("roles", {})
#         if roles_info.get("entities_with_roles", 0) > 0:
#             print(f"\n🎭 Roles aplicados: {roles_info['entities_with_roles']} entidades con {roles_info.get('total_roles_defined', 0)} roles")
        
#         print("✅ Generación completada con anotaciones de roles y grupos")
#         return generator
        
#     except Exception as e:
#         print(f"❌ Error: {e}")
#         return None


# def generate_stories_only():
#     """Genera solo stories, rules y domain"""
#     print("📚 GENERACIÓN DE STORIES Y RULES")
#     print("="*40)
    
#     try:
#         story_gen = generate_stories_and_rules("config/", "output/")
#         if story_gen:
#             print("✅ Stories, rules y domain generados exitosamente")
#         return story_gen
#     except Exception as e:
#         print(f"❌ Error: {e}")
#         return None


# def main():
#     """Función principal - punto de entrada"""
#     # Configurar logging
#     setup_logging(logging.INFO)
    
#     # Mostrar opciones
#     print("Selecciona una opción:")
#     print("1. Ejecutar ejemplo completo (validación + NLU + stories + rules)")
#     print("2. Solo validación completa")
#     print("3. Solo generación de NLU (con roles y grupos)")
#     print("4. Solo generación de stories y rules")
#     print("5. Demostración de expansión con roles")
    
#     try:
#         choice = input("Opción (1-5): ").strip()
        
#         if choice == "1":
#             return run_complete_example()
#         elif choice == "2":
#             return quick_validation_only()
#         elif choice == "3":
#             return generate_nlu_only()
#         elif choice == "4":
#             return generate_stories_only()
#         elif choice == "5":
#             # Demostración específica de roles
#             generator = NLUGenerator("config/", "data/")
#             generator.load_all()
#             demonstrate_intent_expansion_with_roles(generator)
#             demonstrate_segments_loading(generator)
#             return generator
#         else:
#             print("Opción inválida")
#             return None
            
#     except KeyboardInterrupt:
#         print("\n⏹️ Cancelado por el usuario")
#         return None
#     except Exception as e:
#         print(f"❌ Error: {e}")
#         logging.error(f"Error en main: {e}", exc_info=True)
#         return None


# if __name__ == "__main__":
#     main()