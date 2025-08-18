# train.py
import os
from pathlib import Path
from exporter import exportar_yaml, exportar_synonyms_a_yaml, generar_synonyms_from_list, exportar_lookup_tables, validar_yaml
from bot.entrenador.examples_generator import generar_ejemplos_completos
from bot.entrenador.data_generator import generar_domain_yaml, generar_stories_rules, cargar_config
from bot.entrenador.importer import generar_imports

def main():
    # -------------------------
    # Crear carpeta data
    # -------------------------
    Path("data").mkdir(exist_ok=True)
    nlu_path = "data/nlu.yml"
    lookup_path = "data/lookup_tables.yml"
    synonyms_path = "data/synonyms.yml"

    # -------------------------
    # 1. Generar lookup tables y entidades por producto
    # -------------------------
    lookup, entidades_por_producto = generar_imports(data_dir="data")
    exportar_lookup_tables(lookup, lookup_path)
    validar_yaml(lookup_path)

    # -------------------------
    # 2. Cargar configuración de intents
    # -------------------------
    config = cargar_config("intents_config.yml")

    # -------------------------
    # 3. Generar ejemplos NLU
    # -------------------------
    ejemplos = generar_ejemplos_completos(config, lookup, entidades_por_producto, max_total=500)
    exportar_yaml(ejemplos, nlu_path)
    validar_yaml(nlu_path)

    # -------------------------
    # 4. Generar synonyms
    # -------------------------
    productos = lookup.get("producto", [])
    synonyms = generar_synonyms_from_list(productos)
    exportar_synonyms_a_yaml(synonyms, synonyms_path)
    validar_yaml(synonyms_path)

    # -------------------------
    # 5. Generar stories y rules
    # -------------------------
    generar_stories_rules(config, output_path_stories="data/stories.yml", output_path_rules="data/rules.yml")

    # -------------------------
    # 6. Generar domain.yml
    # -------------------------
    generar_domain_yaml(config, output_path="data/domain.yml")

    # -------------------------
    # 7. Entrenar modelo (opcional)
    # -------------------------
    if input("¿Entrenar modelo? (s/N): ").lower() in ["s", "si", "sí", "y", "yes"]:
        os.system("rasa train")
        print("✅ Entrenamiento completado.")

if __name__ == "__main__":
    main()
