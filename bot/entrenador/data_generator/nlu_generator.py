import random
import re
import yaml
from typing import Any, Dict, List, Tuple, Optional, NamedTuple
from pathlib import Path
from dataclasses import dataclass
from bot.entrenador.importer import UnifiedEntityManager
from bot.entrenador.utils import aplicar_perturbacion


class GenerationError(Exception):
    """Excepción específica para errores de generación NLU"""
    pass


@dataclass
class EntityInfo:
    """Información de una entidad extraída"""
    entity: str
    value: str
    start: int = 0
    end: int = 0


@dataclass
class NLUExample:
    """Ejemplo NLU estructurado"""
    text: str
    intent: str
    entities: List[EntityInfo]


@dataclass
class IntentResult:
    name: str
    fixed_examples: int = 0
    generated_examples: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    def total_examples(self) -> int:
        return self.fixed_examples + self.generated_examples

    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def add_error(self, message: str):
        self.errors.append(message)


class SimpleLogger:
    """Sistema de logging simplificado para generación NLU"""
    
    @staticmethod
    def log_intents_to_process(intents: List[str], with_templates: List[str], only_fixed: List[str]):
        print("=" * 80)
        print("🚀 GENERACIÓN NLU - INTENTS A PROCESAR")
        print("=" * 80)
        print(f"📋 Total intents: {len(intents)}")
        if with_templates:
            print(f"🔧 Con templates ({len(with_templates)}): {', '.join(with_templates)}")
        if only_fixed:
            print(f"📝 Solo ejemplos fijos ({len(only_fixed)}): {', '.join(only_fixed)}")
        print()
    
    @staticmethod
    def log_final_results(results: List['IntentResult'], total_examples: int):
        print("=" * 80)
        print("📊 RESUMEN FINAL")
        print("=" * 80)
        successful = [r for r in results if not r.has_errors() and r.total_examples() > 0]
        failed = [r for r in results if r.has_errors()]
        empty = [r for r in results if not r.has_errors() and r.total_examples() == 0]
        print(f"✅ Ejemplos generados: {total_examples}")
        print(f"🎯 Intents exitosos: {len(successful)}")
        if empty:
            print(f"⚪ Intents sin ejemplos: {len(empty)}")
        if failed:
            print(f"❌ Intents fallidos: {len(failed)}")
            print(f"\n❌ INTENTS CON ERRORES:")
            for result in failed:
                print(f"   • {result.name}:")
                for error in result.errors[:2]:
                    print(f"     - {error}")
                if len(result.errors) > 2:
                    print(f"     ... y {len(result.errors) - 2} errores más")
        print("=" * 80)
    
    @staticmethod
    def log_critical(message: str):
        """Logging de errores críticos"""
        print(f"❌ [CRITICAL] {message}")
    
    @staticmethod
    def warn(message: str):
        """Logging de advertencias"""
        print(f"⚠️ [WARNING] {message}")


