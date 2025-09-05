import os
from pathlib import Path
from bot.entrenador.data_generator.domain_generator import DomainGenerator
from bot.entrenador.data_generator.nlu_generator import NLUGenerator
from bot.entrenador.data_generator.stories_generator import StoriesGenerator
from scripts.config_loader import ConfigLoader
from bot.entrenador.importer import generar_imports_unificado, UnifiedEntityManager
from bot.entrenador.exporter import UnifiedExporter, validar_yaml

# Colores para terminal
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    BOLD = '\033[1m'
    ENDC = '\033[0m'

def get_project_root() -> Path:
    """Obtiene la ruta raíz del proyecto dinámicamente"""
    # Desde donde sea que esté train.py, ir a la raíz
    current_file = Path(__file__).parent.resolve()
    # Si train.py está en la raíz, usar el directorio del archivo
    # Si está en subdirectorio, ajustar según sea necesario
    return current_file.parent

def main():
    print(f"{Colors.HEADER}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}SISTEMA UNIFICADO DE ENTRENAMIENTO - VERSIÓN OPTIMIZADA{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*80}{Colors.ENDC}")
    
    # Obtener rutas absolutas
    project_root = get_project_root()
    data_dir = project_root / "data"
    
    # Crear carpeta data
    data_dir.mkdir(exist_ok=True)
    print(f"{Colors.OKBLUE}Preparando directorio de datos en {data_dir}...{Colors.ENDC}")

    # 1. GENERAR ENTIDADES USANDO SISTEMA UNIFICADO
    print(f"{Colors.OKCYAN}FASE 1: Generando entidades desde sistema unificado...{Colors.ENDC}")
    
    # Generar todas las entidades desde entities.yml centralizado
    lookup_tables, pattern_entities, dynamic_entities_info = generar_imports_unificado(data_dir=str(data_dir))
    
    print(f"{Colors.OKGREEN}Entidades generadas:{Colors.ENDC}")
    print(f"  • Lookup entities (CSV): {len(lookup_tables)}")
    print(f"  • Pattern entities (estáticas): {len(pattern_entities)}")
    print(f"  • Dynamic entities (regex): {len(dynamic_entities_info)}")

    # 2. CARGAR CONFIGURACIÓN DE INTENTS
    print(f"{Colors.OKCYAN}FASE 2: Cargando configuración de intents...{Colors.ENDC}")
    config_data = ConfigLoader.cargar_config()
    intents = config_data["intents"]
    
    print(f"{Colors.OKGREEN}Configuración cargada: {len(intents)} intents{Colors.ENDC}")

    # 3. GENERAR EJEMPLOS NLU (opcional)
    ejemplos = []
    if input(f"{Colors.HEADER}¿Generar nuevos ejemplos NLU? (s/N): {Colors.ENDC}").lower() in ["s", "si", "sí", "y", "yes"]:
        print(f"{Colors.OKCYAN}FASE 3: Generando ejemplos NLU...{Colors.ENDC}")
        
        # Combinar todas las entidades para el generador
        all_lookup_entities = {**lookup_tables, **pattern_entities}
        
        ejemplos = NLUGenerator.generar_ejemplos(
            config=config_data, 
            lookup=all_lookup_entities,  # Ahora incluye tanto CSV como patterns
            synonyms=config_data.get("segments", {}),
            n_por_intent=500,
            use_limits_file=True
        )
        print(f"{Colors.OKGREEN}Ejemplos generados: {len(ejemplos)}{Colors.ENDC}")
    else:
        print(f"{Colors.WARNING}Manteniendo ejemplos NLU existentes{Colors.ENDC}")

    # 4. EXPORTAR NLU COMPLETO (TODO EN UNO)
    print(f"{Colors.OKCYAN}FASE 4: Exportando NLU completo (ejemplos + lookups + regex)...{Colors.ENDC}")
    
    # Usar rutas absolutas para exportación
    nlu_path = data_dir / "nlu.yml"
    
    # Exportar TODO en un solo archivo para que Rasa tenga acceso completo
    nlu_success = UnifiedExporter.exportar_nlu_completo(
        ejemplos=ejemplos,
        lookup_tables=lookup_tables,
        pattern_entities=pattern_entities,
        dynamic_entities_info=dynamic_entities_info,
        output_path=str(nlu_path)
    )
    
    if nlu_success:
        validar_yaml(str(nlu_path))
        print(f"{Colors.OKGREEN}NLU completo exportado y validado{Colors.ENDC}")
    else:
        print(f"{Colors.FAIL}Error exportando NLU completo{Colors.ENDC}")
        return

    # 5. GENERAR SINÓNIMOS AUTOMÁTICOS
    print(f"{Colors.OKCYAN}FASE 5: Generando sinónimos automáticos...{Colors.ENDC}")
    synonyms_path = data_dir / "synonyms.yml"
    
    UnifiedExporter.exportar_synonyms_desde_lookup(
        lookup_tables=lookup_tables,
        output_path=str(synonyms_path)
    )
    validar_yaml(str(synonyms_path))

    # 6. EXPORTAR ARCHIVOS SEPARADOS (opcional, para debugging)
    if input(f"{Colors.HEADER}¿Exportar archivos separados para debugging? (s/N): {Colors.ENDC}").lower() in ["s", "si", "sí", "y", "yes"]:
        print(f"{Colors.OKCYAN}FASE 6: Exportando archivos separados...{Colors.ENDC}")
        
        separate_results = UnifiedExporter.exportar_archivos_separados(
            lookup_tables=lookup_tables,
            pattern_entities=pattern_entities,
            dynamic_entities_info=dynamic_entities_info,
            output_dir=str(data_dir)
        )
        
        for file_type, success in separate_results.items():
            status = "✅" if success else "❌"
            print(f"  {status} {file_type}")

    # 7. GENERAR STORIES Y RULES
    print(f"{Colors.OKCYAN}FASE 7: Generando stories y rules...{Colors.ENDC}")
    stories_path = data_dir / "stories.yml"
    rules_path = data_dir / "rules.yml"
    
    StoriesGenerator.generar_stories_rules(
        config_data,
        output_path_stories=str(stories_path),
        output_path_rules=str(rules_path)
    )
    validar_yaml(str(stories_path))
    validar_yaml(str(rules_path))
    print(f"{Colors.OKGREEN}Stories y rules generados{Colors.ENDC}")

    # 8. GENERAR DOMAIN.YML
    print(f"{Colors.OKCYAN}FASE 8: Generando domain.yml...{Colors.ENDC}")
    domain_path = project_root / "domain.yml"
    
    DomainGenerator.generar_domain(config=config_data, output_path=str(domain_path))
    validar_yaml(str(domain_path))
    print(f"{Colors.OKGREEN}Domain generado{Colors.ENDC}")

    # 9. RESUMEN PRE-ENTRENAMIENTO
    print(f"\n{Colors.HEADER}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}RESUMEN DE ARCHIVOS GENERADOS{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*80}{Colors.ENDC}")
    
    # Usar rutas absolutas para verificación
    archivos_verificar = [
        data_dir / "nlu.yml",
        data_dir / "synonyms.yml", 
        data_dir / "stories.yml",
        data_dir / "rules.yml",
        project_root / "domain.yml"
    ]
    
    for archivo in archivos_verificar:
        if archivo.exists():
            # Mostrar ruta relativa para mejor legibilidad
            try:
                ruta_relativa = archivo.relative_to(project_root)
                print(f"{Colors.OKGREEN}✅ {ruta_relativa}{Colors.ENDC}")
            except ValueError:
                print(f"{Colors.OKGREEN}✅ {archivo}{Colors.ENDC}")
        else:
            try:
                ruta_relativa = archivo.relative_to(project_root)
                print(f"{Colors.FAIL}❌ {ruta_relativa} - FALTANTE{Colors.ENDC}")
            except ValueError:
                print(f"{Colors.FAIL}❌ {archivo} - FALTANTE{Colors.ENDC}")
    
    # Mostrar estadísticas del sistema unificado
    print(f"\n{Colors.HEADER}ESTADÍSTICAS DEL SISTEMA UNIFICADO:{Colors.ENDC}")
    print(f"  • Lookup entities: {len(lookup_tables)} (desde CSV)")
    print(f"  • Pattern entities: {len(pattern_entities)} (estáticas)")
    print(f"  • Dynamic entities: {len(dynamic_entities_info)} (regex)")
    print(f"  • Total intents: {len(intents)}")
    if ejemplos:
        print(f"  • Training examples: {len(ejemplos)}")

    # 10. ENTRENAR MODELO
    if input(f"\n{Colors.HEADER}¿Entrenar modelo con Rasa? (s/N): {Colors.ENDC}").lower() in ["s", "si", "sí", "y", "yes"]:
        print(f"{Colors.OKCYAN}FASE 10: Entrenando modelo...{Colors.ENDC}")
        
        # Verificar que Rasa esté disponible
        try:
            result = os.system("rasa --version > nul 2>&1" if os.name == 'nt' else "rasa --version > /dev/null 2>&1")
            if result != 0:
                print(f"{Colors.FAIL}❌ Rasa no está instalado o no está en PATH{Colors.ENDC}")
                return
        except:
            print(f"{Colors.FAIL}❌ Error verificando instalación de Rasa{Colors.ENDC}")
            return
        
        # Cambiar al directorio del proyecto para entrenar
        original_dir = Path.cwd()
        try:
            os.chdir(project_root)
            print(f"{Colors.OKCYAN}Iniciando entrenamiento con Rasa desde {project_root}...{Colors.ENDC}")
            result = os.system("rasa train")
            
            if result == 0:
                print(f"{Colors.OKGREEN}✅ Entrenamiento completado exitosamente{Colors.ENDC}")
                
                # Verificar modelo generado
                models_dir = project_root / "models"
                if models_dir.exists():
                    model_files = list(models_dir.glob("*.tar.gz"))
                    if model_files:
                        latest_model = max(model_files, key=lambda x: x.stat().st_mtime)
                        print(f"{Colors.OKGREEN}Modelo generado: {latest_model.name}{Colors.ENDC}")
                    else:
                        print(f"{Colors.WARNING}⚠️ No se encontraron archivos de modelo{Colors.ENDC}")
            else:
                print(f"{Colors.FAIL}❌ Error durante el entrenamiento{Colors.ENDC}")
        finally:
            # Volver al directorio original
            os.chdir(original_dir)
    else:
        print(f"{Colors.WARNING}Entrenamiento omitido{Colors.ENDC}")

    # 11. FINALIZACIÓN
    print(f"\n{Colors.HEADER}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}PROCESO COMPLETADO{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*80}{Colors.ENDC}")
    
    print(f"{Colors.OKGREEN}Sistema unificado funcionando correctamente.{Colors.ENDC}")
    print(f"{Colors.OKBLUE}El agente tiene acceso a:{Colors.ENDC}")
    print(f"  • Todas las lookup tables (CSV + patterns)")
    print(f"  • Todos los regex patterns para entidades dinámicas") 
    print(f"  • Sinónimos automáticos generados")
    print(f"  • Ejemplos de entrenamiento completos")
    
    if input(f"\n{Colors.HEADER}¿Mostrar información detallada del sistema? (s/N): {Colors.ENDC}").lower() in ["s", "si", "sí", "y", "yes"]:
        mostrar_info_detallada(project_root)

