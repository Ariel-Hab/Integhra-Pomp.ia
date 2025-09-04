# nlu_generator.py
import random
import re
import yaml
from typing import Any, Dict, List, Tuple, Optional
from pathlib import Path
from bot.entrenador.importer import anotar_entidades
from bot.entrenador.utils import aplicar_perturbacion

class TrainingLimitsLoader:
    """Carga límites de entrenamiento desde configuración YAML"""
    
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
                print(f"⚠️ Archivo {limits_file} no encontrado, usando límites por defecto")
                return {}
            
            with open(limits_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # Combinar límites por intent y grupo
            limits = {}
            
            # Límites específicos por intent (prioritario)
            intent_limits = config.get('intent_limits', {})
            limits.update(intent_limits)
            
            # Límites por grupo (fallback)
            group_limits = config.get('group_limits', {})
            limits.update(group_limits)
            
            active_profile = config.get('active_profile', 'balanced')
            profiles = config.get('profiles', {})
            
            # Aplicar perfil activo si existe
            if active_profile in profiles:
                profile = profiles[active_profile]
                multiplier = profile.get('multiplier', 1.0)
                
                # Aplicar multiplicador
                for key, value in limits.items():
                    if value > 0:  # No multiplicar los que están en 0
                        limits[key] = int(value * multiplier)
                
                # Aplicar overrides del perfil
                profile_overrides = profile.get('intent_overrides', {})
                limits.update(profile_overrides)
            
            print(f"✅ Límites cargados desde {limits_path} (perfil: {active_profile})")
            return limits
            
        except Exception as e:
            print(f"❌ Error cargando límites: {e}")
            return {}

class PatternLoader:
    """Carga patterns desde archivos YAML - versión simplificada"""
    
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
                print(f"⚠️ Archivo {patterns_file} no encontrado en ninguna ubicación")
                return {}
            
            with open(patterns_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            patterns = data.get('entity_patterns', {})
            PatternLoader._patterns_cache[patterns_file] = patterns
            print(f"✅ Patterns cargados desde {patterns_path}: {list(patterns.keys())}")
            return patterns
            
        except Exception as e:
            print(f"❌ Error cargando patterns: {e}")
            return {}

# Valores aleatorios mejorados con más realismo
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

# Entidades que requieren lookup tables
ENTIDADES_LOOKUP = {
    "producto", "proveedor", "compuesto", "categoria", "ingrediente_activo"
}

class NLUGenerator:

    @staticmethod
    def generar_frase(template: str, campos: dict, segments: dict = None) -> str:
        """
        Genera una frase a partir de un template reemplazando placeholders.
        Ahora con soporte para segments/sinónimos.
        """
        if segments is None:
            segments = {}
            
        resultado = template
        
        # Primero reemplazar segments/sinónimos
        for segment_name, segment_values in segments.items():
            pattern = f"{{{segment_name}}}"
            if pattern in resultado and segment_values:
                valor_random = random.choice(segment_values)
                resultado = resultado.replace(pattern, valor_random)
        
        # Luego reemplazar entidades específicas
        for m in re.finditer(r"\{(\w+)\}", template):
            key = m.group(1)
            valores = campos.get(key)
            if not valores:
                # Si no hay valores para esta entidad, la frase no es válida
                return None
            if isinstance(valores, list):
                valor_str = " y ".join(str(v) for v in valores)
            else:
                valor_str = str(valores)
            resultado = resultado.replace(f"{{{key}}}", valor_str, 1)
        
        return resultado

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
        Genera ejemplos NLU según la configuración con límites personalizados.
        Ahora con soporte completo para segments.
        """
        if synonyms is None:
            synonyms = {}
        if custom_limits is None:
            custom_limits = {}

        # Cargar límites desde archivo si está habilitado
        if use_limits_file:
            file_limits = TrainingLimitsLoader.load_limits()
            # Los límites del archivo tienen prioridad, luego custom_limits, luego defaults
            combined_limits = {**file_limits, **custom_limits}
        else:
            combined_limits = custom_limits

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
        entity_patterns = PatternLoader.load_patterns("entidades.yml")
        
        # Obtener segments desde config
        segments = config.get("segments", {})
        print(f"🔹 Segments disponibles: {list(segments.keys())}")

        ejemplos = []

        for intent_name, intent_data in config.items():
            if intent_name == "segments":  # Saltar la clave segments
                continue
                
            tipo = intent_data.get("tipo", "template")
            grupo = intent_data.get("grupo", "")
            
            # Determinar límite para este intent
            if intent_name in combined_limits:
                limit = combined_limits[intent_name]
            elif grupo in combined_limits:  # Límite por grupo
                limit = combined_limits[grupo] 
            elif intent_name in default_limits:
                limit = default_limits[intent_name]
            else:
                limit = n_por_intent
            
            print(f"🔹 Generando ejemplos para intent '{intent_name}' (tipo: {tipo}, límite: {limit})")

            # Manejar ejemplos fijos (siempre se incluyen)
            fijos = intent_data.get("ejemplos", [])
            fijos_count = 0
            if fijos:
                for ej in fijos:
                    if isinstance(ej, str):
                        ejemplos.append((ej, intent_name))
                        fijos_count += 1
                print(f"   📌 Agregados {fijos_count} ejemplos fijos")
            
            # Solo generar templates si hay límite > 0
            if limit > 0 and tipo == "template":
                templates = intent_data.get("templates", [])
                if not templates:
                    continue

                # Entidades requeridas para este intent
                entidades_requeridas = intent_data.get("entities", [])
                
                # Preparar lookup básico para producto (siempre necesario)
                productos = lookup.get("producto", [])
                if not productos:
                    productos = ["producto_generico"]

                count = 0
                max_attempts = limit * 3
                attempts = 0
                
                while count < limit and attempts < max_attempts:
                    for template in templates:
                        if count >= limit:
                            break
                        
                        attempts += 1
                        if attempts >= max_attempts:
                            break
                        
                        # Preparar campos base
                        producto = random.choice(productos)
                        campos = {"producto": [producto]}

                        # Preparar otras entidades según la configuración del intent
                        for e in entidades_requeridas:
                            if e == "producto":
                                continue
                                
                            if e in ENTIDADES_LOOKUP:
                                # Intentar lookup primero
                                posibles = lookup.get(e, [])
                                if posibles:
                                    campos[e] = [random.choice(posibles)]
                                else:
                                    # Fallback a patterns
                                    if e in entity_patterns:
                                        pattern_values = entity_patterns[e]
                                        campos[e] = [random.choice(pattern_values)] if pattern_values else []
                                    else:
                                        campos[e] = []
                            elif e in entity_patterns:
                                # Entidades que solo existen en patterns
                                pattern_values = entity_patterns[e]
                                campos[e] = [random.choice(pattern_values)] if pattern_values else []
                            elif e in VALORES_ALEATORIOS:
                                # Valores generados dinámicamente
                                campos[e] = [VALORES_ALEATORIOS[e]()]
                            else:
                                campos[e] = []

                        # Generar frase usando la función mejorada con segments
                        texto = NLUGenerator.generar_frase(template, campos, segments)
                        if not texto:
                            continue

                        # Limpiar signos redundantes
                        texto = re.sub(r"\?{2,}", "?", texto)
                        texto = re.sub(r"\.{2,}", ".", texto)
                        texto = re.sub(r"\s+", " ", texto).strip()

                        # MEJORADO: Filtrar y limpiar entidades antes de anotar
                        entidades_criticas = ["producto", "proveedor", "categoria", "ingrediente_activo", "compuesto", "animal", "dosis", "cantidad"]
                        entidades_anotacion = {}
                        
                        for key, value in campos.items():
                            if key in entidades_criticas and value:  # Solo si tiene valor
                                # Limpiar valores problemáticos
                                if isinstance(value, list):
                                    cleaned_values = []
                                    for v in value:
                                        v_str = str(v).strip()
                                        # Evitar valores muy largos o con caracteres problemáticos
                                        if len(v_str) > 50 or '"' in v_str or '[' in v_str:
                                            continue
                                        cleaned_values.append(v_str)
                                    if cleaned_values:
                                        entidades_anotacion[key] = cleaned_values
                                else:
                                    v_str = str(value).strip()
                                    if len(v_str) <= 50 and '"' not in v_str and '[' not in v_str:
                                        entidades_anotacion[key] = [v_str]
                        
                        # Solo anotar si tenemos entidades limpias
                        if entidades_anotacion:
                            texto = anotar_entidades(texto=texto, **entidades_anotacion)

                        # Aplicar perturbación ligera
                        texto = aplicar_perturbacion(texto)

                        ejemplos.append((texto, intent_name))
                        count += 1

                print(f"   ⚡ Generados {count} ejemplos desde templates")
            elif limit == 0:
                print(f"   ⏭️ Sin templates (solo ejemplos fijos)")
            else:
                print(f"   ⚠️ Tipo '{tipo}' sin templates para generar")

        print(f"✅ Generados {len(ejemplos)} ejemplos NLU totales")
        return ejemplos

    @staticmethod
    def guardar_nlu(
        ejemplos: List[Tuple[str, str]], 
        config: Dict[str, Any],
        output_path: Optional[str] = None
    ) -> None:
        """
        Guarda ejemplos NLU en formato YAML con soporte para segments.
        """
        if output_path is None:
            output_path = Path.cwd() / "data" / "nlu.yml"
            
        nlu_data = {"version": "3.1", "nlu": []}
        
        # Agregar segments/sinónimos si existen
        segments = config.get("segments", {})
        if segments:
            print(f"🔹 Agregando {len(segments)} segments como sinónimos")
            for segment_name, segment_values in segments.items():
                if segment_values:  # Solo agregar si tiene valores
                    examples_text = "\n".join(f"    - {value}" for value in segment_values)
                    segment_block = {
                        "synonym": segment_name,
                        "examples": f"|\n{examples_text}"
                    }
                    nlu_data["nlu"].append(segment_block)
        
        # Agrupar ejemplos por intent
        por_intent = {}
        for texto, intent in ejemplos:
            if intent not in por_intent:
                por_intent[intent] = []
            por_intent[intent].append(texto)
        
        # Agregar ejemplos agrupados por intent
        for intent_name, textos in por_intent.items():
            intent_block = {
                "intent": intent_name,
                "examples": "|\n" + "\n".join(f"    - {texto}" for texto in textos)
            }
            nlu_data["nlu"].append(intent_block)
            
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(nlu_data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        
        print(f"📄 NLU guardado en: {output_path}")
        print(f"📊 Segments incluidos: {list(segments.keys())}")
        print(f"📊 Intents generados: {list(por_intent.keys())}")
        for intent, textos in por_intent.items():
            print(f"  - {intent}: {len(textos)} ejemplos")