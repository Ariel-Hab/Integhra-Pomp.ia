#!/usr/bin/env python3
"""
train.py - Entrenador RASA Optimizado
Orquesta la generación de datos, stories y dominio sin duplicar funcionalidades.
"""

import os
import sys
from pathlib import Path
from typing import Dict
from bot.entrenador.data_generator.domain_generator import DomainGenerator
from bot.entrenador.data_generator.nlu_generator import NLUGenerator
from bot.entrenador.data_generator.stories_generator import StoriesGenerator
from scripts.config_loader import ConfigLoader
from bot.entrenador.importer import generar_imports_unificado
from bot.entrenador.exporter import UnifiedExporter, validar_yaml

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    BOLD = '\033[1m'
    ENDC = '\033[0m'

def get_project_paths() -> Dict[str, Path]:
    """Detecta raíz del proyecto y rutas principales."""
    current_file = Path(__file__).parent.resolve()
    project_root = current_file
    for parent in current_file.parents:
        if (parent / "context").exists() and (parent / "bot").exists():
            project_root = parent
            break
    return {
        "project_root": project_root,
        "context_config": project_root / "context" / "context_config.yml",
        "bot_data": project_root / "bot" / "data",
        "domain_file": project_root / "bot" / "domain.yml"
    }

def main():
    print(f"{Colors.HEADER}🚀 ENTRENADOR RASA OPTIMIZADO{Colors.ENDC}")
    print("="*60)

    try:
        # Paths
        paths = get_project_paths()
        paths["bot_data"].mkdir(parents=True, exist_ok=True)

        print(f"{Colors.OKBLUE}📁 Rutas del proyecto:{Colors.ENDC}")
        print(f"   • Raíz: {paths['project_root']}")
        print(f"   • Config: {paths['context_config']}")
        print(f"   • Data: {paths['bot_data']}")

        # FASE 1: Cargar configuración
        print(f"\n{Colors.OKCYAN}FASE 1: Cargando configuración{Colors.ENDC}")
        config_data = ConfigLoader.cargar_config(str(paths["context_config"]))

        # FASE 2: Generar entidades
        print(f"\n{Colors.OKCYAN}FASE 2: Generando entidades{Colors.ENDC}")
        lookup_tables, pattern_entities, dynamic_entities_info = generar_imports_unificado(
            data_dir=str(paths["bot_data"])
        )
        print(f"{Colors.OKGREEN}✅ Entidades generadas:{Colors.ENDC}")
        print(f"   • Lookup: {len(lookup_tables)}")
        print(f"   • Patterns: {len(pattern_entities)}")
        print(f"   • Dynamic: {len(dynamic_entities_info)}")

        # FASE 3: Generar ejemplos NLU (opcional)
        ejemplos = []
        if input(f"\n{Colors.HEADER}¿Generar ejemplos NLU? (s/N): {Colors.ENDC}").lower() in ["s", "si", "sí", "y", "yes"]:
            print(f"{Colors.OKCYAN}FASE 3: Generando ejemplos NLU{Colors.ENDC}")
            all_entities = {**lookup_tables, **pattern_entities}
            ejemplos = NLUGenerator.generar_ejemplos(
                config=config_data,
                lookup=all_entities,
                synonyms=config_data.get("segments", {}),
                dynamic_entities=dynamic_entities_info,
                n_por_intent=500,
                use_limits_file=True
            )
            print(f"{Colors.OKGREEN}✅ Ejemplos generados: {len(ejemplos)}{Colors.ENDC}")

        # FASE 4: Exportar NLU completo
        print(f"\n{Colors.OKCYAN}FASE 4: Exportando NLU completo{Colors.ENDC}")
        nlu_path = paths["bot_data"] / "nlu.yml"
        if not UnifiedExporter.exportar_nlu_completo(
            ejemplos=ejemplos,
            lookup_tables=lookup_tables,
            pattern_entities=pattern_entities,
            dynamic_entities_info=dynamic_entities_info,
            output_path=str(nlu_path)
        ):
            print(f"{Colors.FAIL}❌ Error exportando NLU{Colors.ENDC}")
            return False
        validar_yaml(str(nlu_path))
        print(f"{Colors.OKGREEN}✅ NLU exportado: {nlu_path}{Colors.ENDC}")

        # FASE 5: Generar sinónimos automáticos
        print(f"\n{Colors.OKCYAN}FASE 5: Generando sinónimos{Colors.ENDC}")
        synonyms_path = paths["bot_data"] / "synonyms.yml"
        UnifiedExporter.exportar_synonyms_desde_lookup(
            lookup_tables=lookup_tables,
            output_path=str(synonyms_path)
        )
        validar_yaml(str(synonyms_path))
        print(f"{Colors.OKGREEN}✅ Sinónimos: {synonyms_path}{Colors.ENDC}")

        # FASE 6: Generar Stories y Rules
        print(f"\n{Colors.OKCYAN}FASE 6: Generando Stories y Rules{Colors.ENDC}")
        stories_path = paths["bot_data"] / "stories.yml"
        rules_path = paths["bot_data"] / "rules.yml"

        if 'flow_groups' not in config_data:
            from bot.entrenador.data_generator.stories_generator import StoriesGeneratorMinimal
            StoriesGeneratorMinimal.generar_stories_rules_minimal(
                config=config_data,
                output_path_stories=str(stories_path),
                output_path_rules=str(rules_path)
            )
        else:
            StoriesGenerator.generar_stories_rules(
                config=config_data,
                output_path_stories=str(stories_path),
                output_path_rules=str(rules_path)
            )
        validar_yaml(str(stories_path))
        validar_yaml(str(rules_path))
        print(f"{Colors.OKGREEN}✅ Stories: {stories_path}{Colors.ENDC}")
        print(f"{Colors.OKGREEN}✅ Rules: {rules_path}{Colors.ENDC}")

        # FASE 7: Generar Domain
        print(f"\n{Colors.OKCYAN}FASE 7: Generando Domain{Colors.ENDC}")
        DomainGenerator.generar_domain(
            config=config_data,
            output_path=str(paths["domain_file"])
        )
        validar_yaml(str(paths["domain_file"]))
        print(f"{Colors.OKGREEN}✅ Domain: {paths['domain_file']}{Colors.ENDC}")

        # FASE 8: Entrenar modelo (opcional)
        if input(f"\n{Colors.HEADER}¿Entrenar modelo con Rasa? (s/N): {Colors.ENDC}").lower() in ["s", "si", "sí", "y", "yes"]:
            print(f"{Colors.OKCYAN}FASE 8: Entrenando modelo{Colors.ENDC}")
            if os.system("rasa --version > /dev/null 2>&1") != 0:
                print(f"{Colors.FAIL}❌ Rasa no está instalado{Colors.ENDC}")
                return False

            original_dir = Path.cwd()
            try:
                os.chdir(paths["project_root"])
                print(f"📍 Entrenando desde: {paths['project_root']}")
                if os.system("rasa train") == 0:
                    print(f"{Colors.OKGREEN}✅ Entrenamiento completado{Colors.ENDC}")
                    models_dir = paths["project_root"] / "models"
                    if models_dir.exists():
                        model_files = list(models_dir.glob("*.tar.gz"))
                        if model_files:
                            latest_model = max(model_files, key=lambda x: x.stat().st_mtime)
                            model_size = latest_model.stat().st_size / (1024 * 1024)
                            print(f"📦 Modelo: {latest_model.name} ({model_size:.1f} MB)")
                else:
                    print(f"{Colors.FAIL}❌ Error durante entrenamiento{Colors.ENDC}")
                    return False
            finally:
                os.chdir(original_dir)

        print(f"\n{Colors.HEADER}🎉 ENTRENAMIENTO COMPLETADO{Colors.ENDC}")
        print("="*60)
        print("✅ Archivos generados en bot/data/:")
        print("   • nlu.yml")
        print("   • synonyms.yml")
        print("   • stories.yml")
        print("   • rules.yml")
        print("   • domain.yml")
        print("="*60)

        return True

    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}⚠️ Entrenamiento cancelado{Colors.ENDC}")
        return False
    except Exception as e:
        import traceback
        print(f"{Colors.FAIL}❌ Error crítico: {e}{Colors.ENDC}")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
