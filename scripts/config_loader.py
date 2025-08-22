import yaml
from pathlib import Path
from typing import Dict, Any, List

class ConfigLoader:
    @staticmethod
    def _load_yaml(path: Path) -> Dict[str, Any]:
        """Carga un YAML y devuelve un diccionario vacío si no existe."""
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    @staticmethod
    def cargar_config(path="intents_config.yml") -> Dict[str, Any]:
        """
        Carga un archivo de configuración de intents.
        Devuelve un diccionario con:
        {
            "intents": {...},
            "fallback": {...},
            "flow_groups": {...},
            "story_starters": [...],
            "follow_up_only": [...]
        }
        """
        path_obj = Path(path)
        if not path_obj.is_absolute():
            path_obj = (Path(__file__).parent.parent / path_obj).resolve()
        if not path_obj.exists():
            raise FileNotFoundError(f"No se encontró el archivo: {path_obj}")

        data = ConfigLoader._load_yaml(path_obj)
        intents_raw = data.get("intents", {})
        flow_groups = data.get("flow_groups", {})  # Nuevo: cargar flow_groups

        # Primero cargamos todos los intents y sus archivos
        intents: Dict[str, Any] = {}
        grupos: Dict[str, List[str]] = {}  # Para mapear grupo -> lista de intents
        story_starters: List[str] = []
        follow_up_only: List[str] = []

        for intent_name, intent_data in intents_raw.items():
            tipo = intent_data.get("tipo")
            action = intent_data.get("action")
            grupo = intent_data.get("grupo")
            archivo = intent_data.get("archivo")
            next_intents_raw = intent_data.get("next_intents", [])
            story_starter = intent_data.get("story_starter", True)  # Default True para compatibilidad

            # Clasificar intent según story_starter
            if story_starter:
                story_starters.append(intent_name)
            else:
                follow_up_only.append(intent_name)

            # Cargar contenido del archivo
            file_data = ConfigLoader._load_yaml(path_obj.parent / archivo) if archivo else {}

            if tipo == "ejemplos":
                intent_obj = {
                    "tipo": "ejemplos",
                    "limitado": intent_data.get("limitado", False),
                    "ejemplos": file_data.get("ejemplos", []),
                    "responses": file_data.get("responses", {}),
                    "action": action,
                    "grupo": grupo,
                    "story_starter": story_starter,
                    "next_intents_raw": next_intents_raw  # se procesará después
                }
            elif tipo == "template":
                intent_obj = {
                    "tipo": "template",
                    "action": action,
                    "templates": file_data.get("templates", []),
                    "entities": file_data.get("entities", []),
                    "grupo": grupo,
                    "story_starter": story_starter,
                    "next_intents_raw": next_intents_raw  # se procesará después
                }
            else:
                raise ValueError(f"Tipo de intent desconocido para '{intent_name}': {tipo}")

            intents[intent_name] = intent_obj

            # Mapear grupo -> intents
            if grupo:
                grupos.setdefault(grupo, []).append(intent_name)

        # Función para expandir next_intents incluyendo flow_groups
        def expand_next_intents(next_list: List[str], visited: set = None) -> List[str]:
            if visited is None:
                visited = set()
            expanded = []
            for n in next_list:
                if n in visited:
                    continue
                if n in flow_groups:  # Es un flow_group
                    visited.add(n)
                    expanded.extend(expand_next_intents(flow_groups[n], visited))
                elif n in grupos:  # Es un grupo de intents
                    visited.add(n)
                    expanded.extend(grupos[n])
                else:  # Es un intent individual
                    expanded.append(n)
            
            # Eliminar duplicados manteniendo orden
            seen = set()
            return [x for x in expanded if not (x in seen or seen.add(x))]

        # Ahora expandimos next_intents incluyendo flow_groups
        for intent_name, intent_obj in intents.items():
            expanded_next = expand_next_intents(intent_obj.get("next_intents_raw", []))
            intent_obj["next_intents"] = expanded_next
            # Borrar la clave temporal
            del intent_obj["next_intents_raw"]

        fallback = data.get("fallback", {})

        return {
            "intents": intents,
            "fallback": fallback,
            "flow_groups": flow_groups,
            "story_starters": sorted(story_starters),
            "follow_up_only": sorted(follow_up_only)
        }

    @staticmethod
    def get_conversation_flow_stats(config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analiza el flujo de conversación y devuelve estadísticas útiles.
        """
        intents = config.get("intents", {})
        story_starters = config.get("story_starters", [])
        follow_up_only = config.get("follow_up_only", [])
        flow_groups = config.get("flow_groups", {})
        
        # Contar conexiones entre intents
        connections = {}
        for intent_name, intent_data in intents.items():
            next_intents = intent_data.get("next_intents", [])
            connections[intent_name] = len(next_intents)
        
        # Encontrar intents sin salida (terminales)
        terminal_intents = [name for name, count in connections.items() if count == 0]
        
        # Encontrar intents más conectados
        most_connected = max(connections.items(), key=lambda x: x[1]) if connections else None
        
        return {
            "total_intents": len(intents),
            "story_starters_count": len(story_starters),
            "follow_up_only_count": len(follow_up_only),
            "flow_groups_count": len(flow_groups),
            "terminal_intents": terminal_intents,
            "most_connected_intent": most_connected[0] if most_connected else None,
            "max_connections": most_connected[1] if most_connected else 0,
            "average_connections": sum(connections.values()) / len(connections) if connections else 0
        }