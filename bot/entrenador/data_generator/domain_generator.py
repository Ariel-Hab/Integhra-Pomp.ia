# domain_generator.py - Versión Corregida y Simplificada
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Set, List

class DomainLogger:
    """Sistema de logging simplificado para DomainGenerator"""
    
    @staticmethod
    def info(message: str, component: str = "DOMAIN"):
        print(f"[{component}] {message}")
    
    @staticmethod
    def error(message: str, component: str = "DOMAIN"):
        print(f"[{component}] ERROR: {message}")
    
    @staticmethod
    def warning(message: str, component: str = "DOMAIN"):
        print(f"[{component}] WARNING: {message}")
    
    @staticmethod
    def success(message: str, component: str = "DOMAIN"):
        print(f"[{component}] SUCCESS: {message}")

class DomainGenerator:

    @staticmethod
    def _process_actions_responses(
        intents_data: Dict[str, Any], 
        fallback: Dict[str, Any], 
        all_responses: Dict[str, Any] = None,
        context_validation: Dict[str, Any] = None
    ) -> tuple[Set[str], Dict[str, Any]]:
        """Procesa actions y responses de forma simplificada"""
        actions = set()
        responses = {}
        
        DomainLogger.info("Procesando actions y responses...")
        
        # PASO 1: Responses del archivo (validadas)
        if all_responses and isinstance(all_responses, dict):
            valid_responses = 0
            for key, value in all_responses.items():
                if isinstance(value, list) and all(isinstance(item, dict) for item in value):
                    responses[key] = value
                    valid_responses += 1
                else:
                    DomainLogger.warning(f"Response inválida ignorada: {key}")
            
            DomainLogger.info(f"Responses válidas cargadas: {valid_responses}")

        # PASO 2: Actions desde intents + responses automáticas
        for intent_name, intent_data in intents_data.items():
            action = intent_data.get("action")
            if action and isinstance(action, str):
                actions.add(action)

            # Response automática si no existe
            response_key = f"utter_{intent_name}"
            if response_key not in responses:
                responses[response_key] = [
                    {"text": f"Procesando {intent_name.replace('_', ' ')}"}
                ]

        # PASO 3: Actions core esenciales
        core_actions = [
            "action_default_fallback",
            "action_buscar_producto", 
            "action_buscar_oferta",
            "action_consultar_novedades",
            "action_dar_recomendacion"
        ]
        actions.update(core_actions)
        
        # PASO 4: Responses básicas obligatorias
        essential_responses = {
            "utter_default": [{"text": "No entendí. ¿Podrías reformular?"}],
            "utter_greet": [{"text": "Hola! ¿En qué puedo ayudarte?"}],
            "utter_goodbye": [{"text": "Hasta luego!"}]
        }
        
        for key, value in essential_responses.items():
            if key not in responses:
                responses[key] = value
        
        DomainLogger.success(f"Actions: {len(actions)}, Responses: {len(responses)}")
        return actions, responses

    @staticmethod
    def _create_slots_from_config(entities_config: Dict[str, Any], slots_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        VERSIÓN CORREGIDA: Genera slots con mappings básicos y compatibles
        """
        slots = {}
        
        DomainLogger.info("Generando slots...")
        
        # PASO 1: Slots automáticos desde entidades - CON MAPPINGS BÁSICOS
        entity_slots_created = 0
        for entity_name, entity_info in entities_config.items():
            # Configuración básica compatible con Rasa 3.x
            slot_config = {
                "type": "text",
                "influence_conversation": False,
                "mappings": [
                    {
                        "type": "from_entity",
                        "entity": entity_name
                    }
                ]
            }
            
            slots[entity_name] = slot_config
            entity_slots_created += 1
            
        DomainLogger.info(f"Slots automáticos creados: {entity_slots_created}")

        # PASO 2: Slots críticos del sistema
        critical_slots = {
            "context_switch": {
                "type": "bool",
                "initial_value": False,
                "influence_conversation": False,
                "mappings": [{"type": "custom"}]
            },
            "contexto_conversacion": {
                "type": "text",
                "influence_conversation": True,
                "initial_value": "inicial",
                "mappings": [{"type": "custom"}]
            },
            "ultima_consulta": {
                "type": "text",
                "influence_conversation": False,
                "mappings": [{"type": "custom"}]
            },
            "session_started": {
                "type": "bool", 
                "initial_value": True,
                "influence_conversation": False,
                "mappings": [{"type": "custom"}]
            }
        }
        
        # Agregar slots críticos
        critical_slots_added = 0
        for slot_name, slot_config in critical_slots.items():
            if slot_name not in slots:
                slots[slot_name] = slot_config
                critical_slots_added += 1
        
        DomainLogger.info(f"Slots críticos agregados: {critical_slots_added}")
        
        # PASO 3: Slots manuales - SIMPLIFICADOS PERO FUNCIONALES
        manual_slots_added = 0
        for slot_name, slot_config in slots_config.items():
            if slot_name in slots:
                continue  # Ya existe
                
            if isinstance(slot_config, dict):
                # Configuración compatible básica
                compatible_config = {
                    "type": slot_config.get("type", "text"),
                    "influence_conversation": slot_config.get("influence_conversation", False)
                }
                
                # Agregar initial_value si existe
                if "initial_value" in slot_config:
                    compatible_config["initial_value"] = slot_config["initial_value"]
                
                # Agregar values para categorical
                if slot_config.get("type") == "categorical" and "values" in slot_config:
                    compatible_config["values"] = slot_config["values"]
                
                # Mappings simplificados pero funcionales
                original_mappings = slot_config.get("mappings", [])
                if original_mappings:
                    # Mantener mappings básicos, filtrar los problemáticos
                    safe_mappings = []
                    for mapping in original_mappings:
                        if isinstance(mapping, dict):
                            mapping_type = mapping.get("type")
                            if mapping_type in ["from_entity", "custom"]:
                                safe_mappings.append(mapping)
                    
                    compatible_config["mappings"] = safe_mappings if safe_mappings else [{"type": "custom"}]
                else:
                    compatible_config["mappings"] = [{"type": "custom"}]
                
                slots[slot_name] = compatible_config
                manual_slots_added += 1
            else:
                # Slot simple
                slots[slot_name] = {
                    "type": "text",
                    "influence_conversation": False,
                    "mappings": [{"type": "custom"}]
                }
                manual_slots_added += 1
        
        DomainLogger.info(f"Slots manuales procesados: {manual_slots_added}")
        DomainLogger.success(f"Total slots generados: {len(slots)}")
        
        return slots

    @staticmethod
    def _print_statistics(domain: Dict[str, Any], config: Dict[str, Any]) -> None:
        """Estadísticas simplificadas y precisas"""
        responses = domain.get('responses', {})
        slots = domain.get('slots', {})
        actions = domain.get('actions', [])
        entities_config = config.get('entities', {})
        
        print("\n" + "="*60)
        print("ESTADÍSTICAS DEL DOMAIN GENERADO")
        print("="*60)
        
        # Estadísticas básicas
        print(f"Intents: {len(domain.get('intents', []))}")
        print(f"Entidades: {len(domain.get('entities', []))}")
        print(f"Slots: {len(slots)}")
        print(f"Actions: {len(actions)}")
        print(f"Responses: {len(responses)}")
        
        # Clasificar slots
        entity_slots = [name for name in slots.keys() if name in entities_config]
        system_slots = [name for name in slots.keys() if any(k in name for k in ["context", "session", "ultima"])]
        
        print(f"\nDETALLE DE SLOTS:")
        print(f"  • Entity slots: {len(entity_slots)}")
        print(f"  • System slots: {len(system_slots)}")
        print(f"  • Other slots: {len(slots) - len(entity_slots) - len(system_slots)}")
        
        # Verificaciones críticas
        print(f"\nVERIFICACIONES:")
        
        # 1. Intents sin response
        intents_list = []
        for item in domain.get('intents', []):
            if isinstance(item, str):
                intents_list.append(item)
            elif isinstance(item, dict):
                intents_list.extend(item.keys())
        
        missing_responses = []
        for intent in intents_list:
            response_key = f"utter_{intent}"
            if response_key not in responses:
                missing_responses.append(intent)
        
        if missing_responses:
            DomainLogger.warning(f"Intents sin response: {missing_responses}")
        else:
            print("  ✓ Todos los intents tienen response")
        
        # 2. Entidades críticas
        critical_entities = ["producto", "ingrediente_activo", "compuesto", "proveedor"]
        missing_entities = [e for e in critical_entities if e not in domain.get('entities', [])]
        if missing_entities:
            DomainLogger.warning(f"Entidades críticas faltantes: {missing_entities}")
        else:
            print("  ✓ Entidades críticas presentes")
        
        # 3. Slots con mappings
        slots_with_mappings = 0
        slots_without_mappings = 0
        for slot_name, slot_config in slots.items():
            if slot_config.get("mappings"):
                slots_with_mappings += 1
            else:
                slots_without_mappings += 1
        
        print(f"  • Slots con mappings: {slots_with_mappings}")
        if slots_without_mappings > 0:
            DomainLogger.warning(f"Slots sin mappings: {slots_without_mappings}")
        
        print("="*60)

    @staticmethod
    def generar_domain(config: Dict[str, Any], output_path: Optional[str] = None) -> None:
        """CORREGIDO: Domain funcional con mappings requeridos"""
        
        if output_path is None:
            output_path = Path.cwd() / "domain.yml"

        print("[DOMAIN] Iniciando generación de domain.yml")
        
        # Extraer configuración
        intents_data = config.get("intents", {})
        entities_config = config.get("entities", {})
        slots_config = config.get("slots", {})
        fallback = config.get("fallback", {})
        all_responses = config.get("all_responses", {})

        print(f"[DOMAIN] Config cargada - Intents: {len(intents_data)}, Entidades: {len(entities_config)}")

        # Procesar componentes
        all_intents = list(intents_data.keys())
        entities = list(entities_config.keys())
        
        # Generar slots CON mappings requeridos
        slots = DomainGenerator._create_slots_from_config(entities_config, slots_config)
        
        # Procesar actions y responses
        actions, responses = DomainGenerator._process_actions_responses(
            intents_data, fallback, all_responses
        )

        # Construir domain funcional
        domain = {
            "version": "3.1",
            "intents": all_intents,
            "entities": entities,
            "slots": slots,
            "responses": responses,
            "actions": sorted(actions),
            "session_config": {
                "session_expiration_time": 60,
                "carry_over_slots_to_new_session": True
            }
        }

        # Escribir domain.yml
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                yaml.dump(domain, f, allow_unicode=True, sort_keys=False, indent=2)
            
            print(f"[DOMAIN] ✅ Domain guardado en: {output_path}")
            
            # Mostrar estadísticas
            DomainGenerator._print_statistics(domain, config)
            
        except Exception as e:
            print(f"[DOMAIN] ❌ ERROR escribiendo domain.yml: {e}")
            raise

    @staticmethod
    def validar_domain(domain_path: str) -> Dict[str, List[str]]:
        """Valida un domain.yml existente"""
        try:
            with open(domain_path, 'r', encoding='utf-8') as f:
                domain = yaml.safe_load(f)
        except Exception as e:
            return {"errores": [f"No se pudo cargar domain.yml: {e}"]}
        
        problemas = {
            "errores": [],
            "advertencias": [],
            "sugerencias": []
        }
        
        # Validaciones críticas
        required_keys = ["intents", "entities", "slots", "responses", "actions"]
        for key in required_keys:
            if key not in domain:
                problemas["errores"].append(f"Falta sección requerida: {key}")
        
        # Validar consistencia intent-response
        intents = domain.get("intents", [])
        responses = domain.get("responses", {})
        
        for intent in intents:
            intent_name = intent if isinstance(intent, str) else list(intent.keys())[0]
            response_key = f"utter_{intent_name}"
            if response_key not in responses:
                problemas["advertencias"].append(f"Intent '{intent_name}' sin response '{response_key}'")
        
        # Validar slots tienen mappings
        slots = domain.get("slots", {})
        for slot_name, slot_config in slots.items():
            if not slot_config.get("mappings"):
                problemas["advertencias"].append(f"Slot '{slot_name}' sin mappings")
        
        return problemas