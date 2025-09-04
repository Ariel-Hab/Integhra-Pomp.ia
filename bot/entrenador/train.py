# train.py
import os
from pathlib import Path
from bot.entrenador.data_generator.domain_generator import DomainGenerator
from bot.entrenador.data_generator.nlu_generator import NLUGenerator
from bot.entrenador.data_generator.stories_generator import StoriesGenerator
from scripts.config_loader import ConfigLoader
from exporter import exportar_yaml, exportar_synonyms_a_yaml, generar_synonyms_from_list, exportar_lookup_tables, validar_yaml
from bot.entrenador.importer import generar_imports

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

def main():
    # -------------------------
    # Crear carpeta data
    # -------------------------
    Path("data").mkdir(exist_ok=True)
    nlu_path = "data/nlu.yml"
    lookup_path = "data/lookup_tables.yml"
    synonyms_path = "data/synonyms.yml"

    print(f"{Colors.OKBLUE}🗂 Creando carpeta 'data' y preparando paths...{Colors.ENDC}")

    # -------------------------
    # 1. Generar lookup tables y entidades por producto
    # -------------------------
    print(f"{Colors.OKCYAN}📦 Generando lookup tables y entidades...{Colors.ENDC}")
    lookup, entidades_por_producto = generar_imports(data_dir="data")
    exportar_lookup_tables(lookup, lookup_path)
    validar_yaml(lookup_path)
    print(f"{Colors.OKGREEN}✅ Lookup tables listas{Colors.ENDC}")

    # -------------------------
    # 2. Cargar configuración de intents
    # -------------------------
    print(f"{Colors.OKCYAN}⚙️  Cargando configuración de intents...{Colors.ENDC}")
    config_data = ConfigLoader.cargar_config()
    intents = config_data["intents"]
    fallback = config_data.get("fallback", {})
    print(f"{Colors.OKGREEN}✅ Configuración cargada{Colors.ENDC}")

    # -------------------------
    # Preguntar si generar nuevos ejemplos NLU
    # -------------------------
    if input(f"{Colors.HEADER}¿Generar nuevos ejemplos NLU? (s/N): {Colors.ENDC}").lower() in ["s", "si", "sí", "y", "yes"]:
        print(f"{Colors.OKCYAN}🟢 Generando ejemplos NLU...{Colors.ENDC}")
        ejemplos = NLUGenerator.generar_ejemplos(intents, lookup, n_por_intent=500)
        exportar_yaml(ejemplos, nlu_path)
        validar_yaml(nlu_path)
        print(f"{Colors.OKGREEN}✅ Ejemplos NLU generados y validados{Colors.ENDC}")
    else:
        print(f"{Colors.WARNING}⚪ Se mantienen los ejemplos NLU existentes{Colors.ENDC}")

    # -------------------------
    # 3. Generar stories y rules
    # -------------------------
    print(f"{Colors.OKCYAN}📖 Generando stories y rules...{Colors.ENDC}")
    StoriesGenerator.generar_stories_rules(
        config_data,
        output_path_stories="data/stories.yml",
        output_path_rules="data/rules.yml"
    )
    print(f"{Colors.OKGREEN}✅ Stories y rules generados{Colors.ENDC}")

    # -------------------------
    # 4. Generar domain.yml
    # -------------------------
    print(f"{Colors.OKCYAN}📦 Generando domain.yml...{Colors.ENDC}")
    DomainGenerator.generar_domain(config=config_data, output_path="domain.yml")
    print(f"{Colors.OKGREEN}✅ Domain generado{Colors.ENDC}")

    # -------------------------
    # 5. Entrenar modelo
    # -------------------------
    if input(f"{Colors.HEADER}¿Entrenar modelo? (s/N): {Colors.ENDC}").lower() in ["s", "si", "sí", "y", "yes"]:
        print(f"{Colors.OKCYAN}🚀 Entrenando modelo...{Colors.ENDC}")
        os.system("rasa train")
        print(f"{Colors.OKGREEN}✅ Entrenamiento completado{Colors.ENDC}")
    else:
        print(f"{Colors.WARNING}⚪ Se saltó el entrenamiento{Colors.ENDC}")

if __name__ == "__main__":
    main()
