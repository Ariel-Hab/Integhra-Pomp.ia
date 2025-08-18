# importer.py
import os
import re
import csv
import random
import unicodedata
from pathlib import Path
from typing import Iterable

import pandas as pd
from utils import formatear_nombre, generar_fecha_random, limpiar_texto, extraer_nombre_y_dosis

# -------------------------
# ANOTACIÓN DE ENTIDADES
# -------------------------
def anotar_entidades(texto, nombre, proveedor, cantidad, dosis, compuesto, categoria,
                     dia=None, fecha=None, cantidad_stock=None, cantidad_descuento=None):

    def limpiar_valor(valor):
        if not valor:
            return None
        valor = valor.strip()
        valor = re.sub(r"[\[\]\(\)]", "", valor)
        return valor

    def anotar(valor, label, texto_actual):
        if isinstance(valor, Iterable) and not isinstance(valor, str):
            for v in valor:
                texto_actual = anotar(v, label, texto_actual)
            return texto_actual

        valor = limpiar_valor(valor)
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

# -------------------------
# LECTURA DE CSV
# -------------------------
def leer_entidades_csv(ruta_csv):
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

# -------------------------
# GENERACIÓN DE LOOKUP TABLES
# -------------------------
def generar_lookup_tables(data_dir="data"):
    lookup_tables = {}

    PALABRAS_IRRELEVANTES = [
        'excipientes', 'csp', 'agua destilada', 'contenido de', 'cada',
        'ml', 'g', 'mg', 'unidad', 'unidades', 'equivalente a', 'por',
        'comp', 'tableta', 'comprimido', 'mgml'
    ]

    def quitar_acentos(texto):
        return ''.join(c for c in unicodedata.normalize('NFD', texto)
                       if unicodedata.category(c) != 'Mn')

    def limpiar_y_extraer_compuestos(texto_compuesto):
        texto = texto_compuesto.lower()
        texto = quitar_acentos(texto)
        texto = re.sub(r'\([^)]*\)', ' ', texto)
        texto = re.sub(r'[:;+/]', ',', texto)
        texto = re.sub(r'\b(c\.?s\.?p\.?|principios? activos?:?|contenido:?|cont(?:iene|:)?|formula:?|componentes?:?)\b', '', texto)
        texto = re.sub(r'\b(mg|g|ml|ui|mcg|mcg/ml|%)\b', ' ', texto)
        texto = re.sub(r'[^\w\s,]', ' ', texto)
        texto = re.sub(r'\s+', ' ', texto).strip()
        for palabra in PALABRAS_IRRELEVANTES:
            palabra_esc = re.escape(palabra)
            texto = re.sub(r'\b' + palabra_esc + r'\b', ' ', texto, flags=re.IGNORECASE)
        texto = re.sub(r'\s+', ' ', texto).strip()

        patron = re.compile(r'([a-záéíóúñü\-]+(?: [a-záéíóúñü\-]+)*)', re.IGNORECASE)
        candidatos = patron.findall(texto)
        compuestos = [c.strip() for c in candidatos if len(c.strip()) >= 3 and not re.fullmatch(r'[\d\s,.]+', c)]
        return sorted(set(compuestos))

    def cargar_lista(archivo, columna, tipo=None):
        path = os.path.join(data_dir, archivo)
        if not os.path.exists(path):
            return []

        df = pd.read_csv(path, on_bad_lines='skip')
        if archivo == "enterprise.csv":
            df = df[df["enterprise_type_id"].isin([1])]

        resultados = []
        for row in df.itertuples(index=False):
            valor_raw = getattr(row, columna, "")
            if pd.isna(valor_raw):
                continue
            valor_raw = str(valor_raw).strip()
            if not valor_raw or valor_raw == "." or len(valor_raw) == 1:
                continue

            if tipo == "producto":
                nombre_raw, _ = extraer_nombre_y_dosis(valor_raw)
                nombre = formatear_nombre(nombre_raw)
                if nombre and len(nombre) > 1:
                    resultados.append(nombre)
            elif tipo == "compuesto":
                resultados.extend(limpiar_y_extraer_compuestos(valor_raw))
            elif tipo == "categoria":
                categoria = limpiar_texto(valor_raw)
                if categoria and len(categoria) > 1:
                    resultados.append(categoria)
            elif tipo == "proveedor":
                proveedor_full = formatear_nombre(valor_raw)
                if proveedor_full and len(proveedor_full) > 1:
                    resultados.append(proveedor_full)
                    palabras = proveedor_full.split()
                    if len(palabras) > 1:
                        resultados.append(palabras[0])
            else:
                limpio = limpiar_texto(valor_raw)
                if limpio and len(limpio) > 1:
                    resultados.append(limpio)
        return resultados

    lookup_tables["producto"] = cargar_lista("product.csv", "title", tipo="producto")
    lookup_tables["categoria"] = cargar_lista("category.csv", "title", tipo="categoria")
    lookup_tables["proveedor"] = cargar_lista("enterprise.csv", "title", tipo="proveedor")
    lookup_tables["compuesto"] = cargar_lista("product.csv", "active_ingredient", tipo="compuesto")

    return lookup_tables

# -------------------------
# GENERACIÓN DE ENTIDADES POR PRODUCTO
# -------------------------
def generar_entidades_por_producto(lookup):
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

# -------------------------
# PIPELINE COMPLETO
# -------------------------
def generar_imports(data_dir="data"):
    Path(data_dir).mkdir(exist_ok=True)

    # 1️⃣ Generar lookup tables
    lookup = generar_lookup_tables(data_dir)
    print("✅ Lookup tables generadas")

    # 2️⃣ Generar entidades por producto
    entidades = generar_entidades_por_producto(lookup)
    print(f"✅ Entidades generadas para {len(entidades)} productos")

    # 3️⃣ Exportar lookup tables
    for key, valores in lookup.items():
        path = Path(data_dir) / f"{key}_lookup.csv"
        with path.open("w", encoding="utf-8") as f:
            for v in sorted(set(valores)):
                f.write(f"{v}\n")
    print(f"✅ Lookup tables exportadas a {data_dir}")

    return lookup, entidades

# -------------------------
# EJECUCIÓN DIRECTA
# -------------------------
if __name__ == "__main__":
    lookup, entidades = generar_imports()
    # Ejemplo de anotación rápida
    ejemplo_texto = "Tomar Paracetamol 500 mg de Laboratorios XYZ cada lunes"
    producto = "paracetamol"
    proveedor = "laboratorios xyz"
    cantidad = "500 mg"
    dosis = "500 mg"
    compuesto = "paracetamol"
    categoria = "analgésico"
    texto_anotado = anotar_entidades(ejemplo_texto, producto, proveedor, cantidad, dosis, compuesto, categoria, dia="lunes")
    print("Ejemplo anotado:", texto_anotado)
