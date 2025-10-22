from langchain_community.llms import Ollama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableParallel, RunnablePassthrough

# --- Simulación de tu Arquitectura ---

def fake_entity_extractor(pregunta: str) -> dict:
    """
    Simula tu `actions_busqueda.py` (`_extract_search_parameters_from_entities`).
    Extrae entidades de la pregunta del usuario.
    """
    print(f"\n[PASO 1: Extrayendo entidades de: '{pregunta}']")
    pregunta = pregunta.lower()
    parametros = {}
    if "holliday" in pregunta:
        parametros["empresa"] = "Holliday"
    if "descuento" in pregunta or "oferta" in pregunta:
        parametros["estado"] = "en_oferta"
    if not parametros:
        parametros["default"] = "busqueda_general"
    
    print(f"-> Entidades extraídas: {parametros}")
    return parametros

def fake_database_retriever(parametros: dict) -> str:
    """
    Simula tu (NUEVO) paso de búsqueda en la Base de Datos.
    Usa los parámetros extraídos para encontrar productos/ofertas.
    """
    print(f"\n[PASO 2: Buscando en la BD con: {parametros}]")
    
    # Simulación de consulta a la BD
    if parametros.get("empresa") == "Holliday" and parametros.get("estado") == "en_oferta":
        # Simula que encontramos productos
        productos_encontrados = [
            {"nombre": "Producto A (Holliday)", "precio": 100, "stock": 50},
            {"nombre": "Producto B (Holliday)", "precio": 120, "stock": 30}
        ]
        print(f"-> Productos encontrados: {len(productos_encontrados)}")
        return str(productos_encontrados) # Convertimos a string para el prompt
        
    elif parametros.get("empresa") == "Holliday":
        # Simula que encontramos otros productos de Holliday
        productos_encontrados = [
            {"nombre": "Producto C (Holliday)", "precio": 200, "stock": 10}
        ]
        print(f"-> Productos encontrados: {len(productos_encontrados)}")
        return str(productos_encontrados)
        
    else:
        # Simula que no encontramos nada
        print("-> No se encontraron productos.")
        return "[]" # Retorna una lista vacía como string

# --- Configuración de LangChain (RAG) ---

# 1. Configura la conexión al LLM (igual que antes)
llm = Ollama(model="phi3:mini")

# 2. Crea el NUEVO prompt (plantilla de RAG)
#    Ahora tiene dos variables: "contexto" (de la BD) y "pregunta" (del usuario)
prompt_template = """
Eres un asistente servicial que responde en español.
Responde la pregunta del usuario basándote ÚNICAMENTE en el siguiente contexto de la base de datos.
Si el contexto está vacío ('[]'), di que no encontraste productos para esos filtros.

Contexto de la Base de Datos:
{contexto}

Pregunta del Usuario:
{pregunta}

Respuesta:
"""

prompt = ChatPromptTemplate.from_template(prompt_template)

# 3. Crea el "parser" (igual que antes)
output_parser = StrOutputParser()

# 4. Encadena todo junto (la nueva cadena RAG)
#    Esto se ve complejo, pero es la forma de LangChain de hacer el diagrama de arriba.

# 4a. Definimos los "caminos" paralelos:
#     - El "contexto" se obtiene extrayendo entidades Y LUEGO buscando en la BD.
#     - La "pregunta" original del usuario se pasa directamente.
chain_setup = RunnableParallel(
    contexto=fake_entity_extractor | fake_database_retriever,
    pregunta=RunnablePassthrough() # Pasa la pregunta original sin cambios
)

# 4b. Construimos la cadena (Chain) final
#     Paso 1: Ejecutar la extracción y la búsqueda (chain_setup)
#     Paso 2: Poner los resultados en el Prompt (prompt)
#     Paso 3: Enviar el prompt al LLM (llm)
#     Paso 4: Limpiar la salida (output_parser)
chain = chain_setup | prompt | llm | output_parser


# 5. ¡Ejecútalo!
try:
    print("--- Probando la cadena RAG (Búsqueda CON resultados) ---")
    pregunta = "Quiero ver productos de Holliday con descuento"
    respuesta = chain.invoke(pregunta)
    
    print("\n[PASO 3: Respuesta Final del LLM]")
    print(f"P: {pregunta}")
    print(f"R: {respuesta}")

    print("\n--- Probando la cadena RAG (Búsqueda SIN resultados) ---")
    pregunta_sin_match = "Quiero ver ofertas de Royal Canin"
    respuesta_sin_match = chain.invoke(pregunta_sin_match)

    print("\n[PASO 3: Respuesta Final del LLM]")
    print(f"P: {pregunta_sin_match}")
    print(f"R: {respuesta_sin_match}")

except Exception as e:
    print(f"Error: No se pudo conectar con Ollama. ¿Está corriendo el servicio?")
    print(f"Detalle: {e}")
