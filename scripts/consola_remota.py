import requests

# Configuración del endpoint
API_URL = "http://localhost:8000/message"  # Cambia si tu servidor está en otra IP/puerto
RESET_URL = "http://localhost:8000/reset_context"

# Usuario que vamos a usar en la conversación
USER_ID = "remote_user"

def enviar_mensaje(texto):
    """Envía un mensaje al bot y devuelve la respuesta"""
    payload = {"message": texto, "user_id": USER_ID}
    try:
        respuesta = requests.post(API_URL, json=payload)
        data = respuesta.json()
        if data.get("responses"):
            for i, msg in enumerate(data["responses"]):
                print(f"🤖 Bot ({i+1}): {msg.get('text', msg)}")
        else:
            print("⚠️ El bot no respondió.")
    except Exception as e:
        print(f"❌ Error al enviar mensaje: {e}")

def reset_contexto():
    """Reinicia slots y contexto del usuario"""
    try:
        r = requests.post(f"{RESET_URL}?user_id={USER_ID}")
        if r.status_code == 200:
            print("🔄 Contexto reiniciado exitosamente")
        else:
            print(f"⚠️ No se pudo reiniciar el contexto: {r.text}")
    except Exception as e:
        print(f"❌ Error al reiniciar contexto: {e}")

def main():
    print("🗨️ Conversación remota con el bot (escribe 'exit' para salir, 'reset' para reiniciar contexto)")
    while True:
        texto = input(">> Tú: ").strip()
        if texto.lower() in ["exit", "quit", "salir"]:
            break
        elif texto.lower() == "reset":
            reset_contexto()
            continue
        elif not texto:
            continue
        enviar_mensaje(texto)

if __name__ == "__main__":
    main()
