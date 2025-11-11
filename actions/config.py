# actions/utils/config.py

import logging
import yaml
import unicodedata
import os
from pathlib import Path
from typing import Dict, List, Any, Optional


from actions.models.model_manager import get_search_engine
from actions.models.model_manager import get_chat_model


logger = logging.getLogger(__name__)

class DomainBasedConfigurationManager:
    """
    Gestor de configuración que extrae TODO del domain.yml y carga los modelos.
    Sin dependencias circulares, usando domain como fuente única de verdad.
    """
    
    _instance = None
    _config_loaded = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._config_loaded:
            # Estructuras de datos principales
            self.domain_data = {}
            self.lookup_tables = {}
            self.intent_config = {}
            
            # Instancias de modelos
            self.chat_model_instance = None 
            self.search_engine_instance = None
            
            # Mapeos derivados
            self.intent_to_slots = {}
            self.intent_to_action = {}
            self.entity_to_slot_mapping = {}
            self.search_intent_mappings = {}
            
            # Estado del sistema
            self._health_status = {}
            
            # Cargar configuración
            self._load_all_configs()
            DomainBasedConfigurationManager._config_loaded = True
    
    def _detect_project_root(self) -> Path:
        """Detecta automáticamente la raíz del proyecto Rasa"""
        root = Path(__file__).parent.parent / "actions"
        current = root
        max_depth = 5
        
        for _ in range(max_depth):
            rasa_indicators = ['domain.yml', 'endpoints.yml', 'credentials.yml']
            if any((current / indicator).exists() for indicator in rasa_indicators):
                logger.info(f"Raíz del proyecto Rasa detectada: {current}")
                return current
                
            if current.parent == current:
                break
            current = current.parent
        
        fallback = root
        logger.warning(f"No se detectó raíz del proyecto, usando: {fallback}")
        return fallback
    
    def _get_domain_paths(self) -> List[Path]:
        """Genera lista de paths posibles para domain.yml"""
        project_root = self._detect_project_root()
        current_dir = Path(__file__).parent
        paths = [
            Path(os.environ.get('RASA_DOMAIN_PATH', '')),
            project_root / "domain.yml",
            project_root / "domain.yaml",
            project_root / "bot" / "domain.yml",
            project_root / "data" / "domain.yml",
            current_dir / "domain.yml",
            current_dir.parent / "domain.yml"
        ]
        return [p for p in paths if p and p != Path('')]
    
    def _get_lookup_paths(self) -> List[Path]:
        """Genera lista de paths para lookup tables"""
        project_root = self._detect_project_root()
        paths = [
            Path(os.environ.get('RASA_LOOKUP_PATH', '')),
            project_root / "bot" / "data" / "lookup_tables.yml",
            project_root / "data" / "lookup_tables.yml",
            project_root / "lookup_tables.yml",
            project_root / "data" / "nlu.yml"
        ]
        return [p for p in paths if p and p != Path('')]

    def _load_all_configs(self):
        """Carga toda la configuración: domain, lookups y AMBOS modelos."""
        try:
            self._health_status = {
                'domain_loaded': False,
                'lookup_tables_loaded': False,
                'chat_model_loaded': False,
                'search_engine_loaded': False,
                'critical_errors': [],
                'warnings': [],
                'paths_tried': {'domain': [], 'lookup': []}
            }
            
            # 1. Cargar domain.yml
            domain_loaded = self._load_domain()
            self._health_status['domain_loaded'] = domain_loaded
            
            # 2. Extraer configuración del domain
            if domain_loaded:
                self._extract_config_from_domain()
            
            # 3. Cargar lookup tables
            lookup_loaded = self._load_lookup_tables()
            self._health_status['lookup_tables_loaded'] = lookup_loaded
            
            # 4. Obtener ChatModel
            chat_model_loaded = self._get_chat_model_instance()
            self._health_status['chat_model_loaded'] = chat_model_loaded
            
            # 5. Obtener SearchEngine
            search_engine_loaded = self._get_search_engine_instance()
            self._health_status['search_engine_loaded'] = search_engine_loaded
            
            # 6. Construir mapeos inteligentes
            self._build_intelligent_mappings()
            
            # 7. Validar estado del sistema
            self._validate_system_health()
            
            # 8. Reportar estado
            self._report_loading_status()
            
        except Exception as e:
            logger.error(f"Error crítico cargando configuración: {e}", exc_info=True)
            self._health_status['critical_errors'].append(str(e))
            self._set_fallback_config()

    def _get_chat_model_instance(self) -> bool:
        """
        Obtiene la instancia del ChatModel desde el ModelManager.
        Ya no es responsable de cargarlo ni calentarlo.
        """
        try:
            logger.info("🧠 [ChatModel] Obteniendo instancia desde ModelManager...")
            
            self.chat_model_instance = get_chat_model() 
            
            # --- ✅ CORRECCIÓN ---
            # La lógica de _cpu_available / _gpu_available ya no existe aquí.
            # Si get_chat_model() no lanzó una excepción, la instancia se obtuvo.
            if self.chat_model_instance:
                logger.info("✅ [ChatModel] Instancia obtenida")
                return True
            else:
                # Este caso es improbable si get_chat_model() funciona bien
                logger.warning("⚠️ [ChatModel] No se pudo obtener la instancia (retornó None)")
                return False
                
        except Exception as e:
            error_msg = f"No se pudo obtener ChatModel: {e}"
            logger.error(f"❌ [ChatModel] {error_msg}")
            self._health_status['critical_errors'].append(error_msg)
            return False

    def _get_search_engine_instance(self) -> bool:
        """
        Obtiene la instancia del SearchEngine desde el ModelManager.
        """
        try:
            logger.info("🔍 [SearchEngine] Obteniendo instancia desde ModelManager...")
            
            self.search_engine_instance = get_search_engine()
            
            # --- ✅ CORRECCIÓN ---
            # 1. Se cambió para que verifique self.search_engine_instance (no el chat_model)
            # 2. Se eliminó la lógica de _cpu_available / _gpu_available
            if self.search_engine_instance:
                logger.info("✅ [SearchEngine] Instancia obtenida")
                return True
            else:
                logger.warning("⚠️ [SearchEngine] No se pudo obtener la instancia (retornó None)")
                return False
                
        except Exception as e:
            error_msg = f"No se pudo cargar SearchEngine: {e}"
            logger.error(f"❌ [SearchEngine] {error_msg}")
            self._health_status['critical_errors'].append(error_msg)
            return False
                

    def _load_domain(self) -> bool:
        """Carga el domain.yml"""
        domain_paths = self._get_domain_paths()
        self._health_status['paths_tried']['domain'] = [str(p) for p in domain_paths]
        
        for domain_path in domain_paths:
            logger.debug(f"Intentando cargar domain desde: {domain_path}")
            
            try:
                if domain_path.exists() and domain_path.is_file():
                    with open(domain_path, 'r', encoding='utf-8') as f:
                        domain_data = yaml.safe_load(f)
                    
                    if domain_data and isinstance(domain_data, dict):
                        self.domain_data = domain_data
                        logger.info(f"✅ Domain cargado desde: {domain_path}")
                        intents = domain_data.get('intents', [])
                        entities = domain_data.get('entities', [])
                        slots = domain_data.get('slots', {})
                        actions = domain_data.get('actions', [])
                        
                        logger.info(f"   📋 Intents: {len(intents)}")
                        logger.info(f"   🏷️ Entities: {len(entities)}")
                        logger.info(f"   📊 Slots: {len(slots)}")
                        logger.info(f"   🎯 Actions: {len(actions)}")
                        
                        return True
                    else:
                        logger.warning(f"Domain vacío o inválido: {domain_path}")
                        
            except yaml.YAMLError as e:
                logger.error(f"Error YAML en {domain_path}: {e}")
                self._health_status['warnings'].append(f"YAML error en {domain_path}: {e}")
            except Exception as e:
                logger.warning(f"Error leyendo {domain_path}: {e}")
                self._health_status['warnings'].append(f"Error leyendo {domain_path}: {e}")
        
        logger.error("❌ No se pudo cargar ningún domain.yml")
        self._health_status['critical_errors'].append("No se encontró domain.yml válido")
        return False
    
    def _extract_config_from_domain(self):
        """Extrae configuración estructurada del domain.yml"""
        try:
            intents = self.domain_data.get('intents', [])
            entities = self.domain_data.get('entities', [])
            slots = self.domain_data.get('slots', {})
            actions = self.domain_data.get('actions', [])
            
            self.intent_config = {
                'intents': {},
                'entities': {},
                'slots': {},
                'actions': actions
            }
            
            for intent in intents:
                intent_name = intent if isinstance(intent, str) else str(intent)
                self.intent_config['intents'][intent_name] = {
                    'name': intent_name,
                    'entities': [],
                    'action': self._determine_action_for_intent(intent_name)
                }
            
            for entity in entities:
                entity_name = entity if isinstance(entity, str) else str(entity)
                self.intent_config['entities'][entity_name] = {
                    'name': entity_name,
                    'type': 'text'
                }
            
            for slot_name, slot_config in slots.items():
                self.intent_config['slots'][slot_name] = {
                    'name': slot_name,
                    'type': slot_config.get('type', 'text'),
                    'mappings': slot_config.get('mappings', []),
                    'influence_conversation': slot_config.get('influence_conversation', False)
                }
            
            logger.info(f"✅ Configuración extraída del domain: {len(self.intent_config['intents'])} intents procesados")
            
        except Exception as e:
            logger.error(f"Error extrayendo configuración del domain: {e}", exc_info=True)
            self._health_status['critical_errors'].append(f"Error procesando domain: {e}")
    
    def _determine_action_for_intent(self, intent_name: str) -> str:
        """Determina la acción apropiada para un intent basándose en patrones"""
        action_mappings = {
            'buscar_': 'action_busqueda_situacion',
            'consultar_': 'action_busqueda_situacion', 
            'completar_pedido': 'action_busqueda_situacion',
            'modificar_busqueda': 'action_busqueda_situacion',
            'saludo': 'action_smalltalk_situacion',
            'despedida': 'action_despedida_limpia_contexto',
            'agradecimiento': 'action_conf_neg_agradecer',
            'off_topic': 'action_fallback',
            'out_of_scope': 'action_fallback',
            'ambiguity_fallback': 'action_fallback'
        }
        
        if intent_name in action_mappings:
            return action_mappings[intent_name]
        
        for prefix, action in action_mappings.items():
            if intent_name.startswith(prefix.rstrip('_')):
                return action
        
        return 'action_default_fallback'
    
    def _load_lookup_tables(self) -> bool:
        """Carga lookup tables"""
        lookup_paths = self._get_lookup_paths()
        self._health_status['paths_tried']['lookup'] = [str(p) for p in lookup_paths]
        
        for lookup_path in lookup_paths:
            logger.debug(f"Intentando cargar lookup tables desde: {lookup_path}")
            
            try:
                if lookup_path.exists() and lookup_path.is_file():
                    loaded_lookups = self._parse_lookup_file(lookup_path)
                    
                    if loaded_lookups:
                        self.lookup_tables = loaded_lookups
                        logger.info(f"✅ Lookup tables cargadas desde: {lookup_path}")
                        logger.info(f"   Categorías: {list(loaded_lookups.keys())}")
                        logger.info(f"   Total elementos: {sum(len(v) for v in loaded_lookups.values())}")
                        return True
                    else:
                        logger.warning(f"Lookup tables vacías en: {lookup_path}")
                        
            except Exception as e:
                logger.warning(f"Error cargando lookup tables desde {lookup_path}: {e}")
                self._health_status['warnings'].append(f"Error en lookup {lookup_path}: {e}")
        
        logger.error("❌ No se pudieron cargar lookup tables")
        self._health_status['critical_errors'].append("No se encontraron lookup tables válidas")
        return False
    
    def _parse_lookup_file(self, path: Path) -> Dict[str, List[str]]:
        """Parsea archivo de lookup tables"""
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        if not data:
            return {}
        
        lookup_dict = {}
        
        if isinstance(data, dict) and "nlu" in data:
            for entry in data["nlu"]:
                if isinstance(entry, dict) and "lookup" in entry:
                    lookup_name = entry["lookup"]
                    examples = []
                    
                    if "examples" in entry:
                        examples_text = entry["examples"]
                        if isinstance(examples_text, str):
                            for line in examples_text.splitlines():
                                line = line.strip()
                                if line.startswith("- "):
                                    value = line[2:].strip()
                                    if value:
                                        examples.append(value)
                    
                    if examples:
                        lookup_dict[lookup_name] = examples
                        logger.debug(f"Lookup '{lookup_name}': {len(examples)} elementos")
        
        elif isinstance(data, dict):
            for key, values in data.items():
                if key == "nlu":
                    continue
                    
                if isinstance(values, list):
                    clean_values = [str(v).strip() for v in values if v and str(v).strip()]
                    if clean_values:
                        lookup_dict[key] = clean_values
                elif isinstance(values, str) and values.strip():
                    lookup_dict[key] = [values.strip()]
        
        return lookup_dict
    
    def _build_intelligent_mappings(self):
        """Construye mapeos inteligentes basándose en el domain y lookup tables"""
        try:
            slots_config = self.domain_data.get('slots', {})
            for slot_name, slot_config in slots_config.items():
                mappings = slot_config.get('mappings', [])
                for mapping in mappings:
                    if mapping.get('type') == 'from_entity':
                        entity_name = mapping.get('entity', slot_name)
                        self.entity_to_slot_mapping[entity_name] = slot_name
            
            search_entities = ['producto', 'empresa', 'categoria', 'animal', 'sintoma', 'dosis', 'estado']
            comparative_entities = ['cantidad', 'precio', 'descuento', 'bonificacion', 'stock', 'comparador']
            temporal_entities = ['tiempo', 'fecha', 'dia']
            
            intent_entity_mappings = {
                'buscar_producto': search_entities + comparative_entities + temporal_entities,
                'buscar_oferta': search_entities + ['descuento', 'bonificacion', 'precio'] + temporal_entities,
                'consultar_recomendaciones': search_entities + comparative_entities,
                'modificar_busqueda': search_entities + comparative_entities + temporal_entities,
                'completar_pedido': search_entities + comparative_entities
            }
            
            for intent_name in self.intent_config['intents'].keys():
                if intent_name in intent_entity_mappings:
                    entities = intent_entity_mappings[intent_name]
                elif intent_name.startswith('buscar_'):
                    entities = search_entities + comparative_entities + temporal_entities
                elif intent_name.startswith('consultar_'):
                    entities = search_entities + comparative_entities
                else:
                    entities = ['sentimiento']
                
                self.intent_config['intents'][intent_name]['entities'] = entities
                self.intent_to_slots[intent_name] = entities
                self.intent_to_action[intent_name] = self.intent_config['intents'][intent_name]['action']
            
            self.search_intent_mappings = {
                'buscar_producto': {
                    'search_type': 'producto',
                    'required_entities': ['producto', 'categoria', 'empresa', 'animal'],
                    'optional_entities': ['sintoma', 'dosis', 'estado', 'cantidad', 'precio']
                },
                'buscar_oferta': {
                    'search_type': 'oferta', 
                    'required_entities': ['producto', 'categoria', 'empresa'],
                    'optional_entities': ['descuento', 'bonificacion', 'precio', 'animal', 'tiempo']
                }
            }
            
            self._create_lookup_to_domain_mapping()
            
            logger.info(f"✅ Mapeos inteligentes construidos:")
            logger.info(f"   🔗 Intent->slots: {len(self.intent_to_slots)}")
            logger.info(f"   🏷️ Entity->slot: {len(self.entity_to_slot_mapping)}")
            logger.info(f"   🔍 Search mappings: {len(self.search_intent_mappings)}")
            
        except Exception as e:
            logger.error(f"Error construyendo mapeos inteligentes: {e}", exc_info=True)
            self._health_status['warnings'].append(f"Error en mapeos: {e}")
    
    def _create_lookup_to_domain_mapping(self):
        """Crea mapeo entre lookup tables y entities del domain"""
        self.lookup_to_domain_mapping = {}
        
        explicit_mappings = {
            'compuesto': 'sintoma',
            'indicador_temporal': 'tiempo',
            'sentimiento_positivo': 'sentimiento',
            'sentimiento_negativo': 'sentimiento'
        }
        
        lookup_categories = list(self.lookup_tables.keys())
        domain_entities = list(self.intent_config['entities'].keys())
        
        for lookup_cat in lookup_categories:
            if lookup_cat in explicit_mappings:
                self.lookup_to_domain_mapping[lookup_cat] = explicit_mappings[lookup_cat]
            elif lookup_cat in domain_entities:
                self.lookup_to_domain_mapping[lookup_cat] = lookup_cat
            else:
                for domain_entity in domain_entities:
                    if lookup_cat in domain_entity or domain_entity in lookup_cat:
                        self.lookup_to_domain_mapping[lookup_cat] = domain_entity
                        break
        
        logger.debug(f"Mapeo lookup->domain: {self.lookup_to_domain_mapping}")
    
    def _validate_system_health(self):
        """Valida estado del sistema con información del domain"""
        critical_categories = ['empresa', 'categoria', 'animal', 'dosis']
        missing_critical = []
        
        for category in critical_categories:
            found = False
            if category in self.lookup_tables:
                found = True
            else:
                for lookup_cat, domain_entity in self.lookup_to_domain_mapping.items():
                    if domain_entity == category and lookup_cat in self.lookup_tables:
                        found = True
                        break
            
            if not found:
                missing_critical.append(category)
        
        if missing_critical:
            mapped_missing = []
            for missing in missing_critical:
                if missing not in [v for v in self.lookup_to_domain_mapping.values()]:
                    mapped_missing.append(missing)
            
            if mapped_missing:
                error_msg = f"Categorías críticas faltantes: {mapped_missing}"
                self._health_status['critical_errors'].append(error_msg)
                logger.error(f"❌ {error_msg}")
            else:
                logger.info("✅ Categorías críticas disponibles a través de mapeos")
        
        search_intents = [name for name in self.intent_to_slots.keys() if name.startswith('buscar_')]
        if not search_intents:
            self._health_status['warnings'].append("No se encontraron intents de búsqueda")
        
        total_lookup_elements = sum(len(v) for v in self.lookup_tables.values())
        self._health_status.update({
            'total_intents': len(self.intent_to_slots),
            'total_lookup_categories': len(self.lookup_tables),
            'total_lookup_elements': total_lookup_elements,
            'search_intents_count': len(search_intents),
            'has_critical_categories': len(missing_critical) == 0
        })

    def _report_loading_status(self):
        """Reporta estado de carga"""
        status = self.get_health_status()
        
        logger.info("=" * 60)
        logger.info("📊 ESTADO DEL SISTEMA")
        logger.info("=" * 60)
        logger.info(f"   📄 Domain: {'✅ Cargado' if status.get('domain_loaded') else '❌ Faltante'}")
        logger.info(f"   📚 Lookups: {'✅ Cargadas' if status.get('lookup_tables_loaded') else '❌ Faltantes'}")
        logger.info(f"   💬 ChatModel: {'✅ Conectado' if status.get('chat_model_loaded') else '❌ No conectado'}")
        logger.info(f"   🔍 SearchEngine: {'✅ Conectado' if status.get('search_engine_loaded') else '❌ No conectado'}")
        
        logger.info("-" * 25)
        logger.info(f"📊 Intents: {status.get('total_intents', 0)}")
        logger.info(f"📊 Intents de búsqueda: {status.get('search_intents_count', 0)}")
        logger.info(f"📊 Lookup categories: {status.get('total_lookup_categories', 0)}")
        logger.info(f"📊 Total lookup elements: {status.get('total_lookup_elements', 0)}")
        
        if status['critical_errors']:
            logger.error("🚨 ERRORES CRÍTICOS:")
            for error in status['critical_errors']:
                logger.error(f"   - {error}")
        
        if status['warnings']:
            logger.warning("⚠️ ADVERTENCIAS:")
            for warning in status['warnings'][:3]:
                logger.warning(f"   - {warning}")
        
        logger.info("=" * 60)

    def _set_fallback_config(self):
        """Configuración de emergencia"""
        logger.warning("🆘 Activando configuración de emergencia")
        
        if self.domain_data:
            try:
                self._extract_config_from_domain()
                self._build_intelligent_mappings()
                return
            except Exception as e:
                logger.error(f"Error en configuración de emergencia: {e}")
        
        self.intent_config = {"intents": {}, "entities": {}, "slots": {}}
        self.lookup_tables = {}
        self.intent_to_slots = {}
        self.intent_to_action = {}
    
    # === MÉTODOS PÚBLICOS ===
    
    def get_chat_model(self) -> Optional[Any]:
        """Devuelve la instancia del ChatModel."""
        return self.chat_model_instance
    
    def get_search_engine(self) -> Optional[Any]:
        """Devuelve la instancia del SearchEngine."""
        return self.search_engine_instance

    def get_intent_config(self) -> Dict[str, Any]:
        return self.intent_config
    
    def get_lookup_tables(self) -> Dict[str, List[str]]:
        return self.lookup_tables
    
    def get_entities_for_intent(self, intent_name: str) -> List[str]:
        return self.intent_to_slots.get(intent_name, [])
    
    def get_action_for_intent(self, intent_name: str) -> Optional[str]:
        return self.intent_to_action.get(intent_name)
    
    def validate_entity_value(self, entity_type: str, value: str) -> bool:
        if not self.lookup_tables:
            logger.debug("No hay lookup tables, aceptando valor")
            return True
        
        if entity_type in self.lookup_tables:
            return self._check_value_in_lookup(entity_type, value)
        
        for lookup_cat, domain_entity in getattr(self, 'lookup_to_domain_mapping', {}).items():
            if domain_entity == entity_type and lookup_cat in self.lookup_tables:
                logger.debug(f"Validando '{value}' en '{entity_type}' usando lookup '{lookup_cat}'")
                return self._check_value_in_lookup(lookup_cat, value)
        
        logger.debug(f"No hay lookup para '{entity_type}', aceptando valor")
        return True
    
    def _check_value_in_lookup(self, lookup_category: str, value: str) -> bool:
        try:
            normalized_value = normalize_text(value)
            normalized_lookup = [normalize_text(v) for v in self.lookup_tables[lookup_category]]
            return normalized_value in normalized_lookup
        except Exception as e:
            logger.error(f"Error validando '{value}' en '{lookup_category}': {e}")
            return True
    
    def get_entity_suggestions(self, entity_type: str, value: str, max_suggestions: int = 3) -> List[str]:
        lookup_category = self._resolve_lookup_category(entity_type)
        
        if not lookup_category or lookup_category not in self.lookup_tables:
            return []
        
        try:
            import difflib
            
            normalized_value = normalize_text(value)
            original_values = self.lookup_tables[lookup_category]
            normalized_lookup = [normalize_text(v) for v in original_values]
            
            suggestions = difflib.get_close_matches(
                normalized_value, normalized_lookup, n=max_suggestions, cutoff=0.6
            )
            
            original_suggestions = []
            for suggestion in suggestions:
                for original in original_values:
                    if normalize_text(original) == suggestion:
                        original_suggestions.append(original)
                        break
            
            return original_suggestions
            
        except Exception as e:
            logger.error(f"Error obteniendo sugerencias para '{value}': {e}")
            return []
    
    def _resolve_lookup_category(self, entity_type: str) -> Optional[str]:
        if entity_type in self.lookup_tables:
            return entity_type
        
        for lookup_cat, domain_entity in getattr(self, 'lookup_to_domain_mapping', {}).items():
            if domain_entity == entity_type:
                return lookup_cat
        
        return None
    
    def get_health_status(self) -> Dict[str, Any]:
        return self._health_status.copy()
    
    def get_search_intent_info(self, intent_name: str) -> Dict[str, Any]:
        return self.search_intent_mappings.get(intent_name, {})


