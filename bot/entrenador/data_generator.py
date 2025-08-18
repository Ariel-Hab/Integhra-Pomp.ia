import yaml
from pathlib import Path

def cargar_config(path="intents_config.yml"):
    path_obj = Path(path)
    if not path_obj.is_absolute():
        # relativo a este archivo
        path_obj = (Path(__file__).parent / path_obj).resolve()
    if not path_obj.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {path_obj}")
    with open(path_obj, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {i["name"]: i for i in data["intents"]}


def generar_domain_yaml(config: dict, output_path="data/domain.yml"):
    entidades = sorted({e for i in config.values() for e in i.get("entities",[])})
    slots = {e: {"type":"text","mappings":[{"type":"from_entity","entity":e}]} for e in entidades}
    slots["ultimo_intent"] = {"type":"text","mappings":[{"type":"from_text"}]}

    intents = list(config.keys())
    actions = sorted({i["action"] for i in config.values()})
    responses = {f"utter_{i}":[{"text":f"Respuesta para {i}"}] for i in intents}

    domain = {
        "version":"3.1",
        "intents": intents,
        "entities": entidades,
        "slots": slots,
        "forms": {},
        "responses": responses,
        "actions": actions
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path,"w",encoding="utf-8") as f: yaml.dump(domain,f,allow_unicode=True,sort_keys=False)

def generar_stories_rules(config: dict, output_path_stories="data/stories.yml", output_path_rules="data/rules.yml"):
    stories_yaml = {"version":"3.1","stories":[]}
    rules_yaml = {"version":"3.1","rules":[]}
    for intent_name, intent_data in config.items():
        steps_story = [{"intent":intent_name}]
        steps_rule = [{"intent":intent_name}]
        if intent_data["action"] == "action_busqueda":
            steps_story += [{"active_loop":"validate_busqueda_form"},{"active_loop":None},{"action":"action_busqueda"}]
            steps_rule += [{"active_loop":"validate_busqueda_form"}]
        else:
            steps_story += [{"action":intent_data["action"]}]
            steps_rule += [{"action":intent_data["action"]}]

        stories_yaml["stories"].append({"story":f"story_{intent_name}", "steps":steps_story})
        rules_yaml["rules"].append({"rule":f"rule_{intent_name}", "steps":steps_rule})

    for path,data in [(output_path_stories,stories_yaml),(output_path_rules,rules_yaml)]:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path,"w",encoding="utf-8") as f: yaml.dump(data,f,allow_unicode=True,sort_keys=False)
