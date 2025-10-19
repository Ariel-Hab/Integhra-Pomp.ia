import asyncio
import websockets
import requests
import threading
import sys

# ---------- CONFIGURACIÓN ----------
# Asegurate de que coincidan con tu servidor
RASA_SERVER_URL = "http://localhost:8000"
WEBSOCKET_URL = "ws://localhost:8000/ws"
USER_ID = "console_tester"
# -----------------------------------

async def listen_to_websocket():
    """
    Se conecta al WebSocket y escucha mensajes del servidor.
    Esta función corre de forma asíncrona y para siempre.
    """
    uri = f"{WEBSOCKET_URL}/{USER_ID}"
    print(f"📡 Conectando al WebSocket en {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Conexión WebSocket establecida. ¡Listo para recibir respuestas!")
            # Bucle infinito para escuchar mensajes
            async for message in websocket:
                if message == "[END_OF_STREAM]":
                    # Cuando llega el marcador de fin, imprimimos una nueva línea
                    # para separar la respuesta del siguiente prompt de usuario.
                    print("\n>> Tú: ", end="", flush=True)
                else:
                    # Imprime cada chunk sin saltar de línea
                    print(message, end="", flush=True)
    except Exception as e:
        print(f"\n❌ Error de WebSocket: {e}")
        print("   Asegurate de que tu servidor FastAPI esté corriendo.")
        sys.exit()

def send_messages():
    """
    Toma la entrada del usuario y la envía al servidor Rasa vía HTTP POST.
    Esta función es síncrona y bloqueante.
    """
    url = f"{RASA_SERVER_URL}/message"
    print("⌨️  Escribí tu mensaje y presioná Enter. Escribí 'salir' para terminar.")
    print(">> Tú: ", end="", flush=True)

    while True:
        try:
            message = input()
            if message.lower() in ["salir", "exit", "quit"]:
                break
            if not message:
                print(">> Tú: ", end="", flush=True)
                continue

            # Enviar el mensaje al endpoint de Rasa
            response = requests.post(url, json={"message": message, "user_id": USER_ID})
            response.raise_for_status() # Lanza un error si la petición falla

        except requests.exceptions.RequestException as e:
            print(f"\n❌ Error enviando mensaje HTTP: {e}")
        except (KeyboardInterrupt, EOFError):
            break
    
    print("\n👋 ¡Hasta luego!")
    sys.exit()

def main():
    """
    Orquesta el cliente, corriendo el listener de input en un hilo
    y el listener de WebSocket en el bucle de eventos principal.
    """
    # La función input() es "bloqueante", paraliza todo.
    # El truco es correrla en su propio hilo para que no interfiera
    # con el listener asíncrono del WebSocket.
    input_thread = threading.Thread(target=send_messages, daemon=True)
    input_thread.start()

    # El listener del WebSocket corre en el hilo principal
    asyncio.run(listen_to_websocket())

if __name__ == "__main__":
    main()