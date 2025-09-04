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
    def cargar_config(
        context_path="context/context_config.yml",
        ejemplos_path="context/examples.yml",
        templates_path="context/templates.yml",
        responses_path="context/responses.yml",
        segments_path="context/segments.yml"  # NUEVO: soporte para segments
    ) -> Dict[str, Any]:
        """Carga la configuración completa de intents, entidades, slots y responses."""
        base_path = Path(__file__).parent.parent
        context_file = (base_path / context_path).resolve()
        ejemplos_file = (base_path / ejemplos_path).resolve()
        templates_file = (base_path / templates_path).resolve()
        responses_file = (base_path / responses_path).resolve()
        segments_file = (base_path / segments_path).resolve()  # NUEVO

        # Verificar archivos requeridos
        required_files = [context_file, ejemplos_file, templates_file, responses_file]
        for f in required_files:
            if not f.exists():
                raise FileNotFoundError(f"No se encontró el archivo: {f}")

        # Cargar todos los archivos
        context_data = ConfigLoader._load_yaml(context_file)
        ejemplos_data = ConfigLoader._load_yaml(ejemplos_file)
        templates_data = ConfigLoader._load_yaml(templates_file)
        responses_data = ConfigLoader._load_yaml(responses_file)
        segments_data = ConfigLoader._load_yaml(segments_file)  # NUEVO

        # Extraer configuraciones principales
        intents_raw = context_data.get("intents", {})
        entities_config = context_data.get("entities", {})
        slots_config = context_data.get("slots", {})
        detection_patterns = context_data.get("detection_patterns", {})
        flow_groups = context_data.get("flow_groups", {})
        story_starters = context_data.get("story_starters", [])
        follow_up_only = context_data.get("follow_up_only", [])
        
        # Configuraciones con defaults mejorados
        context_validation = context_data.get("context_validation", {})
        context_validation.setdefault("enabled", False)
        context_validation.setdefault("action", "action_context_validator")
        context_validation.setdefault("max_switches", 5)
        
        session_config = context_data.get("session_config", {})
        session_config.setdefault("session_expiration_time", 180)
        session_config.setdefault("carry_over_slots_to_new_session", True)
        
        fallback = context_data.get("fallback", {})
        fallback.setdefault("action", "action_fallback")
        fallback.setdefault("response", "Perdón, no entendí lo que quisiste decir.")
        fallback.setdefault("threshold", 0.6)

        intents: Dict[str, Any] = {}
        grupos: Dict[str, List[str]] = {}

        # Procesar cada intent
        for intent_name, intent_data in intents_raw.items():
            tipo = intent_data.get("tipo", "template")
            action = intent_data.get("action")
            grupo = intent_data.get("grupo")
            next_intents_raw = intent_data.get("next_intents", [])
            story_starter = intent_data.get("story_starter", True)
            entities = intent_data.get("entities", [])
            detection_patterns_refs = intent_data.get("detection_patterns", [])
            validation_rules = intent_data.get("validation_rules", {})
            context_switch = intent_data.get("context_switch", False)  # NUEVO

            # Clasificar automáticamente si no está explícito
            if intent_name not in story_starters and intent_name not in follow_up_only:
                if story_starter:
                    story_starters.append(intent_name)
                else:
                    follow_up_only.append(intent_name)

            # Cargar ejemplos con formato mejorado
            ejemplos_raw = ejemplos_data.get(intent_name, [])
            if isinstance(ejemplos_raw, dict):
                ejemplos = ejemplos_raw.get("examples", [])
            elif isinstance(ejemplos_raw, list):
                ejemplos = ejemplos_raw
            else:
                ejemplos = []

            # Cargar templates con soporte para múltiples formatos
            templates = []
            
            # Formato 1: Direct key-value (templates.yml estándar)
            templates_raw = templates_data.get(intent_name, [])
            if isinstance(templates_raw, list):
                templates = templates_raw
            elif isinstance(templates_raw, dict):
                templates = templates_raw.get("templates", [])
            
            # Formato 2: NLU format (si templates.yml tiene formato NLU como el tuyo)
            if not templates and "nlu" in templates_data:
                for nlu_item in templates_data["nlu"]:
                    if isinstance(nlu_item, dict) and nlu_item.get("intent") == intent_name:
                        examples_text = nlu_item.get("examples", "")
                        # Parsear ejemplos de formato "- ejemplo"
                        for line in examples_text.split('\n'):
                            line = line.strip()
                            if line.startswith('- '):
                                template_text = line[2:].strip()
                                # Remover comillas si existen
                                if template_text.startswith('"') and template_text.endswith('"'):
                                    template_text = template_text[1:-1]
                                templates.append(template_text)

            # Cargar responses
            responses = responses_data.get("responses", {}).get(f"utter_{intent_name}", [])

            print(f"Intent '{intent_name}': {len(ejemplos)} ejemplos, {len(templates)} templates, {len(responses)} responses")

            # Crear objeto intent
            intent_obj = {
                "tipo": tipo,
                "ejemplos": ejemplos,
                "templates": templates,
                "responses": responses,
                "action": action,
                "entities": entities,
                "detection_patterns": ConfigLoader._resolve_detection_patterns(detection_patterns_refs, detection_patterns),
                "validation_rules": validation_rules,
                "grupo": grupo,
                "story_starter": story_starter,
                "context_switch": context_switch,  # NUEVO
                "next_intents_raw": next_intents_raw
            }

            intents[intent_name] = intent_obj

            # Agrupar por grupo
            if grupo:
                grupos.setdefault(grupo, []).append(intent_name)

        # Expandir next_intents con mejor lógica
        def expand_next_intents(next_list: List[str], visited: set = None) -> List[str]:
            if visited is None:
                visited = set()
            expanded = []
            for n in next_list:
                if n in visited:
                    continue
                if n in flow_groups:
                    visited.add(n)
                    expanded.extend(expand_next_intents(flow_groups[n], visited))
                elif n in grupos:
                    visited.add(n)
                    expanded.extend(grupos[n])
                else:
                    expanded.append(n)
            # Remover duplicados manteniendo orden
            seen = set()
            return [x for x in expanded if not (x in seen or seen.add(x))]

        # Aplicar expansión de next_intents
        for intent_name, intent_obj in intents.items():
            expanded_next = expand_next_intents(intent_obj.get("next_intents_raw", []))
            intent_obj["next_intents"] = expanded_next
            del intent_obj["next_intents_raw"]

        print(f"ConfigLoader: cargados {len(intents)} intents, {len(story_starters)} story_starters, {len(follow_up_only)} follow_up_only")
        
        # NUEVO: Procesar segments para sinónimos
        segments = {}
        if segments_data.get("nlu"):
            for item in segments_data["nlu"]:
                if item.get("synonym"):
                    synonym_name = item["synonym"]
                    examples_text = item.get("examples", "")
                    # Parsear ejemplos de formato "- ejemplo"
                    examples_list = []
                    for line in examples_text.split('\n'):
                        line = line.strip()
                        if line.startswith('- '):
                            examples_list.append(line[2:])
                    segments[synonym_name] = examples_list
        
        return {
            "intents": intents,
            "entities": entities_config,
            "slots": slots_config,
            "detection_patterns": detection_patterns,
            "fallback": fallback,
            "flow_groups": flow_groups,
            "story_starters": sorted(set(story_starters)),
            "follow_up_only": sorted(set(follow_up_only)),
            "context_validation": context_validation,
            "session_config": session_config,
            "all_responses": responses_data.get("responses", {}),
            "segments": segments  # NUEVO: incluir segmentos/sinónimos
        }

    @staticmethod
    def _resolve_detection_patterns(pattern_refs: List[str], patterns_config: Dict[str, Any]) -> List[str]:
        """Resuelve referencias a patrones de detección."""
        resolved = []
        for ref in pattern_refs:
            if "." in ref:
                parts = ref.split(".")
                if len(parts) == 2:
                    category, key = parts
                    if category in patterns_config and key in patterns_config[category]:
                        resolved.extend(patterns_config[category][key])
            else:
                if ref in patterns_config:
                    resolved.extend(patterns_config[ref])
        return resolved

    # ===== MÉTODOS DE UTILIDAD EXTENDIDOS =====
    
    @staticmethod
    def get_entities_for_intent(config: Dict[str, Any], intent_name: str) -> List[str]:
        """Obtiene las entidades válidas para un intent específico"""
        return config.get("intents", {}).get(intent_name, {}).get("entities", [])

    @staticmethod
    def get_detection_patterns_for_intent(config: Dict[str, Any], intent_name: str) -> List[str]:
        """Obtiene los patrones de detección para un intent específico"""
        return config.get("intents", {}).get(intent_name, {}).get("detection_patterns", [])

    @staticmethod
    def get_validation_rules_for_intent(config: Dict[str, Any], intent_name: str) -> Dict[str, Any]:
        """Obtiene las reglas de validación para un intent específico"""
        return config.get("intents", {}).get(intent_name, {}).get("validation_rules", {})

    @staticmethod
    def detect_sentiment_in_message(config: Dict[str, Any], message: str) -> str:
        """Detecta el sentimiento en un mensaje usando los patrones configurados"""
        message_lower = message.lower()
        patterns = config.get("detection_patterns", {}).get("sentiment_analysis", {})
        
        # Verificar rechazo total primero (más específico)
        rejection_indicators = patterns.get("rejection_indicators", [])
        if any(indicator in message_lower for indicator in rejection_indicators):
            return "rejection"
        
        # Verificar sentimientos negativos
        negative_indicators = patterns.get("negative_indicators", [])
        if any(indicator in message_lower for indicator in negative_indicators):
            return "negative"
        
        # Verificar sentimientos positivos
        positive_indicators = patterns.get("positive_indicators", [])
        if any(indicator in message_lower for indicator in positive_indicators):
            return "positive"
        
        return "neutral"

    @staticmethod
    def detect_implicit_intentions(config: Dict[str, Any], message: str) -> List[str]:
        """Detecta intenciones implícitas en un mensaje"""
        message_lower = message.lower()
        patterns = config.get("detection_patterns", {}).get("implicit_intentions", {})
        detected = []
        
        for intention_type, indicators in patterns.items():
            if any(indicator in message_lower for indicator in indicators):
                detected.append(intention_type)
        
        return detected

    @staticmethod
    def get_conversation_flow_stats(config: Dict[str, Any]) -> Dict[str, Any]:
        """Analiza el flujo de conversación y devuelve estadísticas útiles."""
        intents = config.get("intents", {})
        story_starters = config.get("story_starters", [])
        follow_up_only = config.get("follow_up_only", [])
        flow_groups = config.get("flow_groups", {})
        entities = config.get("entities", {})

        connections = {}
        for intent_name, intent_data in intents.items():
            next_intents = intent_data.get("next_intents", [])
            connections[intent_name] = len(next_intents)

        terminal_intents = [name for name, count in connections.items() if count == 0]
        most_connected = max(connections.items(), key=lambda x: x[1]) if connections else None

        # Estadísticas de entidades
        entity_stats = {
            "total_entities": len(entities),
            "lookup_entities": len([e for e in entities.values() if isinstance(e, dict) and e.get("lookup_table", False)]),
            "pattern_entities": len([e for e in entities.values() if isinstance(e, dict) and e.get("patterns", [])])
        }

        return {
            "total_intents": len(intents),
            "story_starters_count": len(story_starters),
            "follow_up_only_count": len(follow_up_only),
            "flow_groups_count": len(flow_groups),
            "terminal_intents": terminal_intents,
            "most_connected_intent": most_connected[0] if most_connected else None,
            "max_connections": most_connected[1] if most_connected else 0,
            "average_connections": sum(connections.values()) / len(connections) if connections else 0,
            "context_validation_enabled": config.get("context_validation", {}).get("enabled", False),
            "entity_stats": entity_stats,
            "segments_count": len(config.get("segments", {}))  # NUEVO
        }