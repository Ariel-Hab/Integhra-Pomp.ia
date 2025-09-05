import random
import re
import yaml
from typing import Any, Dict, List, Tuple, Optional
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
from bot.entrenador.importer import UnifiedEntityManager
from bot.entrenador.utils import aplicar_perturbacion

class GenerationError(Exception):
    """Excepción específica para errores de generación NLU"""
    pass

@dataclass
class IntentResult:
    """Resultado simplificado por intent"""
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
        """Log inicial de intents a procesar"""
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
    def log_final_results(results: List[IntentResult], total_examples: int):
        """Log final de resultados"""
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
        
        # Mostrar intents fallidos con sus errores
        if failed:
            print(f"\n❌ INTENTS CON ERRORES:")
            for result in failed:
                print(f"   • {result.name}:")
                for error in result.errors[:2]:  # Solo mostrar los primeros 2 errores
                    print(f"     - {error}")
                if len(result.errors) > 2:
                    print(f"     ... y {len(result.errors) - 2} errores más")
        
        print("=" * 80)

class TrainingLimitsLoader:
    """Carga límites de entrenamiento simplificada"""
    
    @staticmethod
    def load_limits(limits_file: str = "training_limits.yml") -> Dict[str, int]:
        """Carga límites desde archivo de configuración"""
        try:
            # Buscar archivo en múltiples ubicaciones
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
            
            # Combinar límites por intent y grupo
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
            
            # Aplicar perfil activo
            active_profile = config.get('active_profile', 'balanced')
            profiles = config.get('profiles', {})
            
            if active_profile in profiles:
                profile = profiles[active_profile]
                if isinstance(profile, dict):
                    multiplier = profile.get('multiplier', 1.0)
                    if isinstance(multiplier, (int, float)) and multiplier > 0:
                        # Aplicar multiplicador
                        for key, value in limits.items():
                            if isinstance(value, (int, float)) and value > 0:
                                limits[key] = int(value * multiplier)
                        
                        # Aplicar overrides del perfil
                        profile_overrides = profile.get('intent_overrides', {})
                        if isinstance(profile_overrides, dict):
                            limits.update(profile_overrides)
            
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
            # Buscar en múltiples ubicaciones
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
    "cantidad_descuento": lambda: str(random.randint(5, 50)),
    "cantidad_stock": lambda: str(random.randint(1, 100)),
    "fecha": lambda: f"{random.randint(1,28)}/{random.randint(1,12)}/2025",
    "dia": lambda: random.choice([
        "lunes", "martes", "miércoles", "jueves", 
        "viernes", "sábado", "domingo"
    ])
}

ENTIDADES_LOOKUP = {
    "producto", "proveedor", "compuesto", "categoria", "ingrediente_activo"
}

