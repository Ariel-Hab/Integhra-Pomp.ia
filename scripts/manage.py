#!/usr/bin/env python3
"""
Simplified PompIA manager for running bot/actions and training
"""

import subprocess
import sys
import os
import urllib.request
import urllib.parse
import json
import time

def run(cmd, cwd=None):
    """Run a command and print its output."""
    print(f"\n⚙️  Ejecutando: {' '.join(cmd)} (cwd: {cwd or os.getcwd()})\n")
    try:
        subprocess.run(cmd, check=True, cwd=cwd)
        print("✅ Comando ejecutado correctamente.\n")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error ejecutando: {' '.join(cmd)}")
        sys.exit(e.returncode)

# --- Poetry commands for local development ---
def install_deps(group):
    """Install dependencies for a given group."""
    run(["poetry", "install", "--only", group, "--without", "dev"])

# --- Bot commands ---
def run_bot():
    install_deps("bot")
    run(["poetry", "run", "python", "main.py"], cwd="bot")

def train_bot_nlu():
    install_deps("bot")
    run(["poetry", "run", "python", "entrenador/train.py"], cwd="bot")

def train_bot_model():
    install_deps("bot")
    run(["poetry", "run", "rasa", "train"], cwd="bot")

def reload_bot_model():
    """Hot reload latest Rasa model in running agent via HTTP endpoint"""
    print("🔄 Iniciando recarga del modelo...")
    print("⏳ Esto puede tomar varios minutos debido a la carga de TensorFlow/BERT...")
    
    try:
        # Create POST request to reload endpoint with longer timeout
        req = urllib.request.Request(
            "http://localhost:8000/reload_model",
            method='POST',
            headers={'Content-Type': 'application/json'}
        )
        
        # Use much longer timeout for model loading (5 minutes)
        with urllib.request.urlopen(req, timeout=300) as response:
            if response.status == 200:
                result = json.loads(response.read().decode())
                print("✅ Bot model reloaded successfully")
                print(f"Response: {result}")
            else:
                print(f"❌ Failed to reload bot model. Status: {response.status}")
                error_text = response.read().decode()
                print(f"Response: {error_text}")
                
    except urllib.error.URLError as e:
        if "Connection refused" in str(e):
            print("❌ Could not connect to bot server. Make sure the bot is running on localhost:8000")
        elif "timed out" in str(e):
            print("❌ Timeout while reloading model (>5 minutes)")
            print("💡 Model loading is taking too long. This might indicate:")
            print("   - Large model size")
            print("   - Limited system resources") 
            print("   - Network issues with action server")
        else:
            print(f"❌ Network error: {e}")
    except Exception as e:
        print(f"❌ Error reloading model: {e}")

def check_bot_status():
    """Check if bot server is running and responsive"""
    try:
        req = urllib.request.Request("http://localhost:8000/")
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                result = json.loads(response.read().decode())
                print("✅ Bot server is running")
                print(f"Status: {result}")
                return True
            else:
                print(f"⚠️ Bot server responded with status: {response.status}")
                return False
    except Exception as e:
        print(f"❌ Bot server is not reachable: {e}")
        return False

def check_models():
    """Check for available models in the models directory"""
    models_path = "bot/models" if os.path.exists("bot/models") else "models"
    
    if not os.path.exists(models_path):
        print(f"❌ Models directory '{models_path}' does not exist")
        return False
    
    models = []
    for item in os.listdir(models_path):
        item_path = os.path.join(models_path, item)
        if os.path.isdir(item_path) or item.endswith(".tar.gz"):
            models.append(item)
    
    if models:
        print(f"✅ Found {len(models)} model(s) in '{models_path}':")
        for model in sorted(models, key=lambda x: os.path.getmtime(os.path.join(models_path, x)), reverse=True):
            model_path = os.path.join(models_path, model)
            mtime = os.path.getmtime(model_path)
            import datetime
            time_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            size = os.path.getsize(model_path) if os.path.isfile(model_path) else "N/A"
            print(f"  - {model} (modified: {time_str}, size: {size} bytes)")
        return True
    else:
        print(f"❌ No models found in '{models_path}'")
        print("💡 Run 'python manage.py train_model' to train a new model first")
        return False

def test_chat():
    """Test a simple chat message"""
    if not check_bot_status():
        print("❌ Cannot test chat - bot server not running")
        return
    
    try:
        # Test message
        test_data = {
            "message": "hola",
            "user_id": "test_user"
        }
        
        req = urllib.request.Request(
            "http://localhost:8000/message",
            data=json.dumps(test_data).encode(),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status == 200:
                result = json.loads(response.read().decode())
                print("✅ Chat test successful")
                print(f"Bot response: {result}")
            else:
                print(f"❌ Chat test failed. Status: {response.status}")
                print(f"Response: {response.read().decode()}")
                
    except Exception as e:
        print(f"❌ Chat test error: {e}")

# --- Actions commands ---
def run_actions():
    install_deps("actions")
    run(["poetry", "run", "rasa", "run", "actions", "--actions", "actions"])

# --- Main entry ---
def main():
    if len(sys.argv) < 2:
        print("Uso: python manage.py [bot|actions|train_nlu|train_model|reload_model|check_models|status|test_chat]")
        sys.exit(0)

    cmd = sys.argv[1].lower()
    if cmd == "bot":
        run_bot()
    elif cmd == "actions":
        run_actions()
    elif cmd == "train":
        train_bot_nlu()
    elif cmd == "rasa_train":
        train_bot_model()
    elif cmd == "reload_model":
        reload_bot_model()
    elif cmd == "check_models":
        check_models()
    elif cmd == "status":
        check_bot_status()
    elif cmd == "test_chat":
        test_chat()
    else:
        print(f"❌ Comando '{cmd}' no reconocido.")
        print("Comandos disponibles: bot, actions, train, rasa_train, reload_model, check_models, status, test_chat")

if __name__ == "__main__":
    main()