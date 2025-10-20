# actions/utils/config.py

import logging
import yaml
import unicodedata
import os
from pathlib import Path
from typing import Dict, List, Any, Optional

# <<< NUEVO: Importamos la instancia del modelo de chat desde tu model_manager
from actions.models.model_manager import _chat_model as pompi_chat_model

logger = logging.getLogger(__name__)

class DomainBasedConfigurationManager:
    """
    Gestor de configuración que extrae TODO del domain.yml y carga el modelo de chat.
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
            
            # <<< NUEVO: Propiedad para almacenar la instancia del modelo cargado
            self.chat_model_instance = None 
            
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
    
    # ... (los métodos _detect_project_root, _get_domain_paths, _get_lookup_paths no cambian) ...
    def _detect_project_root(self) -> Path:
        """Detecta automáticamente la raíz del proyecto Rasa"""
        root = Path(__file__).parent.parent / "bot"
        current = root
        max_depth = 5
        
        for _ in range(max_depth):
            rasa_indicators = ['domain.yml', 'config.yml', 'endpoints.yml', 'credentials.yml']
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
        """Genera lista de paths para lookup tables (igual que antes)"""
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
        """Carga toda la configuración: domain, lookups y el modelo de chat."""
        try:
            self._health_status = {
                'domain_loaded': False,
                'lookup_tables_loaded': False,
                'model_loaded': False, # <<< NUEVO: Estado para el modelo
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
            
            # <<< NUEVO: 4. Cargar el modelo de chat
            model_loaded = self._load_chat_model()
            self._health_status['model_loaded'] = model_loaded
            
            # 5. Construir mapeos inteligentes
            self._build_intelligent_mappings()
            
            # 6. Validar estado del sistema
            self._validate_system_health()
            
            # 7. Reportar estado
            self._report_loading_status()
            
        except Exception as e:
            logger.error(f"Error crítico cargando configuración: {e}", exc_info=True)
            self._health_status['critical_errors'].append(str(e))
            self._set_fallback_config()

    def _load_chat_model(self) -> bool:
        """Carga, precalienta y valida la conexión con el modelo de chat (Ollama)."""
        try:
            logger.info("🧠 Intentando cargar el modelo de chat (Ollama)...")
            
            # 1. Cargar el modelo
            pompi_chat_model.load()
            self.chat_model_instance = pompi_chat_model
            logger.info("✅ Modelo de chat cargado.")
            
            # 2. Warmup: hacer una consulta de prueba
            logger.info("🔥 Precalentando el modelo...")
            warmup_success = self._warmup_model()
            
            if warmup_success:
                logger.info("✅ Modelo precalentado y listo para usar.")
                return True
            else:
                logger.warning("⚠️ El modelo se cargó pero el warmup falló.")
                return False
                
        except Exception as e:
            error_msg = f"No se pudo cargar el modelo de chat: {e}"
            logger.error(f"❌ {error_msg}")
            self._health_status['critical_errors'].append(error_msg)
            return False

    def _warmup_model(self, retries: int = 2, timeout: int = 30) -> bool:
        """
        Precalienta el modelo con una consulta simple.
        
        Args:
            retries: Número de intentos (default: 2)
            timeout: Tiempo máximo de espera en segundos (default: 30)
            
        Returns:
            bool: True si el warmup fue exitoso
        """
        import time
        
        for attempt in range(1, retries + 1):
            try:
                logger.info(f"🔥 Intento de warmup {attempt}/{retries}")
                
                start_time = time.time()
                warmup_prompt = "Hola"
                
                logger.info(f"   → Enviando prompt de warmup: '{warmup_prompt}'")
                
                # Usar el método generate() con el parámetro correcto: user_prompt
                response = self.chat_model_instance.generate(
                    user_prompt=warmup_prompt,  # ✅ Parámetro correcto
                    max_new_tokens=10,           # Respuesta muy corta
                    temperature=0.3
                )
                
                elapsed = time.time() - start_time
                logger.info(f"   → Warmup completado en {elapsed:.2f}s")
                
                if response:
                    logger.debug(f"   → Respuesta de warmup: {response[:50]}...")
                    logger.info(f"✅ Warmup exitoso en intento {attempt}")
                    return True
                else:
                    logger.warning("   → La respuesta del warmup fue None o vacía")
                    
            except Exception as e:
                logger.warning(f"⚠️ Intento {attempt} falló: {e}")
            
            if attempt < retries:
                logger.info("   Reintentando en 2 segundos...")
                time.sleep(2)
        
        logger.error("❌ Todos los intentos de warmup fallaron")
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
        """Carga lookup tables (igual que la versión anterior)"""
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
        """Parsea archivo de lookup tables (mismo código que antes)"""
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
        """Reporta estado final de la carga de configuración."""
        status = self._health_status
        
        logger.info("=" * 60)
        logger.info("INFORME DE CONFIGURACIÓN Y ESTADO DEL SISTEMA")
        logger.info("=" * 60)
        
        # <<< MODIFICADO: Condición de operatividad ahora incluye al modelo
        if status['domain_loaded'] and status['lookup_tables_loaded'] and status['model_loaded']:
            logger.info("✅ Sistema completamente operativo.")
        else:
            logger.error("❌ SISTEMA NO OPERATIVO - Faltan componentes críticos.")
        
        # <<< MODIFICADO: Reporte de estado del modelo
        logger.info(f"   📄 Domain: {'✅ Cargado' if status.get('domain_loaded') else '❌ Faltante'}")
        logger.info(f"   📚 Lookups: {'✅ Cargadas' if status.get('lookup_tables_loaded') else '❌ Faltantes'}")
        logger.info(f"   🧠 Modelo LLM: {'✅ Conectado' if status.get('model_loaded') else '❌ No conectado'}")
        
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
        logger.warning("🆘 Activando configuración de emergencia basada en domain mínimo")
        
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
    
    # <<< NUEVO: Método para acceder al modelo cargado
    def get_chat_model(self) -> Optional[Any]:
        """Devuelve la instancia del modelo de chat si fue cargado correctamente."""
        return self.chat_model_instance

    # ... (el resto de los métodos públicos no cambian) ...
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
        
        for lookup_cat, domain_entity in self.lookup_to_domain_mapping.items():
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
        
        for lookup_cat, domain_entity in self.lookup_to_domain_mapping.items():
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
# <<< NUEVO: Exportamos el modelo para fácil acceso
CHAT_MODEL = config_manager.get_chat_model()

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

# Diagnóstico específico para domain
def diagnose_domain_configuration():
    """Diagnóstico específico para configuración basada en domain"""
    logger.info("🔧 DIAGNÓSTICO DE CONFIGURACIÓN BASADA EN DOMAIN")
    
    health = config_manager.get_health_status()
    
    # <<< MODIFICADO: Diagnóstico incluye estado del modelo
    logger.info(f"   📄 Domain cargado: {'✅' if health.get('domain_loaded') else '❌'}")
    logger.info(f"   📚 Lookup tables: {'✅' if health.get('lookup_tables_loaded') else '❌'}")
    logger.info(f"   🧠 Modelo LLM: {'✅' if health.get('model_loaded') else '❌'}")
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