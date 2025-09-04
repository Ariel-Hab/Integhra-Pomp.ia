#!/usr/bin/env python3
"""
Gestor de tareas PompIA con menú interactivo y acceso rápido
-----------------------------------------------------------
Uso:
    python manage.py            # Muestra menú principal
    python manage.py local      # Abre menú Bot Local
    python manage.py docker     # Abre menú Docker
    python manage.py deps       # Abre menú Dependencias
    python manage.py clean      # Abre menú Limpieza
    python manage.py snapshot   # Ejecuta snapshot directamente
"""

import subprocess
import sys
import os

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

def run(cmd, shell=False, cwd=None):
    pretty_cmd = " ".join(cmd) if isinstance(cmd, list) else cmd
    print(f"\n⚙️  Ejecutando: {pretty_cmd} (cwd: {cwd or os.getcwd()})\n")
    try:
        subprocess.run(cmd, shell=shell, check=True, cwd=cwd)
        print("✅ Comando ejecutado correctamente.\n")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error ejecutando: {pretty_cmd}")
        try:
            if e.stdout:
                print(e.stdout)
            if e.stderr:
                print(e.stderr)
        except Exception:
            pass
        sys.exit(e.returncode)

# --- Funciones Docker ---
def docker_up(): run(["docker", "compose", "up"])
def docker_build(): run(["docker", "compose", "build"])
def docker_restart(): run("docker compose down && docker compose up --build", shell=True)
def docker_logs(): run(["docker", "compose", "logs", "-f"])
def docker_shell_rasa(): run(["docker", "compose", "exec", "rasa", "bash"])
def docker_run_agent(): run(["docker", "compose", "up", "rasa", "actions","--actions","actions.actions"])
def docker_train_container(): run(["docker", "compose", "exec", "rasa", "rasa", "train"])

# --- Dependencias Contenedor ---
def update_deps_container_rasa(): run(["docker", "compose", "exec", "rasa", "poetry", "install", "--no-root", "--only", "bot", "--without", "dev"])
def update_deps_container_actions(): run(["docker", "compose", "exec", "rasa_actions", "poetry", "install", "--no-root", "--only", "actions", "--without", "dev"])
def update_deps_container_trainer(): run(["docker", "compose", "exec", "rasa_trainer", "poetry", "install", "--no-root", "--only", "bot", "--without", "dev"])
def update_deps_all_containers():
    update_deps_container_rasa()
    update_deps_container_actions()
    update_deps_container_trainer()

# --- Dependencias Local ---
def install_deps_bot_local(): run(["poetry", "install", "--only", "bot", "--without", "dev"])
def install_deps_actions_local(): run(["poetry", "install", "--only", "actions", "--without", "dev"])

# --- Bot Local ---
def train_local_nlu():
    install_deps_bot_local()
    run(["poetry", "run", "python", "entrenador/train.py"], cwd="bot")
def train_local():
    install_deps_bot_local()
    run(["poetry", "run", "rasa", "train"], cwd="bot")
def run_bot_local():
    install_deps_bot_local()
    run(["poetry", "run", "python", "main.py"], cwd="bot")
def run_actions_local():
    install_deps_actions_local()
    run(["poetry", "run", "rasa", "run", "actions","--actions","actions"])

# --- Limpieza ---
def clean_down_volumes(): run(["docker", "compose", "down", "--volumes", "--remove-orphans"])
def prune_system(): run(["docker", "system", "prune", "-af", "--volumes"])
def clean_all_deep():
    run(["docker", "container", "prune", "-f"])
    run(["docker", "image", "prune", "-af"])
    run(["docker", "volume", "prune", "-f"])
    run(["docker", "network", "prune", "-f"])
def reset_all():
    clean_down_volumes()
    docker_build()
    docker_up()

