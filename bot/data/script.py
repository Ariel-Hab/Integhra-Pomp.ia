import yaml
import re

# Ruta a tu archivo .yml
INPUT_FILE = "lookup_tables.yml"
OUTPUT_FILE = "nlu_filtrado.yml"

# Leer el YAML como texto (para preservar formato tipo Rasa)
with open(INPUT_FILE, "r", encoding="utf-8") as f:
    contenido = f.read()

# Buscar bloque de lookup: producto
patron = r"(lookup:\s*producto\s*[\s\S]*?examples:\s*\|[\s\S]*?)(?=\n\s*-\s*\w|\Z)"
coincidencias = re.findall(patron, contenido)

if coincidencias:
    bloque = coincidencias[0]

    # Filtrar las líneas de productos
    lineas = bloque.splitlines()
    nuevas_lineas = []
    for linea in lineas:
        if linea.strip().startswith("- "):
            palabra = linea.strip()[2:].strip()
            if len(palabra) >= 3:
                nuevas_lineas.append(linea)
        else:
            nuevas_lineas.append(linea)

    bloque_filtrado = "\n".join(nuevas_lineas)
    contenido = contenido.replace(bloque, bloque_filtrado)

# Guardar nuevo archivo
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(contenido)

print(f"Archivo procesado. Guardado en {OUTPUT_FILE}")
