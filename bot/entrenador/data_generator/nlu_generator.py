import random
import re
from typing import Any, Dict, List, Tuple, Optional
from collections import defaultdict

from bot.entrenador.importer import anotar_entidades
from bot.entrenador.utils import aplicar_perturbacion

VALORES_ALEATORIOS = {
    "cantidad": lambda: str(random.randint(1, 20)),
    "dosis": lambda: f"{random.randint(1, 3)} pastillas",
    "cantidad_descuento": lambda: str(random.randint(5, 50)),
    "cantidad_stock": lambda: str(random.randint(1, 100)),
    "fecha": lambda: f"{random.randint(1,28)}/{random.randint(1,12)}/2025",
    "dia": lambda: random.choice(["lunes","martes","miércoles","jueves","viernes","sábado","domingo"])
}

ENTIDADES_LOOKUP = {"producto", "proveedor", "compuesto", "categoria"}

class NLUGenerator:

    @staticmethod
    def generar_frase(template: str, campos: dict) -> str:
        resultado = template
        for m in re.finditer(r"\{(\w+)\}", template):
            key = m.group(1)
            valores = campos.get(key)
            if not valores:
                return None
            if isinstance(valores, list):
                valor_str = " y ".join(str(v) for v in valores)
            else:
                valor_str = str(valores)
            resultado = resultado.replace(f"{{{key}}}", valor_str, 1)
        return resultado

    @staticmethod
    def generar_ejemplos(
        config: Dict[str, Any],
        lookup: Dict[str, List[str]],
        synonyms: Optional[Dict[str, List[str]]] = None,
        n_por_intent: int = 50
    ) -> List[Tuple[str, str]]:
        """
        Genera ejemplos NLU según la configuración.
        - Intents tipo 'template' → reemplaza placeholders dinámicamente usando productos y lookup.
        - Intents tipo 'ejemplos' → usa ejemplos fijos.
        """
        if synonyms is None:
            synonyms = {}

        ejemplos = []

        for intent_name, intent_data in config.items():
            tipo = intent_data.get("tipo", "template")

            if tipo == "ejemplos":
                # Agregar ejemplos fijos
                for ej in intent_data.get("ejemplos", []):
                    ejemplos.append((ej, intent_name))
                continue

            templates = intent_data.get("templates", [])
            if not templates:
                continue

            productos = lookup.get("producto", [])
            if not productos:
                productos = ["producto_generico"]

            count = 0
            while count < n_por_intent:
                for template in templates:
                    if count >= n_por_intent:
                        break
                    producto = random.choice(productos)
                    campos = {"producto": [producto]}

                    for e in intent_data.get("entities", []):
                        if e == "producto":
                            continue
                        if e in ENTIDADES_LOOKUP:
                            posibles = lookup.get(e, [])
                            campos[e] = [random.choice(posibles)] if posibles else []
                        else:
                            campos[e] = [VALORES_ALEATORIOS[e]()] if e in VALORES_ALEATORIOS else []

                    # Reemplazar sinónimos
                    texto_template = template
                    for key, valores in synonyms.items():
                        texto_template = re.sub(rf"\{{{key}\}}", lambda _: random.choice(valores), texto_template)

                    # Generar frase
                    texto = NLUGenerator.generar_frase(texto_template, campos)
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
                    count += 1

        print(f"✅ Generados {len(ejemplos)} ejemplos NLU")
        return ejemplos
