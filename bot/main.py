import os
import threading
import uvicorn
from fastapi import FastAPI
from rasa.core.agent import Agent
from rasa.core.utils import EndpointConfig
from rasa.core.channels.channel import CollectingOutputChannel, UserMessage

# ---------- Configuración ----------
ACTION_SERVER_URL = "http://localhost:5055/webhook"
action_endpoint = EndpointConfig(url=ACTION_SERVER_URL)
agent = Agent.load("models", action_endpoint=action_endpoint)

app = FastAPI()

# ---------- OutputChannel que loguea todos los mensajes ----------
class LoggingOutputChannel(CollectingOutputChannel):
    def send_text_message(self, recipient_id: str, message: str) -> None:
        super().send_text_message(recipient_id, message)
        print(f"💬 [OutputChannel] Action envió mensaje: {message}")

    def send_image_url(self, recipient_id: str, image_url: str) -> None:
        super().send_image_url(recipient_id, image_url)
        print(f"🖼 [OutputChannel] Action envió imagen: {image_url}")

    def send_custom_json(self, recipient_id: str, json_message: dict) -> None:
        super().send_custom_json(recipient_id, json_message)
        print(f"📦 [OutputChannel] Action envió JSON: {json_message}")

# ---------- Endpoint HTTP ----------
@app.post("/message")
async def chat(payload: dict):
    user_text = payload.get("message", "")
    print(f"➡️ [API] Mensaje recibido: {user_text}")

    output_channel = LoggingOutputChannel()
    user_msg = UserMessage(text=user_text, output_channel=output_channel)

    print(f"🔹 [API] Antes de handle_message")
    await agent.handle_message(user_msg)
    print(f"🔹 [API] Después de handle_message")

    print(f"📄 [API] Mensajes en OutputChannel: {output_channel.messages}")
    return {"responses": output_channel.messages}


# ---------- Consola interactiva ----------
def consola_listener():
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    while True:
        try:
            user_text = input(">> Tú: ")
            if user_text.lower() in ["exit", "quit", "salir"]:
                print("👋 Cerrando consola...")
                break

            print(f"➡️ [Consola] Mensaje recibido: {user_text}")
            output_channel = LoggingOutputChannel()
            user_msg = UserMessage(text=user_text, output_channel=output_channel)

            print(f"🔹 [Consola] Antes de handle_message")
            loop.run_until_complete(agent.handle_message(user_msg))
            print(f"🔹 [Consola] Después de handle_message")

            for r in output_channel.messages:
                if r.get("text"):
                    print("🤖 Texto:", r["text"])
            print("-" * 50)

        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    hilo_consola = threading.Thread(target=consola_listener, daemon=True)
    hilo_consola.start()

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)
