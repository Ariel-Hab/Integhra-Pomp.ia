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

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

async def run():
    action_endpoint = EndpointConfig(url="http://localhost:5055/webhook")
    agent = Agent.load("models", action_endpoint=action_endpoint)

    print("🤖 Agente Rasa listo. Escribí tu pregunta (Ctrl+C para salir):")

    while True:
        try:
            texto = input("👤 > ")
            responses = await agent.handle_text(texto)
            for response in responses:
                print("   🗨️   ", response.get("text", "[Sin respuesta]"))
        except KeyboardInterrupt:
            print("\n👋 Cerrando agente...")
            break

if __name__ == "__main__":
    asyncio.run(run())
