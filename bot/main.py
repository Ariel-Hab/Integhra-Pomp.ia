import os
import threading
import uvicorn
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from rasa.core.agent import Agent
from rasa.core.utils import EndpointConfig
from rasa.core.channels.channel import CollectingOutputChannel, UserMessage
from rasa.shared.core.events import SessionStarted, SlotSet
import glob

# ---------- Configuración ----------
ACTION_SERVER_URL = os.getenv("ACTION_SERVER_URL", "http://localhost:5055/webhook")
MODEL_FOLDER = os.getenv("RASA_MODEL_PATH", "models")
PORT = int(os.getenv("PORT", 8000))

print(f"🚀 Configuración:")
print(f"   - Action Server: {ACTION_SERVER_URL}")
print(f"   - Carpeta de modelos: {MODEL_FOLDER}")
print(f"   - Puerto: {PORT}")

# ---------- Funciones para cargar/reload modelos ----------
def get_latest_model(model_folder="models"):
    """Return the latest model path inside the models folder"""
    # Check if model folder exists
    if not os.path.exists(model_folder):
        print(f"❌ La carpeta '{model_folder}' no existe")
        return None
    
    # Get all potential model files/folders
    model_patterns = [
        os.path.join(model_folder, "*.tar.gz"),  # Compressed models
        os.path.join(model_folder, "*")          # Model directories
    ]
    
    models = []
    for pattern in model_patterns:
        models.extend(glob.glob(pattern))
    
    # Filter to only valid models (directories or .tar.gz files)
    models = [m for m in models if os.path.isdir(m) or m.endswith(".tar.gz")]
    
    if not models:
        print(f"❌ No se encontraron modelos en '{model_folder}'")
        print(f"💡 Archivos encontrados: {os.listdir(model_folder) if os.path.exists(model_folder) else 'carpeta no existe'}")
        return None
    
    # Sort by modification time (newest first)
    models.sort(key=os.path.getmtime, reverse=True)
    latest_model = models[0]
    
    print(f"🗂 Último modelo encontrado: {latest_model}")
    return latest_model

def load_agent():
    """Load agent safely with latest model"""
    latest_model = get_latest_model(MODEL_FOLDER)
    if not latest_model:
        return None
    try:
        action_endpoint = EndpointConfig(url=ACTION_SERVER_URL)
        agent = Agent.load(latest_model, action_endpoint=action_endpoint)
        print(f"✅ Agente Rasa cargado desde: {latest_model}")
        return agent
    except Exception as e:
        print(f"❌ Error cargando agente Rasa: {e}")
        import traceback
        traceback.print_exc()
        return None

# Inicializar agente
agent = load_agent()

def reload_agent():
    global agent
    print("🔄 Recargando agente...")
    old_agent = agent
    agent = load_agent()
    success = agent is not None
    if success:
        print("✅ Agente recargado exitosamente")
        # Clean up old agent if needed
        if old_agent:
            try:
                # Attempt to clean up resources
                pass  # Rasa agents don't have explicit cleanup methods
            except Exception as e:
                print(f"⚠️ Warning durante cleanup: {e}")
    else:
        print("❌ Falló la recarga del agente")
        # Keep the old agent if reload failed
        agent = old_agent
    return success

