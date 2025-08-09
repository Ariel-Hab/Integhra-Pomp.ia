import os
import json
import subprocess
from pathlib import Path
from datetime import datetime
import sys
sys.stdout.reconfigure(encoding='utf-8')
import tomli
import yaml

BASE_DIR = Path.cwd()
CONTEXT_FILE = BASE_DIR / "project_context.json"

def get_file_structure_summary(base_dir, max_depth=3):
    """Recorre la estructura de archivos hasta max_depth y devuelve un árbol resumido."""
    def helper(path, depth):
        if depth > max_depth:
            return {"note": "max depth reached"}
        try:
            files = [
                f for f in os.listdir(path)
                if os.path.isfile(os.path.join(path, f)) and not f.endswith('.pyc')
            ]
            dirs = [
                d for d in os.listdir(path)
                if os.path.isdir(os.path.join(path, d))
                and d != '__pycache__'
                and not d.startswith('.git')
            ]
            return {
                "num_files": len(files),
                "num_dirs": len(dirs),
                "files": files,
                "dirs": {d: helper(os.path.join(path, d), depth+1) for d in dirs}
            }
        except Exception:
            return {"error": "no access"}
    return helper(base_dir, 0)

def get_poetry_groups_dependencies(pyproject_path):
    """Lee las dependencias generales y por grupos desde pyproject.toml."""
    try:
        with open(pyproject_path, "rb") as f:
            data = tomli.load(f)
        tool_poetry = data.get("tool", {}).get("poetry", {})
        groups = tool_poetry.get("group", {})

        groups_deps = {
            group_name: group_data.get("dependencies", {})
            for group_name, group_data in groups.items()
        }
        general_deps = tool_poetry.get("dependencies", {})

        return {"general": general_deps, "groups": groups_deps}
    except Exception as e:
        return {"error": f"No se pudo leer pyproject.toml: {e}"}

def read_file_if_exists(path, max_chars=3000):
    """Lee un archivo si existe, recortando a max_chars para evitar sobrecarga."""
    p = Path(path)
    if p.exists():
        text = p.read_text(encoding="utf-8", errors="ignore")
        return text[:max_chars] + ("..." if len(text) > max_chars else "")
    return None

def get_docker_info():
    """Extrae configuración de docker-compose.yml y Dockerfiles."""
    info = {}
    docker_compose_path = BASE_DIR / "docker-compose.yml"
    if docker_compose_path.exists():
        try:
            with open(docker_compose_path, "r", encoding="utf-8") as f:
                info["docker_compose"] = yaml.safe_load(f)
        except Exception as e:
            info["docker_compose_error"] = str(e)
    # Buscar Dockerfiles
    dockerfiles = list(BASE_DIR.glob("Dockerfile*"))
    dockerfile_contents = {}
    for df in dockerfiles:
        dockerfile_contents[df.name] = read_file_if_exists(df, max_chars=3000)
    if dockerfile_contents:
        info["dockerfiles"] = dockerfile_contents
    return info

def get_git_info():
    """Devuelve info de Git si está disponible."""
    try:
        branch = subprocess.check_output(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        commit = subprocess.check_output(
            ['git', 'log', '-1', '--pretty=format:%h - %s'],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        status = subprocess.check_output(
            ['git', 'status', '--short', '--untracked-files=no'],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        return {"branch": branch, "last_commit": commit, "status_summary": status}
    except Exception:
        return None

def main():
    
    try:
        context = {
            "timestamp": datetime.now().isoformat(),
            "base_dir": str(BASE_DIR),
            "file_structure": get_file_structure_summary(BASE_DIR),
            "poetry_dependencies": get_poetry_groups_dependencies(BASE_DIR / "pyproject.toml"),
            "docker_info": get_docker_info(),
            "manage_py": read_file_if_exists(BASE_DIR / "manage.py"),
            "scripts": {p.name: read_file_if_exists(p) for p in (BASE_DIR / "scripts").glob("*.py")} if (BASE_DIR / "scripts").exists() else {},
            "readme_excerpt": read_file_if_exists(BASE_DIR / "README.md", max_chars=2000),
            # "git_info": get_git_info()
        }

        with open(CONTEXT_FILE, "w", encoding="utf-8") as f:
            json.dump(context, f, indent=2, ensure_ascii=False)

        print(f"✅ Contexto guardado en {CONTEXT_FILE}")
    except Exception as e:
        print(f"❌ Error guardando contexto: {e}")

if __name__ == "__main__":
    main()
