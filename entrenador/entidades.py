import re
import csv
from pathlib import Path
import random
from utils import formatear_nombre, generar_fecha_random

def anotar_entidades(texto, nombre, proveedor, cantidad, dosis, compuesto, categoria,
                     dia=None, fecha=None, cantidad_stock=None, cantidad_descuento=None):
    def anotar(valor, label, texto_actual):
        if valor and valor in texto_actual:
            pattern = re.escape(valor)
            return re.sub(pattern, f"[{valor}]({label})", texto_actual, count=1)
        return texto_actual

    texto = anotar(nombre, "producto", texto)
    texto = anotar(proveedor, "proveedor", texto)
    texto = anotar(cantidad, "cantidad", texto)
    texto = anotar(dosis, "dosis", texto)
    texto = anotar(compuesto, "ingrediente_activo", texto)
    texto = anotar(categoria, "categoria", texto)
    texto = anotar(dia, "tiempo", texto)
    texto = anotar(fecha, "fecha", texto)
    texto = anotar(cantidad_stock, "cantidad_stock", texto)
    texto = anotar(cantidad_descuento, "cantidad_descuento", texto)
    return texto

def leer_entidades_csv(ruta_csv):
    """
    Lee un CSV (una columna con entidades, sin encabezado obligatorio) y devuelve lista limpia.
    """
    entidades = []
    ruta = Path(ruta_csv)
    if not ruta.exists():
        print(f"❌ El archivo {ruta_csv} no existe.")
        return entidades

    with ruta.open(encoding="utf-8") as f:
        lector = csv.reader(f)
        for fila in lector:
            if fila:
                valor = fila[0].strip()
                if valor:
                    entidades.append(valor)
    return entidades



def generar_entidades_por_producto(lookup):
    """
    Dada la tabla lookup con listas de entidades, genera un dict con
    para cada producto las entidades generadas al azar asociadas.
    Devuelve:
      dict { producto_formateado: { 'nombre':..., 'cantidad':..., 'dosis':..., 'proveedor':..., etc } }
    """
    productos = lookup.get("producto", [])
    proveedores = lookup.get("proveedor", [])
    categorias = lookup.get("categoria", [])
    compuestos = lookup.get("compuesto", [])

    entidades_por_producto = {}

    for prod_raw in productos:
        nombre = formatear_nombre(prod_raw)
        cantidad = random.choice(["5 mg", "10 ml", "50 mg", "30 g"])
        dosis = random.choice(["5 mg", "50 mg", "10 ml", "100 ml"])
        proveedor = formatear_nombre(random.choice(proveedores)) if proveedores else "un proveedor"
        compuesto = random.choice(compuestos) if compuestos else "un compuesto"
        categoria = random.choice(categorias) if categorias else "una categoría"
        fecha = generar_fecha_random()
        dia = random.choice(["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"])
        cantidad_stock = random.choice(["10 unidades", "50 productos", "pocas unidades", "stock limitado"])
        cantidad_descuento = random.choice(["20%", "10%", "$500", "15%"])

        entidades_por_producto[nombre] = {
            "nombre": nombre,
            "cantidad": cantidad,
            "dosis": dosis,
            "proveedor": proveedor,
            "compuesto": compuesto,
            "categoria": categoria,
            "fecha": fecha,
            "dia": dia,
            "cantidad_stock": cantidad_stock,
            "cantidad_descuento": cantidad_descuento,
        }

    return entidades_por_producto