# Función utilitaria
def normalize_text(text: str) -> str:
    if not text:
        return ""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8").lower()


# === INSTANCIA GLOBAL Y EXPORTS ===

config_manager = DomainBasedConfigurationManager()

# Exports para compatibilidad
INTENT_CONFIG = config_manager.get_intent_config()
LOOKUP_TABLES = config_manager.get_lookup_tables()
INTENT_TO_SLOTS = config_manager.intent_to_slots
INTENT_TO_ACTION = config_manager.intent_to_action
CHAT_MODEL = config_manager.get_chat_model()
SEARCH_ENGINE = config_manager.get_search_engine()

def get_lookup_tables() -> Dict[str, List[str]]:
    return config_manager.get_lookup_tables()

def get_intent_config() -> Dict[str, Any]:
    return config_manager.get_intent_config()

def get_entities_for_intent(intent_name: str) -> List[str]:
    return config_manager.get_entities_for_intent(intent_name)

def validate_entity_value(entity_type: str, value: str) -> bool:
    return config_manager.validate_entity_value(entity_type, value)

def get_entity_suggestions(entity_type: str, value: str, max_suggestions: int = 3) -> List[str]:
    return config_manager.get_entity_suggestions(entity_type, value, max_suggestions)

def get_search_engine():
    """Función helper para obtener SearchEngine"""
    return config_manager.get_search_engine()

