#!/usr/bin/env python3
"""
Consola interactiva para conversar con el bot servidor HTTP
"""

import json
import urllib.request
import urllib.parse

def check_server_status():
    """Check if bot server is running"""
    try:
        req = urllib.request.Request("http://localhost:8000/health")
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                result = json.loads(response.read().decode())
                print("✅ Servidor bot está funcionando")
                return True
            else:
                print(f"⚠️ Servidor responde con estado: {response.status}")
                return False
    except Exception as e:
        print(f"❌ Servidor bot no está disponible: {e}")
        print("💡 Inicia el servidor con: poetry run manage bot")
        return False

def send_message(message, user_id="console_user"):
    """Send message to bot server via HTTP"""
    try:
        data = {
            "message": message,
            "user_id": user_id
        }
        
        req = urllib.request.Request(
            "http://localhost:8000/message",
            data=json.dumps(data).encode(),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=60) as response:
            if response.status == 200:
                result = json.loads(response.read().decode())
                return result
            else:
                error_text = response.read().decode()
                print(f"❌ Error del servidor: {response.status}")
                print(f"Detalle: {error_text}")
                return None
                
    except urllib.error.URLError as e:
        if "Connection refused" in str(e):
            print("❌ No se puede conectar al servidor bot en localhost:8000")
            print("💡 Asegúrate de que el bot esté ejecutándose con: poetry run manage bot")
        elif "timed out" in str(e):
            print("❌ Timeout esperando respuesta del servidor")
        else:
            print(f"❌ Error de red: {e}")
        return None
    except Exception as e:
        print(f"❌ Error enviando mensaje: {e}")
        return None

def reload_server_model():
    """Reload model on running server"""
    try:
        req = urllib.request.Request(
            "http://localhost:8000/reload_model",
            method='POST',
            headers={'Content-Type': 'application/json'}
        )
        
        print("🔄 Enviando comando de recarga al servidor...")
        print("⏳ Esto puede tomar varios minutos...")
        
        with urllib.request.urlopen(req, timeout=300) as response:  # 5 minute timeout
            if response.status == 200:
                result = json.loads(response.read().decode())
                print("✅ Modelo recargado en el servidor")
                print(f"Respuesta: {result}")
                return True
            else:
                error_text = response.read().decode()
                print(f"❌ Error recargando: {response.status}")
                print(f"Detalle: {error_text}")
                return False
                
    except urllib.error.URLError as e:
        if "timed out" in str(e):
            print("❌ Timeout recargando modelo (>5 minutos)")
        else:
            print(f"❌ Error de red: {e}")
        return False
    except Exception as e:
        print(f"❌ Error recargando modelo: {e}")
        return False

def interactive_chat():
    """Start interactive chat session with HTTP server"""
    print("🤖 Chat con PompIA (Cliente HTTP)")
    print("💡 Conectando al servidor en localhost:8000")
    print("💡 Escribe 'quit', 'exit' o 'salir' para terminar")
    print("💡 Escribe 'reload' para recargar el modelo del servidor")
    print("💡 Escribe 'status' para verificar el estado del servidor")
    print("-" * 60)
    
    # Check server first
    if not check_server_status():
        return
    
    user_id = "console_user"
    
    while True:
        try:
            user_input = input(">> Tú: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'salir', 'q']:
                print("👋 ¡Hasta luego!")
                break
            
            if user_input.lower() == 'status':
                check_server_status()
                continue
            
            if user_input.lower() == 'reload':
                reload_server_model()
                continue
                
            if not user_input:
                continue
                
            print("⏳ Enviando mensaje al servidor...")
            response = send_message(user_input, user_id)
            
            if response is None:
                print("❌ No se pudo conectar al servidor")
                print("💡 Verifica que esté ejecutándose: poetry run manage bot")
                continue
            
            if response.get('responses'):
                for i, msg in enumerate(response['responses']):
                    if isinstance(msg, dict) and 'text' in msg:
                        print(f"🤖 Bot: {msg['text']}")
                    elif isinstance(msg, dict):
                        # Handle other message types
                        if 'image' in msg:
                            print(f"🖼️ Bot: [Imagen: {msg['image']}]")
                        elif 'custom' in msg:
                            print(f"🔧 Bot: [Respuesta personalizada: {msg['custom']}]")
                        else:
                            print(f"🤖 Bot: {msg}")
                    else:
                        print(f"🤖 Bot: {msg}")
            
            if response.get('error'):
                print(f"⚠️ Error del bot: {response['error']}")
            
            if not response.get('responses') and not response.get('error'):
                print("🔇 Bot no respondió")
                
        except KeyboardInterrupt:
            print("\n👋 Chat interrumpido por el usuario")
            break
        except EOFError:
            print("\n👋 Chat terminado")
            break
        except Exception as e:
            print(f"❌ Error en chat: {e}")

def main():
    """Main entry point"""
    interactive_chat()

if __name__ == "__main__":
    main()