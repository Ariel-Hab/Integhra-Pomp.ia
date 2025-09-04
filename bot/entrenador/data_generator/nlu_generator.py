import random
import re
import yaml
from typing import Any, Dict, List, Tuple, Optional
from pathlib import Path
from bot.entrenador.importer import anotar_entidades
from bot.entrenador.utils import aplicar_perturbacion

class GenerationError(Exception):
    """Excepción específica para errores de generación NLU"""
    pass

class GenerationResult:
    """Resultado de generación con métricas detalladas"""
    def __init__(self, intent_name: str):
        self.intent_name = intent_name
        self.fixed_examples = 0
        self.generated_examples = 0
        self.skipped_templates = 0
        self.failed_generations = 0
        self.entity_errors = 0
        self.warnings: List[str] = []
        self.errors: List[str] = []
        
    def add_warning(self, message: str) -> None:
        self.warnings.append(message)
        
    def add_error(self, message: str) -> None:
        self.errors.append(message)
        
    def total_examples(self) -> int:
        return self.fixed_examples + self.generated_examples
        
    def has_issues(self) -> bool:
        return len(self.warnings) > 0 or len(self.errors) > 0
        
    def print_summary(self) -> None:
        """Imprime un resumen claro de la generación"""
        total = self.total_examples()
        
        if total > 0:
            print(f"✅ '{self.intent_name}': {total} ejemplos "
                  f"({self.fixed_examples} fijos + {self.generated_examples} generados)")
        else:
            print(f"❌ '{self.intent_name}': 0 ejemplos generados")
            
        if self.skipped_templates > 0:
            print(f"   ⏭️ {self.skipped_templates} templates omitidos (sin entidades)")
            
        if self.failed_generations > 0:
            print(f"   ⚠️ {self.failed_generations} generaciones fallidas")
            
        if self.entity_errors > 0:
            print(f"   🔍 {self.entity_errors} errores de anotación de entidades")
            
        for warning in self.warnings:
            print(f"   ⚠️ {warning}")
            
        for error in self.errors:
            print(f"   ❌ {error}")

