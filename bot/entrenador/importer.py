# importer.py - Versión mejorada con extracción automática de entidades desde config
import os
import re
import csv
import random
import unicodedata
from pathlib import Path
from typing import Iterable, Dict, Any, Optional

import pandas as pd
from utils import formatear_nombre, generar_fecha_random, limpiar_texto, extraer_nombre_y_dosis

# Cache para configuración para evitar recargar en cada llamada
_CONFIG_CACHE = None

def cargar_config_entities():
    """
    Carga la configuración de entidades desde el ConfigLoader.
    Utiliza cache para evitar recargas innecesarias.
    """
    global _CONFIG_CACHE
    
    if _CONFIG_CACHE is None:
        try:
            # Importar dinámicamente para evitar dependencias circulares
            from scripts.config_loader import ConfigLoader
            
            config = ConfigLoader.cargar_config()
            entities_config = config.get("entities", {})
            
            # Extraer nombres de todas las entidades definidas en el config
            entity_names = list(entities_config.keys())
            
            _CONFIG_CACHE = {
                "entity_names": entity_names,
                "entities_config": entities_config
            }
            
            print(f"[Importer] Entidades cargadas desde config: {entity_names}")
            
        except ImportError as e:
            print(f"[Importer] Error importando ConfigLoader: {e}")
            # Fallback a entidades básicas
            _CONFIG_CACHE = {
                "entity_names": [
                    "producto", "proveedor", "cantidad", "dosis", "compuesto", 
                    "ingrediente_activo", "categoria", "dia", "fecha", 
                    "cantidad_stock", "cantidad_descuento", "animal",
                    "sentimiento_positivo", "sentimiento_negativo", 
                    "rechazo_total", "intencion_buscar", "solicitud_ayuda"
                ],
                "entities_config": {}
            }
        except Exception as e:
            print(f"[Importer] Error cargando config: {e}")
            # Usar fallback
            _CONFIG_CACHE = {
                "entity_names": [
                    "producto", "proveedor", "cantidad", "dosis", "compuesto", 
                    "ingrediente_activo", "categoria", "animal"
                ],
                "entities_config": {}
            }
    
    return _CONFIG_CACHE

def invalidar_cache_config():
    """Invalida el cache de configuración para forzar recarga."""
    global _CONFIG_CACHE
    _CONFIG_CACHE = None

