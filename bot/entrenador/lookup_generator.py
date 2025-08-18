import re
import unicodedata
import os
import pandas as pd
from utils import limpiar_texto, extraer_nombre_y_dosis, formatear_nombre

def generar_lookup_tables(data_dir="data"):
    lookup_tables = {}



    PALABRAS_IRRELEVANTES = [
        'excipientes', 'csp', 'agua destilada', 'contenido de', 'cada',
        'ml', 'g', 'mg', 'unidad', 'unidades', 'equivalente a', 'por',
        'comp', 'tableta', 'comprimido', 'mgml'
    ]

    def quitar_acentos(texto):
        return ''.join(
            c for c in unicodedata.normalize('NFD', texto)
            if unicodedata.category(c) != 'Mn'
        )

    def limpiar_y_extraer_compuestos(texto_compuesto):
        texto = texto_compuesto.lower()
        texto = quitar_acentos(texto)

        # Eliminar contenido dentro de paréntesis
        texto = re.sub(r'\([^)]*\)', ' ', texto)

        # Normalizar separadores a comas
        texto = re.sub(r'[:;+/]', ',', texto)

        # Eliminar palabras clave irrelevantes y dosis (con word boundaries)
        texto = re.sub(r'\b(c\.?s\.?p\.?|principios? activos?:?|contenido:?|cont(?:iene|:)?|formula:?|componentes?:?)\b', '', texto)

        # Eliminar solo unidades como palabras completas (no dentro de otras palabras)
        texto = re.sub(r'\b(mg|g|ml|ui|mcg|mcg/ml|%)\b', ' ', texto)

        # Quitar caracteres especiales que no sean letras, números, espacios o comas
        texto = re.sub(r'[^\w\s,]', ' ', texto)

        # Limpiar espacios extras
        texto = re.sub(r'\s+', ' ', texto).strip()

        # Eliminar palabras irrelevantes solo si están completas
        for palabra in PALABRAS_IRRELEVANTES:
            palabra_esc = re.escape(palabra)
            texto = re.sub(r'\b' + palabra_esc + r'\b', ' ', texto, flags=re.IGNORECASE)

        texto = re.sub(r'\s+', ' ', texto).strip()

        # Extraer compuestos (palabras o frases con espacios)
        patron = re.compile(r'([a-záéíóúñü\-]+(?: [a-záéíóúñü\-]+)*)', re.IGNORECASE)

        candidatos = patron.findall(texto)

        compuestos = []
        for c in candidatos:
            c = c.strip()
            if len(c) < 3:
                continue
            if re.fullmatch(r'[\d\s,.]+', c):
                continue
            compuestos.append(c)

        compuestos = sorted(set(compuestos))
        return compuestos



    def cargar_lista(archivo, columna, tipo=None, data_dir="data"):
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
                compuestos = limpiar_y_extraer_compuestos(valor_raw)
                resultados.extend(compuestos)

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
    # lookup_tables["producto"].append("producto")
    lookup_tables["categoria"] = cargar_lista("category.csv", "title", tipo="categoria")
    # lookup_tables["categoria"].append("categoría")
    # lookup_tables["categoria"].append("categoría médica")
    lookup_tables["proveedor"] = cargar_lista("enterprise.csv", "title", tipo="proveedor")
    # lookup_tables["proveedor"].append("proveedor")
    # lookup_tables["proveedor"].append("empresa")
    lookup_tables["compuesto"] = cargar_lista("product.csv", "active_ingredient", tipo="compuesto")
    # lookup_tables["compuesto"].append("compuesto")
    # lookup_tables["compuesto"].append("ingrediente activo")
    # lookup_tables["compuesto"].append("ingrediente")


    return lookup_tables  # ← Agregá esta línea