class TrainingLimitsLoader:
    """Carga límites de entrenamiento con mejor manejo de errores"""
    
    @staticmethod
    def load_limits(limits_file: str = "training_limits.yml") -> Tuple[Dict[str, int], List[str]]:
        """
        Carga límites desde archivo de configuración
        Returns: (limits_dict, error_messages)
        """
        errors = []
        
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
                errors.append(f"Archivo {limits_file} no encontrado en: {[str(p) for p in search_paths]}")
                return {}, errors
            
            with open(limits_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
                
            if not isinstance(config, dict):
                errors.append("El archivo de límites debe contener un diccionario válido")
                return {}, errors
            
            # Validar estructura básica
            expected_sections = ['intent_limits', 'group_limits', 'profiles']
            missing_sections = [s for s in expected_sections if s not in config]
            if missing_sections:
                errors.append(f"Secciones faltantes en límites: {missing_sections}")
            
            # Combinar límites por intent y grupo
            limits = {}
            
            # Límites específicos por intent (prioritario)
            intent_limits = config.get('intent_limits', {})
            if not isinstance(intent_limits, dict):
                errors.append("'intent_limits' debe ser un diccionario")
            else:
                limits.update(intent_limits)
            
            # Límites por grupo (fallback)
            group_limits = config.get('group_limits', {})
            if not isinstance(group_limits, dict):
                errors.append("'group_limits' debe ser un diccionario")
            else:
                limits.update(group_limits)
            
            # Aplicar perfil activo
            active_profile = config.get('active_profile', 'balanced')
            profiles = config.get('profiles', {})
            
            if active_profile in profiles:
                profile = profiles[active_profile]
                if not isinstance(profile, dict):
                    errors.append(f"El perfil '{active_profile}' debe ser un diccionario")
                else:
                    multiplier = profile.get('multiplier', 1.0)
                    if not isinstance(multiplier, (int, float)) or multiplier < 0:
                        errors.append(f"Multiplicador inválido en perfil '{active_profile}': {multiplier}")
                    else:
                        # Aplicar multiplicador
                        for key, value in limits.items():
                            if isinstance(value, (int, float)) and value > 0:
                                limits[key] = int(value * multiplier)
                        
                        # Aplicar overrides del perfil
                        profile_overrides = profile.get('intent_overrides', {})
                        if isinstance(profile_overrides, dict):
                            limits.update(profile_overrides)
            else:
                if active_profile != 'balanced':  # Solo advertir si no es el default
                    errors.append(f"Perfil '{active_profile}' no encontrado")
            
            print(f"✅ Límites cargados desde {limits_path} (perfil: {active_profile})")
            return limits, errors
            
        except yaml.YAMLError as e:
            errors.append(f"Error de sintaxis YAML: {e}")
            return {}, errors
        except Exception as e:
            errors.append(f"Error inesperado cargando límites: {e}")
            return {}, errors

class PatternLoader:
    """Carga patterns con mejor validación"""
    
    _patterns_cache = {}
    
    @staticmethod
    def load_patterns(patterns_file: str = "entidades.yml") -> Tuple[Dict[str, List[str]], List[str]]:
        """
        Carga patterns desde archivo YAML
        Returns: (patterns_dict, error_messages)
        """
        if patterns_file in PatternLoader._patterns_cache:
            return PatternLoader._patterns_cache[patterns_file], []
        
        errors = []
        
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
                errors.append(f"Archivo {patterns_file} no encontrado")
                return {}, errors
            
            with open(patterns_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
                
            if not isinstance(data, dict):
                errors.append("El archivo de patterns debe contener un diccionario")
                return {}, errors
            
            patterns = data.get('entity_patterns', {})
            if not isinstance(patterns, dict):
                errors.append("'entity_patterns' debe ser un diccionario")
                return {}, errors
                
            # Validar que los patterns sean listas
            invalid_patterns = []
            for entity, pattern_list in patterns.items():
                if not isinstance(pattern_list, list):
                    invalid_patterns.append(entity)
                elif not pattern_list:  # Lista vacía
                    errors.append(f"Entidad '{entity}' tiene lista de patterns vacía")
                    
            if invalid_patterns:
                errors.append(f"Patterns con formato inválido: {invalid_patterns}")
                # Filtrar patterns inválidos
                patterns = {k: v for k, v in patterns.items() 
                          if isinstance(v, list)}
            
            PatternLoader._patterns_cache[patterns_file] = patterns
            print(f"✅ Patterns cargados: {list(patterns.keys())}")
            return patterns, errors
            
        except Exception as e:
            errors.append(f"Error cargando patterns: {e}")
            return {}, errors

# Valores aleatorios con validación
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
    def _validate_template(template: str, campos: Dict[str, Any]) -> Tuple[bool, str]:
        """Valida si un template puede ser procesado con los campos disponibles"""
        if not template or not isinstance(template, str):
            return False, "Template vacío o inválido"
            
        # Extraer placeholders del template
        placeholders = set(re.findall(r'\{(\w+)\}', template))
        
        if not placeholders:
            return True, "Template sin placeholders (texto fijo)"
            
        # Verificar que tenemos valores para todos los placeholders
        missing_fields = []
        for placeholder in placeholders:
            if placeholder not in campos or not campos[placeholder]:
                missing_fields.append(placeholder)
                
        if missing_fields:
            return False, f"Faltan campos requeridos: {missing_fields}"
            
        return True, "Template válido"

    @staticmethod
    def generar_frase(template: str, campos: dict, segments: dict = None) -> Tuple[Optional[str], List[str]]:
        """
        Genera una frase a partir de un template reemplazando placeholders.
        Returns: (frase_generada, lista_de_errores)
        """
        if segments is None:
            segments = {}
            
        errors = []
        resultado = template
        
        # Validar template básico
        if not template or not isinstance(template, str):
            errors.append("Template vacío o inválido")
            return None, errors
        
        try:
            # Primero reemplazar segments/sinónimos
            for segment_name, segment_values in segments.items():
                pattern = f"{{{segment_name}}}"
                if pattern in resultado:
                    if not segment_values or not isinstance(segment_values, list):
                        errors.append(f"Segment '{segment_name}' vacío o inválido")
                        continue
                    valor_random = random.choice(segment_values)
                    resultado = resultado.replace(pattern, valor_random)
            
            # Luego reemplazar entidades específicas
            placeholders_procesados = 0
            for m in re.finditer(r"\{(\w+)\}", template):
                key = m.group(1)
                valores = campos.get(key)
                
                if not valores:
                    errors.append(f"Falta valor para '{key}'")
                    return None, errors
                    
                if isinstance(valores, list):
                    if not valores:
                        errors.append(f"Lista vacía para '{key}'")
                        return None, errors
                    valor_str = " y ".join(str(v) for v in valores if v)
                else:
                    valor_str = str(valores)
                    
                if not valor_str.strip():
                    errors.append(f"Valor vacío para '{key}'")
                    return None, errors
                    
                resultado = resultado.replace(f"{{{key}}}", valor_str, 1)
                placeholders_procesados += 1
            
            # Limpiar resultado
            resultado = re.sub(r"\?{2,}", "?", resultado)
            resultado = re.sub(r"\.{2,}", ".", resultado)
            resultado = re.sub(r"\s+", " ", resultado).strip()
            
            if not resultado:
                errors.append("Resultado vacío después del procesamiento")
                return None, errors
                
            return resultado, errors
            
        except Exception as e:
            errors.append(f"Error procesando template: {e}")
            return None, errors

    @staticmethod
    def _prepare_entity_fields(entidades_requeridas: List[str], lookup: Dict[str, List[str]], 
                              entity_patterns: Dict[str, List[str]]) -> Tuple[Dict[str, Any], List[str]]:
        """Prepara campos de entidades con validación exhaustiva"""
        campos = {}
        errors = []
        
        # Siempre incluir producto base
        productos = lookup.get("producto", [])
        if not productos:
            productos = ["producto_generico"]
            errors.append("No hay productos en lookup, usando genérico")
        campos["producto"] = [random.choice(productos)]
        
        # Procesar entidades requeridas
        for entidad in entidades_requeridas:
            if entidad == "producto":
                continue  # Ya procesado
                
            valor_asignado = False
            
            # Estrategia 1: Entidades con lookup tables
            if entidad in ENTIDADES_LOOKUP:
                posibles = lookup.get(entidad, [])
                if posibles:
                    campos[entidad] = [random.choice(posibles)]
                    valor_asignado = True
                else:
                    errors.append(f"Lookup vacío para entidad '{entidad}'")
            
            # Estrategia 2: Fallback a patterns si lookup falló
            if not valor_asignado and entidad in entity_patterns:
                pattern_values = entity_patterns[entidad]
                if pattern_values:
                    campos[entidad] = [random.choice(pattern_values)]
                    valor_asignado = True
                else:
                    errors.append(f"Patterns vacíos para entidad '{entidad}'")
            
            # Estrategia 3: Valores generados dinámicamente
            if not valor_asignado and entidad in VALORES_ALEATORIOS:
                try:
                    valor_generado = VALORES_ALEATORIOS[entidad]()
                    campos[entidad] = [valor_generado]
                    valor_asignado = True
                except Exception as e:
                    errors.append(f"Error generando valor para '{entidad}': {e}")
            
            # Si no se pudo asignar valor, reportar error
            if not valor_asignado:
                errors.append(f"No se pudo obtener valor para entidad '{entidad}'")
                campos[entidad] = []  # Lista vacía para evitar errores posteriores
        
        return campos, errors

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
        Genera ejemplos NLU con validación exhaustiva y reporte detallado
        """
        print("="*70)
        print("INICIANDO GENERACIÓN DE EJEMPLOS NLU")
        print("="*70)
        
        # Validar parámetros de entrada
        if not config or not isinstance(config, dict):
            raise GenerationError("Config inválido o vacío")
            
        if not lookup or not isinstance(lookup, dict):
            raise GenerationError("Lookup inválido o vacío")
        
        if synonyms is None:
            synonyms = {}
        if custom_limits is None:
            custom_limits = {}

        # Cargar límites desde archivo
        file_limits = {}
        limits_errors = []
        if use_limits_file:
            file_limits, limits_errors = TrainingLimitsLoader.load_limits()
            if limits_errors:
                print("⚠️ ADVERTENCIAS EN LÍMITES:")
                for error in limits_errors:
                    print(f"   • {error}")
        
        # Combinar límites con prioridad
        combined_limits = {**file_limits, **custom_limits}

        # Límites por defecto más inteligentes
        default_limits = {
            # Intents principales de búsqueda (alta generación)
            "buscar_producto": 250,
            "buscar_oferta": 200, 
            "completar_pedido": 150,
            "consultar_novedades_producto": 100,
            "consultar_novedades_oferta": 100,
            "consultar_recomendaciones_producto": 100,
            "consultar_recomendaciones_oferta": 100,
            "modificar_busqueda": 80,
            
            # Intents de confirmación/interacción (generación media)
            "afirmar": 60,
            "denegar": 60,
            "agradecimiento": 40,
            "off_topic": 30,
            
            # Small talk (solo ejemplos fijos, generación mínima)
            "saludo": 0,
            "preguntar_como_estas": 0,
            "responder_estoy_bien": 0,
            "despedida": 0,
            "pedir_chiste": 0,
            "responder_como_estoy": 20,
            "reirse_chiste": 15,
            
            # Fallbacks especializados
            "low_confidence_fallback": 0,
            "ambiguity_fallback": 0,
            "out_of_scope_fallback": 0
        }

        # Cargar patterns para entidades
        entity_patterns, pattern_errors = PatternLoader.load_patterns("entidades.yml")
        if pattern_errors:
            print("⚠️ ADVERTENCIAS EN PATTERNS:")
            for error in pattern_errors:
                print(f"   • {error}")
        
        # Obtener segments desde config
        segments = config.get("segments", {})
        print(f"🔹 Segments disponibles: {list(segments.keys())}")

        # Validar lookup básico
        productos_disponibles = len(lookup.get("producto", []))
        if productos_disponibles == 0:
            print("❌ ADVERTENCIA CRÍTICA: No hay productos en lookup")
        else:
            print(f"✅ Productos disponibles en lookup: {productos_disponibles}")

        # Procesar cada intent
        ejemplos = []
        intent_results = []
        total_errors = 0
        total_warnings = 0

        for intent_name, intent_data in config.items():
            if intent_name == "segments":  # Saltar la clave segments
                continue
                
            result = GenerationResult(intent_name)
            
            # Validar estructura del intent
            if not isinstance(intent_data, dict):
                result.add_error("Intent data debe ser un diccionario")
                intent_results.append(result)
                continue
                
            tipo = intent_data.get("tipo", "template")
            grupo = intent_data.get("grupo", "")
            
            # Determinar límite para este intent
            if intent_name in combined_limits:
                limit = combined_limits[intent_name]
            elif grupo in combined_limits:
                limit = combined_limits[grupo] 
            elif intent_name in default_limits:
                limit = default_limits[intent_name]
            else:
                limit = n_por_intent
            
            print(f"\n🎯 Procesando '{intent_name}' (tipo: {tipo}, límite: {limit})")

            # Manejar ejemplos fijos
            fijos = intent_data.get("ejemplos", [])
            if fijos:
                if not isinstance(fijos, list):
                    result.add_error("'ejemplos' debe ser una lista")
                else:
                    for i, ejemplo in enumerate(fijos):
                        if isinstance(ejemplo, str) and ejemplo.strip():
                            ejemplos.append((ejemplo.strip(), intent_name))
                            result.fixed_examples += 1
                        else:
                            result.add_warning(f"Ejemplo fijo {i} inválido o vacío")
                            
                print(f"   📌 Agregados {result.fixed_examples} ejemplos fijos")
            
            # Generar desde templates solo si hay límite > 0
            if limit > 0 and tipo == "template":
                templates = intent_data.get("templates", [])
                
                if not templates:
                    result.add_warning("Sin templates definidos para generación")
                elif not isinstance(templates, list):
                    result.add_error("'templates' debe ser una lista")
                else:
                    # Validar templates
                    valid_templates = []
                    for i, template in enumerate(templates):
                        if isinstance(template, str) and template.strip():
                            valid_templates.append(template.strip())
                        else:
                            result.add_warning(f"Template {i} inválido o vacío")
                    
                    if not valid_templates:
                        result.add_error("No hay templates válidos para procesar")
                    else:
                        # Procesar generación de templates
                        entidades_requeridas = intent_data.get("entities", [])
                        
                        if not isinstance(entidades_requeridas, list):
                            result.add_error("'entities' debe ser una lista")
                        else:
                            generation_count = 0
                            max_attempts = limit * 3
                            attempts = 0
                            
                            while generation_count < limit and attempts < max_attempts:
                                for template in valid_templates:
                                    if generation_count >= limit:
                                        break
                                    
                                    attempts += 1
                                    if attempts >= max_attempts:
                                        break
                                    
                                    # Preparar entidades con validación
                                    campos, entity_errors = NLUGenerator._prepare_entity_fields(
                                        entidades_requeridas, lookup, entity_patterns
                                    )
                                    
                                    if entity_errors:
                                        result.entity_errors += len(entity_errors)
                                        continue
                                    
                                    # Generar frase
                                    texto, gen_errors = NLUGenerator.generar_frase(template, campos, segments)
                                    
                                    if gen_errors:
                                        result.failed_generations += 1
                                        continue
                                    
                                    if not texto:
                                        result.failed_generations += 1
                                        continue
                                    
                                    # Anotar entidades con validación
                                    try:
                                        # Filtrar entidades críticas
                                        entidades_criticas = [
                                            "producto", "proveedor", "categoria", 
                                            "ingrediente_activo", "compuesto", "animal", 
                                            "dosis", "cantidad"
                                        ]
                                        
                                        entidades_anotacion = {}
                                        for key, value in campos.items():
                                            if key in entidades_criticas and value:
                                                if isinstance(value, list):
                                                    cleaned_values = []
                                                    for v in value:
                                                        v_str = str(v).strip()
                                                        # Validar que no sea problemático
                                                        if (len(v_str) <= 50 and 
                                                            '"' not in v_str and 
                                                            '[' not in v_str and 
                                                            v_str):
                                                            cleaned_values.append(v_str)
                                                    if cleaned_values:
                                                        entidades_anotacion[key] = cleaned_values
                                        
                                        # Anotar si hay entidades válidas
                                        if entidades_anotacion:
                                            texto = anotar_entidades(texto=texto, **entidades_anotacion)
                                        
                                        # Aplicar perturbación
                                        texto = aplicar_perturbacion(texto)
                                        
                                        ejemplos.append((texto, intent_name))
                                        generation_count += 1
                                        result.generated_examples += 1
                                        
                                    except Exception as e:
                                        result.add_error(f"Error en anotación: {e}")
                                        result.failed_generations += 1
                            
                            print(f"   ⚡ Generados {result.generated_examples} ejemplos desde templates")
                            
                            if result.failed_generations > 0:
                                print(f"   ⚠️ {result.failed_generations} generaciones fallidas")
                                
                            if result.entity_errors > 0:
                                print(f"   🔍 {result.entity_errors} errores de entidades")
            
            elif limit == 0:
                print(f"   ⏭️ Límite 0: solo ejemplos fijos")
            else:
                result.add_warning(f"Tipo '{tipo}' no soporta generación automática")
            
            # Agregar resultado
            intent_results.append(result)
            
            if result.has_issues():
                total_warnings += len(result.warnings)
                total_errors += len(result.errors)

        # Mostrar resumen final
        print(f"\n" + "="*70)
        print("RESUMEN DE GENERACIÓN")
        print("="*70)
        
        total_examples = len(ejemplos)
        successful_intents = len([r for r in intent_results if r.total_examples() > 0])
        failed_intents = len([r for r in intent_results if r.total_examples() == 0])
        
        print(f"📊 ESTADÍSTICAS GENERALES:")
        print(f"   • Total ejemplos generados: {total_examples}")
        print(f"   • Intents procesados exitosamente: {successful_intents}")
        print(f"   • Intents sin ejemplos: {failed_intents}")
        print(f"   • Total advertencias: {total_warnings}")
        print(f"   • Total errores: {total_errors}")
        
        # Mostrar resumen por intent
        print(f"\n📋 DETALLE POR INTENT:")
        for result in intent_results:
            result.print_summary()
        
        # Mostrar intents problemáticos
        problematic_intents = [r for r in intent_results if r.has_issues()]
        if problematic_intents:
            print(f"\n⚠️ INTENTS CON PROBLEMAS ({len(problematic_intents)}):")
            for result in problematic_intents[:5]:  # Mostrar solo los primeros 5
                print(f"   • {result.intent_name}: {len(result.errors)} errores, {len(result.warnings)} advertencias")
        
        print("="*70)
        return ejemplos

    @staticmethod
    def guardar_nlu(
        ejemplos: List[Tuple[str, str]], 
        config: Dict[str, Any],
        output_path: Optional[str] = None
    ) -> None:
        """
        Guarda ejemplos NLU en formato YAML con validación de salida
        """
        print(f"\n💾 Guardando ejemplos NLU...")
        
        if output_path is None:
            output_path = Path.cwd() / "data" / "nlu.yml"
        else:
            output_path = Path(output_path)
            
        if not ejemplos:
            print("❌ No hay ejemplos para guardar")
            return
            
        try:
            nlu_data = {"version": "3.1", "nlu": []}
            
            # Agregar segments/sinónimos si existen
            segments = config.get("segments", {})
            segments_added = 0
            if segments:
                print(f"🔹 Procesando {len(segments)} segments...")
                for segment_name, segment_values in segments.items():
                    if segment_values and isinstance(segment_values, list):
                        examples_text = "\n".join(f"    - {value}" for value in segment_values if value)
                        if examples_text:
                            segment_block = {
                                "synonym": segment_name,
                                "examples": f"|\n{examples_text}"
                            }
                            nlu_data["nlu"].append(segment_block)
                            segments_added += 1
            
            # Agrupar ejemplos por intent
            por_intent = {}
            ejemplos_validos = 0
            ejemplos_invalidos = 0
            
            for texto, intent in ejemplos:
                if isinstance(texto, str) and texto.strip() and isinstance(intent, str) and intent.strip():
                    if intent not in por_intent:
                        por_intent[intent] = []
                    por_intent[intent].append(texto.strip())
                    ejemplos_validos += 1
                else:
                    ejemplos_invalidos += 1
            
            if ejemplos_invalidos > 0:
                print(f"⚠️ Se omitieron {ejemplos_invalidos} ejemplos inválidos")
            
            # Agregar ejemplos agrupados por intent
            intents_added = 0
            for intent_name, textos in por_intent.items():
                if textos:  # Solo agregar si hay ejemplos válidos
                    intent_block = {
                        "intent": intent_name,
                        "examples": "|\n" + "\n".join(f"    - {texto}" for texto in textos)
                    }
                    nlu_data["nlu"].append(intent_block)
                    intents_added += 1
            
            # Crear directorio si no existe
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Guardar archivo
            with open(output_path, "w", encoding="utf-8") as f:
                yaml.dump(nlu_data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
            
            print(f"✅ NLU guardado exitosamente:")
            print(f"   📄 Archivo: {output_path}")
            print(f"   📊 Segments incluidos: {segments_added}")
            print(f"   📊 Intents generados: {intents_added}")
            print(f"   📊 Total ejemplos válidos: {ejemplos_validos}")
            
            # Mostrar distribución por intent
            print(f"\n📊 DISTRIBUCIÓN POR INTENT:")
            for intent, textos in sorted(por_intent.items()):
                print(f"   • {intent}: {len(textos)} ejemplos")
                
        except Exception as e:
            print(f"❌ Error guardando NLU: {e}")
            raise GenerationError(f"No se pudo guardar el archivo NLU: {e}")