def anotar_entidades(texto: str, **kwargs) -> str:
    """
    Anota entidades en el texto basándose automáticamente en la configuración.
    Acepta cualquier entidad definida en el config como parámetro nombrado.
    
    Args:
        texto: El texto a anotar
        **kwargs: Entidades como parámetros nombrados (producto=valor, proveedor=valor, etc.)
    
    Returns:
        str: Texto con entidades anotadas en formato [valor](entidad)
    
    Example:
        texto_anotado = anotar_entidades(
            texto="necesito paracetamol para mi perro",
            producto="paracetamol",
            animal="perro"
        )
    """
    
    # Cargar configuración de entidades
    config_data = cargar_config_entities()
    entity_names = config_data["entity_names"]
    entities_config = config_data["entities_config"]
    
    def limpiar_valor(valor):
        """Limpia y valida un valor de entidad."""
        if not valor:
            return None
        valor = str(valor).strip()
        valor = re.sub(r"[\[\]\(\)]", "", valor)
        return valor if valor else None

    def anotar_valor(valor, label: str, texto_actual: str) -> str:
        """Anota un valor específico en el texto con mejor alineación de tokens."""
        # Manejar listas de valores
        if isinstance(valor, Iterable) and not isinstance(valor, str):
            for v in valor:
                texto_actual = anotar_valor(v, label, texto_actual)
            return texto_actual

        valor = limpiar_valor(valor)
        if not valor or valor not in texto_actual:
            return texto_actual
            
        # Solo anotar si no está ya anotado
        if f"[{valor}]" in texto_actual:
            return texto_actual
        
        # MEJORADO: Manejar entidades con espacios y puntos (ej: "konig s.a.")
        # Buscar coincidencias exactas respetando límites de palabra
        import re
        
        # Escapar caracteres especiales pero mantener estructura
        valor_escaped = re.escape(valor)
        # Pero permitir que los puntos sean opcionales para mejor matching
        valor_pattern = valor_escaped.replace(r'\.', r'\.?')
        
        # Buscar con límites de palabra flexibles
        pattern = r'\b' + valor_pattern + r'\b'
        match = re.search(pattern, texto_actual, re.IGNORECASE)
        
        if match:
            matched_text = match.group(0)
            # Reemplazar la coincidencia exacta encontrada
            return texto_actual.replace(matched_text, f"[{matched_text}]({label})", 1)
        
        return texto_actual

    def determinar_etiqueta_entidad(entity_name: str) -> str:
        """
        Determina la etiqueta correcta para una entidad.
        Maneja casos especiales y aliases.
        """
        # Casos especiales para compatibilidad
        if entity_name == "compuesto":
            return "ingrediente_activo"  # Mapear compuesto a ingrediente_activo
        elif entity_name == "ingrediente_activo":
            return "ingrediente_activo"
        elif entity_name == "dia":
            return "tiempo"  # Mantener compatibilidad con etiqueta tiempo
        else:
            return entity_name

    # Procesar todas las entidades pasadas como kwargs
    texto_resultado = texto
    
    # Procesar entidades en orden de prioridad (entidades principales primero)
    entidades_prioritarias = [
        "producto", "proveedor", "cantidad", "dosis", 
        "ingrediente_activo", "compuesto", "categoria", "animal"
    ]
    
    # Primero procesar entidades prioritarias
    for entity_name in entidades_prioritarias:
        if entity_name in kwargs:
            valor = kwargs[entity_name]
            etiqueta = determinar_etiqueta_entidad(entity_name)
            texto_resultado = anotar_valor(valor, etiqueta, texto_resultado)
    
    # Luego procesar el resto de entidades
    for entity_name, valor in kwargs.items():
        if entity_name not in entidades_prioritarias:
            # Verificar si la entidad está definida en el config
            if entity_name in entity_names:
                etiqueta = determinar_etiqueta_entidad(entity_name)
                texto_resultado = anotar_valor(valor, etiqueta, texto_resultado)
            else:
                print(f"[Importer] Advertencia: Entidad '{entity_name}' no está definida en config")
    
    return texto_resultado

def obtener_entidades_disponibles() -> Dict[str, Any]:
    """
    Devuelve información sobre las entidades disponibles desde el config.
    
    Returns:
        dict: Información de entidades con sus tipos y configuraciones
    """
    config_data = cargar_config_entities()
    return {
        "entity_names": config_data["entity_names"],
        "entities_config": config_data["entities_config"],
        "total_entities": len(config_data["entity_names"])
    }

def validar_entidades_kwargs(**kwargs) -> Dict[str, str]:
    """
    Valida que las entidades pasadas existan en la configuración.
    
    Returns:
        dict: Mapa de errores/advertencias por entidad
    """
    config_data = cargar_config_entities()
    entity_names = config_data["entity_names"]
    
    issues = {}
    
    for entity_name, valor in kwargs.items():
        if entity_name not in entity_names:
            issues[entity_name] = f"Entidad no definida en config"
        elif not valor:
            issues[entity_name] = f"Valor vacío para entidad"
    
    return issues

# -------------------------
# RESTO DE FUNCIONES SIN CAMBIOS (mantener compatibilidad)
# -------------------------
def leer_entidades_csv(ruta_csv):
    """Mantener función original para compatibilidad."""
    entidades = []
    ruta = Path(ruta_csv)
    if not ruta.exists():
        print(f"El archivo {ruta_csv} no existe.")
        return entidades

    with ruta.open(encoding="utf-8") as f:
        lector = csv.reader(f)
        for fila in lector:
            if fila:
                valor = fila[0].strip()
                if valor:
                    entidades.append(valor)
    return entidades

