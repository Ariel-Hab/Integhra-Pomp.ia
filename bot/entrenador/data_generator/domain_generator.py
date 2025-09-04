# domain_generator.py - Mejorado para integración completa con ConfigLoader
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Set, List

class DomainGenerator:

    @staticmethod
    def _process_actions_responses(
        intents_data: Dict[str, Any], 
        fallback: Dict[str, Any], 
        all_responses: Dict[str, Any] = None,
        context_validation: Dict[str, Any] = None
    ) -> tuple[Set[str], Dict[str, Any]]:
        """
        Procesa actions y responses con mejor integración.
        """
        actions = set()
        responses = {}
        
        # PASO 1: Usar responses del archivo responses.yml tal como están
        if all_responses:
            responses.update(all_responses)
            print(f"[DomainGenerator] Cargadas {len(all_responses)} responses del archivo responses.yml")

        # PASO 2: Procesar intents y sus actions
        for intent_name, intent_data in intents_data.items():
            action = intent_data.get("action")
            if action:
                actions.add(action)
                print(f"[DomainGenerator] Action agregada: {action} (de intent {intent_name})")

            response_key = f"utter_{intent_name}"
            
            # Solo crear si NO existe en el archivo responses.yml
            if response_key not in responses:
                # Crear response básica pero más inteligente
                grupo = intent_data.get("grupo", "")
                if grupo == "busqueda":
                    response_text = f"Buscando información sobre {intent_name.replace('_', ' ')}..."
                elif grupo == "small_talk":
                    response_text = f"Respuesta social para {intent_name.replace('_', ' ')}"
                else:
                    response_text = f"Respuesta para {intent_name.replace('_', ' ')}"
                
                responses[response_key] = [{"text": response_text}]
                print(f"[DomainGenerator] Response creada: {response_key}")

        # PASO 3: Manejar fallback mejorado
        if fallback.get("action"):
            actions.add(fallback["action"])
            if "utter_fallback" not in responses:
                fallback_resp = fallback.get("response", "Lo siento, no entendí.")
                responses["utter_fallback"] = [{"text": fallback_resp}]

        # PASO 4: Context validation actions
        if context_validation and context_validation.get("enabled", False):
            context_action = context_validation.get("action", "action_context_validator")
            actions.add(context_action)
            print(f"[DomainGenerator] Context validation action agregada: {context_action}")

        # PASO 5: Core actions requeridas - Lista actualizada
        core_actions = [
            # Actions principales del sistema
            "action_busqueda_situacion",
            "action_smalltalk_situacion", 
            "action_fallback",
            "action_conf_neg_agradecer",
            "action_generica",  # Agregada según context_config
            "action_generic_intent_reporter",  # Agregada según context_config
            
            # Context management
            "action_context_validator",
            "action_despedida_limpia_contexto",
            
        ]
        actions.update(core_actions)
        
        print(f"[DomainGenerator] Total responses: {len(responses)}")
        print(f"[DomainGenerator] Total actions: {len(actions)}")
        
        return actions, responses

    @staticmethod
    def _create_slots_from_config(entities_config: Dict[str, Any], slots_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Genera slots automáticamente desde entidades + slots manuales.
        Mejorado para manejar mejor ingrediente_activo y otros casos especiales.
        """
        slots = {}
        
        # PASO 1: Agregar slots de entidades automáticamente
        for entity_name, entity_info in entities_config.items():
            # Configuración base
            slot_config = {
                "type": "text",
                "influence_conversation": False,
                "mappings": [{"type": "from_entity", "entity": entity_name}]
            }
            
            # CASOS ESPECIALES según el tipo de entidad
            if isinstance(entity_info, dict):
                # Usar lookup_table si está definido
                if entity_info.get("lookup_table", False):
                    slot_config["type"] = "categorical"  # Mejor para lookup tables
                
                # Entidades con patterns específicos
                if entity_info.get("patterns", []):
                    slot_config["type"] = "text"  # Mantener text para patterns
            
            # MAPEO CRUZADO MEJORADO
            if entity_name == "compuesto":
                # Mapear tanto compuesto como ingrediente_activo al slot compuesto
                slot_config["mappings"] = [
                    {"type": "from_entity", "entity": "compuesto"},
                    {"type": "from_entity", "entity": "ingrediente_activo"}
                ]
                print(f"[DomainGenerator] Slot 'compuesto' mapeará entidades: compuesto, ingrediente_activo")
            
            elif entity_name == "ingrediente_activo":
                # Crear slot específico para ingrediente_activo también
                slot_config["mappings"] = [
                    {"type": "from_entity", "entity": "ingrediente_activo"},
                    {"type": "from_entity", "entity": "compuesto"}  # Mapeo bidireccional
                ]
                print(f"[DomainGenerator] Slot 'ingrediente_activo' mapeará entidades: ingrediente_activo, compuesto")
            
            slots[entity_name] = slot_config
            print(f"[DomainGenerator] Auto-slot creado: {entity_name} (tipo: {slot_config['type']})")

        # CRÍTICO: Agregar slot context_switch requerido por stories
        if "context_switch" not in slots:
            slots["context_switch"] = {
                "type": "bool",
                "initial_value": False,
                "influence_conversation": False,
                "mappings": [{"type": "custom"}]
            }
            print(f"[DomainGenerator] Slot crítico agregado: context_switch")
        
        # PASO 2: Agregar slots manuales (preservar mappings de slots automáticos)
        for slot_name, slot_config in slots_config.items():
            if slot_name in slots:
                # Si ya existe, preservar mappings especiales (ingrediente_activo, compuesto)
                existing_mappings = slots[slot_name].get("mappings", [])
                if isinstance(slot_config, dict):
                    merged_config = slot_config.copy()
                    # Preservar mapeos especiales para ingrediente_activo y compuesto
                    if slot_name in ["ingrediente_activo", "compuesto"] and len(existing_mappings) > 1:
                        merged_config["mappings"] = existing_mappings
                    slots[slot_name] = merged_config
                    print(f"[DomainGenerator] Slot manual merged: {slot_name} (preservando mappings especiales)")
                else:
                    slots[slot_name] = {"type": "text", "influence_conversation": False}
                    print(f"[DomainGenerator] Slot manual simplificado: {slot_name}")
            else:
                # Slot completamente nuevo
                if isinstance(slot_config, dict):
                    slots[slot_name] = slot_config.copy()
                    slot_type = slot_config.get("type", "text")
                    print(f"[DomainGenerator] Slot manual agregado: {slot_name} (tipo: {slot_type})")
                else:
                    slots[slot_name] = {"type": "text", "influence_conversation": False}
                    print(f"[DomainGenerator] Slot manual simplificado: {slot_name}")
        
        return slots

    @staticmethod
    def _create_forms_from_config(intents_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        NUEVO: Genera forms automáticamente para intents que requieren múltiples entidades.
        """
        forms = {}
        
        for intent_name, intent_data in intents_data.items():
            entities = intent_data.get("entities", [])
            validation_rules = intent_data.get("validation_rules", {})
            
            # Solo crear form si hay reglas de validación complejas
            if validation_rules.get("requires_at_least_one") and len(entities) > 2:
                required_slots = validation_rules.get("requires_at_least_one", [])
                optional_slots = validation_rules.get("optional", [])
                
                form_name = f"form_{intent_name}"
                forms[form_name] = {
                    "required_slots": {slot: [{"type": "from_entity", "entity": slot}] for slot in required_slots},
                    "ignored_intents": ["off_topic", "despedida"]  # Intents que pueden interrumpir
                }
                
                print(f"[DomainGenerator] Form creado: {form_name} con slots: {required_slots}")
        
        return forms

    @staticmethod
    def _print_statistics(domain: Dict[str, Any], config: Dict[str, Any]) -> None:
        """Estadísticas mejoradas con más detalles"""
        responses = domain.get('responses', {})
        slots = domain.get('slots', {})
        actions = domain.get('actions', [])
        entities_config = config.get('entities', {})
        forms = domain.get('forms', {})

        # Clasificar slots
        entity_slots = [name for name in slots.keys() if name in entities_config]
        context_slots = [name for name in slots.keys() if any(k in name for k in ["search", "context", "intent", "engagement", "sentiment", "pending"])]
        lookup_slots = [name for name in entity_slots if slots.get(name, {}).get("type") == "categorical"]

        print(f"\n🔧 Domain.yml generado exitosamente!")
        print(f"📊 Estadísticas del dominio:")
        print(f"  - Intents: {len(domain.get('intents', []))}")
        print(f"  - Entidades: {len(domain.get('entities', []))}")
        print(f"  - Slots: {len(slots)}")
        print(f"    • Entity slots: {len(entity_slots)}")
        print(f"    • Context slots: {len(context_slots)}")
        print(f"    • Lookup slots: {len(lookup_slots)}")
        print(f"  - Actions: {len(actions)}")
        print(f"  - Responses: {len(responses)}")
        
        if forms:
            print(f"  - Forms: {len(forms)}")
            for form_name, form_config in forms.items():
                required = list(form_config.get("required_slots", {}).keys())
                print(f"    • {form_name}: {required}")
        
        # Verificaciones importantes
        print(f"\n🔍 Verificaciones importantes:")
        
        # Mapeo de intents a responses
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
            print(f"  ⚠️ Intents sin response: {missing_responses}")
        else:
            print(f"  ✅ Todos los intents tienen response")
        
        # Verificar entidades críticas
        critical_entities = ["producto", "ingrediente_activo", "compuesto", "proveedor"]
        missing_entities = [e for e in critical_entities if e not in domain.get('entities', [])]
        if missing_entities:
            print(f"  ⚠️ Entidades críticas faltantes: {missing_entities}")
        else:
            print(f"  ✅ Todas las entidades críticas están presentes")
        
        # Verificar mapeo ingrediente_activo CORREGIDO
        has_ingrediente_activo_entity = "ingrediente_activo" in domain.get('entities', [])
        ingrediente_slot = slots.get("ingrediente_activo", {})
        compuesto_slot = slots.get("compuesto", {})
        
        # Verificación mejorada del mapeo cruzado
        cross_mapping_ok = False
        if ingrediente_slot and compuesto_slot:
            ingrediente_mappings = ingrediente_slot.get("mappings", [])
            compuesto_mappings = compuesto_slot.get("mappings", [])
            
            # Verificar que ambos slots mapeen ambas entidades
            ingrediente_entities = [m.get("entity") for m in ingrediente_mappings if "entity" in m]
            compuesto_entities = [m.get("entity") for m in compuesto_mappings if "entity" in m]
            
            cross_mapping_ok = (
                "ingrediente_activo" in ingrediente_entities and "compuesto" in ingrediente_entities and
                "ingrediente_activo" in compuesto_entities and "compuesto" in compuesto_entities
            )
        
        print(f"  - Mapeo ingrediente_activo:")
        print(f"    • Entidad ingrediente_activo: {'✅' if has_ingrediente_activo_entity else '❌'}")
        print(f"    • Slot ingrediente_activo: {'✅' if ingrediente_slot else '❌'}")
        print(f"    • Mapeo cruzado: {'✅' if cross_mapping_ok else '❌'}")

    @staticmethod
    def generar_domain(config: Dict[str, Any], output_path: Optional[str] = None) -> None:
        """
        Genera domain.yml con integración completa del ConfigLoader mejorado.
        """
        if output_path is None:
            output_path = Path.cwd() / "domain.yml"

        # Extraer configuraciones
        intents_data = config.get("intents", {})
        entities_config = config.get("entities", {})
        slots_config = config.get("slots", {})
        session_config = config.get("session_config", {})
        fallback = config.get("fallback", {})
        context_validation = config.get("context_validation", {})
        story_starters = config.get("story_starters", [])
        follow_up_only = config.get("follow_up_only", [])
        all_responses = config.get("all_responses", {})

        print(f"[DomainGenerator] Procesando {len(intents_data)} intents...")
        print(f"[DomainGenerator] Responses del archivo: {len(all_responses)}")
        print(f"[DomainGenerator] Entidades: {list(entities_config.keys())}")
        print(f"[DomainGenerator] Context validation: {'habilitada' if context_validation.get('enabled') else 'deshabilitada'}")

        # Procesar componentes
        all_intents = list(intents_data.keys())
        entities = list(entities_config.keys())
        
        # Generar slots mejorados
        slots = DomainGenerator._create_slots_from_config(entities_config, slots_config)
        
        # Procesar actions y responses
        actions, responses = DomainGenerator._process_actions_responses(
            intents_data, fallback, all_responses, context_validation
        )
        
        # NUEVO: Generar forms si es necesario (OPCIONAL - puede deshabilitarse)
        crear_forms = False  # Cambiar a True si quieres habilitar forms
        if crear_forms:
            forms = DomainGenerator._create_forms_from_config(intents_data)
        else:
            forms = {}
            print("[DomainGenerator] Forms deshabilitados por configuración")

        # Construir domain
        domain = {
            "version": "3.1",
            "intents": DomainGenerator._format_intents(all_intents, story_starters, follow_up_only),
            "entities": entities,
            "slots": slots,
            "responses": responses,
            "actions": sorted(actions),
        }
        
        # Agregar forms si existen
        if forms:
            domain["forms"] = forms
        
        # Configuración de sesión
        if session_config:
            domain["session_config"] = session_config
        else:
            # Default mejorado
            domain["session_config"] = {
                "session_expiration_time": 180,
                "carry_over_slots_to_new_session": True
            }

        # Crear directorio si no existe
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Escribir domain.yml con formato mejorado
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(domain, f, allow_unicode=True, sort_keys=False, width=float('inf'), indent=2)

        print(f"[DomainGenerator] Domain guardado en: {output_path}")
        DomainGenerator._print_statistics(domain, config)

    @staticmethod
    def _format_intents(all_intents: List[str], starters: List[str], followups: List[str]) -> List[Any]:
        """
        Formatea intents con metadata mejorada.
        """
        formatted = []
        for intent in all_intents:
            props: Dict[str, Any] = {}
            
            # Marcar story starters
            if intent in starters:
                props["is_starter"] = True
            
            # Marcar follow-up only
            if intent in followups:
                props["follow_up_only"] = True
            
            # Todos los intents pueden usar entidades por defecto
            props["use_entities"] = True
            
            # Formatear según si tiene propiedades
            if props and len(props) > 1:  # Más de solo use_entities
                formatted.append({intent: props})
            else:
                formatted.append(intent)
        
        return formatted

    @staticmethod
    def validar_domain(domain_path: str) -> Dict[str, List[str]]:
        """
        NUEVO: Valida un domain.yml existente y reporta problemas.
        """
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
                problemas["advertencias"].append(f"Intent '{intent_name}' no tiene response '{response_key}'")
        
        # Validar entidades críticas
        entities = domain.get("entities", [])
        critical_entities = ["producto", "ingrediente_activo", "proveedor"]
        for entity in critical_entities:
            if entity not in entities:
                problemas["sugerencias"].append(f"Considera agregar entidad crítica: {entity}")
        
        return problemas