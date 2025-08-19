# data_generator.py
import yaml
from pathlib import Path
import random
from collections import defaultdict
from typing import Dict, Any, List, Tuple
import re
from utils import aplicar_perturbacion
from bot.entrenador.importer import anotar_entidades, generar_entidades_por_producto

INTENTS_LIMITADOS = {"fuera_aplicacion"}
MAX_EJEMPLOS_LIMITADOS = 20


# -----------------------------
# Cargar configuración de intents
# -----------------------------
def cargar_config(path="intents_config.yml") -> Dict[str, Any]:
    path_obj = Path(path)
    if not path_obj.is_absolute():
        path_obj = (Path(__file__).parent.parent.parent / path_obj).resolve()
    if not path_obj.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {path_obj}")
    with open(path_obj, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {i["name"]: i for i in data["intents"]}


# -----------------------------
# Generar domain.yml
# -----------------------------
def generar_domain_yaml(config: dict, output_path=None) -> None:
    # Si no se indica ruta, se genera en la raíz del proyecto
    if output_path is None:
        output_path = Path.cwd() / "domain.yml"

    # Entidades
    entidades = sorted({e for i in config.values() for e in i.get("entities", [])})
    
    # Slots
    slots = {e: {"type": "text", "mappings": [{"type": "from_entity", "entity": e}]} for e in entidades}
    slots["ultimo_intent"] = {"type": "text", "mappings": [{"type": "from_text"}]}
    
    # Intents y actions
    intents = list(config.keys())
    actions = sorted({i["action"] for i in config.values()})
    
    # Responses
    responses = {f"utter_{i}": [{"text": f"Respuesta para {i}"}] for i in intents}
    
    # Forms (vacíos por defecto, con required_slots como lista)
    forms = {f"{i}_form": {"required_slots": []} for i in intents if "form" in i.lower()}

    # Siempre incluir validate_busqueda_form si se usa
    if any(i["action"] == "action_busqueda" for i in config.values()):
        forms["validate_busqueda_form"] = {"required_slots": []}

    # Armado del domain
    domain = {
        "version": "3.1",
        "intents": intents,
        "entities": entidades,
        "slots": slots,
        "forms": forms,
        "responses": responses,
        "actions": actions
    }

    # Asegurarse que la carpeta exista
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    # Guardar YAML
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(domain, f, allow_unicode=True, sort_keys=False)
    
    print(f"domain.yml generado en: {output_path}")


# -----------------------------
# Generar stories y rules
# -----------------------------
def generar_stories_rules(config: dict, output_path_stories="data/stories.yml", output_path_rules="data/rules.yml") -> None:
    stories_yaml = {"version": "3.1", "stories": []}
    rules_yaml = {"version": "3.1", "rules": []}

    for intent_name, intent_data in config.items():
        steps_story = [{"intent": intent_name}]
        steps_rule = [{"intent": intent_name}]
        if intent_data["action"] == "action_busqueda":
            steps_story += [{"active_loop": "validate_busqueda_form"}, {"active_loop": None}, {"action": "action_busqueda"}]
            steps_rule += [{"active_loop": "validate_busqueda_form"}]
        else:
            steps_story += [{"action": intent_data["action"]}]
            steps_rule += [{"action": intent_data["action"]}]

        stories_yaml["stories"].append({"story": f"story_{intent_name}", "steps": steps_story})
        rules_yaml["rules"].append({"rule": f"rule_{intent_name}", "steps": steps_rule})

    for path, data in [(output_path_stories, stories_yaml), (output_path_rules, rules_yaml)]:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)


# -----------------------------
# Generar ejemplos NLU
# -----------------------------
def generar_fuera_aplicacion() -> List[tuple]:
    ejemplos = ["Hola", "Gracias", "¿Cómo estás?", "Nos vemos", "¿Querés volver a productos y ofertas?"]
    return [(e, "fuera_aplicacion") for e in ejemplos]


def mezclar_listas_entidades(entidades_por_producto: Dict[str, Dict[str, str]], campo: str, max_valores=4) -> List[str]:
    valores = list({e[campo] for e in entidades_por_producto.values() if e.get(campo)})
    if not valores:
        return []
    random.shuffle(valores)
    # Permitir devolver más de un valor para frases múltiples
    num_valores = random.randint(1, min(max_valores, len(valores)))
    return valores[:num_valores]


