import yaml
from pathlib import Path
from typing import Dict, Any, List, Set

class StoriesGenerator:

    @staticmethod
    def generar_stories_rules(
        config: Dict[str, Any],
        output_path_stories="data/stories.yml",
        output_path_rules="data/rules.yml",
        max_depth: int = 2,  # Reducido de 3 a 2
        max_stories_per_starter: int = 10,  # Límite por starter
        include_terminal_only: bool = True  # Solo generar paths hacia intents terminales
    ) -> None:

        intents = config.get("intents", {})
        flow_groups = config.get("flow_groups", {})
        story_starters = config.get("story_starters", [])
        follow_up_only = config.get("follow_up_only", [])

        stories_yaml = {"version": "3.1", "stories": []}
        rules_yaml = {"version": "3.1", "rules": []}

        # Identificar intents terminales (sin next_intents)
        terminal_intents = {
            name for name, data in intents.items() 
            if not data.get("next_intents", [])
        }
        
        print(f"Intents terminales encontrados: {terminal_intents}")

        # Construir mapping grupo -> intents
        grupos: Dict[str, List[str]] = {}
        for intent_name, intent_data in intents.items():
            grupo = intent_data.get("grupo")
            if grupo:
                grupos.setdefault(grupo, []).append(intent_name)

        def expand_next_intents(next_list: List[str], visited_groups: Set[str] = None) -> List[str]:
            """Expande grupos tanto de intents como de flow_groups"""
            if visited_groups is None:
                visited_groups = set()
            expanded = []
            for ni in next_list:
                if ni in flow_groups:  # Es un flow group
                    if ni in visited_groups:
                        continue
                    visited_groups.add(ni)
                    expanded.extend(expand_next_intents(flow_groups[ni], visited_groups))
                elif ni in grupos:  # Es un grupo de intents
                    if ni in visited_groups:
                        continue
                    visited_groups.add(ni)
                    expanded.extend(expand_next_intents(grupos[ni], visited_groups))
                else:  # Es un intent individual
                    expanded.append(ni)
            
            # Eliminar duplicados manteniendo orden
            seen = set()
            return [x for x in expanded if not (x in seen or seen.add(x))]

        def build_essential_stories(intent_name: str, visited: List[str] = None, depth: int = 0) -> List[List[Dict[str, Any]]]:
            """Genera solo stories esenciales, priorizando paths cortos y útiles"""
            if visited is None:
                visited = []
            
            # Condiciones de parada más estrictas
            if (intent_name in visited or 
                depth > max_depth or 
                len(visited) >= 4):  # Máximo 4 steps por story
                return []

            visited.append(intent_name)
            intent_data = intents.get(intent_name, {})
            action = intent_data.get("action")

            steps = [{"intent": intent_name}]

            # Solo agregar utters si NO hay action definida
            if not action:
                for utter_name in intent_data.get("responses", {}):
                    steps.append({"action": utter_name})
                if not intent_data.get("responses"):
                    steps.append({"action": f"utter_{intent_name}"})

            # Siempre agregar la acción si está definida
            if action:
                steps.append({"action": action})

            stories = [steps]  # Siempre incluir story simple

            # Si es terminal, no expandir más
            if intent_name in terminal_intents:
                return stories

            # Expandir next_intents de forma más selectiva
            next_intents_expanded = expand_next_intents(intent_data.get("next_intents", []))
            
            # ESTRATEGIA: Solo expandir hacia algunos next_intents, no todos
            # Priorizar intents terminales y follow_up_only
            priority_intents = []
            regular_intents = []
            
            for next_intent in next_intents_expanded:
                if next_intent in intents:
                    if (next_intent in terminal_intents or 
                        next_intent in follow_up_only):
                        priority_intents.append(next_intent)
                    else:
                        regular_intents.append(next_intent)
            
            # Procesar solo intents prioritarios + máximo 2 regulares
            selected_intents = priority_intents + regular_intents[:2]
            
            for next_intent in selected_intents:
                child_stories = build_essential_stories(next_intent, visited.copy(), depth + 1)
                for child in child_stories[:2]:  # Solo los primeros 2 child stories
                    stories.append(steps + child)
                    
                # Límite de stories por intent
                if len(stories) >= max_stories_per_starter:
                    break

            return stories

        def build_simple_stories(intent_name: str) -> List[List[Dict[str, Any]]]:
            """Genera solo stories simples de 1-2 pasos máximo"""
            intent_data = intents.get(intent_name, {})
            action = intent_data.get("action")

            # Story básica
            steps = [{"intent": intent_name}]
            if action:
                steps.append({"action": action})
            else:
                steps.append({"action": f"utter_{intent_name}"})
            
            stories = [steps]
            
            # Solo agregar UN next_intent si existe
            next_intents = expand_next_intents(intent_data.get("next_intents", []))
            if next_intents:
                # Elegir el primer intent terminal o follow_up
                next_intent = None
                for ni in next_intents:
                    if ni in terminal_intents or ni in follow_up_only:
                        next_intent = ni
                        break
                
                if not next_intent and next_intents:
                    next_intent = next_intents[0]  # Tomar el primero
                
                if next_intent and next_intent in intents:
                    next_data = intents[next_intent]
                    next_steps = steps + [{"intent": next_intent}]
                    if next_data.get("action"):
                        next_steps.append({"action": next_data["action"]})
                    else:
                        next_steps.append({"action": f"utter_{next_intent}"})
                    stories.append(next_steps)
            
            return stories

        # ESTRATEGIA DE GENERACIÓN: Mixta según el tipo
        print(f"Generando stories optimizadas desde {len(story_starters)} story starters...")
        
        for intent_name in story_starters:
            if intent_name not in intents:
                print(f"Warning: Story starter '{intent_name}' no encontrado en intents")
                continue

            # Para intents de búsqueda/negocio: stories más complejas
            intent_data = intents[intent_name]
            if intent_data.get("grupo") in ["busqueda"]:
                all_stories = build_essential_stories(intent_name)[:max_stories_per_starter]
            else:
                # Para small_talk: stories simples
                all_stories = build_simple_stories(intent_name)

            for i, steps_story in enumerate(all_stories, start=1):
                story_name = f"story_{intent_name}_{i}" if len(all_stories) > 1 else f"story_{intent_name}"
                stories_yaml["stories"].append({"story": story_name, "steps": steps_story})

        # Generar rules para TODOS los intents (tanto starters como follow-up)
        print(f"Generando rules para {len(intents)} intents...")
        for intent_name in intents.keys():
            intent_data = intents[intent_name]
            action = intent_data.get("action")
            responses = intent_data.get("responses", {})

            if action:
                steps_rule = [{"intent": intent_name}, {"action": action}]
            elif responses:
                steps_rule = [{"intent": intent_name}] + [{"action": u} for u in responses.keys()]
            else:
                steps_rule = [{"intent": intent_name}, {"action": f"utter_{intent_name}"}]

            rules_yaml["rules"].append({"rule": f"rule_{intent_name}", "steps": steps_rule})

        # Guardar archivos
        for path, data in [(output_path_stories, stories_yaml), (output_path_rules, rules_yaml)]:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, sort_keys=False)

        # Mostrar estadísticas mejoradas
        print(f"\n📊 Generación completada:")
        print(f"  - Stories generadas: {len(stories_yaml['stories'])} (optimizadas)")
        print(f"  - Rules generadas: {len(rules_yaml['rules'])}")
        print(f"  - Story starters utilizados: {len(story_starters)}")
        print(f"  - Follow-up intents: {len(follow_up_only)}")
        print(f"  - Intents terminales: {len(terminal_intents)}")
        print(f"  - Promedio stories por starter: {len(stories_yaml['stories']) / len(story_starters):.1f}")

    @staticmethod
    def generar_minimas(
        config: Dict[str, Any],
        output_path_stories="data/stories_minimal.yml"
    ) -> None:
        """
        Genera el mínimo de stories necesarias - solo 1 por story starter
        """
        intents = config.get("intents", {})
        story_starters = config.get("story_starters", [])
        
        stories_yaml = {"version": "3.1", "stories": []}

        for intent_name in story_starters:
            if intent_name not in intents:
                continue
                
            intent_data = intents[intent_name]
            action = intent_data.get("action")
            
            steps = [{"intent": intent_name}]
            if action:
                steps.append({"action": action})
            else:
                steps.append({"action": f"utter_{intent_name}"})
            
            stories_yaml["stories"].append({
                "story": f"minimal_{intent_name}",
                "steps": steps
            })

        # Guardar archivo
        Path(output_path_stories).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path_stories, "w", encoding="utf-8") as f:
            yaml.dump(stories_yaml, f, allow_unicode=True, sort_keys=False)

        print(f"Stories mínimas generadas: {len(stories_yaml['stories'])}")