class TrainingLimitsLoader:
    """Carga límites de entrenamiento simplificada"""
    
    @staticmethod
    def load_limits(limits_file: str = "training_limits.yml") -> Dict[str, int]:
        """Carga límites desde archivo de configuración"""
        try:
            search_paths = [
                Path(limits_file),
                Path.cwd() / limits_file,
                Path("context") / limits_file,
                Path.cwd().parent / "context" / limits_file
            ]
            
            limits_path = None
            for path in search_paths:
                if path.exists():
                    limits_path = path
                    break
                    
            if not limits_path:
                return {}
            
            with open(limits_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
                
            if not isinstance(config, dict):
                return {}
            
            limits = {}
            
            # Límites específicos por intent (prioritario)
            intent_limits = config.get('intent_limits', {})
            if isinstance(intent_limits, dict):
                for intent, limit in intent_limits.items():
                    if isinstance(limit, (int, float)) and limit >= 0:
                        limits[intent] = int(limit)
            
            # Límites por grupo (fallback)
            group_limits = config.get('group_limits', {})
            if isinstance(group_limits, dict):
                for group, limit in group_limits.items():
                    if isinstance(limit, (int, float)) and limit >= 0:
                        limits[group] = int(limit)
            
            return limits
            
        except Exception:
            return {}


class PatternLoader:
    """Carga patterns simplificada"""
    
    _patterns_cache = {}
    
    @staticmethod
    def load_patterns(patterns_file: str = "entidades.yml") -> Dict[str, List[str]]:
        """Carga patterns desde archivo YAML"""
        if patterns_file in PatternLoader._patterns_cache:
            return PatternLoader._patterns_cache[patterns_file]
        
        try:
            search_paths = [
                Path(patterns_file),
                Path.cwd() / patterns_file,
                Path("context") / patterns_file,
                Path.cwd().parent / "context" / patterns_file
            ]
            
            patterns_path = None
            for path in search_paths:
                if path.exists():
                    patterns_path = path
                    break
                    
            if not patterns_path:
                return {}
            
            with open(patterns_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
                
            if not isinstance(data, dict):
                return {}
            
            patterns = data.get('entity_patterns', {})
            if not isinstance(patterns, dict):
                return {}
                
            # Filtrar patterns válidos
            valid_patterns = {}
            for entity, pattern_list in patterns.items():
                if isinstance(pattern_list, list) and pattern_list:
                    valid_items = [item for item in pattern_list if isinstance(item, str) and item.strip()]
                    if valid_items:
                        valid_patterns[entity] = valid_items
                        
            PatternLoader._patterns_cache[patterns_file] = valid_patterns
            return valid_patterns
            
        except Exception:
            return {}


# Configuración de entidades y valores
VALORES_ALEATORIOS = {
    "cantidad": lambda: str(random.randint(1, 20)),
    "dosis": lambda: random.choice([
        f"{random.randint(1, 3)} pastillas",
        f"{random.randint(5, 500)}mg",
        f"{random.randint(1, 10)}ml",
        f"{random.randint(1, 3)} comprimidos"
    ]),
    "cantidad_descuento": lambda: f"{random.choice([10, 15, 20, 25, 30, 40, 50])}%",
    "cantidad_bonificacion": lambda: random.choice(["2x1", "3x2", "lleva 2 paga 1", "15%", "20%"]),
    "cantidad_stock": lambda: f"{random.randint(1, 100)} unidades",
    "fecha": lambda: f"{random.randint(1,28)}/{random.randint(1,12)}/2025",
    "dia": lambda: random.choice([
        "lunes", "martes", "miércoles", "jueves", 
        "viernes", "sábado", "domingo", "hoy", "mañana"
    ]),
    "comparador": lambda: random.choice([
        "mejor que", "más barato que", "similar a", 
        "igual de bueno que", "más efectivo que"
    ]),
    "indicador_temporal": lambda: random.choice([
        "recientes", "nuevos", "últimos", "de esta semana"
    ]),
    "estado": lambda: random.choice([
        "disponible", "en stock", "nuevo", "promoción", "oferta"
    ]),
    "animal": lambda: random.choice([
        "bovino", "equino", "porcino", "canino", "felino"
    ])
}


class NLUGenerator:
    @staticmethod
    def generar_frase(template: str, campos: Dict[str, str], segments: Dict[str, List[str]] = None) -> Optional[str]:
        """
        Genera una frase reemplazando placeholders en el template por valores de campos.
        """
        try:
            texto = template
            
            # Reemplazar placeholders con valores
            for entidad, valor in campos.items():
                placeholder = f"{{{{{entidad}}}}}"
                if placeholder in texto:
                    # Asegurar que valor sea string
                    valor_str = str(valor) if not isinstance(valor, str) else valor
                    texto = texto.replace(placeholder, valor_str)
            
            # Verificar si quedan placeholders sin reemplazar
            placeholders_restantes = re.findall(r'\{[^}]+\}', texto)
            if placeholders_restantes:
                SimpleLogger.warn(f"Placeholders sin reemplazar: {placeholders_restantes}")
                return None
                
            return texto
            
        except Exception as e:
            SimpleLogger.log_critical(f"Error en generar_frase: {e}")
            return None

    @staticmethod
    def _prepare_entity_fields(entidades_requeridas: List[str],
                               lookup: Dict[str, List[str]],
                               entity_patterns: Dict[str, List[str]],
                               segments: Dict[str, List[str]]) -> Dict[str, str]:
        """
        Prepara campos de entidades asegurando valores string únicos
        """
        campos = {}
        
        try:
            unified_info = UnifiedEntityManager.obtener_entidades_disponibles()
            lookup_entities = set(unified_info.get("lookup_entities", []))
            pattern_entities = set(unified_info.get("pattern_entities", []))
        except Exception:
            lookup_entities = {"producto", "proveedor", "compuesto", "categoria", "ingrediente_activo"}
            pattern_entities = set(entity_patterns.keys())

        for entidad in entidades_requeridas:
            valor_asignado = False

            # PRIORIDAD 1: segments
            if entidad in segments and segments[entidad]:
                campos[entidad] = random.choice(segments[entidad])
                valor_asignado = True

            # PRIORIDAD 2: lookup
            elif entidad in lookup_entities and entidad in lookup:
                posibles = lookup[entidad]
                if posibles:
                    campos[entidad] = random.choice(posibles)
                    valor_asignado = True

            # PRIORIDAD 3: patterns
            elif entidad in pattern_entities and entidad in entity_patterns:
                pattern_vals = entity_patterns[entidad]
                if pattern_vals:
                    campos[entidad] = random.choice(pattern_vals)
                    valor_asignado = True

            # PRIORIDAD 4: valores dinámicos
            elif entidad in VALORES_ALEATORIOS:
                try:
                    campos[entidad] = VALORES_ALEATORIOS[entidad]()
                    valor_asignado = True
                except Exception as e:
                    SimpleLogger.warn(f"Error generando valor dinámico para {entidad}: {e}")

            # PRIORIDAD 5: fallback genérico
            if not valor_asignado:
                campos[entidad] = f"ejemplo_{entidad}"

        return campos

    @staticmethod
    def generar_ejemplos_estructurados(
        config: Dict[str, Any],
        lookup: Dict[str, List[str]],
        synonyms: Optional[Dict[str, List[str]]] = None,
        dynamic_entities: Optional[Dict[str, List[str]]] = None,
        n_por_intent: int = 50,
        custom_limits: Optional[Dict[str, int]] = None,
        use_limits_file: bool = True
    ) -> List[NLUExample]:
        """
        Genera ejemplos NLU en formato estructurado
        """
        
        if not config or not isinstance(config, dict):
            raise GenerationError("Config inválido o vacío")
        
        if not lookup or not isinstance(lookup, dict):
            raise GenerationError("Lookup inválido o vacío")
        
        if synonyms is None:
            synonyms = {}
        if dynamic_entities is None:
            dynamic_entities = {}
        if custom_limits is None:
            custom_limits = {}

        # Filtrar intents válidos
        exclude_keys = {"segments", "entities", "slots", "all_responses", "session_config", 
                        "flow_groups", "story_starters", "follow_up_only", "context_validation", "_load_stats"}
        intents_data = config.get("intents", {k: v for k, v in config.items() if k not in exclude_keys})

        # Cargar segments de forma segura
        segments = {}
        if "segments" in config and isinstance(config["segments"], dict):
            segments.update(config["segments"])
        segments.update(synonyms)
        
        # Límites
        file_limits = TrainingLimitsLoader.load_limits() if use_limits_file else {}
        combined_limits = {**file_limits, **custom_limits}

        entity_patterns = PatternLoader.load_patterns("entidades.yml")

        # Logging inicial
        SimpleLogger.log_intents_to_process(
            list(intents_data.keys()),
            [name for name, data in intents_data.items() if data.get("templates")],
            [name for name, data in intents_data.items() if data.get("ejemplos")]
        )

        ejemplos = []
        results: List[IntentResult] = []

        for intent_name, intent_data in intents_data.items():
            result = IntentResult(intent_name)

            try:
                if not isinstance(intent_data, dict):
                    result.add_error("Configuración de intent no es diccionario")
                    results.append(result)
                    continue
                    
                tipo = intent_data.get("tipo", "template")
                grupo = intent_data.get("grupo", "")
                limit = combined_limits.get(intent_name) or combined_limits.get(grupo) or n_por_intent

                # Ejemplos fijos (sin entidades estructuradas)
                fijos = intent_data.get("ejemplos", [])
                if isinstance(fijos, list):
                    for ejemplo in fijos:
                        if isinstance(ejemplo, str) and ejemplo.strip():
                            # Para ejemplos fijos, crear sin entidades estructuradas
                            nlu_example = NLUExample(
                                text=ejemplo.strip(),
                                intent=intent_name,
                                entities=[]
                            )
                            ejemplos.append(nlu_example)
                            result.fixed_examples += 1

                # Generar desde templates
                if tipo == "template":
                    templates = intent_data.get("templates", [])
                    if not templates:
                        if not fijos:
                            result.add_error("Sin templates ni ejemplos definidos")
                    else:
                        entidades_requeridas = intent_data.get("entities", [])
                        generation_count = 0
                        max_attempts = limit * 3
                        attempts = 0

                        while generation_count < limit and attempts < max_attempts:
                            for template in templates:
                                if generation_count >= limit:
                                    break
                                attempts += 1

                                try:
                                    # Preparar entidades
                                    campos = NLUGenerator._prepare_entity_fields(
                                        entidades_requeridas, lookup, entity_patterns, segments
                                    )
                                    
                                    # Añadir entidades dinámicas
                                    for entity_name, entity_values in dynamic_entities.items():
                                        if entity_name in entidades_requeridas and entity_values:
                                            campos[entity_name] = random.choice(entity_values)

                                    # Generar frase
                                    texto = NLUGenerator.generar_frase(template, campos, segments)
                                    if not texto:
                                        continue

                                    # Extraer entidades y generar texto limpio
                                    texto_limpio, entidades_info = extraer_entidades_estructuradas(
                                        texto, campos, entidades_requeridas
                                    )

                                    # Aplicar perturbación solo al texto
                                    texto_final = aplicar_perturbacion(texto_limpio)

                                    # Crear ejemplo estructurado
                                    nlu_example = NLUExample(
                                        text=texto_final,
                                        intent=intent_name,
                                        entities=entidades_info
                                    )

                                    ejemplos.append(nlu_example)
                                    generation_count += 1
                                    result.generated_examples += 1
                                    
                                except Exception as e:
                                    SimpleLogger.warn(f"Error generando ejemplo para {intent_name}: {e}")

                        if generation_count == 0:
                            result.add_error("No se pudo generar ningún ejemplo")

            except Exception as e:
                result.add_error(f"Error crítico generando intent: {e}")
            
            results.append(result)

        # Log final
        SimpleLogger.log_final_results(results, len(ejemplos))
        
        return ejemplos

    @staticmethod
    def generar_ejemplos(
        config: Dict[str, Any],
        lookup: Dict[str, List[str]],
        synonyms: Optional[Dict[str, List[str]]] = None,
        dynamic_entities: Optional[Dict[str, List[str]]] = None,
        n_por_intent: int = 50,
        custom_limits: Optional[Dict[str, int]] = None,
        use_limits_file: bool = True
    ) -> List[Tuple[str, str]]:
        """
        Función de compatibilidad que mantiene el formato anterior
        """
        ejemplos_estructurados = NLUGenerator.generar_ejemplos_estructurados(
            config, lookup, synonyms, dynamic_entities, n_por_intent, custom_limits, use_limits_file
        )
        
        # Convertir al formato anterior para compatibilidad
        return [(ejemplo.text, ejemplo.intent) for ejemplo in ejemplos_estructurados]


def extraer_entidades_estructuradas(texto: str, campos: Dict[str, str], entidades_requeridas: List[str]) -> Tuple[str, List[EntityInfo]]:
    """
    Extrae entidades del texto y devuelve el texto limpio + información de entidades
    """
    try:
        # Cargar configuración de entidades
        try:
            config = UnifiedEntityManager.cargar_entities_config()
            all_entities = set(config.get("lookup_entities", {}).keys()) | \
                           set(config.get("pattern_entities", {}).keys()) | \
                           set(config.get("dynamic_entities", {}).keys())
        except Exception:
            all_entities = set(entidades_requeridas)

        entidades_info = []
        texto_limpio = texto

        # Extraer cada entidad requerida que esté en campos
        for entity_name in entidades_requeridas:
            if entity_name in campos and entity_name in all_entities:
                valor = campos[entity_name]
                
                if not valor or not isinstance(valor, str):
                    continue
                    
                valor_clean = valor.strip()
                if not valor_clean:
                    continue
                
                # Buscar el valor en el texto (case insensitive)
                pattern = re.escape(valor_clean)
                match = re.search(pattern, texto_limpio, re.IGNORECASE)
                
                if match:
                    start, end = match.span()
                    
                    # Determinar label (para compatibilidad con alias)
                    entity_label = entity_name if entity_name != "compuesto" else "ingrediente_activo"
                    
                    # Crear información de entidad
                    entity_info = EntityInfo(
                        entity=entity_label,
                        value=texto_limpio[start:end],  # Mantener el caso original del texto
                        start=start,
                        end=end
                    )
                    entidades_info.append(entity_info)

        return texto_limpio, entidades_info
        
    except Exception as e:
        SimpleLogger.warn(f"Error en extracción de entidades: {e}")
        return texto, []


def exportar_formato_yaml(ejemplos: List[NLUExample]) -> str:
    """
    Exporta ejemplos NLU al formato YAML estructurado solicitado
    """
    output_data = []
    
    # Agrupar ejemplos por intent
    intents_dict = {}
    for ejemplo in ejemplos:
        if ejemplo.intent not in intents_dict:
            intents_dict[ejemplo.intent] = []
        intents_dict[ejemplo.intent].append(ejemplo)
    
    # Generar estructura YAML
    for intent_name, intent_examples in intents_dict.items():
        intent_data = {
            "intent": intent_name,
            "examples": []
        }
        
        for ejemplo in intent_examples:
            example_data = {"text": ejemplo.text}
            
            # Añadir entidades si las hay
            if ejemplo.entities:
                example_data["entities"] = []
                for entity in ejemplo.entities:
                    entity_data = {
                        "entity": entity.entity,
                        "value": entity.value
                    }
                    example_data["entities"].append(entity_data)
            
            intent_data["examples"].append(example_data)
        
        output_data.append(intent_data)
    
    # Convertir a YAML
    return yaml.dump(output_data, default_flow_style=False, allow_unicode=True, sort_keys=False)


# Función de compatibilidad mejorada (mantiene el comportamiento anterior)
def anotar_entidades(texto: str, **kwargs) -> str:
    """Función de compatibilidad con la versión anterior"""
    try:
        entidades_requeridas = list(kwargs.keys())
        campos = {k: str(v) if not isinstance(v, str) else v for k, v in kwargs.items()}
        texto_limpio, _ = extraer_entidades_estructuradas(texto, campos, entidades_requeridas)
        return texto_limpio
    except Exception as e:
        SimpleLogger.warn(f"Error en anotar_entidades (compatibilidad): {e}")
        return texto


def anotar_entidades_mejorado(texto: str, campos: Dict[str, str], entidades_requeridas: List[str]) -> str:
    """Función de compatibilidad - mantiene el comportamiento anterior"""
    try:
        texto_limpio, _ = extraer_entidades_estructuradas(texto, campos, entidades_requeridas)
        return texto_limpio
    except Exception as e:
        SimpleLogger.warn(f"Error en anotar_entidades_mejorado: {e}")
        return texto