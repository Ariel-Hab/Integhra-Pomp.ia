import yaml
import json
import re
from collections import defaultdict

# Archivos Rasa
NLU_FILE = "data/nlu.yml"
DOMAIN_FILE = "domain.yml"
RULES_FILE = "data/rules.yml"
STORIES_FILE = "data/stories.yml"
OUTPUT_FILE = "contexto_agente.json"


def load_yaml(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        print(f"⚠️ Archivo no encontrado: {file_path}")
        return {}
    except Exception as e:
        print(f"❌ Error leyendo {file_path}: {e}")
        return {}


def parse_nlu(nlu_data):
    intents_data = defaultdict(list)

    for item in nlu_data.get("nlu", []):
        intent = item.get("intent")
        examples = item.get("examples")
        if intent and examples:
            for ex in examples.split("\n"):
                ex = ex.strip("- ").strip()
                if ex:
                    intents_data[intent].append(ex)

    parsed = {}
    for intent, examples in intents_data.items():
        entidades_info = []
        for ex in examples:
            # Regex para detectar entidades con o sin roles/grupos
            matches = re.finditer(r"\[(.*?)\]\((\w+)(?:\{(.*?)\})?\)", ex)
            for m in matches:
                entidad = m.group(2)
                meta = m.group(3)
                rol, grupo = None, None
                if meta:
                    try:
                        meta_dict = json.loads("{" + meta + "}")
                        rol = meta_dict.get("role")
                        grupo = meta_dict.get("group")
                    except Exception:
                        pass
                entidades_info.append({
                    "texto": m.group(1),
                    "entidad": entidad,
                    "role": rol,
                    "group": grupo
                })

        parsed[intent] = {
            "ejemplos": len(examples),
            "ejemplos_texto": examples,
            "entidades": entidades_info
        }
    return parsed


def parse_domain(domain_data):
    entities_raw = domain_data.get("entities", [])
    entities = []
    entities_info = {}

    for e in entities_raw:
        if isinstance(e, str):
            entities.append(e)
        elif isinstance(e, dict):
            name = list(e.keys())[0]
            entities.append(name)
            entities_info[name] = e[name]  # guarda roles/grupos si existen

    return {
        "intents": [i if not isinstance(i, dict) else list(i.keys())[0] for i in domain_data.get("intents", [])],
        "entities": entities,
        "entities_info": entities_info,  # <- roles y groups definidos
        "slots": domain_data.get("slots", {}),
        "responses": domain_data.get("responses", {}),
        "actions": domain_data.get("actions", []),
    }


def parse_rules(rules_data):
    return rules_data.get("rules", [])


def parse_stories(stories_data):
    return stories_data.get("stories", [])


def compare_nlu_domain(nlu, domain):
    report = {
        "intents_en_domain_sin_ejemplos": [],
        "intents_en_nlu_no_declarados": [],
        "entidades_en_domain_no_usadas": [],
        "entidades_usadas_no_declaradas": [],
        "roles_en_domain_no_usados": {},
        "roles_usados_no_declarados": {},
        "groups_en_domain_no_usados": {},
        "groups_usados_no_declarados": {}
    }

    # Intents
    intents_nlu = set(nlu.keys())
    intents_domain = set(domain["intents"])
    report["intents_en_domain_sin_ejemplos"] = list(intents_domain - intents_nlu)
    report["intents_en_nlu_no_declarados"] = list(intents_nlu - intents_domain)

    # Entidades
    entidades_nlu = set()
    roles_nlu = defaultdict(set)
    groups_nlu = defaultdict(set)

    for intent, data in nlu.items():
        for ent in data["entidades"]:
            entidades_nlu.add(ent["entidad"])
            if ent["role"]:
                roles_nlu[ent["entidad"]].add(ent["role"])
            if ent["group"]:
                groups_nlu[ent["entidad"]].add(ent["group"])

    entidades_domain = set(domain["entities"])
    report["entidades_en_domain_no_usadas"] = list(entidades_domain - entidades_nlu)
    report["entidades_usadas_no_declaradas"] = list(entidades_nlu - entidades_domain)

    # Roles y Groups
    for entidad, meta in domain["entities_info"].items():
        domain_roles = set(meta.get("roles", []))
        domain_groups = set(meta.get("groups", []))

        usados_roles = roles_nlu.get(entidad, set())
        usados_groups = groups_nlu.get(entidad, set())

        no_usados_roles = domain_roles - usados_roles
        no_usados_groups = domain_groups - usados_groups
        extra_roles = usados_roles - domain_roles
        extra_groups = usados_groups - domain_groups

        if no_usados_roles:
            report["roles_en_domain_no_usados"][entidad] = list(no_usados_roles)
        if extra_roles:
            report["roles_usados_no_declarados"][entidad] = list(extra_roles)

        if no_usados_groups:
            report["groups_en_domain_no_usados"][entidad] = list(no_usados_groups)
        if extra_groups:
            report["groups_usados_no_declarados"][entidad] = list(extra_groups)

    return report


def main():
    # Cargar datos
    nlu_data = load_yaml(NLU_FILE)
    domain_data = load_yaml(DOMAIN_FILE)
    rules_data = load_yaml(RULES_FILE)
    stories_data = load_yaml(STORIES_FILE)

    # Parsear
    nlu = parse_nlu(nlu_data)
    domain = parse_domain(domain_data)
    rules = parse_rules(rules_data)
    stories = parse_stories(stories_data)

    # Comparar NLU vs Domain
    inconsistencias = compare_nlu_domain(nlu, domain)

    # Armar contexto completo
    context = {
        "nlu": nlu,
        "domain": domain,
        "rules": rules,
        "stories": stories,
        "inconsistencias": inconsistencias,
    }

    # Guardar en JSON
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(context, f, indent=2, ensure_ascii=False)

    print(f"✅ Contexto del agente guardado en {OUTPUT_FILE}")
    print("📊 Resumen de inconsistencias:")
    print(json.dumps(inconsistencias, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