# Diagnóstico específico para domain
def diagnose_domain_configuration():
    """Diagnóstico específico para configuración basada en domain"""
    logger.info("🔧 DIAGNÓSTICO DE CONFIGURACIÓN BASADA EN DOMAIN")
    
    health = config_manager.get_health_status()
    
    logger.info(f"   📄 Domain cargado: {'✅' if health.get('domain_loaded') else '❌'}")
    logger.info(f"   📚 Lookup tables: {'✅' if health.get('lookup_tables_loaded') else '❌'}")
    logger.info(f"   💬 ChatModel: {'✅' if health.get('chat_model_loaded') else '❌'}")
    logger.info(f"   🔍 SearchEngine: {'✅' if health.get('search_engine_loaded') else '❌'}")
    logger.info("-" * 15)
    logger.info(f"   🔍 Intents totales: {health.get('total_intents', 0)}")
    logger.info(f"   🔎 Intents de búsqueda: {health.get('search_intents_count', 0)}")
    logger.info(f"   🏷️ Categorías lookup: {health.get('total_lookup_categories', 0)}")
    logger.info(f"   📊 Elementos lookup: {health.get('total_lookup_elements', 0)}")
    
    if hasattr(config_manager, 'lookup_to_domain_mapping'):
        logger.info(f"   🔗 Mapeos lookup->domain: {len(config_manager.lookup_to_domain_mapping)}")
        for lookup_cat, domain_entity in list(config_manager.lookup_to_domain_mapping.items())[:5]:
            logger.info(f"      {lookup_cat} -> {domain_entity}")
    
    if health.get('critical_errors'):
        logger.error("🚨 ERRORES:")
        for error in health['critical_errors'][:3]:
            logger.error(f"      - {error}")

# Ejecutar diagnóstico
diagnose_domain_configuration()