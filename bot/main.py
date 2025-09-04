import os
import threading
import uvicorn
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware  # ✅ CORS import
from pydantic import BaseModel
from rasa.core.agent import Agent
from rasa.core.utils import EndpointConfig
from rasa.core.channels.channel import CollectingOutputChannel, UserMessage

# ---------- Configuración con variables de entorno ----------
ACTION_SERVER_URL = os.getenv("ACTION_SERVER_URL", "http://localhost:5055/webhook")
MODEL_PATH = os.getenv("RASA_MODEL_PATH", "models")
PORT = int(os.getenv("PORT", "8000"))

print(f"🚀 Configuración:")
print(f"   - Action Server: {ACTION_SERVER_URL}")
print(f"   - Modelo: {MODEL_PATH}")
print(f"   - Puerto: {PORT}")

# Inicializar agente con manejo de errores
try:
    action_endpoint = EndpointConfig(url=ACTION_SERVER_URL)
    agent = Agent.load(MODEL_PATH, action_endpoint=action_endpoint)
    print("✅ Agente Rasa cargado correctamente")
except Exception as e:
    print(f"❌ Error cargando agente Rasa: {e}")
    agent = None

app = FastAPI(title="Rasa Chat API", version="1.0.0")

# ✅ Configurar CORS para permitir requests desde Flutter
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especifica los dominios exactos
    allow_credentials=True,
    allow_methods=["*"],  # Permite GET, POST, OPTIONS, etc.
    allow_headers=["*"],  # Permite todos los headers
)

# ---------- Modelos Pydantic ----------
class ChatRequest(BaseModel):
    message: str
    user_id: str = "default_user"

class ChatResponse(BaseModel):
    responses: list
    error: str = None

# ---------- OutputChannel mejorado ----------
class LoggingOutputChannel(CollectingOutputChannel):
    def __init__(self):
        super().__init__()
        self.error_count = 0
        
    async def send_text_message(self, recipient_id: str, text: str, **kwargs) -> None:
        try:
            # Llamar al método padre SOLO con parámetros que acepta
            await super().send_text_message(recipient_id, text)
            print(f"💬 [OutputChannel] Texto enviado: {text[:100]}{'...' if len(text) > 100 else ''}")
            
            # Manejar kwargs adicionales si es necesario
            if kwargs:
                print(f"🔧 [OutputChannel] Kwargs ignorados: {list(kwargs.keys())}")
                
        except Exception as e:
            print(f"❌ [OutputChannel] Error enviando texto: {e}")
            self.error_count += 1
            # Fallback manual
            self.messages.append({"text": text, "recipient_id": recipient_id})

    async def send_image_url(self, recipient_id: str, image: str, **kwargs) -> None:
        try:
            await super().send_image_url(recipient_id, image)
            print(f"🖼 [OutputChannel] Imagen enviada: {image}")
        except Exception as e:
            print(f"❌ [OutputChannel] Error enviando imagen: {e}")
            self.error_count += 1
            self.messages.append({"image": image, "recipient_id": recipient_id})

    async def send_custom_json(self, recipient_id: str, json_message: dict, **kwargs) -> None:
        try:
            await super().send_custom_json(recipient_id, json_message)
            print(f"📦 [OutputChannel] JSON enviado: {str(json_message)[:100]}...")
        except Exception as e:
            print(f"❌ [OutputChannel] Error enviando JSON: {e}")
            self.error_count += 1
            self.messages.append({"custom": json_message, "recipient_id": recipient_id})

    async def send_response(self, recipient_id: str, message: dict) -> None:
        try:
            await super().send_response(recipient_id, message)
            print(f"📨 [OutputChannel] Respuesta enviada correctamente")
        except Exception as e:
            print(f"❌ [OutputChannel] Error enviando respuesta: {e}")
            self.error_count += 1
            # Fallback completo
            if message not in self.messages:
                self.messages.append(message)
                
    def get_health_status(self):
        return {
            "total_messages": len(self.messages),
            "error_count": self.error_count,
            "status": "healthy" if self.error_count == 0 else "degraded"
        }

# ---------- Endpoints HTTP ----------
@app.get("/")
async def root():
    return {
        "status": "running", 
        "agent_loaded": agent is not None,
        "action_server": ACTION_SERVER_URL,
        "cors_enabled": True  # ✅ Indicador de CORS habilitado
    }

@app.get("/health")
async def health_check():
    if agent is None:
        raise HTTPException(status_code=503, detail="Rasa agent not loaded")
    
    return {
        "status": "healthy",
        "agent": "loaded",
        "action_server": ACTION_SERVER_URL
    }

