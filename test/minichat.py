import requests
import sys

# ---------- CONFIGURACIÓN ----------
# URL del conector REST de Rasa
RASA_SERVER_URL = "http://localhost:8000/webhooks/rest/webhook"
SENDER_ID = "console_tester"
# -----------------------------------

def start_chat():
    """
    Inicia un bucle de chat interactivo con el servidor Rasa
    usando el endpoint REST (petición-respuesta).
    """
    print("✅ Chat iniciado. Escribí tu mensaje y presioná Enter.")
    print("   Para terminar, escribí 'salir'.")

    while True:
        try:
            # 1. Obtener mensaje del usuario
            message = input(">> Tú: ")

            # Salir si el usuario lo pide
            if message.lower() in ["salir", "exit", "quit"]:
                break
            
            # No enviar mensajes vacíos
            if not message.strip():
                continue

            # 2. Enviar el mensaje a Rasa
            # El payload para el conector REST usa 'sender' y 'message'
            payload = {
                "sender": SENDER_ID,
                "message": message
            }
            response = requests.post(RASA_SERVER_URL, json=payload)
            response.raise_for_status() # Lanza un error si la petición falla (ej. 404, 500)

            # 3. Recibir y mostrar la(s) respuesta(s) del bot
            bot_responses = response.json()
            if not bot_responses:
                print("🤖 Pompi: (No hubo respuesta)")
            
            for resp in bot_responses:
                # Rasa puede enviar múltiples mensajes (texto, imágenes, botones, etc.)
                # Aquí solo mostramos el texto.
                bot_text = resp.get("text", "(Respuesta sin texto)")
                print(f"🤖 Pompi: {bot_text}")

        except requests.exceptions.RequestException as e:
            print(f"\n❌ Error de conexión: No se pudo conectar a {RASA_SERVER_URL}.")
            print(f"   Asegurate de que tu servidor Rasa esté corriendo.")
            break
        except (KeyboardInterrupt, EOFError):
            # Permite salir con Ctrl+C o Ctrl+D
            break
        except Exception as e:
            print(f"\n❌ Ocurrió un error inesperado: {e}")
            break

    print("\n👋 ¡Hasta luego!")

if __name__ == "__main__":
    start_chat()