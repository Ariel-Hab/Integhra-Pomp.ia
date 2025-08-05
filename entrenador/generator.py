from collections import defaultdict
import random
from lookup import generar_lookup_tables
from templates import variar_plantilla
from utils import aplicar_perturbacion, formatear_nombre, generar_fecha_random
import re
from entidades import (
     anotar_entidades,
    generar_entidades_por_producto
)





def generar_fuera_aplicacion():
    ejemplos_fuera = [
        "Hola",
        "Buenas tardes",
        "¿Cómo estás?",
        "Gracias por tu ayuda",
        "Nos vemos",
        "Quería saber qué día es hoy",
        "¿Tenés promociones de café?",
        "¿Dónde queda tu local?",
        "Necesito ayuda con mi cuenta",
        "Esto no anda",
        "No me interesa eso",
        "Me equivoqué de chat",
        "Gracias, eso era todo",
        "Chau",
        "¿Puedo hablar con alguien?",
        "¿Tenés atención al cliente?",
        "Hola, ¿me podés decir la hora?",
        "No quiero nada",
        "Es una emergencia",
        "¿Cuándo cierran?"
    ]
    return [(ej, "fuera_aplicacion") for ej in ejemplos_fuera]

from paraphraser import Paraphraser  # importa la clase

def generar_ejemplos(data_dir="data", max_total=200):
    ejemplos = []
    lookup = generar_lookup_tables(data_dir)
    entidades_por_producto = generar_entidades_por_producto(lookup)

    if not entidades_por_producto:
        print("❌ No hay productos disponibles para generar entidades.")
        return ejemplos

    ejemplos_fuera = generar_fuera_aplicacion()
    ejemplos.extend(ejemplos_fuera)
    print(f"Se agregaron {len(ejemplos_fuera)} ejemplos para fuera_aplicacion")

    paraphraser = Paraphraser()  # instancia solo una vez

    for nombre, entidades in entidades_por_producto.items():
        if len(ejemplos) >= max_total:
            break

        for intent in ["buscar_producto", "buscar_oferta"]:
            n_ejemplos = random.randint(1, 3)
            for _ in range(n_ejemplos):
                if len(ejemplos) >= max_total:
                    break

                texto_base = variar_plantilla(
                    nombre=entidades["nombre"],
                    proveedor=entidades["proveedor"],
                    cantidad=entidades["cantidad"],
                    dosis=entidades["dosis"],
                    compuesto=entidades["compuesto"],
                    categoria=entidades["categoria"],
                    fecha=entidades["fecha"],
                    dia=entidades["dia"],
                    cantidad_stock=entidades["cantidad_stock"],
                    cantidad_descuento=entidades["cantidad_descuento"],
                    intent=intent
                )

                texto_perturbado = aplicar_perturbacion(texto_base)

                # Aquí llamamos a tu método parafrasear con el texto y las entidades
                # texto_parafraseado = paraphraser.parafrasear(texto_perturbado, **entidades)
                # if texto_parafraseado is None:
                #     # Si hubo problema validando entidades, saltamos este ejemplo
                #     print(f"⚠️ Se perdió alguna entidad protegida al parafrasear el texto base: {texto_base}")
                #     continue

                texto_anotado = anotar_entidades(
                    texto_perturbado,
                    entidades["nombre"],
                    entidades["proveedor"],
                    entidades["cantidad"],
                    entidades["dosis"],
                    entidades["compuesto"],
                    entidades["categoria"],
                    dia=entidades["dia"],
                    fecha=entidades["fecha"],
                    cantidad_stock=entidades["cantidad_stock"],
                    cantidad_descuento=entidades["cantidad_descuento"],
                )
                ejemplos.append((texto_anotado, intent))
                print(f"Ejemplo #{len(ejemplos)} generado para intent {intent} con producto {nombre}")

    return ejemplos
