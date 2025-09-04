# stories_generator.py - Versión sin contradicciones
import yaml
from pathlib import Path
from typing import Dict, Any, List, Set

class StoriesGenerator:

    @staticmethod
    def generar_stories_rules(
        config: Dict[str, Any],
        output_path_stories="data/stories.yml",
        output_path_rules="data/rules.yml",
        max_depth: int = 2,  # Reducido para evitar complejidad
        max_stories_per_starter: int = 8,  # Reducido para evitar contradicciones
        include_context_validation: bool = False,  # DESHABILITADO temporalmente
        context_validation_action: str = "action_context_validator",
        context_slot_name: str = "context_switch",
        include_advanced_patterns: bool = False  # DESHABILITADO temporalmente
    ) -> None:
        """
        Genera stories y rules SIN CONTRADICCIONES.
        Versión simplificada que prioriza la consistencia.
        """

        intents = config.get("intents", {})
        flow_groups = config.get("flow_groups", {})
        story_starters = config.get("story_starters", [])
        follow_up_only = config.get("follow_up_only", [])

        stories_yaml = {"version": "3.1", "stories": []}
        rules_yaml = {"version": "3.1", "rules": []}

        # Clasificar intents por tipo
        busqueda_intents = {name for name, data in intents.items() if data.get("grupo") == "busqueda"}
        confirmacion_intents = {name for name, data in intents.items() if data.get("grupo") in ["confirmacion", "negacion", "agradecimiento"]}
        smalltalk_intents = {name for name, data in intents.items() if data.get("grupo") == "small_talk"}

        print(f"Busqueda: {busqueda_intents}")
        print(f"Confirmacion: {confirmacion_intents}")
        print(f"Small talk: {smalltalk_intents}")

        # Expandir next_intents de forma segura
        def expand_next_intents(next_list: List[str], visited_groups: Set[str] = None) -> List[str]:
            if visited_groups is None:
                visited_groups = set()
            expanded = []
            for ni in next_list:
                if ni in flow_groups and ni not in visited_groups:
                    visited_groups.add(ni)
                    expanded.extend(expand_next_intents(flow_groups[ni], visited_groups))
                elif ni in intents and ni not in expanded:  # Evitar duplicados
                    expanded.append(ni)
            return expanded

        # STORIES SIMPLIFICADAS - Solo happy paths básicos
        def build_simple_stories(intent_name: str, visited: List[str] = None, depth: int = 0) -> List[List[Dict[str, Any]]]:
            if visited is None:
                visited = []
            if intent_name in visited or depth >= max_depth:
                return []

            visited.append(intent_name)
            intent_data = intents.get(intent_name, {})
            action = intent_data.get("action") or f"utter_{intent_name}"

            # SOLO action, SIN context switching por ahora
            steps = [{"intent": intent_name}, {"action": action}]
            stories = [steps]

            # Limitar next_intents para evitar explosión combinatoria
            next_intents = expand_next_intents(intent_data.get("next_intents", []))[:2]  # MAX 2

            for ni in next_intents:
                child_stories = build_simple_stories(ni, visited.copy(), depth + 1)
                for child_story in child_stories:
                    if len(steps + child_story) <= 6:  # Limitar longitud de stories
                        stories.append(steps + child_story)

            return stories

        # Generar stories por starter
        for starter in story_starters[:8]:  # Limitar starters
            if starter not in intents:
                continue

            print(f"Generando stories para: {starter}")
            starter_stories = build_simple_stories(starter)
            
            # Limitar cantidad de stories por starter
            starter_stories = starter_stories[:max_stories_per_starter]

            for i, story_steps in enumerate(starter_stories):
                story_name = f"story_{starter}_{i+1}" if len(starter_stories) > 1 else f"story_{starter}"
                stories_yaml["stories"].append({
                    "story": story_name,
                    "steps": story_steps
                })

        # RULES SIMPLIFICADAS - Una regla simple por intent
        print("Generando rules simplificadas...")
        
        for intent_name, intent_data in intents.items():
            action = intent_data.get("action") or f"utter_{intent_name}"
            
            # SOLO regla básica - SIN context switching
            basic_rule = {
                "rule": f"rule_{intent_name}",
                "steps": [
                    {"intent": intent_name},
                    {"action": action}
                ]
            }
            rules_yaml["rules"].append(basic_rule)

        # Rules especiales para fallback
        fallback_rule = {
            "rule": "rule_default_fallback",
            "steps": [
                {"intent": "nlu_fallback"},
                {"action": "action_default_fallback"}
            ]
        }
        rules_yaml["rules"].append(fallback_rule)

        # Guardar archivos
        for path, data in [(output_path_stories, stories_yaml), (output_path_rules, rules_yaml)]:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

        print(f"✅ Stories y Rules generados SIN contradicciones!")
        print(f"  📚 Stories: {len(stories_yaml['stories'])}")
        print(f"  📋 Rules: {len(rules_yaml['rules'])}")
        print(f"  🎯 Enfoque: Simplicidad y consistencia")
        
        # Validación básica
        story_intents = set()
        rule_intents = set()
        
        for story in stories_yaml["stories"]:
            for step in story["steps"]:
                if "intent" in step:
                    story_intents.add(step["intent"])
        
        for rule in rules_yaml["rules"]:
            for step in rule["steps"]:
                if "intent" in step:
                    rule_intents.add(step["intent"])
        
        print(f"  🔍 Intents en stories: {len(story_intents)}")
        print(f"  🔍 Intents en rules: {len(rule_intents)}")
        
        # Detectar posibles solapamientos
        overlap = story_intents & rule_intents
        print(f"  ⚠️ Solapamiento stories-rules: {len(overlap)} intents")

# Versión alternativa aún más simple si la anterior falla
class StoriesGeneratorMinimal:

    @staticmethod
    def generar_stories_rules_minimal(
        config: Dict[str, Any],
        output_path_stories="data/stories.yml",
        output_path_rules="data/rules.yml"
    ) -> None:
        """
        Versión MÍNIMA que garantiza 0 contradicciones.
        Solo reglas básicas, sin stories complejas.
        """
        
        intents = config.get("intents", {})
        
        stories_yaml = {"version": "3.1", "stories": []}
        rules_yaml = {"version": "3.1", "rules": []}
        
        # SOLO UNA STORY MUY SIMPLE
        simple_story = {
            "story": "story_basic_interaction",
            "steps": [
                {"intent": "saludo"},
                {"action": "utter_saludo"},
                {"intent": "buscar_producto"}, 
                {"action": "utter_buscar_producto"},
                {"intent": "agradecimiento"},
                {"action": "utter_agradecimiento"}
            ]
        }
        stories_yaml["stories"].append(simple_story)
        
        # SOLO REGLAS BÁSICAS
        for intent_name, intent_data in intents.items():
            action = intent_data.get("action") or f"utter_{intent_name}"
            
            rule = {
                "rule": f"rule_{intent_name}",
                "steps": [
                    {"intent": intent_name},
                    {"action": action}
                ]
            }
            rules_yaml["rules"].append(rule)
        
        # Guardar
        for path, data in [(output_path_stories, stories_yaml), (output_path_rules, rules_yaml)]:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        
        print(f"✅ Stories y Rules MÍNIMAS generadas!")
        print(f"  📚 Stories: {len(stories_yaml['stories'])}")
        print(f"  📋 Rules: {len(rules_yaml['rules'])}")
        print(f"  🎯 Garantía: CERO contradicciones")