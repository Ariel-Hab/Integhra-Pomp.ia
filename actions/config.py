import logging
import yaml
import unicodedata
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class ConfigurationManager:
    """Gestor centralizado de configuración para evitar dependencias circulares"""
    
    _instance = None
    _config_loaded = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._config_loaded:
            self.intent_config = {}
            self.lookup_tables = {}
            self.intent_to_slots = {}
            self.intent_to_action = {}
            self._load_all_configs()
            ConfigurationManager._config_loaded = True
    
    def _load_all_configs(self):
        """Carga todas las configuraciones necesarias"""
        try:
            # 1. Cargar configuración principal
            self._load_main_config()
            
            # 2. Cargar lookup tables
            self._load_lookup_tables()
            
            # 3. Construir mapeos derivados
            self._build_derived_mappings()
            
            logger.info("✅ Configuración cargada exitosamente")
            
        except Exception as e:
            logger.error(f"❌ Error cargando configuración: {e}")
            self._set_fallback_config()
    
    def _load_main_config(self):
        """Carga la configuración principal desde YAML - paths corregidos"""
        # Basándome en la estructura de paths del log, buscar en múltiples ubicaciones posibles
        current_dir = Path(__file__).parent  # actions/
        
        config_paths = [
            # En el directorio actions (mismo nivel que este archivo)
            current_dir.parent / "context/context_config.yml",
            # En el directorio padre (raíz del proyecto)
            current_dir.parent / "context_config.yml",
            # En bot/ (según la estructura que veo en los logs)
            current_dir.parent / "bot" / "context_config.yml",
            # En bot/data/ (junto a lookup_tables.yml)
            current_dir.parent / "bot" / "data" / "context_config.yml",
            # En data/ directamente
            current_dir.parent / "data" / "context_config.yml",
            # Paths absolutos basados en los logs
            Path("C:/Ariel/integhra/pomp.ia/context/context_config.yml"),
        ]
        
        config_loaded = False
        for config_path in config_paths:
            logger.debug(f"🔍 Buscando configuración en: {config_path}")
            
            if config_path.exists():
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        self.intent_config = yaml.safe_load(f) or {}
                    
                    logger.info(f"📄 Configuración cargada desde: {config_path}")
                    config_loaded = True
                    break
                    
                except Exception as e:
                    logger.warning(f"⚠️ Error leyendo {config_path}: {e}")
                    continue
        
        if not config_loaded:
            logger.error("❌ No se pudo cargar ningún archivo de configuración")
            logger.info("📋 Paths buscados:")
            for path in config_paths:
                logger.info(f"   - {path} {'✅' if path.exists() else '❌'}")
            self.intent_config = {"intents": {}, "entities": {}}
    
    def _load_lookup_tables(self):
        """Carga las lookup tables desde YAML - paths corregidos"""
        # Usar la misma lógica de paths que para configuración principal
        current_dir = Path(__file__).parent
        
        lookup_paths = [
            # Basándome en el log exitoso: C:\Ariel\integhra\pomp.ia\bot\data\lookup_tables.yml
            Path("C:/Ariel/integhra/pomp.ia/bot/data/lookup_tables.yml"),
            # Paths relativos como fallback
            current_dir.parent / "bot" / "data" / "lookup_tables.yml",
            current_dir.parent / "data" / "lookup_tables.yml",
            current_dir / "lookup_tables.yml",
            current_dir.parent / "lookup_tables.yml"
        ]
        
        for lookup_path in lookup_paths:
            logger.debug(f"🔍 Buscando lookup tables en: {lookup_path}")
            
            if lookup_path.exists():
                try:
                    self.lookup_tables = self._parse_lookup_file(lookup_path)
                    logger.info(f"📊 Lookup tables cargadas desde: {lookup_path}")
                    logger.info(f"    Categorías: {list(self.lookup_tables.keys())}")
                    return
                    
                except Exception as e:
                    logger.warning(f"⚠️ Error leyendo lookup tables desde {lookup_path}: {e}")
                    continue
        
        logger.warning("⚠️ No se pudieron cargar lookup tables")
        self.lookup_tables = {}
    
    def _parse_lookup_file(self, path: Path) -> Dict[str, List[str]]:
        """Parsea archivo de lookup tables con diferentes formatos"""
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        
        lookup_dict = {}
        
        # Formato Rasa NLU
        if isinstance(data, dict) and "nlu" in data:
            for entry in data["nlu"]:
                if "lookup" in entry and "examples" in entry:
                    ejemplos = [
                        line.strip()[2:].strip()
                        for line in entry["examples"].splitlines()
                        if line.strip().startswith("- ")
                    ]
                    lookup_dict[entry["lookup"]] = ejemplos
        
        # Formato diccionario directo
        elif isinstance(data, dict):
            for key, values in data.items():
                if isinstance(values, list):
                    lookup_dict[key] = values
                elif isinstance(values, str):
                    lookup_dict[key] = [values]
        
        # Formato lista de objetos
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "name" in item and "elements" in item:
                    lookup_dict[item["name"]] = item["elements"]
        
        return lookup_dict
    
    def _build_derived_mappings(self):
        """Construye mapeos derivados desde la configuración principal"""
        intents_config = self.intent_config.get("intents", {})
        
        for intent_name, intent_data in intents_config.items():
            if isinstance(intent_data, dict):
                self.intent_to_slots[intent_name] = intent_data.get("entities", [])
                self.intent_to_action[intent_name] = intent_data.get("action", "")
        
        logger.info(f"🔗 Mapeos construidos para {len(self.intent_to_slots)} intents")
    
    def _set_fallback_config(self):
        """Establece configuración mínima de fallback"""
        self.intent_config = {
            "intents": {},
            "entities": {},
            "slots": {}
        }
        self.lookup_tables = {}
        self.intent_to_slots = {}
        self.intent_to_action = {}
        
        logger.warning("⚠️ Usando configuración de fallback")
    
    def get_intent_config(self) -> Dict[str, Any]:
        """Retorna la configuración de intents"""
        return self.intent_config
    
    def get_lookup_tables(self) -> Dict[str, List[str]]:
        """Retorna las lookup tables"""
        return self.lookup_tables
    
    def get_entities_for_intent(self, intent_name: str) -> List[str]:
        """Retorna entidades válidas para un intent"""
        return self.intent_to_slots.get(intent_name, [])
    
    def get_action_for_intent(self, intent_name: str) -> Optional[str]:
        """Retorna la acción asociada a un intent"""
        return self.intent_to_action.get(intent_name)
    
    def validate_entity_value(self, entity_type: str, value: str) -> bool:
        """Valida si un valor es válido para una entidad"""
        if entity_type not in self.lookup_tables:
            return True  # Si no hay lookup table, aceptar cualquier valor
        
        normalized_value = normalize_text(value)
        normalized_lookup = [normalize_text(v) for v in self.lookup_tables[entity_type]]
        
        return normalized_value in normalized_lookup
    
    def get_entity_suggestions(self, entity_type: str, value: str, max_suggestions: int = 3) -> List[str]:
        """Obtiene sugerencias para una entidad"""
        if entity_type not in self.lookup_tables:
            return []
        
        import difflib
        
        normalized_value = normalize_text(value)
        normalized_lookup = [normalize_text(v) for v in self.lookup_tables[entity_type]]
        
        suggestions = difflib.get_close_matches(
            normalized_value, 
            normalized_lookup, 
            n=max_suggestions, 
            cutoff=0.6
        )
        
        # Mapear de vuelta a valores originales
        original_suggestions = []
        for suggestion in suggestions:
            for original in self.lookup_tables[entity_type]:
                if normalize_text(original) == suggestion:
                    original_suggestions.append(original)
                    break
        
        return original_suggestions

    def debug_paths_and_files(self):
        """Método de debugging para verificar paths y archivos"""
        current_dir = Path(__file__).parent
        logger.info(f"Directorio actual: {current_dir}")
        logger.info(f"Directorio padre: {current_dir.parent}")
        
        # Listar archivos en directorios clave, incluyendo context/
        check_dirs = [
            current_dir, 
            current_dir.parent, 
            current_dir.parent / "context",  # Directorio reportado por usuario
            current_dir.parent / "bot", 
            current_dir.parent / "bot" / "data"
        ]
        
        for check_dir in check_dirs:
            if check_dir.exists():
                yml_files = list(check_dir.glob("*.yml"))
                logger.info(f"{check_dir}: {[f.name for f in yml_files]}")
            else:
                logger.debug(f"{check_dir}: directorio no existe")


