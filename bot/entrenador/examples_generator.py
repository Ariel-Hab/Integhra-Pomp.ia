import random
from collections import defaultdict
from typing import Dict, Any, List, Tuple
from templates_generator import generar_frase
from utils import aplicar_perturbacion
from bot.entrenador.importer import anotar_entidades

INTENTS_LIMITADOS = {"fuera_aplicacion"}
MAX_EJEMPLOS_LIMITADOS = 20

def generar_fuera_aplicacion() -> List[Tuple[str,str]]:
    ejemplos = ["Hola","Gracias","¿Cómo estás?","Nos vemos"]
    return [(e,"fuera_aplicacion") for e in ejemplos]

def mezclar_listas_entidades(entidades_por_producto, campo, max_valores=4):
    valores = list({e[campo] for e in entidades_por_producto.values() if e.get(campo)})
    if not valores: return []
    random.shuffle(valores)
    cantidad = min(max_valores,len(valores))
    return valores[:cantidad]

def generar_ejemplos_completos(
    config: Dict[str, Any],
    lookup: Dict[str,List[str]],
    entidades_por_producto: Dict[str, Dict[str,str]],
    max_total=500
) -> List[Tuple[str,str]]:

    ejemplos = generar_fuera_aplicacion()[:MAX_EJEMPLOS_LIMITADOS]

    if not entidades_por_producto: 
        return ejemplos

    contador_limitados = defaultdict(int)
    templates_sin_reemplazo = {i: config[i]["templates"][:] for i in INTENTS_LIMITADOS}

    for _, _ in entidades_por_producto.items():
        if len(ejemplos) >= max_total: break
        for intent_name, intent_data in config.items():
            if len(ejemplos) >= max_total: break
            templates = intent_data["templates"]
            if intent_name in INTENTS_LIMITADOS:
                if contador_limitados[intent_name]>=MAX_EJEMPLOS_LIMITADOS or not templates_sin_reemplazo[intent_name]:
                    continue
                template = templates_sin_reemplazo[intent_name].pop(0)
                contador_limitados[intent_name]+=1
            else:
                template = random.choice(templates)

            campos = {e: mezclar_listas_entidades(entidades_por_producto,e) for e in intent_data.get("entities",[])}
            texto = generar_frase(template, intent_name, campos)
            texto = aplicar_perturbacion(texto)
            texto = anotar_entidades(texto, **campos)
            ejemplos.append((texto,intent_name))

    return ejemplos
