import re
import yaml
from collections import defaultdict
import unidecode

def generar_synonyms_from_list(canonicos):
    """
    Dado un listado de nombres canónicos, genera un dict listo para exportar a synonyms.yml.
    Incluye variantes: original, lowercase, sin acentos (unidecode).
    """
    synonyms = {"version": "3.1", "nlu": []}
    
    for item in canonicos:
        variantes = set()
        variantes.add(item)  # original
        variantes.add(item.lower())
        variantes.add(unidecode.unidecode(item.lower()))
        
        # Quitamos el nombre canonico de la lista de variantes
        ejemplos = [v for v in variantes if v != item]
        
        if ejemplos:
            # Formatear ejemplos con guiones y saltos de línea para YAML
            ejemplos_str = "\n".join(f"- {e}" for e in ejemplos)
            
            synonyms["nlu"].append({
                "synonym": item,
                "examples": ejemplos_str
            })
    
    return synonyms

def exportar_synonyms_a_yaml(synonyms, path="data/synonyms.yml"):
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(synonyms, f, allow_unicode=True, sort_keys=False)


def limpiar_yaml(ejemplo):
    ejemplo = ejemplo.replace('"', '\\"')
    ejemplo = ejemplo.replace('\n', ' ').replace('\r', '')
    ejemplo = re.sub(r'\s{2,}', ' ', ejemplo)
    return ejemplo.strip()

def exportar_yaml(ejemplos, output_path="data/nlu.yml"):
    intents = defaultdict(list)
    for texto, intent in ejemplos:
        intents[intent].append(texto)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write('version: "3.1"\n\nnlu:\n')
        for intent, ejemplos_intent in intents.items():
            f.write(f'- intent: {intent}\n  examples: |\n')
            for ejemplo in ejemplos_intent:
                clean = limpiar_yaml(ejemplo)
                f.write(f'    - "{clean}"\n')
            f.write("\n")

def validar_yaml(path="data/nlu.yml"):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            yaml.safe_load(f)
        print("✅ YAML válido.")
    except yaml.YAMLError as e:
        print("❌ Error en YAML:", e)

def exportar_lookup_tables(lookup_tables, output_path="data/nlu.yml"):
    with open(output_path, "a", encoding="utf-8") as f:
        for entity, ejemplos in lookup_tables.items():
            if not ejemplos:
                continue
            f.write(f'- lookup: {entity}\n  examples: |\n')
            for e in ejemplos:
                e = str(e).strip()
                e = e.replace('\n', ' ').replace('\r', '')
                e = e.replace('"', "'")  # evitar errores de comillas
                e = re.sub(r"\s{2,}", " ", e)  # elimina espacios duplicados

                if ":" in e:
                    print(f"⚠️ Posible problema en entidad '{entity}': {e}")
                    continue  # saltear

                if e:
                    f.write(f'    - {e}\n')
            f.write('\n')