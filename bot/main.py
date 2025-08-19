import logging.config
import yaml
import asyncio
import os

# Desactivar logs molestos desde el principio
with open("logging.yml", "r") as f:
    logging_config = yaml.safe_load(f.read())
    logging.config.dictConfig(logging_config)

from rasa.core.agent import Agent
from rasa.core.utils import EndpointConfig
from rasa.core.tracker_store import InMemoryTrackerStore

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

async def main():
    # Configurar endpoint de acciones
    action_endpoint = EndpointConfig(url="http://localhost:5055/webhook")

    # Cargar agente una sola vez
    agent = Agent.load("models", action_endpoint=action_endpoint)
    print("🤖 Pompito esta listo. Escribí tu pregunta (Ctrl+C para salir).")
    print("   ✨ Escribí 'reset' para reiniciar el contexto actual.")

    # Tracker store en memoria para mantener contexto
    tracker_store = InMemoryTrackerStore(agent.domain)

    while True:
        try:
            texto = input("👤 > ").strip()

            if texto.lower() == "reset":
                tracker_store.tracker_store.clear()
                print("♻️ Contexto reiniciado.")
                continue

            # Crear tracker temporal desde store
            responses = await agent.handle_text(texto)
            for response in responses:
                print("   🗨️   ", response.get("text", "[Sin respuesta]"))

        except KeyboardInterrupt:
            print("\n👋 Cerrando agente...")
            break
        except Exception as e:
            print(f"❌ Ocurrió un error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
