import os
from pathlib import Path
from random import random as rnd
from generator import generar_ejemplos, generar_fuera_aplicacion
from exporter import exportar_synonyms_a_yaml, exportar_yaml, generar_synonyms_from_list, validar_yaml, exportar_lookup_tables
from lookup import generar_lookup_tables

#token: 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

def leer_archivo(path):
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def main():
    Path("data").mkdir(exist_ok=True)

    generar_ejemplos_input = input("¿Querés generar nuevos ejemplos? (s/N): ").strip().lower()
    generar_ejemplos_flag = generar_ejemplos_input in ["s", "sí", "si", "y", "yes"]

    ejemplos = []
    nlu_path = "data/nlu.yml"

    if generar_ejemplos_flag:
        cant = input("¿Cuántos ejemplos querés generar? (ej: 100): ").strip()
        try:
            cant = int(cant)
        except ValueError:
            print("❌ Número inválido. Se usará 100 por defecto.")
            cant = 100
        ejemplos_buscar = generar_ejemplos(max_total=cant)
        ejemplos_fuera = generar_fuera_aplicacion()

        todos_los_ejemplos = ejemplos_buscar + ejemplos_fuera
        # rnd.shuffle(todos_los_ejemplos)
        exportar_yaml(todos_los_ejemplos, nlu_path)
        print(f"✅ Generados y exportados {len(todos_los_ejemplos)} ejemplos nuevos.")
    else:
        print("ℹ️ Conservando ejemplos existentes en", nlu_path)

    validar_yaml(nlu_path)

    regenerar_lookup = input("¿Querés regenerar las lookup y synonyms tables? (s/N): ").strip().lower()
    if regenerar_lookup in ["s", "sí", "si", "y", "yes"]:
        tablas = generar_lookup_tables("data")
        synonyms = generar_synonyms_from_list(tablas["producto"])
        exportar_synonyms_a_yaml(synonyms)
        exportar_lookup_tables(tablas, nlu_path)
        print("✅ Lookup y synonyms tables regeneradas y exportadas.")
    else:
        print("ℹ️ Conservando lookup y synonyms tables existentes.")

    entrenar = input("¿Querés entrenar el modelo ahora? (s/N): ").strip().lower()
    if entrenar in ["s", "sí", "si", "y", "yes"]:
        print("🚀 Entrenando el agente con 'rasa train'...")
        resultado = os.system("rasa train")
        if resultado == 0:
            print("✅ Entrenamiento finalizado con éxito.")
        else:
            print("❌ Error al entrenar el agente.")
    else:
        print("ℹ️ No se entrenó el modelo. Proceso terminado.")

if __name__ == "__main__":
    main()