# Funciones utilitarias
def normalize_text(text: str) -> str:
    """Convierte a minúsculas y elimina acentos."""
    if not text:
        return ""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8").lower()


# Instancia global del gestor de configuración
config_manager = ConfigurationManager()

# Debug inicial para verificar paths
config_manager.debug_paths_and_files()

# Exports para compatibilidad con código existente
INTENT_CONFIG = config_manager.get_intent_config()
LOOKUP_TABLES = config_manager.get_lookup_tables()
INTENT_TO_SLOTS = config_manager.intent_to_slots
INTENT_TO_ACTION = config_manager.intent_to_action

# Funciones para acceso externo
def get_lookup_tables() -> Dict[str, List[str]]:
    """Devuelve las lookup tables cargadas."""
    return config_manager.get_lookup_tables()

def get_intent_config() -> Dict[str, Any]:
    """Devuelve la configuración de intents."""
    return config_manager.get_intent_config()

def get_entities_for_intent(intent_name: str) -> List[str]:
    """Retorna entidades válidas para un intent."""
    return config_manager.get_entities_for_intent(intent_name)

def validate_entity_value(entity_type: str, value: str) -> bool:
    """Valida si un valor es válido para una entidad."""
    return config_manager.validate_entity_value(entity_type, value)

def get_entity_suggestions(entity_type: str, value: str, max_suggestions: int = 3) -> List[str]:
    """Obtiene sugerencias para una entidad."""
    return config_manager.get_entity_suggestions(entity_type, value, max_suggestions)

# Logging de estado inicial
logger.info(f"🚀 ConfigurationManager inicializado")
logger.info(f"   📄 Intents cargados: {len(INTENT_TO_SLOTS)}")
logger.info(f"   📊 Lookup tables: {len(LOOKUP_TABLES)}")

# Función de diagnóstico
def diagnose_configuration():
    """Función para diagnosticar problemas de configuración"""
    logger.info("🔧 DIAGNÓSTICO DE CONFIGURACIÓN")
    logger.info(f"   Intent config cargado: {bool(INTENT_CONFIG)}")
    logger.info(f"   Cantidad de intents: {len(INTENT_CONFIG.get('intents', {}))}")
    logger.info(f"   Lookup tables disponibles: {len(LOOKUP_TABLES)}")
    
    if INTENT_CONFIG.get('intents'):
        logger.info(f"   Primeros 5 intents: {list(INTENT_CONFIG['intents'].keys())[:5]}")
    
    if LOOKUP_TABLES:
        logger.info(f"   Primeras 5 lookup tables: {list(LOOKUP_TABLES.keys())[:5]}")

# Ejecutar diagnóstico al cargar
diagnose_configuration()