# --- Snapshot ---
def snapshot():
    script_path = os.path.join("scripts", "savecontext.py")
    python_exe = sys.executable or "python"
    if not os.path.exists(script_path):
        print(f"❌ No se encontró '{script_path}'. Ejecuta este script desde la raíz del proyecto.")
        return
    try:
        result = subprocess.run([python_exe, script_path], capture_output=True, text=True, check=True)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)
        print("✅ Snapshot completado.\n")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error ejecutando '{script_path}':")
        if e.stdout:
            print(e.stdout)
        if e.stderr:
            print(e.stderr)

# --- Menús ---
def ejecutar_menu(titulo, opciones):
    while True:
        print(f"\n{titulo}")
        print("=" * len(titulo))
        for key, (desc, _) in opciones.items():
            print(f"{key}) {desc}")
        choice = input("\nSelecciona una opción: ").strip()
        if choice in opciones:
            accion = opciones[choice][1]
            if accion is None:
                break
            try:
                accion()
            except KeyboardInterrupt:
                print("\n✋ Interrumpido por el usuario.")
        else:
            print("❌ Opción no válida. Intenta de nuevo.")

def menu_docker():
    opciones = {
        "1": ("Levantar contenedores", docker_up),
        "2": ("Construir imágenes", docker_build),
        "3": ("Reiniciar con build", docker_restart),
        "4": ("Ver logs", docker_logs),
        "5": ("Shell en contenedor Rasa", docker_shell_rasa),
        "6": ("Ejecutar bot + acciones (compose up)", docker_run_agent),
        "7": ("Entrenar bot (contenedor Rasa)", docker_train_container),
        "0": ("Volver", None),
    }
    ejecutar_menu("📦 Menú Docker", opciones)

def menu_dependencias():
    opciones = {
        "1": ("Actualizar deps en contenedor Rasa", update_deps_container_rasa),
        "2": ("Actualizar deps en contenedor Actions", update_deps_container_actions),
        "3": ("Actualizar deps en contenedor Trainer", update_deps_container_trainer),
        "4": ("Actualizar deps en TODOS los contenedores", update_deps_all_containers),
        "5": ("Instalar deps bot local", install_deps_bot_local),
        "6": ("Instalar deps actions local", install_deps_actions_local),
        "0": ("Volver", None),
    }
    ejecutar_menu("📚 Menú Dependencias", opciones)

def menu_local():
    opciones = {
        "1": ("Entrenar bot local (entrenador/train.py)", train_local_nlu),
        "2": ("Ejecutar bot local (main.py)", run_bot_local),
        "3": ("Ejecutar servidor de acciones local", run_actions_local),
        "4": ("Entrenar modelo local (rasa run train)", train_local),
        "0": ("Volver", None),
    }
    ejecutar_menu("💻 Menú Bot Local", opciones)

def menu_limpieza():
    opciones = {
        "1": ("Bajar contenedores + volúmenes", clean_down_volumes),
        "2": ("Prune total de Docker (peligroso)", prune_system),
        "3": ("Limpieza profunda (contenedores, imágenes, volúmenes, redes)", clean_all_deep),
        "4": ("Reset (down + build + up)", reset_all),
        "0": ("Volver", None),
    }
    ejecutar_menu("🧹 Menú Limpieza", opciones)

# --- Menú principal ---
def menu_principal():
    opciones = {
        "1": ("Docker", menu_docker),
        "2": ("Dependencias", menu_dependencias),
        "3": ("Bot Local", menu_local),
        "4": ("Limpieza", menu_limpieza),
        "5": ("Snapshot (guardar contexto)", snapshot),
        "0": ("Salir", None),
    }
    ejecutar_menu("🚀 Gestor de tareas PompIA", opciones)

# --- Main ---
def main():
    if len(sys.argv) == 1:
        # Sin argumentos: menú principal
        menu_principal()
    else:
        cmd = sys.argv[1].lower()
        if cmd == "local":
            menu_local()
        elif cmd == "docker":
            menu_docker()
        elif cmd == "deps":
            menu_dependencias()
        elif cmd == "clean":
            menu_limpieza()
        elif cmd == "snapshot" :
            snapshot()
        else:
            print(f"❌ Comando '{cmd}' no reconocido.\n")
            menu_principal()

if __name__ == "__main__":
    main()