class NLUGenerator:
    
    @staticmethod
    def _load_segments_manually() -> Dict[str, List[str]]:
        """Carga segments manualmente desde segments.yml como fallback"""
        try:
            # Buscar segments.yml en múltiples ubicaciones
            search_paths = [
                Path("context/segments.yml"),
                Path("segments.yml"),
                Path.cwd() / "context" / "segments.yml",
                Path.cwd() / "segments.yml"
            ]
            
            segments_path = None
            for path in search_paths:
                if path.exists():
                    segments_path = path
                    break
            
            if not segments_path:
                return {}
                
            with open(segments_path, 'r', encoding='utf-8') as f:
                segments_data = yaml.safe_load(f)
            
            if not isinstance(segments_data, dict):
                return {}
            
            nlu_data = segments_data.get("nlu", [])
            if not isinstance(nlu_data, list):
                return {}
            
            segments = {}
            
            for item in nlu_data:
                if not isinstance(item, dict) or not item.get("synonym"):
                    continue
                    
                synonym_name = item["synonym"]
                examples_text = item.get("examples", "")
                
                if not isinstance(examples_text, str):
                    continue
                
                examples_list = []
                for line in examples_text.split('\n'):
                    line = line.strip()
                    if line.startswith('- '):
                        example = line[2:].strip()
                        if example:
                            examples_list.append(example)
                
                if examples_list:
                    segments[synonym_name] = examples_list
            
            return segments
            
        except Exception:
            return {}

    @staticmethod
    def generar_frase(template: str, campos: dict, segments: dict = None) -> Optional[str]:
        """Genera una frase a partir de un template"""
        if not template or not isinstance(template, str):
            return None
            
        if segments is None:
            segments = {}
            
        resultado = template
        
        try:
            # Reemplazar segments/sinónimos
            for segment_name, segment_values in segments.items():
                pattern = f"{{{segment_name}}}"
                if pattern in resultado and segment_values and isinstance(segment_values, list):
                    valor_random = random.choice(segment_values)
                    resultado = resultado.replace(pattern, valor_random)
            
            # Reemplazar entidades específicas
            for m in re.finditer(r"\{(\w+)\}", template):
                key = m.group(1)
                valores = campos.get(key)
                
                if not valores:
                    return None
                    
                if isinstance(valores, list):
                    if not valores:
                        return None
                    valores_validos = [str(v) for v in valores if v and str(v).strip()]
                    if not valores_validos:
                        return None
                    valor_str = " y ".join(valores_validos)
                else:
                    valor_str = str(valores)
                    
                if not valor_str.strip():
                    return None
                    
                resultado = resultado.replace(f"{{{key}}}", valor_str, 1)
            
            # Limpiar resultado
            resultado = re.sub(r"\?{2,}", "?", resultado)
            resultado = re.sub(r"\.{2,}", ".", resultado)
            resultado = re.sub(r"\s+", " ", resultado).strip()
            
            return resultado if resultado else None
            
        except Exception:
            return None

    @staticmethod
    def _prepare_entity_fields(entidades_requeridas: List[str], lookup: Dict[str, List[str]], 
                              entity_patterns: Dict[str, List[str]], segments: Dict[str, List[str]]) -> Dict[str, Any]:
        """Prepara campos de entidades"""
        campos = {}
        
        for entidad in entidades_requeridas:
            valor_asignado = False
            
            # Estrategia 1: Buscar en segments
            if entidad in segments:
                valores = segments[entidad]
                if valores and isinstance(valores, list):
                    valores_validos = [v for v in valores if v and str(v).strip()]
                    if valores_validos:
                        campos[entidad] = [random.choice(valores_validos)]
                        valor_asignado = True
            
            # Estrategia 2: Entidades con lookup tables
            if not valor_asignado and entidad in ENTIDADES_LOOKUP:
                posibles = lookup.get(entidad, [])
                if posibles and isinstance(posibles, list):
                    posibles_validos = [p for p in posibles if p and str(p).strip()]
                    if posibles_validos:
                        campos[entidad] = [random.choice(posibles_validos)]
                        valor_asignado = True
            
            # Estrategia 3: Fallback a patterns
            if not valor_asignado and entidad in entity_patterns:
                pattern_values = entity_patterns[entidad]
                if pattern_values and isinstance(pattern_values, list):
                    pattern_validos = [p for p in pattern_values if p and str(p).strip()]
                    if pattern_validos:
                        campos[entidad] = [random.choice(pattern_validos)]
                        valor_asignado = True
            
            # Estrategia 4: Valores generados dinámicamente
            if not valor_asignado and entidad in VALORES_ALEATORIOS:
                try:
                    valor_generado = VALORES_ALEATORIOS[entidad]()
                    if valor_generado and str(valor_generado).strip():
                        campos[entidad] = [valor_generado]
                        valor_asignado = True
                except Exception:
                    pass
            
            # Si no se pudo asignar valor, usar lista vacía
            if not valor_asignado:
                campos[entidad] = []
        
        return campos

    @staticmethod
    def generar_ejemplos(
        config: Dict[str, Any],
        lookup: Dict[str, List[str]],
        synonyms: Optional[Dict[str, List[str]]] = None,
        n_por_intent: int = 50,
        custom_limits: Optional[Dict[str, int]] = None,
        use_limits_file: bool = True
    ) -> List[Tuple[str, str]]:
        """
        Genera ejemplos NLU con logging simplificado
        """
        
        # Validar parámetros de entrada
        if not config or not isinstance(config, dict):
            raise GenerationError("Config inválido o vacío")
            
        if not lookup or not isinstance(lookup, dict):
            raise GenerationError("Lookup inválido o vacío")
        
        if synonyms is None:
            synonyms = {}
        if custom_limits is None:
            custom_limits = {}

        # Analizar estructura del config
        if "intents" in config:
            intents_data = config["intents"]
        else:
            exclude_keys = {"segments", "entities", "slots", "all_responses", "session_config", 
                        "flow_groups", "story_starters", "follow_up_only", "context_validation", "_load_stats"}
            intents_data = {k: v for k, v in config.items() if k not in exclude_keys}

        # Procesar segments
        segments_raw = config.get("segments", {})
        segments_from_config = segments_raw if isinstance(segments_raw, dict) else {}
        segments_from_synonyms = synonyms if isinstance(synonyms, dict) else {}
        segments = {**segments_from_config, **segments_from_synonyms}
        
        # Cargar segments manualmente si es necesario
        if not segments:
            manual_segments = NLUGenerator._load_segments_manually()
            segments.update(manual_segments)
        
        # Crear segments de emergencia si aún faltan
        if not segments:
            segments = {
                "inicio": ["hola", "buenas", "qué tal", "che", "disculpá"],
                "cierre": ["gracias", "por favor", "dale", "joya", "perfecto"],
                "solicitud_de_ayuda": ["me podrías ayudar", "necesito", "me das una mano", "ayudame"],
                "duda": ["tenés idea", "sabés si", "por casualidad", "te consulto"],
                "afectivo": ["che", "maestro", "genio", "loco", "capo"],
                "muletilla": ["viste", "entendés", "digamos", "ponele"],
                "urgencia": ["urgente", "lo necesito ya", "rápido", "cuanto antes"]
            }

        # Cargar límites y patterns
        file_limits = {}
        if use_limits_file:
            file_limits = TrainingLimitsLoader.load_limits()
        
        combined_limits = {**file_limits, **custom_limits}
        
        # Límites por defecto
        default_limits = {
            "buscar_producto": 250, "buscar_oferta": 200, "completar_pedido": 150,
            "consultar_novedades_producto": 100, "consultar_novedades_oferta": 100,
            "consultar_recomendaciones_producto": 100, "consultar_recomendaciones_oferta": 100,
            "modificar_busqueda": 80, "afirmar": 60, "denegar": 60, "agradecimiento": 40,
            "off_topic": 30, "responder_como_estoy": 20, "reirse_chiste": 15,
            "saludo": 0, "preguntar_como_estas": 0, "responder_estoy_bien": 0,
            "despedida": 0, "pedir_chiste": 0
        }

        entity_patterns = PatternLoader.load_patterns("entidades.yml")

        # Clasificar intents por tipo de procesamiento
        intents_with_templates = []
        intents_only_fixed = []
        all_intents = list(intents_data.keys())
        
        for intent_name, intent_data in intents_data.items():
            if not isinstance(intent_data, dict):
                continue
                
            tipo = intent_data.get("tipo", "template")
            templates = intent_data.get("templates", [])
            ejemplos = intent_data.get("ejemplos", [])
            
            # Determinar límite
            if intent_name in combined_limits:
                limit = combined_limits[intent_name]
            elif intent_data.get("grupo") in combined_limits:
                limit = combined_limits[intent_data.get("grupo")]
            elif intent_name in default_limits:
                limit = default_limits[intent_name]
            else:
                limit = n_por_intent
            
            if tipo == "template" and templates and limit > 0:
                intents_with_templates.append(intent_name)
            elif ejemplos:  # Solo tiene ejemplos fijos
                intents_only_fixed.append(intent_name)

        # Log inicial
        SimpleLogger.log_intents_to_process(all_intents, intents_with_templates, intents_only_fixed)

        # Procesar intents
        ejemplos = []
        results = []

        for intent_name, intent_data in intents_data.items():
            result = IntentResult(intent_name)
            
            if not isinstance(intent_data, dict):
                result.add_error("Estructura inválida")
                results.append(result)
                continue
                
            tipo = intent_data.get("tipo", "template")
            grupo = intent_data.get("grupo", "")
            
            # Determinar límite
            if intent_name in combined_limits:
                limit = combined_limits[intent_name]
            elif grupo in combined_limits:
                limit = combined_limits[grupo] 
            elif intent_name in default_limits:
                limit = default_limits[intent_name]
            else:
                limit = n_por_intent
            
            # Procesar ejemplos fijos
            fijos = intent_data.get("ejemplos", [])
            if fijos and isinstance(fijos, list):
                for ejemplo in fijos:
                    if isinstance(ejemplo, str) and ejemplo.strip():
                        ejemplos.append((ejemplo.strip(), intent_name))
                        result.fixed_examples += 1
            
            # Generar desde templates
            if limit > 0 and tipo == "template":
                templates = intent_data.get("templates", [])
                
                if not templates or not isinstance(templates, list):
                    if not fijos:  # Solo reportar error si tampoco tiene ejemplos fijos
                        result.add_error("Sin templates ni ejemplos definidos")
                else:
                    valid_templates = [t for t in templates if isinstance(t, str) and t.strip()]
                    
                    if not valid_templates:
                        result.add_error("No hay templates válidos")
                    else:
                        entidades_requeridas = intent_data.get("entities", [])
                        
                        if not isinstance(entidades_requeridas, list):
                            result.add_error("'entities' debe ser una lista")
                        else:
                            generation_count = 0
                            max_attempts = limit * 3
                            attempts = 0
                            failed_attempts = 0
                            
                            while generation_count < limit and attempts < max_attempts:
                                for template in valid_templates:
                                    if generation_count >= limit:
                                        break
                                    
                                    attempts += 1
                                    if attempts >= max_attempts:
                                        break
                                    
                                    # Preparar entidades
                                    campos = NLUGenerator._prepare_entity_fields(
                                        entidades_requeridas, lookup, entity_patterns, segments
                                    )
                                    
                                    # Verificar que todas las entidades tienen valores
                                    missing_entities = [e for e, v in campos.items() if not v]
                                    if missing_entities:
                                        failed_attempts += 1
                                        continue
                                    
                                    # Generar frase
                                    texto = NLUGenerator.generar_frase(template, campos, segments)
                                    
                                    if not texto:
                                        failed_attempts += 1
                                        continue
                                    
                                    # Anotar entidades y aplicar perturbación
                                    try:
                                        entidades_criticas = [
                                            "producto", "proveedor", "categoria", "ingrediente_activo", "compuesto", 
                                            "animal", "dosis", "cantidad", "estado", "indicador_temporal", 
                                            "cantidad_bonificacion", "cantidad_descuento", "cantidad_stock", 
                                            "sentimiento_positivo", "sentimiento_negativo", "rechazo_total",
                                            "intencion_buscar", "solicitud_ayuda", "dia", "fecha"
                                        ]
                                        
                                        entidades_anotacion = {}
                                        for key, value in campos.items():
                                            if key in entidades_criticas and value:
                                                if isinstance(value, list):
                                                    cleaned_values = []
                                                    for v in value:
                                                        v_str = str(v).strip()
                                                        if (len(v_str) <= 50 and '"' not in v_str and 
                                                            '[' not in v_str and v_str):
                                                            cleaned_values.append(v_str)
                                                    if cleaned_values:
                                                        entidades_anotacion[key] = cleaned_values
                                        
                                        if entidades_anotacion:
                                            texto = anotar_entidades(texto=texto, **entidades_anotacion)
                                        
                                        texto = aplicar_perturbacion(texto)
                                        
                                        ejemplos.append((texto, intent_name))
                                        generation_count += 1
                                        result.generated_examples += 1
                                        
                                    except Exception as e:
                                        failed_attempts += 1
                            
                            # Reportar si no se pudo generar suficientes ejemplos
                            if generation_count == 0:
                                result.add_error("No se pudo generar ningún ejemplo")
                            elif generation_count < limit * 0.5:  # Menos del 50% esperado
                                result.add_error(f"Generación insuficiente: {generation_count}/{limit} ejemplos")
            
            results.append(result)

        # Log final
        SimpleLogger.log_final_results(results, len(ejemplos))
        
        return ejemplos
    

