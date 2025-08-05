import re
import random
from datetime import datetime, timedelta

def limpiar_texto(texto):
    if not isinstance(texto, str):
        return ""
    texto = texto.strip().lower()
    texto = re.sub(r"[^a-záéíóúñü0-9\s]", "", texto)
    if len(texto) <= 2 or texto in {"una", "un", "el", "la", "a"}:
        return ""
    return texto

def extraer_nombre_y_dosis(nombre_completo):
    nombre_completo = limpiar_texto(nombre_completo)
    match = re.search(r"(\d+\s?(mg|ml|g|kg|mcg|ml|mg))", nombre_completo, re.IGNORECASE)
    dosis = match.group(1) if match else ""
    nombre = nombre_completo.split()[0] if nombre_completo else "producto"
    return nombre, dosis

def formatear_nombre(nombre):
    if not isinstance(nombre, str):
        return "producto"
    return random.choice([nombre.lower(), nombre.capitalize()])

def aplicar_perturbacion(texto):
    variantes = [
        texto,
        texto + "?",
        texto + ".",
        texto.replace("¿", "").replace("?", ""),
        texto.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u"),
    ]
    return random.choice(variantes)

def generar_fecha_random():
    hoy = datetime.today()
    futura = hoy + timedelta(days=random.randint(1, 60))
    return futura.strftime("%d/%m/%Y")
