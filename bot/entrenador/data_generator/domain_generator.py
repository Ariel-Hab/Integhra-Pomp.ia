import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Set, List

class DomainGenerator:
    
    @staticmethod
    def generar_domain(
        config: Dict[str, Any], 
        output_path: Optional[str] = None, 
        include_session_config: bool = True,
        include_e2e_actions: bool = False
    ) -> None:
        """
        Genera un domain.yml completo basado en la configuración de intents.
        
        Args:
            config: Configuración completa con intents, flow_groups, etc.
            output_path: Ruta donde guardar el domain.yml
            include_session_config: Si incluir configuración de sesión
            include_e2e_actions: Si incluir acciones end-to-end
        """
        if output_path is None:
            output_path = Path.cwd() / "domain.yml"

        intents_data = config.get("intents", {})
        fallback = config.get("fallback", {})
        story_starters = config.get("story_starters", [])
        follow_up_only = config.get("follow_up_only", [])

        # === INTENTS ===
        all_intents = list(intents_data.keys())
        
        # === ENTITIES & SLOTS ===
        entidades = DomainGenerator._extract_entities(intents_data)
        slots = DomainGenerator._generate_slots(entidades, story_starters)

        # === ACTIONS & RESPONSES ===
        actions, responses = DomainGenerator._process_actions_responses(
            intents_data, fallback, include_e2e_actions
        )

        # === FORMS ===
        # forms = DomainGenerator._generate_forms(intents_data)

        # === SESSION CONFIG ===
        session_config = DomainGenerator._generate_session_config() if include_session_config else {}

        # === CONSTRUIR DOMINIO ===
        domain = {
            "version": "3.1",
            "intents": all_intents,
            "entities": entidades,
            "slots": slots,
            "responses": responses,
            "actions": sorted(actions),
            # "forms": forms if forms else {}
        }
        
        if session_config:
            domain["session_config"] = session_config

        # === GUARDAR ===
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(domain, f, allow_unicode=True, sort_keys=False, width=float('inf'))

        # === ESTADÍSTICAS ===
        DomainGenerator._print_statistics(domain, story_starters, follow_up_only)

    @staticmethod
    def _extract_entities(intents_data: Dict[str, Any]) -> List[str]:
        """Extrae todas las entidades únicas de los intents"""
        entidades = set()
        for intent_data in intents_data.values():
            entidades.update(intent_data.get("entities", []))
        return sorted(entidades)

    @staticmethod
    def _generate_slots(entidades: List[str], story_starters: List[str]) -> Dict[str, Any]:
        """Genera slots para entidades + slots especiales"""
        slots = {}
        
        # Slots para entidades
        for entidad in entidades:
            slots[entidad] = {
                "type": "text",
                "influence_conversation": True,
                "mappings": [
                    {"type": "from_entity", "entity": entidad}
                ]
            }
        
        # Slots especiales para tracking
        slots.update({
            "conversation_started": {
                "type": "bool",
                "initial_value": False,
                "influence_conversation": False,
                "mappings": [{"type": "custom"}]
            },
            "last_intent": {
                "type": "text",
                "influence_conversation": False,
                "mappings": [{"type": "custom"}]
            },
            "user_preference": {
                "type": "categorical",
                "values": ["busqueda", "small_talk", "ayuda"],
                "influence_conversation": True,
                "mappings": [{"type": "custom"}]
            }
        })

        return slots

    @staticmethod
    def _process_actions_responses(
        intents_data: Dict[str, Any], 
        fallback: Dict[str, Any], 
        include_e2e: bool
    ) -> tuple[Set[str], Dict[str, Any]]:
        """Procesa acciones y respuestas de forma inteligente"""
        actions = set()
        responses = {}

        # Acciones core del sistema
        # core_actions = {
        #     "action_listen",
        #     "action_restart", 
        #     "action_session_start",
        #     "action_default_fallback",
        #     "action_deactivate_loop",
        #     "action_revert_fallback_events",
        #     "action_default_ask_affirmation",
        #     "action_default_ask_rephrase",
        #     "action_back"
        # }
        # actions.update(core_actions)

        # Procesar intents
        for intent_name, intent_data in intents_data.items():
            grupo = intent_data.get("grupo", "")
            action = intent_data.get("action")
            intent_responses = intent_data.get("responses", {})
            
            # Agregar action si existe
            if action:
                actions.add(action)
            
            # SIEMPRE incluir responses - las actions pueden usarlas
            if intent_responses:
                # Las responses ya están cargadas desde los archivos individuales
                responses.update(intent_responses)
                print(f"✅ Cargadas {len(intent_responses)} responses para '{intent_name}': {list(intent_responses.keys())}")
            else:
                # Generar response por defecto SIEMPRE que no tenga responses definidas
                # (independientemente de si tiene action - las actions pueden usar los utters)
                response_key = f"utter_{intent_name}"
                responses[response_key] = DomainGenerator._generate_default_response(
                    intent_name, grupo
                )
                print(f"🔧 Generada response por defecto para '{intent_name}': {response_key} (action puede usarla)")

        # Agregar fallback
        if fallback.get("action"):
            actions.add(fallback["action"])
            fallback_response = fallback.get("response", "Lo siento, no entendí.")
            responses["utter_fallback"] = [{"text": fallback_response}]

        # E2E actions si se solicitan
        if include_e2e:
            actions.update([
                "action_extract_slots",
                "action_validate_slots", 
                "action_submit_form"
            ])

        return actions, responses

    @staticmethod
    def _generate_default_response(intent_name: str, grupo: str) -> List[Dict[str, str]]:
        """Genera respuestas por defecto inteligentes según el grupo"""
        response_templates = {
            "small_talk": [
                {"text": f"¡Hola! ¿En qué puedo ayudarte hoy?"},
                {"text": f"¡Perfecto! ¿Hay algo más en lo que pueda asistirte?"}
            ],
            "busqueda": [
                {"text": f"Entendido. Permíteme ayudarte con eso."},
                {"text": f"Perfecto, voy a buscar esa información para ti."}
            ],
            "confirmacion": [
                {"text": f"Perfecto, entendido."},
                {"text": f"De acuerdo, continuemos."}
            ],
            "agradecimiento": [
                {"text": f"¡De nada! ¿Hay algo más en lo que pueda ayudarte?"},
                {"text": f"¡Un placer ayudarte! ¿Necesitas algo más?"}
            ]
        }
        
        return response_templates.get(grupo, [{"text": f"Respuesta para {intent_name}"}])

    # @staticmethod
    # def _generate_forms(intents_data: Dict[str, Any]) -> Dict[str, Any]:
    #     """Genera forms basados en intents que requieren entidades"""
    #     forms = {}
        
    #     for intent_name, intent_data in intents_data.values():
    #         entities = intent_data.get("entities", [])
    #         grupo = intent_data.get("grupo", "")
            
    #         # Solo crear forms para intents de búsqueda con entidades
    #         if grupo == "busqueda" and entities:
    #             form_name = f"{intent_name}_form"
    #             forms[form_name] = {
    #                 "required_slots": entities
    #             }

    #     return forms

    @staticmethod
    def _generate_session_config() -> Dict[str, Any]:
        """Genera configuración de sesión optimizada"""
        return {
            "session_expiration_time": 60,  # minutos
            "carry_over_slots_to_new_session": True
        }

    @staticmethod
    def _print_statistics(domain: Dict[str, Any], story_starters: List[str], follow_up_only: List[str]) -> None:
        """Imprime estadísticas del dominio generado"""
        responses = domain.get('responses', {})
        
        print(f"\n🎯 Domain.yml generado exitosamente!")
        print(f"📊 Estadísticas del dominio:")
        print(f"  - Intents: {len(domain.get('intents', []))}")
        print(f"    • Story starters: {len(story_starters)}")
        print(f"    • Follow-up only: {len(follow_up_only)}")
        print(f"  - Entidades: {len(domain.get('entities', []))}")
        print(f"  - Slots: {len(domain.get('slots', {}))}")
        print(f"  - Actions: {len(domain.get('actions', []))}")
        print(f"  - Responses: {len(responses)}")
        
        # Mostrar detalles de responses cargadas
        if responses:
            print(f"    • Responses encontradas: {', '.join(responses.keys())}")
        
        print(f"  - Forms: {len(domain.get('forms', {}))}")

    @staticmethod
    def generar_domain_minimal(config: Dict[str, Any], output_path: Optional[str] = None) -> None:
        """
        Genera un dominio mínimo para testing rápido
        """
        if output_path is None:
            output_path = Path.cwd() / "domain_minimal.yml"

        intents_data = config.get("intents", {})
        story_starters = config.get("story_starters", [])

        # Solo lo esencial
        domain = {
            "version": "3.1", 
            "intents": story_starters,  # Solo story starters
            "entities": [],
            "slots": {
                "conversation_started": {
                    "type": "bool", 
                    "initial_value": False,
                    "mappings": [{"type": "custom"}]
                }
            },
            "responses": {
                f"utter_{intent}": [{"text": f"Respuesta para {intent}"}] 
                for intent in story_starters
            },
            "actions": [
                "action_listen",
                "action_restart"
            ]
        }

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(domain, f, allow_unicode=True, sort_keys=False)

        print(f"Domain mínimo generado: {len(story_starters)} intents")