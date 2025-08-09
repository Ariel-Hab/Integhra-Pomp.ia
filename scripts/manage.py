#!/usr/bin/env python3
"""
Gestor de tareas para PompIA
----------------------------
Uso:
    python manage.py <comando>

Comandos disponibles:
    up          → Levanta los contenedores
    down        → Baja los contenedores
    build       → Construye imágenes Docker
    restart     → Reinicia el sistema con build
    logs        → Muestra logs en vivo
    shell       → Abre bash dentro del contenedor Rasa
    clean       → Limpieza de contenedores huérfanos
    prune       → Limpieza total de Docker (¡cuidado!)
    clean-all   → Limpieza profunda
    reset       → Borra todo y reconstruye
    train       → Entrena el bot
    run         → Ejecuta bot + acciones
    snapshot    → Guarda contexto del proyecto
    help        → Muestra esta ayuda
"""

import subprocess
import sys
import os

# Forzar UTF-8 para evitar errores con emojis en Windows
sys.stdout.reconfigure(encoding='utf-8')

# ====================
# Funciones utilitarias
# ====================
def run(cmd, shell=False, cwd=None):
    """Ejecuta un comando y muestra su salida en tiempo real."""
    pretty_cmd = ' '.join(cmd) if isinstance(cmd, list) else cmd
    print(f"⚙️  Ejecutando: {pretty_cmd} en {cwd or os.getcwd()}")
    try:
        subprocess.run(cmd, shell=shell, check=True, cwd=cwd)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error ejecutando: {pretty_cmd}")
        sys.exit(e.returncode)


# ====================
# Comandos del gestor
# ====================
def up():
    """Levanta los contenedores"""
    run(["docker", "compose", "up"])

def down():
    """Baja los contenedores"""
    run(["docker", "compose", "down"])

def build():
    """Construye las imágenes Docker"""
    run(["docker", "compose", "build"])

def restart():
    """Reinicia el sistema con build"""
    run("docker compose down && docker compose up --build", shell=True)

def logs():
    """Muestra logs en tiempo real"""
    run(["docker", "compose", "logs", "-f"])

def shell_():
    """Abre una shell dentro del contenedor Rasa"""
    run(["docker", "compose", "exec", "rasa", "bash"])

def clean():
    """Limpia contenedores y volúmenes huérfanos"""
    run(["docker", "compose", "down", "--volumes", "--remove-orphans"])

def prune():
    """Limpieza total de Docker (cuidado)"""
    run(["docker", "system", "prune", "-af", "--volumes"])

def clean_all():
    """Limpieza profunda: contenedores, imágenes, volúmenes y redes"""
    run(["docker", "container", "prune", "-f"])
    run(["docker", "image", "prune", "-af"])
    run(["docker", "volume", "prune", "-f"])
    run(["docker", "network", "prune", "-f"])

def reset():
    """Borra todo, reconstruye y levanta el sistema"""
    clean()
    build()
    up()

def train():
    """Entrena el bot dentro del contenedor"""
    run(["docker", "compose", "exec", "rasa", "rasa", "train"])

def run_agent():
    """Ejecuta bot y acciones juntas"""
    run(["docker", "compose", "up", "rasa", "actions"])

def snapshot():
    """Guarda contexto del proyecto"""
    python_exe = sys.executable
    try:
        result = subprocess.run(
            [python_exe, "scripts/savecontext.py"],
            capture_output=True, text=True, check=True
        )
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error ejecutando savecontext.py:\n{e.stderr}")

def update_deps_bot():
    """Actualiza dependencias en contenedor rasa (bot)"""
    run(["docker", "compose", "exec", "rasa", "poetry", "install", "--no-root", "--only", "bot", "--without", "dev"])

def update_deps_actions():
    """Actualiza dependencias en contenedor actions"""
    run(["docker", "compose", "exec", "rasa_actions", "poetry", "install", "--no-root", "--only", "actions", "--without", "dev"])

def update_deps_trainer():
    """Actualiza dependencias en contenedor trainer"""
    run(["docker", "compose", "exec", "rasa_trainer", "poetry", "install", "--no-root", "--only", "bot", "--without", "dev"])

def update_deps_all():
    """Actualiza dependencias en todos los contenedores"""
    update_deps_bot()
    update_deps_actions()
    update_deps_trainer()

def up_and_update_deps():
    """Levanta los contenedores en background y actualiza dependencias."""
    print("⚙️  Levantando contenedores en segundo plano...")
    run(["docker", "compose", "up", "-d"])
    print("⚙️  Actualizando dependencias en todos los contenedores...")
    update_deps_all()


def help():
    """Muestra la ayuda"""
    print(__doc__)

# Mapeo de comandos
commands = {
    "up": up,
    "down": down,
    "build": build,
    "restart": restart,
    "logs": logs,
    "shell": shell_,
    "clean": clean,
    "prune": prune,
    "clean-all": clean_all,
    "reset": reset,
    "train": train,
    "run": run_agent,
    "snapshot": snapshot,
    "help": help,
    "update_deps_bot": update_deps_bot,
    "update_deps_actions": update_deps_actions,
    "update_deps_trainer": update_deps_trainer,
    "update_deps_all": update_deps_all,
    "up_update_deps": up_and_update_deps,
}

def update_deps_local():
    """Instala dependencias locales para bot y actions"""
    print("⚙️  Instalando dependencias locales (bot + actions)...")
    run(["poetry", "install", "--with", "bot,actions"])

# Funciones para correr localmente (sin contenedor)
def train_local():
    """Entrena el bot localmente"""
    update_deps_local()
    run(["poetry", "run", "rasa", "train"], cwd="bot")

def run_bot_local():
    """Ejecuta el bot localmente"""
    update_deps_local()
    run(["poetry", "run", "rasa", "run"], cwd="bot")

def run_actions_local():
    """Ejecuta el servidor de acciones localmente"""
    update_deps_local()
    run(["poetry", "run", "rasa", "run", "actions"], cwd="actions")


# Mapeo de comandos (agregar estos nuevos comandos)
commands.update({
    "train_local": train_local,
    "run_bot_local": run_bot_local,
    "run_actions_local": run_actions_local,
})


# Punto de entrada
def main():
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        help()
        sys.exit(1)
    command = sys.argv[1]
    commands[command]()

if __name__ == "__main__":
    main()
