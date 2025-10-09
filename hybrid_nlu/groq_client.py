# hybrid_nlu/groq_client.py
import os
import json
from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SYSTEM_PROMPT = """Eres un asistente de NLU para español. 
Extrae del texto un JSON con estos campos:
- intent: uno de [buscar_producto, buscar_oferta, comparar_productos, saludar, despedida, afirmar, negar, pedir_ayuda]
- descuento: porcentaje si existe (ej: "5%") o null
- comparador: uno de [lt, lte, gt, gte, eq] o null
- producto: nombre del producto o null
- empresa: nombre de empresa o null

Responde SOLO con el JSON, sin explicaciones."""

def parse_with_groq(text: str) -> dict:
    """Llama a Groq para extraer intent y entidades del texto."""
    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f'Mensaje: "{text}"'}
        ]
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",  # o "mixtral-8x7b-32768"
            messages=messages,
            temperature=0.1,
            max_tokens=300
        )
        
        content = response.choices[0].message.content.strip()
        
        # Limpiar markdown si viene con ```json
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        
        result = json.loads(content)
        return result
        
    except Exception as e:
        print(f"Error en Groq: {e}")
        return {
            "intent": "nlu_fallback",
            "descuento": None,
            "comparador": None,
            "producto": None,
            "empresa": None
        }