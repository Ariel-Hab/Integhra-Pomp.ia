import os
from dotenv import load_dotenv
import requests
import time
import json

# === CONFIG ===
load_dotenv("../.env.local")
RUNPOD_ENDPOINT = os.getenv("RUNPOD_ENDPOINT_ID")  # tu endpoint ID
API_KEY = os.getenv("RUNPOD_API_KEY")  # tu API key

# === FUNCIONES ===
def run_job(prompt: str):
    url = f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT}/run"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    body = {
        "input": {
            "prompt": prompt
        }
    }

    print(f"📤 Enviando prompt: {prompt}")
    res = requests.post(url, headers=headers, json=body)
    res.raise_for_status()
    job = res.json()
    print(f"✅ Job enviado: {job['id']}")
    return job["id"]

def get_result(job_id: str):
    url = f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT}/status/{job_id}"
    headers = {"Authorization": f"Bearer {API_KEY}"}

    print("⏳ Esperando resultado...")
    while True:
        res = requests.get(url, headers=headers)
        res.raise_for_status()
        job = res.json()
        if job["status"] == "COMPLETED":
            print("✅ Completado")
            return job["output"]
        elif job["status"] == "FAILED":
            raise RuntimeError("❌ El job falló.")
        time.sleep(2)

# === MAIN ===
if __name__ == "__main__":
    prompt = input("🧠 Escribí tu prompt: ")
    job_id = run_job(prompt)
    output = get_result(job_id)

    # Mostrar respuesta del modelo
    print("\n=== 🗣️ RESPUESTA DEL MODELO ===")
    print(json.dumps(output, indent=2, ensure_ascii=False))