def mostrar_info_detallada(project_root: Path):
    """Muestra información detallada del sistema unificado"""
    print(f"\n{Colors.HEADER}INFORMACIÓN DETALLADA DEL SISTEMA{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*50}{Colors.ENDC}")
    
    # Información de entidades disponibles
    info = UnifiedEntityManager.obtener_entidades_disponibles()
    
    print(f"{Colors.OKCYAN}ENTIDADES LOOKUP (desde CSV):{Colors.ENDC}")
    for entity in info.get("lookup_entities", []):
        print(f"  • {entity}")
    
    print(f"\n{Colors.OKCYAN}ENTIDADES PATTERN (estáticas):{Colors.ENDC}")
    for entity in info.get("pattern_entities", []):
        print(f"  • {entity}")
    
    print(f"\n{Colors.OKCYAN}ENTIDADES DYNAMIC (regex):{Colors.ENDC}")
    for entity in info.get("dynamic_entities", []):
        print(f"  • {entity}")
    
    print(f"\n{Colors.OKGREEN}Total de entidades: {info.get('total_entities', 0)}{Colors.ENDC}")
    
    # Verificar archivos clave del sistema con rutas absolutas
    print(f"\n{Colors.OKCYAN}ARCHIVOS DEL SISTEMA:{Colors.ENDC}")
    archivos_sistema = [
        project_root / "bot" / "data" / "entities.yml",
        project_root / "bot" / "data" / "entities_regex.yml", 
        project_root / "context" / "context_config.yml"
    ]
    
    for archivo in archivos_sistema:
        if archivo.exists():
            try:
                ruta_relativa = archivo.relative_to(project_root)
                print(f"  ✅ {ruta_relativa}")
            except ValueError:
                print(f"  ✅ {archivo}")
        else:
            try:
                ruta_relativa = archivo.relative_to(project_root)
                print(f"  ❌ {ruta_relativa} - FALTANTE")
            except ValueError:
                print(f"  ❌ {archivo} - FALTANTE")
                
    # Mostrar directorio de trabajo actual
    print(f"\n{Colors.OKCYAN}INFORMACIÓN DE RUTAS:{Colors.ENDC}")
    print(f"  • Directorio del proyecto: {project_root}")
    print(f"  • Directorio actual: {Path.cwd()}")
    print(f"  • Directorio de datos: {project_root / 'data'}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}Proceso interrumpido por el usuario{Colors.ENDC}")
    except Exception as e:
        print(f"\n{Colors.FAIL}❌ Error inesperado: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()