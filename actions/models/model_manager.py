# model_manager.py
from transformers import pipeline
import logging

logger = logging.getLogger(__name__)

# Variable global del generador (se carga una vez)
_generator = None

def load_model(model_name: str = "bigscience/bloomz-560m"):
    """
    Carga el modelo y lo deja en memoria.
    Si ya está cargado, no lo vuelve a cargar.
    """
    global _generator
    if _generator is None:
        try:
            logger.info(f"Cargando modelo {model_name}...")
            _generator = pipeline("text-generation", model=model_name)
            logger.info("✅ Modelo cargado correctamente")
        except Exception as e:
            logger.error(f"❌ Error cargando modelo {model_name}: {e}", exc_info=True)
            raise e
    return _generator

def generate_text(prompt: str, max_new_tokens: int = 80) -> str:
    """
    Genera texto a partir de un prompt usando el modelo cargado.
    """
    global _generator
    if _generator is None:
        load_model()  # Carga por defecto BLOOMZ 560M

    salida = _generator(
        prompt,
        max_new_tokens=max_new_tokens,
        do_sample=True,
        top_p=0.9,
        temperature=0.7,
    )

    # Extraer texto generado
    return salida[0]["generated_text"].replace(prompt, "").strip()

if __name__ == "__main__":

    print("Probando modelo...")
    resp = generate_text("Hola, ¿puedes contarme un chiste corto?")
    print("Respuesta:", resp)