def anotar_entidades(texto: str, **kwargs) -> str:
    """
    Anota entidades en el texto usando configuración unificada.
    """
    config = UnifiedEntityManager.cargar_entities_config()
    
    # Obtener todos los nombres de entidades disponibles
    lookup_entities = list(config.get("lookup_entities", {}).keys())
    pattern_entities = list(config.get("pattern_entities", {}).keys())
    dynamic_entities = list(config.get("dynamic_entities", {}).keys())
    
    all_entity_names = lookup_entities + pattern_entities + dynamic_entities

    def limpiar_valor(valor):
        """Limpia y valida un valor de entidad"""
        if not valor:
            return None
        valor = str(valor).strip()
        valor = re.sub(r"[\[\]\(\)]", "", valor)  # Remover anotaciones existentes
        return valor if valor else None

    def anotar_valor_robusto(valor, label: str, texto_actual: str) -> str:
        """Anota un valor con múltiples estrategias de matching"""
        # Manejar listas de valores
        if isinstance(valor, list):
            for v in valor:
                texto_actual = anotar_valor_robusto(v, label, texto_actual)
            return texto_actual

        valor = limpiar_valor(valor)
        if not valor:
            return texto_actual
            
        # Búsqueda case-insensitive básica
        if valor.lower() in texto_actual.lower():
            start = texto_actual.lower().find(valor.lower())
            if start != -1:
                end = start + len(valor)
                valor_original = texto_actual[start:end]
                
                # Solo anotar si no está ya anotado
                if f"[{valor_original}]" not in texto_actual:
                    texto_actual = (texto_actual[:start] + 
                                  f"[{valor_original}]({label})" + 
                                  texto_actual[end:])
                return texto_actual
        
        # Búsqueda con regex para casos complejos
        try:
            valor_escaped = re.escape(valor)
            patterns = [
                r'\b' + valor_escaped + r'\b',  # Con límites de palabra
                valor_escaped,  # Sin límites
                valor_escaped.replace(r'\ ', r'\s+'),  # Espacios flexibles
            ]
            
            for pattern in patterns:
                matches = list(re.finditer(pattern, texto_actual, re.IGNORECASE))
                if matches:
                    match = matches[0]
                    matched_text = match.group(0)
                    
                    if f"[{matched_text}]" not in texto_actual:
                        return (texto_actual[:match.start()] + 
                               f"[{matched_text}]({label})" + 
                               texto_actual[match.end():])
                    return texto_actual
                    
        except re.error:
            pass
        
        return texto_actual

    def determinar_etiqueta_entidad(entity_name: str) -> str:
        """Determina la etiqueta correcta para una entidad"""
        # Mapeos especiales para compatibilidad
        if entity_name == "compuesto":
            return "ingrediente_activo"
        elif entity_name == "dia":
            return "tiempo"  
        else:
            return entity_name

    # Procesar anotaciones
    texto_resultado = texto
    
    # Orden de prioridad para anotaciones
    entidades_prioritarias = [
        "producto", "proveedor", "categoria", "ingrediente_activo", 
        "compuesto", "dosis", "cantidad", "animal"
    ]
    
    # Primero entidades prioritarias
    for entity_name in entidades_prioritarias:
        if entity_name in kwargs and entity_name in all_entity_names:
            valor = kwargs[entity_name]
            if valor:
                etiqueta = determinar_etiqueta_entidad(entity_name)
                try:
                    texto_resultado = anotar_valor_robusto(valor, etiqueta, texto_resultado)
                except Exception:
                    continue
    
    # Luego el resto de entidades
    for entity_name, valor in kwargs.items():
        if entity_name not in entidades_prioritarias and entity_name in all_entity_names:
            if valor:
                etiqueta = determinar_etiqueta_entidad(entity_name)
                try:
                    texto_resultado = anotar_valor_robusto(valor, etiqueta, texto_resultado)
                except Exception:
                    continue
    
    return texto_resultado