def generar_lookup_tables(data_dir="data"):
    """Mantener función original con mejora para ingrediente_activo."""
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
    
    # MEJORADO: Agregar ingrediente_activo como alias de compuesto para compatibilidad total
    lookup_tables["ingrediente_activo"] = lookup_tables["compuesto"]

    return lookup_tables

def generar_entidades_por_producto(lookup):
    """Mantener función original sin cambios."""
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
        cantidad_descuento = random.randint(5, 80)

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

def generar_regex_yml(path="data/regex_entities.yml"):
    """Mantener función original sin cambios."""
    import yaml
    regex_data = {
        "version": "3.1",
        "regex": [
            {"name": "cantidad_descuento", "pattern": r"\d{1,3}\s?%"},
            {"name": "cantidad_descuento", "pattern": r"\d{1,5}\s?\$"},
            {"name": "cantidad_descuento", "pattern": r"\d{1,3}\s?(por\s*ciento)"},
        ]
    }

    path = Path(path)
    path.parent.mkdir(exist_ok=True, parents=True)

    with path.open("w", encoding="utf-8") as f:
        yaml.dump(regex_data, f, allow_unicode=True)

    print(f"Archivo regex generado en {path}")

def generar_imports(data_dir="data"):
    """Pipeline completo manteniendo compatibilidad."""
    Path(data_dir).mkdir(exist_ok=True)

    # 1. Generar lookup tables
    lookup = generar_lookup_tables(data_dir)
    print("Lookup tables generadas")

    # 2. Generar entidades por producto
    entidades = generar_entidades_por_producto(lookup)
    print(f"Entidades generadas para {len(entidades)} productos")

    # 3. Exportar lookup tables
    for key, valores in lookup.items():
        if key != "ingrediente_activo":  # Evitar duplicar el archivo compuesto
            path = Path(data_dir) / f"{key}_lookup.csv"
            with path.open("w", encoding="utf-8") as f:
                for v in sorted(set(valores)):
                    f.write(f"{v}\n")
    print(f"Lookup tables exportadas a {data_dir}")

    # 4. Generar regex entities
    generar_regex_yml(Path(data_dir) / "regex_entities.yml")

    return lookup, entidades

# -------------------------
# TESTING Y EJEMPLOS
# -------------------------
if __name__ == "__main__":
    # Mostrar entidades disponibles
    entidades_info = obtener_entidades_disponibles()
    print(f"\nEntidades disponibles: {entidades_info['entity_names']}")
    print(f"Total: {entidades_info['total_entities']}")
    
    # Ejemplo básico con validación
    ejemplo_kwargs = {
        "producto": "paracetamol",
        "animal": "perro",
        "proveedor": "bayer",
        "entidad_inexistente": "valor"  # Esto debería generar advertencia
    }
    
    # Validar antes de anotar
    issues = validar_entidades_kwargs(**ejemplo_kwargs)
    if issues:
        print(f"\nAdvertencias: {issues}")
    
    # Anotar con las entidades válidas
    texto_ejemplo = "necesito paracetamol de bayer para mi perro"
    texto_anotado = anotar_entidades(texto_ejemplo, **ejemplo_kwargs)
    print(f"\nEjemplo: '{texto_ejemplo}'")
    print(f"Anotado: '{texto_anotado}'")
    
    # Ejemplo con entidades emocionales (si están en config)
    ejemplo_emocional = "estoy genial, necesito ayuda con algo"
    texto_emocional = anotar_entidades(
        texto=ejemplo_emocional,
        sentimiento_positivo="genial",
        solicitud_ayuda="ayuda"
    )
    print(f"\nEjemplo emocional: '{ejemplo_emocional}'")
    print(f"Anotado: '{texto_emocional}'")
    
    # Generar imports si se ejecuta directamente
    print("\n" + "="*50)
    print("Generando imports...")
    lookup, entidades = generar_imports()
    print("Proceso completado.")