# ---------- FastAPI ----------
app = FastAPI(title="Rasa Chat API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Pydantic ----------
class ChatRequest(BaseModel):
    message: str
    user_id: str = "default_user"

class ChatResponse(BaseModel):
    responses: list
    error: str = None

# ---------- OutputChannel ----------
class LoggingOutputChannel(CollectingOutputChannel):
    def __init__(self):
        super().__init__()
        self.error_count = 0

    async def send_text_message(self, recipient_id, text, **kwargs):
        try:
            await super().send_text_message(recipient_id, text)
            print(f"💬 Texto enviado: {text[:100]}")
        except Exception as e:
            print(f"❌ Error enviando texto: {e}")
            self.error_count += 1
            self.messages.append({"text": text, "recipient_id": recipient_id})

    def get_health_status(self):
        return {
            "total_messages": len(self.messages),
            "error_count": self.error_count,
            "status": "healthy" if self.error_count == 0 else "degraded"
        }

# ---------- Endpoints ----------
@app.get("/")
async def root():
    return {
        "status": "running",
        "agent_loaded": agent is not None,
        "action_server": ACTION_SERVER_URL,
        "cors_enabled": True,
        "model_folder": MODEL_FOLDER,
        "latest_model": get_latest_model(MODEL_FOLDER)
    }

@app.get("/health")
async def health_check():
    if agent is None:
        raise HTTPException(status_code=503, detail="Rasa agent not loaded")
    return {
        "status": "healthy", 
        "agent": "loaded", 
        "action_server": ACTION_SERVER_URL,
        "model_folder": MODEL_FOLDER
    }
@app.post("/reset_context")
async def reset_context(user_id: str):
    """
    Reinicia el contexto y los slots de un usuario específico.
    """
    if agent is None:
        raise HTTPException(status_code=503, detail="Rasa agent not loaded")

    try:
        # Reinicia la sesión (contexto de conversación)
        await agent.handle_message(UserMessage(
            text=None,
            output_channel=LoggingOutputChannel(),
            sender_id=user_id,
            input_channel=None,
        ))

        # Reinicia todos los slots a None
        tracker = await agent.tracker_store.get_or_create_tracker(user_id)
        events = [SlotSet(slot, None) for slot in tracker.slots.keys()]
        for e in events:
            tracker.update(e)
        await agent.tracker_store.save(tracker)

        return {"status": "success", "message": f"Contexto y slots reiniciados para user_id: {user_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/models")
async def list_models():
    """List available models in the models directory"""
    if not os.path.exists(MODEL_FOLDER):
        return {"models": [], "error": f"Models folder '{MODEL_FOLDER}' does not exist"}
    
    models = []
    for item in os.listdir(MODEL_FOLDER):
        item_path = os.path.join(MODEL_FOLDER, item)
        if os.path.isdir(item_path) or item.endswith(".tar.gz"):
            models.append({
                "name": item,
                "path": item_path,
                "modified": os.path.getmtime(item_path),
                "is_latest": item_path == get_latest_model(MODEL_FOLDER)
            })
    
    return {"models": sorted(models, key=lambda x: x["modified"], reverse=True)}

@app.post("/reload_model")
async def reload_model_endpoint():
    if reload_agent():
        return {
            "status": "success", 
            "message": "Agent reloaded with latest model",
            "latest_model": get_latest_model(MODEL_FOLDER)
        }
    else:
        raise HTTPException(
            status_code=500, 
            detail={
                "message": "Failed to reload agent",
                "model_folder": MODEL_FOLDER,
                "models_available": len(glob.glob(os.path.join(MODEL_FOLDER, "*"))) > 0
            }
        )

@app.post("/message", response_model=ChatResponse)
async def chat(payload: ChatRequest):
    if agent is None:
        raise HTTPException(status_code=503, detail="Rasa agent not available")

    user_text = payload.message.strip()
    user_id = payload.user_id

    if not user_text:
        return ChatResponse(responses=[], error="Empty message")

    output_channel = LoggingOutputChannel()
    user_msg = UserMessage(text=user_text, output_channel=output_channel, sender_id=user_id)

    try:
        await agent.handle_message(user_msg)
        if not output_channel.messages:
            return ChatResponse(
                responses=[{"text": "Lo siento, no pude procesar tu mensaje."}],
                error="No response from agent"
            )
        return ChatResponse(responses=output_channel.messages)
    except Exception as e:
        return ChatResponse(
            responses=[{"text": "Error procesando el mensaje.", "type": "error"}],
            error=str(e)
        )

# ---------- Consola interactiva ----------
def consola_listener():
    if agent is None:
        print("❌ Consola deshabilitada - agente no disponible")
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    print("🎮 Consola interactiva iniciada")

    while True:
        try:
            user_text = input(">> Tú: ").strip()
            if user_text.lower() in ["exit", "quit", "salir"]:
                break
            if not user_text:
                continue
            if user_text.lower() == "reset":
                user_id_reset = "console_user"
                tracker = loop.run_until_complete(agent.tracker_store.get_or_create_tracker(user_id_reset))
                for slot in tracker.slots.keys():
                    tracker.update(SlotSet(slot, None))
                tracker.update(SessionStarted())
                loop.run_until_complete(agent.tracker_store.save(tracker))
                print(f"✅ Contexto y slots reiniciados para la consola (user_id: {user_id_reset})")
                continue

            output_channel = LoggingOutputChannel()
            user_msg = UserMessage(text=user_text, output_channel=output_channel, sender_id="console_user")
            loop.run_until_complete(agent.handle_message(user_msg))

            for i, msg in enumerate(output_channel.messages):
                if "text" in msg:
                    print(f"🤖 Bot ({i+1}): {msg['text']}")
                else:
                    print(f"🤖 Bot ({i+1}): {msg}")

        except KeyboardInterrupt:
            break
        except EOFError:
            break
        except Exception as e:
            print(f"❌ Consola error: {e}")

# ---------- Startup ----------
if __name__ == "__main__":
    if agent is not None:
        hilo_consola = threading.Thread(target=consola_listener, daemon=True)
        hilo_consola.start()
        print("🧵 Consola iniciada en hilo separado")
    else:
        print("⚠️ Consola deshabilitada - agente no disponible")
        print("💡 Entrena un modelo primero con: poetry run rasa train")

    uvicorn.run(app, host="0.0.0.0", port=PORT, reload=False)