#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Story Generator Module - Generador de stories, rules y domain completo
Versión: 1.0 - CORREGIDO PARA FORMATO RASA
"""

import yaml
from typing import Dict, List, Any, Optional, Set
from pathlib import Path
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class StoryDefinition:
    """Definición de una story"""
    name: str
    steps: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleDefinition:
    """Definición de una rule"""
    name: str
    condition: Optional[str] = None
    steps: List[Dict[str, Any]] = field(default_factory=list)
    wait_for_user_input: bool = True


class StoryGenerator:
    """Generador de stories, rules y domain basado en configuraciones"""
    
    def __init__(self, config_dir: str = "config/"):
        self.config_dir = Path(config_dir)
        
        # Configuraciones cargadas
        self.context_config = {}
        self.entities_config = {}
        self.slots_config = {}
        self.responses_config = {}
        
        # Datos procesados
        self.flow_groups = {}
        self.intents_config = {}
        self.custom_actions = {}
        self.stories = []
        self.rules = []
            
        logger.info(f"[StoryGenerator] Inicializando con config_dir={config_dir}")
    
    def load_all_configs(self):
        """Carga todas las configuraciones necesarias"""
        logger.info("[StoryGenerator] Cargando configuraciones")
        
        # Cargar context_config.yml
        context_file = self.config_dir / "context_config.yml"
        if context_file.exists():
            with open(context_file, 'r', encoding='utf-8') as f:
                self.context_config = yaml.safe_load(f)
            logger.info("[StoryGenerator] context_config.yml cargado")
        else:
            raise FileNotFoundError(f"context_config.yml no encontrado: {context_file}")
        
        # Cargar entities_config.yml
        entities_file = self.config_dir / "entities_config.yml"
        if entities_file.exists():
            with open(entities_file, 'r', encoding='utf-8') as f:
                self.entities_config = yaml.safe_load(f)
            logger.info("[StoryGenerator] entities_config.yml cargado")
        
        # Cargar slots_config.yml
        slots_file = self.config_dir / "slots_config.yml"
        if slots_file.exists():
            with open(slots_file, 'r', encoding='utf-8') as f:
                self.slots_config = yaml.safe_load(f)
            logger.info("[StoryGenerator] slots_config.yml cargado")
        
        # Cargar responses.yml - CORREGIR estructura
        responses_file = self.config_dir / "responses.yml"
        if responses_file.exists():
            with open(responses_file, 'r', encoding='utf-8') as f:
                responses_data = yaml.safe_load(f)
                # CORREGIR: Si el archivo tiene version y responses anidados, extraer solo responses
                if isinstance(responses_data, dict) and 'responses' in responses_data:
                    self.responses_config = responses_data['responses']
                    logger.info("[StoryGenerator] responses.yml cargado (estructura anidada detectada)")
                else:
                    # Si el archivo es directo responses (sin version wrapper)
                    self.responses_config = responses_data
                    logger.info("[StoryGenerator] responses.yml cargado (estructura directa)")
        
        # Procesar configuraciones
        self.flow_groups = self.context_config.get('flow_groups', {})
        self.intents_config = self.context_config.get('intents', {})
        self.custom_actions = self.context_config.get('custom_actions', {})

        logger.info("[StoryGenerator] Todas las configuraciones cargadas")
    
    def generate_stories(self):
        """Genera stories basadas en flow_groups y next_intents"""
        logger.info("[StoryGenerator] Generando stories")
        self.stories = []
        
        # Stories básicas por grupo
        for group_name, group_config in self.flow_groups.items():
            group_intents = group_config.get('intents', [])
            starter_allowed = group_config.get('starter_allowed', False)
            
            if starter_allowed and group_intents:
                # Generar story principal del grupo
                story = self._create_group_story(group_name, group_intents)
                self.stories.append(story)
                
                # Generar stories de flujo interno
                self._create_flow_stories(group_name, group_intents)
        
        # Stories de interacciones complejas
        self._create_complex_interaction_stories()
        
        # Stories de paths específicos basados en next_intents
        self._create_next_intent_stories()
        
        logger.info(f"[StoryGenerator] Generadas {len(self.stories)} stories")
    
    def _get_intent_action(self, intent_name: str) -> str:
        """Obtiene la action correspondiente a un intent"""
        # Configuración RAW del intent
        raw_intent_config = self.context_config.get('intents', {}).get(intent_name, {})
        
        # 1. Action directa en el intent
        if 'action' in raw_intent_config:
            return raw_intent_config['action']
        
        # 2. Buscar en custom_actions
        for action_name, action_config in self.custom_actions.items():
            if intent_name in action_config.get('intents', []):
                return action_name
        
        # 3. Fallback por tipo
        if any(keyword in intent_name for keyword in ['buscar', 'consultar', 'modificar', 'oferta']):
            return 'ActionBusquedaSituacion'
        elif intent_name in ['afirmar', 'denegar', 'agradecimiento', 'completar_pedido']:
            return 'ActionConfNegAgradecer'
        elif intent_name == 'despedida':
            return 'ActionDespedidaLimpiaContexto'
        elif intent_name in ['off_topic', 'out_of_scope']:
            return 'ActionFallback'
        else:
            return 'ActionSmallTalkSituacion'
    
    def _create_group_story(self, group_name: str, intents: List[str]) -> StoryDefinition:
        """Crea story principal para un grupo"""
        story_name = f"story_{group_name}_basic"
        
        # Tomar el primer intent como principal
        main_intent = intents[0] if intents else None
        
        steps = []
        if main_intent:
            steps.append({"intent": main_intent})
            
            # Usar action personalizada
            action = self._get_intent_action(main_intent)
            steps.append({"action": action})
        
        story = StoryDefinition(
            name=story_name,
            steps=steps,
            metadata={"group": group_name, "type": "basic"}
        )
        
        return story
    
    def _create_flow_stories(self, group_name: str, intents: List[str]):
        """Crea stories de flujo interno del grupo"""
        for intent in intents:
            intent_config = self.intents_config.get(intent, {})
            next_intents = intent_config.get('next_intents', [])
            
            if next_intents:
                for next_intent in next_intents:
                    story_name = f"story_{intent}_to_{next_intent}"
                    
                    first_action = self._get_intent_action(intent)
                    second_action = self._get_intent_action(next_intent)

                    steps = [
                        {"intent": intent},
                        {"action": first_action},
                        {"intent": next_intent},
                        {"action": second_action}
                    ]
                    
                    story = StoryDefinition(
                        name=story_name,
                        steps=steps,
                        metadata={"group": group_name, "type": "flow", "from": intent, "to": next_intent}
                    )
                    
                    self.stories.append(story)
    
    def _create_complex_interaction_stories(self):
        """Crea stories de interacciones complejas"""
        
        # Story: Búsqueda con confirmación
        search_confirmation_story = StoryDefinition(
            name="story_search_with_confirmation",
            steps=[
                {"intent": "buscar_producto"},
                {"action": "ActionBusquedaSituacion"},
                {"intent": "afirmar"},
                {"action": "ActionConfNegAgradecer"},
                {"intent": "completar_pedido"},
                {"action": "ActionBusquedaSituacion"}
            ],
            metadata={"type": "complex", "pattern": "search_confirmation"}
        )
        self.stories.append(search_confirmation_story)
        
        # Story: Búsqueda con modificación
        search_modification_story = StoryDefinition(
            name="story_search_with_modification",
            steps=[
                {"intent": "buscar_producto"},
                {"action": "ActionBusquedaSituacion"},
                {"intent": "modificar_busqueda"},
                {"action": "ActionBusquedaSituacion"},
                {"intent": "buscar_producto"},
                {"action": "ActionBusquedaSituacion"}
            ],
            metadata={"type": "complex", "pattern": "search_modification"}
        )
        self.stories.append(search_modification_story)
        
        # Story: Flujo completo con saludo y despedida
        complete_flow_story = StoryDefinition(
            name="story_complete_interaction",
            steps=[
                {"intent": "saludo"},
                {"action": "ActionSmallTalkSituacion"},
                {"intent": "buscar_producto"},
                {"action": "ActionBusquedaSituacion"},
                {"intent": "completar_pedido"},
                {"action": "ActionBusquedaSituacion"},
                {"intent": "despedida"},
                {"action": "ActionDespedidaLimpiaContexto"}
            ],
            metadata={"type": "complete", "pattern": "full_interaction"}
        )
        self.stories.append(complete_flow_story)
        
        # Story: Búsqueda de ofertas específica
        offer_search_story = StoryDefinition(
            name="story_offer_search",
            steps=[
                {"intent": "buscar_oferta"},
                {"action": "ActionBusquedaSituacion"},
                {"intent": "afirmar"},
                {"action": "ActionConfNegAgradecer"},
                {"intent": "completar_pedido"},
                {"action": "ActionBusquedaSituacion"}
            ],
            metadata={"type": "complex", "pattern": "offer_search"}
        )
        self.stories.append(offer_search_story)
    
    def _create_next_intent_stories(self):
        """Crea stories basadas en next_intents específicos"""
        for intent_name, intent_config in self.intents_config.items():
            next_intents = intent_config.get('next_intents', [])
            
            # Solo crear stories para intents con múltiples next_intents
            if len(next_intents) > 1:
                for i, next_intent in enumerate(next_intents[:3]):  # Máximo 3 para evitar explosión
                    story_name = f"story_{intent_name}_path_{i+1}"
                    
                    first_action = self._get_intent_action(intent_name)
                    second_action = self._get_intent_action(next_intent)

                    steps = [
                        {"intent": intent_name},
                        {"action": first_action},
                        {"intent": next_intent},
                        {"action": second_action}
                    ]
                    
                    # Si hay un tercer intent en la cadena, agregarlo
                    third_intent_config = self.intents_config.get(next_intent, {})
                    third_intents = third_intent_config.get('next_intents', [])
                    if third_intents:
                        third_intent = third_intents[0]
                        steps.extend([
                            {"intent": third_intent},
                            {"action": self._get_intent_action(third_intent)} 
                        ])
                    
                    story = StoryDefinition(
                        name=story_name,
                        steps=steps,
                        metadata={"type": "path", "origin": intent_name, "path_id": i+1}
                    )
                    
                    self.stories.append(story)
    
    def generate_rules(self):
        """Genera rules para comportamientos deterministas"""
        logger.info("[StoryGenerator] Generando rules")
        self.rules = []
        
        # Rules para intents básicos (saludo, despedida, agradecimiento)
        basic_intents = ['saludo', 'despedida', 'agradecimiento', 'afirmar', 'denegar']
        
        for intent in basic_intents:
            if intent in self.intents_config:
                rule = RuleDefinition(
                    name=f"rule_{intent}",
                    steps=[
                        {"intent": intent},
                        {"action": self._get_intent_action(intent)}
                    ]
                )
                self.rules.append(rule)
        
        # Rules específicas para fallback
        fallback_rule = RuleDefinition(
            name="rule_fallback",
            steps=[
                {"intent": "nlu_fallback"},
                {"action": "ActionFallback"}
            ]
        )
        self.rules.append(fallback_rule)
        
        # Rule para out_of_scope
        if 'out_of_scope' in self.intents_config:
            out_of_scope_rule = RuleDefinition(
                name="rule_out_of_scope",
                steps=[
                    {"intent": "out_of_scope"},
                    {"action": "ActionFallback"} 
                ]
            )
            self.rules.append(out_of_scope_rule)
        
        logger.info(f"[StoryGenerator] Generadas {len(self.rules)} rules")
    
    def generate_domain(self) -> Dict[str, Any]:
        """Genera domain completo de Rasa con formato correcto"""
        logger.info("[StoryGenerator] Generando domain")
        
        # CORECCIÓN: Estructura base con fallback_action siempre presente
        domain = {
            "version": "3.1",
            "config": {
                "store_entities_as_slots": True,
                "fallback_action": "ActionFallback"  # SIEMPRE presente
            }
        }
        
        # Intents - ORDEN ESPECÍFICO como en el ejemplo
        domain["intents"] = list(self.intents_config.keys())
        
        # Entities - Lista simple
        entities = []
        if self.entities_config.get('entities'):
            entities = list(self.entities_config['entities'].keys())
        domain["entities"] = entities
        
        # Slots - FORMATO CORRECTO con mappings
        slots = self._generate_domain_slots()
        if slots:
            domain["slots"] = slots
        
        # Responses - MANTENER ORDEN
        if self.responses_config:
            domain["responses"] = self.responses_config
        
        # Actions - ORDEN ESPECÍFICO: customs primero, luego system actions
        actions = self._generate_domain_actions()
        domain["actions"] = actions
        
        # Session config - FORMATO CORRECTO
        domain["session_config"] = {
            "session_expiration_time": 300,  # Valor por defecto como en ejemplo
            "carry_over_slots_to_new_session": True
        }
        
        logger.info("[StoryGenerator] Domain generado con formato correcto")
        logger.info(f"[StoryGenerator] - {len(domain.get('intents', []))} intents")
        logger.info(f"[StoryGenerator] - {len(domain.get('entities', []))} entities")
        logger.info(f"[StoryGenerator] - {len(domain.get('slots', {}))} slots")
        logger.info(f"[StoryGenerator] - {len(domain.get('actions', []))} actions")
        logger.info(f"[StoryGenerator] - {len(domain.get('responses', {}))} responses")
        
        return domain
    
    def _generate_domain_slots(self) -> Dict[str, Any]:
        """Genera slots para el domain con formato correcto"""
        slots = {}
        
        # Slots de entidades (auto-generados) - FORMATO ESPECÍFICO
        entity_slots = self.slots_config.get('entity_slots', {})
        if entity_slots.get('auto_generate') and self.entities_config.get('entities'):
            exclude_entities = entity_slots.get('exclude', [])
            
            for entity_name in self.entities_config['entities'].keys():
                if entity_name not in exclude_entities:
                    # FORMATO CORRECTO para entity slots
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
        
        # Slots de sistema - USAR CONFIGURACIÓN COMPLETA desde slots_config
        system_slots = self.slots_config.get('system_slots', {})
        for slot_name, slot_config in system_slots.items():
            # Limpiar referencias de template
            clean_config = {k: v for k, v in slot_config.items() if not k.startswith('<<')}
            
            # ASEGURAR que todos los slots tengan mappings (Rasa 3.1 requirement)
            if 'mappings' not in clean_config:
                # Fallback mapping basado en el tipo de slot
                slot_type = clean_config.get('type', 'text')
                
                if slot_type == 'bool':
                    # Para bool slots, usar from_intent como default
                    clean_config['mappings'] = [
                        {
                            "type": "from_intent",
                            "value": True,
                            "intent": "afirmar"
                        },
                        {
                            "type": "from_intent", 
                            "value": False,
                            "intent": "denegar"
                        }
                    ]
                else:
                    # Para otros tipos, usar from_text
                    clean_config['mappings'] = [
                        {
                            "type": "from_text"
                        }
                    ]
            
            slots[slot_name] = clean_config
        
        return slots
    
    def _generate_domain_actions(self) -> List[str]:
        """Genera lista de actions con orden específico"""
        actions = []
        
        # 1. CUSTOM ACTIONS PRIMERO (alfabético)
        custom_action_names = sorted(self.custom_actions.keys())
        actions.extend(custom_action_names)
        
        # 2. SYSTEM ACTIONS (orden específico como en ejemplo)
        system_actions = [
            "action_back",
            "action_deactivate_loop", 
            "action_default_ask_affirmation",
            "action_default_ask_rephrase",
            "action_default_fallback",
            "action_listen",
            "action_restart",
            "action_revert_fallback_events",
            "action_session_start"
        ]
        actions.extend(system_actions)
        
        # Asegurar que no hay duplicados
        return list(dict.fromkeys(actions))  # Mantiene orden y elimina duplicados
    
    def export_stories(self, output_file: str = "output/stories.yml"):
        """Exporta stories a archivo YAML con formato correcto"""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        stories_data = {
            "version": "3.1",
            "stories": []
        }
        
        for story in self.stories:
            story_dict = {
                "story": story.name,
                "steps": story.steps  # SIN metadata en el YAML final
            }
            stories_data["stories"].append(story_dict)
        
        # FORMATO RASA CORRECTO - sin sort_keys para mantener orden
        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(stories_data, f, 
                     default_flow_style=False, 
                     allow_unicode=True, 
                     sort_keys=False,
                     indent=2)
        
        logger.info(f"[StoryGenerator] Stories exportadas a: {output_path}")
    
    def export_rules(self, output_file: str = "output/rules.yml"):
        """Exporta rules a archivo YAML con formato correcto"""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        rules_data = {
            "version": "3.1",
            "rules": []
        }
        
        for rule in self.rules:
            rule_dict = {
                "rule": rule.name,
                "steps": rule.steps
            }
            
            # Solo agregar condición si existe
            if rule.condition:
                rule_dict["condition"] = rule.condition
            
            # Solo agregar wait_for_user_input si es False (no default)
            if not rule.wait_for_user_input:
                rule_dict["wait_for_user_input"] = False
            
            rules_data["rules"].append(rule_dict)
        
        # FORMATO RASA CORRECTO
        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(rules_data, f, 
                     default_flow_style=False, 
                     allow_unicode=True, 
                     sort_keys=False,
                     indent=2)
        
        logger.info(f"[StoryGenerator] Rules exportadas a: {output_path}")
    
    def export_domain(self, output_file: str = "output/domain.yml"):
        """Exporta domain a archivo YAML con formato correcto"""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        domain_data = self.generate_domain()
        
        # FORMATO RASA CORRECTO - orden específico de secciones
        ordered_domain = {}
        
        # Orden específico de las secciones del domain
        if "version" in domain_data:
            ordered_domain["version"] = domain_data["version"]
        if "config" in domain_data:
            ordered_domain["config"] = domain_data["config"]
        if "intents" in domain_data:
            ordered_domain["intents"] = domain_data["intents"]
        if "entities" in domain_data:
            ordered_domain["entities"] = domain_data["entities"]
        if "slots" in domain_data:
            ordered_domain["slots"] = domain_data["slots"]
        if "responses" in domain_data:
            ordered_domain["responses"] = domain_data["responses"]
        if "actions" in domain_data:
            ordered_domain["actions"] = domain_data["actions"]
        if "session_config" in domain_data:
            ordered_domain["session_config"] = domain_data["session_config"]
        
        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(ordered_domain, f, 
                     default_flow_style=False, 
                     allow_unicode=True, 
                     sort_keys=False,
                     indent=2)
        
        logger.info(f"[StoryGenerator] Domain exportado a: {output_path}")
    
    def export_all(self, output_dir: str = "output/"):
        """Exporta stories, rules y domain"""
        output_path = Path(output_dir)
        
        self.export_stories(f"{output_dir}stories.yml")
        self.export_rules(f"{output_dir}rules.yml")
        self.export_domain(f"{output_dir}domain.yml")
        
        logger.info(f"[StoryGenerator] Todos los archivos exportados a: {output_path}")
    
    def diagnose_action_mapping(self):
        """Función de diagnóstico para ver el mapeo de actions"""
        print("\n" + "="*60)
        print("🔍 DIAGNÓSTICO DE MAPEO DE ACTIONS")
        print("="*60)
        
        print(f"Custom Actions cargadas: {len(self.custom_actions)}")
        for action_name, action_config in self.custom_actions.items():
            intents = action_config.get('intents', [])
            print(f"  {action_name}: {intents}")
        
        print(f"\nIntents RAW (antes de templates):")
        raw_intents = self.context_config.get('intents', {})
        for intent_name, intent_config in raw_intents.items():
            if 'action' in intent_config:
                print(f"  {intent_name} -> {intent_config['action']} (RAW)")
        
        print(f"\nIntents procesados (después de templates):")
        for intent_name, intent_config in self.intents_config.items():
            if 'action' in intent_config:
                print(f"  {intent_name} -> {intent_config['action']} (PROCESADO)")
        
        print(f"\nMapeo FINAL de intents -> actions:")
        for intent_name in raw_intents.keys():
            action = self._get_intent_action(intent_name)
            print(f"  {intent_name} -> {action}")
        
        print("="*60)
    
    def print_summary(self):
        """Imprime resumen de generación"""
        print("\n" + "="*70)
        print("📚 RESUMEN DE GENERACIÓN")
        print("="*70)
        
        print(f"📖 STORIES: {len(self.stories)}")
        
        # Agrupar stories por tipo
        story_types = {}
        for story in self.stories:
            story_type = story.metadata.get('type', 'other')
            story_types[story_type] = story_types.get(story_type, 0) + 1
        
        for story_type, count in story_types.items():
            print(f"   • {story_type}: {count}")
        
        print(f"\n📋 RULES: {len(self.rules)}")
        
        print(f"\n🏗️  DOMAIN:")
        print(f"   • Intents: {len(self.intents_config)}")
        if self.entities_config.get('entities'):
            print(f"   • Entities: {len(self.entities_config['entities'])}")
        print(f"   • Responses: {len(self.responses_config)}")
        
        print("="*70)
        print()


def setup_logging():
    """Configura logging básico"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def main():
    """Función principal para testing"""
    setup_logging()
    
    try:
        # Crear generador
        generator = StoryGenerator("config/")
        
        # Cargar configuraciones
        generator.load_all_configs()
        
        # Generar contenido
        generator.generate_stories()
        generator.generate_rules()
        
        # Mostrar resumen
        generator.print_summary()
        
        # Exportar todo
        generator.export_all("output/")
        
        print("✅ Generación completada exitosamente")
        print("📁 Archivos generados:")
        print("   • output/stories.yml")
        print("   • output/rules.yml")
        print("   • output/domain.yml")
        
        return generator
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        raise


if __name__ == "__main__":
    main()