def generar_frase(template: str, campos: dict) -> str:
    """
    Reemplaza placeholders {key} en el template con valores de campos.
    Si algún placeholder obligatorio no tiene valor, devuelve None.
    """
    resultado = template
    for m in re.finditer(r"\{(\w+)\}", template):
        key = m.group(1)
        valores = campos.get(key)
        if not valores:
            return None
        if isinstance(valores, list):
            # Mezclar múltiples entidades en la misma frase
            valor_str = " y ".join(str(v) for v in valores)
        else:
            valor_str = str(valores)
        resultado = resultado.replace(f"{{{key}}}", valor_str, 1)
    return resultado


# Valores aleatorios sensatos
VALORES_ALEATORIOS = {
    "cantidad": lambda: str(random.randint(1, 20)),
    "dosis": lambda: f"{random.randint(1, 3)} pastillas",
    "cantidad_descuento": lambda: f"{random.randint(5, 50)}",
    "cantidad_stock": lambda: str(random.randint(1, 100)),
    "fecha": lambda: f"{random.randint(1,28)}/{random.randint(1,12)}/2025",
    "dia": lambda: random.choice(["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"])
}

ENTIDADES_LOOKUP = {"producto", "proveedor", "compuesto", "categoria"}

def generar_ejemplos_completos(
    config: Dict[str, Any],
    lookup: Dict[str, List[str]],
    synonyms: Dict[str, List[str]] = None,
    max_total=500,
    max_por_intent=50,
    INTENTS_LIMITADOS=None
) -> List[tuple]:

    if INTENTS_LIMITADOS is None:
        INTENTS_LIMITADOS = ["fuera_aplicacion"]

    if synonyms is None:
        synonyms = {}

    ejemplos = []

    # Contador para intents limitados
    contador_limitados = defaultdict(int)
    templates_sin_reemplazo = {i: config[i]["templates"][:] for i in INTENTS_LIMITADOS if i in config}

    while len(ejemplos) < max_total:
        for intent_name, intent_data in config.items():
            if len(ejemplos) >= max_total:
                break

            # Seleccionar template
            templates = intent_data["templates"]
            if intent_name in INTENTS_LIMITADOS:
                if contador_limitados[intent_name] >= max_por_intent or not templates_sin_reemplazo.get(intent_name):
                    continue
                template = templates_sin_reemplazo[intent_name].pop(0)
                contador_limitados[intent_name] += 1
            else:
                template = random.choice(templates)

            # Reemplazar sinónimos
            for key, valores in synonyms.items():
                template = re.sub(rf"\{{{key}\}}", lambda _: random.choice(valores), template)

            # Recolectar valores para placeholders
            campos = {}
            for e in intent_data.get("entities", []):
                if e in ENTIDADES_LOOKUP:
                    posibles = lookup.get(e, [])
                    if posibles:
                        num_valores = random.randint(1, min(3, len(posibles)))
                        campos[e] = random.sample(posibles, num_valores)
                    else:
                        campos[e] = []
                else:
                    # Generar aleatoriamente valores sensatos
                    campos[e] = [VALORES_ALEATORIOS[e]()] if e in VALORES_ALEATORIOS else []

            # Generar frase reemplazando placeholders de manera segura
            texto = template
            skip_frase = False
            for k, vals in campos.items():
                if vals:
                    if len(vals) == 1:
                        reemplazo = vals[0]
                    elif len(vals) == 2:
                        reemplazo = " y ".join(vals)
                    else:
                        reemplazo = ", ".join(vals[:-1]) + " y " + vals[-1]
                    texto = texto.replace(f"{{{k}}}", reemplazo)
                else:
                    # Para placeholders vacíos, si es intente con entidades obligatorias, saltar
                    texto = texto.replace(f"{{{k}}}", "")

            texto = texto.strip()
            if not texto:
                continue

            # Limpiar signos redundantes
            texto = re.sub(r"\?{2,}", "?", texto)
            texto = re.sub(r"\.{2,}", ".", texto)

            # Anotar entidades
            args_entidades = {k: campos.get(k, None) for k in [
                "producto", "proveedor", "cantidad", "dosis", "compuesto",
                "categoria", "dia", "fecha", "cantidad_stock", "cantidad_descuento"
            ]}
            texto = anotar_entidades(texto, **args_entidades)

            # Aplicar perturbación
            texto = aplicar_perturbacion(texto)

            ejemplos.append((texto, intent_name))

            # Ejemplos aleatorios de frases simples (sin entidades)
            if random.random() < 0.1 and intent_name not in INTENTS_LIMITADOS:
                texto_simple = random.choice([
                    "mostrá ofertas",
                    "quiero productos",
                    "ver qué hay",
                    "decime promociones"
                ])
                ejemplos.append((texto_simple, intent_name))

            if len(ejemplos) >= max_total:
                break

    print(f"✅ Generados {len(ejemplos)} ejemplos NLU")
    return ejemplos


