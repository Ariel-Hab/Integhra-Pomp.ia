import random
from utils import generar_fecha_random

SINONIMOS_PRODUCTO = ["producto", "medicamento"]
SINONIMOS_VER = ["mostrame", "quiero ver", "podrías mostrarme", "decime cuáles hay", "enséñame"]
SINONIMOS_PRECIO = ["precio", "costo", "valor"]
SINONIMOS_BUSCAR = ["busco", "necesito", "quiero", "estoy buscando", "me interesa", "tenés"]
SINONIMOS_OFERTA = ["oferta", "promoción", "descuento", "rebaja"]

def variar_plantilla(
    nombre,
    proveedor,
    cantidad,
    dosis,
    compuesto,
    categoria,
    fecha,
    dia,
    cantidad_stock,
    cantidad_descuento,
    intent="buscar_producto"
):
    # Usamos fecha generada por fuera solo si no se pasa:
    if not fecha:
        fecha = generar_fecha_random()
    # Por si alguna entidad viene vacía o None, le asignamos valores por defecto (puede adaptarse):
    proveedor = proveedor if proveedor and proveedor != "." else "un proveedor"
    cantidad = cantidad if cantidad and cantidad != "." else random.choice(["5 mg", "10 ml", "50 mg", "30 g", "20 unidades"])
    dosis = dosis if dosis and dosis != "." else random.choice(["5 mg", "50 mg", "10 ml", "100 ml"])
    compuesto = compuesto if compuesto and compuesto != "." else "un compuesto"
    categoria = categoria if categoria and categoria != "." else "una categoría"
    dia = dia if dia and dia != "." else random.choice(["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"])
    cantidad_stock = cantidad_stock if cantidad_stock and cantidad_stock != "." else random.choice(["10 unidades", "50 productos", "pocas unidades", "stock limitado"])
    cantidad_descuento = cantidad_descuento if cantidad_descuento and cantidad_descuento != "." else random.choice(["20%", "10%", "$500", "15%"])

    frases_dosis = [
        f"en presentación de {dosis}",
        f"que venga en frascos de {dosis}",
        f"en dosis de {dosis}",
        f"con concentración de {dosis}",
        f"que tenga {dosis}"
    ]

    if intent == "buscar_producto":
        frases_precio = [
            f"¿Cuál es el {random.choice(SINONIMOS_PRECIO)} de {nombre}?",
            f"¿Cuánto cuesta {nombre}?",
            f"¿Está {nombre} en descuento?",
            f"¿Hay promociones para {nombre} hasta el {fecha}?",
            f"¿Podés decirme el {random.choice(SINONIMOS_PRECIO)} de {nombre}?"
        ]

        opciones = [
            f"{random.choice(SINONIMOS_BUSCAR).capitalize()} {nombre}",
            f"Tenés {nombre}?",
            f"Estoy buscando {nombre}",

            f"{random.choice(SINONIMOS_BUSCAR).capitalize()} {nombre} del proveedor {proveedor}",
            f"Quiero {nombre} de {proveedor}",

            f"Necesito {cantidad} unidades de {nombre}",
            f"Compraría {cantidad} de {nombre}",

            f"¿{nombre} tiene presentación de {dosis}?",
            f"¿Hay {nombre} {random.choice(frases_dosis)}?",

            f"Busco {nombre} que tenga {compuesto}",
            f"¿Tenés {nombre} con {compuesto}?",

            f"Quiero {nombre} de la categoría {categoria}",
            f"Estoy interesado en {categoria}, especialmente en {nombre}",

            *frases_precio,

            f"{random.choice(SINONIMOS_BUSCAR).capitalize()} {nombre} de {proveedor} con {compuesto}",
            f"¿Tenés {nombre} de {proveedor} en presentación de {dosis}?",
            f"Estoy buscando {nombre} de la categoría {categoria} a buen precio",
            f"Quiero {cantidad} de {nombre} con {compuesto} y saber el precio",
        ]

    elif intent == "buscar_oferta":
        frases_oferta = [
            f"¿Hay alguna {random.choice(SINONIMOS_OFERTA)} para {nombre}?",
            f"¿Qué {random.choice(SINONIMOS_OFERTA)} tenés para {nombre}?",
            f"¿Cuáles son las promociones vigentes para {nombre}?",
            f"¿Está {nombre} con descuento hasta el {fecha}?",
            f"¿Tenés {nombre} en oferta solo por el {dia}?",
            f"¿Qué ofertas hay para {nombre} con un {cantidad_descuento} de descuento?",
            f"Mostrame promociones activas con {cantidad_descuento} de rebaja en {nombre}",
            f"¿Hay alguna promoción de {nombre} con stock de solo {cantidad_stock}?",
            f"¿Hay rebajas para {nombre} de la categoría {categoria} este {dia}?",
            f"Busco productos con descuento que incluyan {compuesto}",
            f"¿Qué {random.choice(SINONIMOS_OFERTA)} hay en {categoria} esta semana?",
            f"Quiero saber si hay ofertas de {nombre} de {proveedor}",
            f"¿Tenés {nombre} en promoción especial por el {dia}?",
            f"¿Qué promociones hay para {nombre} con {compuesto} de {proveedor}?",
            f"¿Hay descuentos del {cantidad_descuento} para {nombre} hasta el {fecha}?",
            f"¿Hay alguna oferta para {nombre} con stock limitado de {cantidad_stock}?",
        ]

        opciones = frases_oferta

    else:
        opciones = [f"{random.choice(SINONIMOS_BUSCAR).capitalize()} {nombre}"]

    return random.choice(opciones)