@app.post("/message", response_model=ChatResponse)
async def chat(payload: ChatRequest):
    if agent is None:
        raise HTTPException(status_code=503, detail="Rasa agent not available")
        
    # ✅ Corrección: acceder a los atributos directamente
    user_text = payload.message.strip()
    user_id = payload.user_id
    
    if not user_text:
        return ChatResponse(responses=[], error="Empty message")
    
    print(f"➡️ [API] Usuario {user_id}: {user_text}")

    # Test de conexión
    if user_text.lower() == "test_connection" and user_id == "health_check":
        print(f"🏥 [API] Test de conexión recibido")
        return ChatResponse(responses=[{"text": "Connection OK"}])

    output_channel = LoggingOutputChannel()
    user_msg = UserMessage(text=user_text, output_channel=output_channel, sender_id=user_id)

    try:
        print(f"🔹 [API] Procesando mensaje...")
        await agent.handle_message(user_msg)
        print(f"🔹 [API] Mensaje procesado exitosamente")

        if not output_channel.messages:
            print("⚠️ [API] No se recibieron respuestas del agente")
            return ChatResponse(
                responses=[{"text": "Lo siento, no pude procesar tu mensaje en este momento."}],
                error="No response from agent"
            )

        print(f"📄 [API] {len(output_channel.messages)} mensajes en OutputChannel")
        
        # Procesar respuestas estructuradas de Rasa
        processed_responses = []
        
        for message in output_channel.messages:
            if isinstance(message, dict):
                # Verificar si es una respuesta estructurada (JSON)
                if "detected_intent" in message and "entities" in message:
                    # Es una respuesta estructurada de las actions
                    processed_responses.append({
                        "text": message.get("message", ""),
                        "type": "structured",
                        "data": {
                            "detected_intent": message.get("detected_intent"),
                            "entities": message.get("entities", []),
                            "timestamp": message.get("timestamp"),
                            "confidence": getattr(message, 'confidence', None)
                        }
                    })
                    print(f"🔍 [API] Respuesta estructurada: Intent={message.get('detected_intent')}, Entities={len(message.get('entities', []))}")
                
                elif "text" in message:
                    # Respuesta de texto normal
                    processed_responses.append({
                        "text": message["text"],
                        "type": "text"
                    })
                    
                elif "image" in message:
                    # Respuesta con imagen
                    processed_responses.append({
                        "image": message["image"],
                        "type": "image"
                    })
                    
                elif "custom" in message or "json_message" in message:
                    # Respuesta JSON custom
                    custom_data = message.get("custom") or message.get("json_message")
                    if isinstance(custom_data, dict) and "detected_intent" in custom_data:
                        # Es nuestra respuesta estructurada
                        processed_responses.append({
                            "text": custom_data.get("message", ""),
                            "type": "structured", 
                            "data": {
                                "detected_intent": custom_data.get("detected_intent"),
                                "entities": custom_data.get("entities", []),
                                "timestamp": custom_data.get("timestamp")
                            }
                        })
                    else:
                        # JSON custom genérico
                        processed_responses.append({
                            "custom": custom_data,
                            "type": "custom"
                        })
                else:
                    # Fallback para otros tipos
                    processed_responses.append(message)
            else:
                # Mensaje en formato string directo
                processed_responses.append({
                    "text": str(message),
                    "type": "text"
                })
        
        # Log del resultado procesado
        structured_count = len([r for r in processed_responses if r.get("type") == "structured"])
        print(f"📊 [API] {structured_count} respuestas estructuradas de {len(processed_responses)} total")
        
        return ChatResponse(responses=processed_responses)
    
    except Exception as e:
        print(f"❌ [API] Error procesando mensaje: {e}")
        import traceback
        traceback.print_exc()  # Para debug adicional
        return ChatResponse(
            responses=[{
                "text": "Hubo un error procesando tu mensaje. Por favor intenta de nuevo.",
                "type": "error"
            }], 
            error=str(e)
        )

# ---------- Consola interactiva mejorada ----------
def consola_listener():
    if agent is None:
        print("❌ [Consola] Agent no disponible - consola deshabilitada")
        return
        
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    print("🎮 [Consola] Consola interactiva iniciada")
    print("💡 [Consola] Escribe 'exit', 'quit' o 'salir' para cerrar")
    print("=" * 50)

    while True:
        try:
            user_text = input(">> Tú: ").strip()
            if user_text.lower() in ["exit", "quit", "salir"]:
                print("👋 Cerrando consola...")
                break
                
            if not user_text:
                continue

            print(f"➡️ [Consola] Procesando: {user_text}")
            output_channel = LoggingOutputChannel()
            user_msg = UserMessage(text=user_text, output_channel=output_channel, sender_id="console_user")

            try:
                print(f"🔹 [Consola] Enviando a agente...")
                loop.run_until_complete(agent.handle_message(user_msg))
                print(f"🔹 [Consola] Respuesta recibida")
                
                # Mostrar respuestas del bot
                if output_channel.messages:
                    for i, response in enumerate(output_channel.messages):
                        print(f"🤖 Bot ({i+1}): ", end="")
                        
                        if response.get("text"):
                            print(response["text"])
                        elif response.get("image"):
                            print(f"[Imagen: {response['image']}]")
                        elif response.get("custom"):
                            print(f"[Custom: {response['custom']}]")
                        else:
                            print(f"[Respuesta completa: {response}]")
                else:
                    print("🔇 [Consola] Bot no respondió")
                    
                # Mostrar health
                health = output_channel.get_health_status()
                if health["error_count"] > 0:
                    print(f"⚠️ [Consola] Errores detectados: {health['error_count']}")
                    
            except Exception as e:
                print(f"❌ [Consola] Error: {e}")
                
            print("-" * 50)

        except KeyboardInterrupt:
            print("\n👋 Cerrando consola...")
            break
        except EOFError:
            print("\n👋 Cerrando consola...")
            break
        except Exception as e:
            print(f"❌ [Consola] Error inesperado: {e}")

# ---------- Startup ----------
if __name__ == "__main__":
    # Iniciar consola en hilo separado solo si el agente está disponible
    if agent is not None:
        hilo_consola = threading.Thread(target=consola_listener, daemon=True)
        hilo_consola.start()
        print("🧵 [Main] Consola iniciada en hilo separado")
    else:
        print("⚠️ [Main] Consola deshabilitada - agente no disponible")

    print(f"🌐 [Main] Iniciando servidor web en puerto {PORT}")
    print("✅ [Main] CORS habilitado para Flutter")
    uvicorn.run(app, host="0.0.0.0", port=PORT, reload=False)