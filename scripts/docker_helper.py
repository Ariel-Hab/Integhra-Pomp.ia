#!/usr/bin/env python3
"""
Docker Helper for PompIA
------------------------
Simplifies management of bot/actions containers and environment monitoring.
Designed for interactive development with mounted volumes.
"""

import subprocess
import sys
import os

# Root dir of the project (docker-compose context)
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run(cmd, shell=False, cwd=None):
    """Run a command and print it nicely"""
    cwd = cwd or ROOT_DIR
    print(f"\n⚙️  Ejecutando: {' '.join(cmd) if isinstance(cmd, list) else cmd} (cwd: {cwd})\n")
    try:
        subprocess.run(cmd, shell=shell, check=True, cwd=cwd)
        print("✅ Comando ejecutado correctamente.\n")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error ejecutando: {cmd}")
        sys.exit(e.returncode)

# --- Container commands ---
def build(service=None):
    """Build all containers or a specific one"""
    cmd = ["docker-compose", "build"]
    if service:
        cmd.append(service)
    run(cmd)

def up(service=None, detach=True):
    """Start all containers or a specific one"""
    cmd = ["docker-compose", "up"]
    if detach:
        cmd.append("-d")
    if service:
        cmd.append(service)
    run(cmd)

def down(service=None):
    """Stop all containers or a specific one"""
    cmd = ["docker-compose", "down"] if service is None else ["docker-compose", "stop", service]
    run(cmd)

def restart(service=None, rebuild=False):
    """
    Restart containers.
    - service: name of the container to restart
    - rebuild: whether to rebuild the image before starting
    """
    if service:
        down(service)
        if rebuild:
            build(service)
        up(service)
    else:
        down()
        if rebuild:
            build()
        up()

def logs(service=None):
    cmd = ["docker-compose", "logs", "-f"]
    if service:
        cmd.append(service)
    run(cmd)

def exec_cmd(service, command, interactive=False):
    """Run a command inside a container"""
    cmd = ["docker-compose", "exec"]
    if interactive:
        cmd.append("-it")
    cmd.append(service)
    cmd += command
    run(cmd)

# --- Project commands ---
def start_bot_interactive():
    """Open a bash shell in the bot container for development"""
    print("🚀 Opening interactive shell in Rasa Bot container...")
    exec_cmd("rasa_bot", ["bash"], interactive=True)

def start_actions_interactive():
    """Open a bash shell in the actions container for development"""
    print("🚀 Opening interactive shell in Actions container...")
    exec_cmd("rasa_actions", ["bash"], interactive=True)

# Optional direct commands
def run_bot():
    exec_cmd("rasa_bot", ["poetry", "run", "python", "main.py"], interactive=True)

def run_actions():
    exec_cmd("rasa_actions", ["poetry", "run", "rasa", "run", "actions", "--actions", "actions"], interactive=True)

# --- Monitoring / info ---
def status():
    print("🖥 Docker environment status:")
    run(["docker", "ps"])
    run(["docker", "images"])
    run(["docker", "volume", "ls"])
    run(["docker", "network", "ls"])

def describe_environment():
    print("🌐 Docker Environment Overview")
    print("Containers running:")
    run(["docker", "ps", "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"])
    print("Images available:")
    run(["docker", "images"])
    print("Volumes:")
    run(["docker", "volume", "ls"])
    print("Networks:")
    run(["docker", "network", "ls"])

# --- Menu ---
def menu():
    options = {
        "1": ("Build all containers", build),
        "2": ("Start all containers (detached)", up),
        "3": ("Stop all containers", down),
        "4": ("Restart everything", restart),
        "5": ("Show logs (bot)", lambda: logs("rasa_bot")),
        "6": ("Show logs (actions)", lambda: logs("rasa_actions")),
        "7": ("Open Rasa Bot container shell", start_bot_interactive),
        "8": ("Open Actions container shell", start_actions_interactive),
        "9": ("Status of Docker environment", status),
        "10": ("Describe full environment", describe_environment),
        "11": ("Restart Bot container", lambda: restart("rasa_bot")),
        "12": ("Restart Actions container", lambda: restart("rasa_actions")),
        "13": ("Restart Bot with rebuild", lambda: restart("rasa_bot", rebuild=True)),
        "14": ("Restart Actions with rebuild", lambda: restart("rasa_actions", rebuild=True)),
        "15": ("Run Bot directly (interactive)", run_bot),
        "16": ("Run Actions directly (interactive)", run_actions),
        "0": ("Exit", None)
    }

    while True:
        print("\n🚀 Docker Helper Menu")
        print("====================")
        for key, (desc, _) in options.items():
            print(f"{key}) {desc}")
        choice = input("\nSelecciona una opción: ").strip()
        if choice in options:
            action = options[choice][1]
            if action is None:
                break
            try:
                action()
            except KeyboardInterrupt:
                print("\n✋ Interrumpido por el usuario.")
        else:
            print("❌ Opción no válida. Intenta de nuevo.")

if __name__ == "__main__":
    menu()
