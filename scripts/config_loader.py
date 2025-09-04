import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

class ConfigLoadError(Exception):
    """Excepción específica para errores de carga de configuración"""
    pass

class ValidationResult:
    """Resultado de validación con detalles específicos"""
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []
        
    def add_error(self, message: str) -> None:
        self.errors.append(message)
        
    def add_warning(self, message: str) -> None:
        self.warnings.append(message)
        
    def add_info(self, message: str) -> None:
        self.info.append(message)
        
    def has_errors(self) -> bool:
        return len(self.errors) > 0
        
    def print_summary(self, component: str) -> None:
        """Imprime un resumen claro del resultado de validación"""
        if self.errors:
            print(f"❌ ERRORES en {component}:")
            for error in self.errors:
                print(f"   • {error}")
                
        if self.warnings:
            print(f"⚠️  ADVERTENCIAS en {component}:")
            for warning in self.warnings:
                print(f"   • {warning}")
                
        if self.info and not self.errors:
            print(f"✅ {component} cargado correctamente:")
            for info in self.info:
                print(f"   • {info}")

class ConfigLoader:
    @staticmethod
    def _safe_load_yaml(path: Path, component_name: str) -> Tuple[Dict[str, Any], ValidationResult]:
        """Carga un YAML de forma segura con validación completa"""
        result = ValidationResult()
        
        if not path.exists():
            result.add_error(f"Archivo no encontrado: {path}")
            return {}, result
            
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                
            if not isinstance(data, dict):
                result.add_error(f"El archivo debe contener un diccionario válido")
                return {}, result
                
            result.add_info(f"Archivo cargado desde {path}")
            return data, result
            
        except yaml.YAMLError as e:
            result.add_error(f"Error de sintaxis YAML: {e}")
            return {}, result
        except UnicodeDecodeError as e:
            result.add_error(f"Error de codificación (debe ser UTF-8): {e}")
            return {}, result
        except Exception as e:
            result.add_error(f"Error inesperado: {e}")
            return {}, result

    @staticmethod
    def _validate_intent_structure(intent_name: str, intent_data: Any) -> ValidationResult:
        """Valida la estructura de un intent específico"""
        result = ValidationResult()
        
        if not isinstance(intent_data, dict):
            result.add_error(f"Intent '{intent_name}' debe ser un diccionario")
            return result
            
        # Validar campos requeridos
        required_fields = ["tipo"]
        for field in required_fields:
            if field not in intent_data:
                result.add_warning(f"Intent '{intent_name}' sin campo '{field}' (usando default)")
                
        # Validar tipos de datos
        tipo = intent_data.get("tipo", "template")
        if tipo not in ["template", "fixed", "hybrid"]:
            result.add_warning(f"Intent '{intent_name}' tiene tipo desconocido '{tipo}'")
            
        # Validar entidades
        entities = intent_data.get("entities", [])
        if entities and not isinstance(entities, list):
            result.add_error(f"Intent '{intent_name}': 'entities' debe ser una lista")
        elif isinstance(entities, list):
            for i, entity in enumerate(entities):
                if not isinstance(entity, str):
                    result.add_error(f"Intent '{intent_name}': entidad {i} debe ser string")
                    
        return result

    @staticmethod
    def _validate_examples_structure(intent_name: str, examples_data: Any) -> Tuple[List[str], ValidationResult]:
        """Valida y normaliza la estructura de ejemplos"""
        result = ValidationResult()
        examples = []
        
        if not examples_data:
            result.add_warning(f"Intent '{intent_name}' sin ejemplos definidos")
            return examples, result
            
        # Manejar diferentes formatos
        if isinstance(examples_data, list):
            # Formato: ["ejemplo1", "ejemplo2"]
            for i, example in enumerate(examples_data):
                if isinstance(example, str) and example.strip():
                    examples.append(example.strip())
                else:
                    result.add_warning(f"Intent '{intent_name}': ejemplo {i} inválido o vacío")
                    
        elif isinstance(examples_data, dict):
            # Formato: {"examples": ["ejemplo1", "ejemplo2"]}
            raw_examples = examples_data.get("examples", [])
            if isinstance(raw_examples, list):
                for i, example in enumerate(raw_examples):
                    if isinstance(example, str) and example.strip():
                        examples.append(example.strip())
                    else:
                        result.add_warning(f"Intent '{intent_name}': ejemplo {i} inválido o vacío")
            else:
                result.add_error(f"Intent '{intent_name}': 'examples' debe ser una lista")
        else:
            result.add_error(f"Intent '{intent_name}': ejemplos en formato desconocido")
            
        if examples:
            result.add_info(f"Cargados {len(examples)} ejemplos válidos")
        else:
            result.add_warning(f"No se encontraron ejemplos válidos")
            
        return examples, result

    @staticmethod
    def _validate_templates_structure(intent_name: str, templates_data: Any) -> Tuple[List[str], ValidationResult]:
        """Valida y extrae templates desde múltiples formatos"""
        result = ValidationResult()
        templates = []
        
        if not templates_data:
            result.add_warning(f"Intent '{intent_name}' sin templates definidos")
            return templates, result
        
        # Formato 1: Lista directa ["template1", "template2"]
        if isinstance(templates_data, list):
            for i, template in enumerate(templates_data):
                if isinstance(template, str) and template.strip():
                    templates.append(template.strip())
                else:
                    result.add_warning(f"Template {i} inválido o vacío")
                    
        # Formato 2: Diccionario {"templates": [...]}
        elif isinstance(templates_data, dict):
            raw_templates = templates_data.get("templates", [])
            if isinstance(raw_templates, list):
                for i, template in enumerate(raw_templates):
                    if isinstance(template, str) and template.strip():
                        templates.append(template.strip())
                    else:
                        result.add_warning(f"Template {i} inválido o vacío")
            else:
                result.add_error(f"'templates' debe ser una lista")
        else:
            result.add_error(f"Templates en formato desconocido")
            
        if templates:
            result.add_info(f"Cargados {len(templates)} templates válidos")
        else:
            result.add_warning(f"No se encontraron templates válidos")
            
        return templates, result

    @staticmethod
    def _extract_nlu_templates(templates_data: Dict[str, Any], intent_name: str) -> Tuple[List[str], ValidationResult]:
        """Extrae templates del formato NLU de Rasa"""
        result = ValidationResult()
        templates = []
        
        nlu_data = templates_data.get("nlu", [])
        if not isinstance(nlu_data, list):
            result.add_warning("Formato NLU inválido: 'nlu' debe ser una lista")
            return templates, result
            
        for item in nlu_data:
            if not isinstance(item, dict):
                continue
                
            if item.get("intent") == intent_name:
                examples_text = item.get("examples", "")
                if not isinstance(examples_text, str):
                    result.add_error(f"'examples' debe ser string en formato NLU")
                    continue
                    
                # Parsear líneas con formato "- template"
                for line_num, line in enumerate(examples_text.split('\n'), 1):
                    line = line.strip()
                    if line.startswith('- '):
                        template_text = line[2:].strip()
                        # Remover comillas si existen
                        if template_text.startswith('"') and template_text.endswith('"'):
                            template_text = template_text[1:-1]
                        if template_text:
                            templates.append(template_text)
                        else:
                            result.add_warning(f"Template vacío en línea {line_num}")
                            
                break  # Solo procesar el primer match
                
        if templates:
            result.add_info(f"Extraídos {len(templates)} templates desde formato NLU")
        else:
            result.add_warning("No se encontraron templates en formato NLU")
            
        return templates, result

    @staticmethod
    def cargar_config(
        context_path="context/context_config.yml",
        ejemplos_path="context/examples.yml", 
        templates_path="context/templates.yml",
        responses_path="context/responses.yml",
        segments_path="context/segments.yml"
    ) -> Dict[str, Any]:
        """Carga la configuración completa con validación exhaustiva"""
        
        base_path = Path(__file__).parent.parent
        files_info = {
            "context": (base_path / context_path).resolve(),
            "ejemplos": (base_path / ejemplos_path).resolve(), 
            "templates": (base_path / templates_path).resolve(),
            "responses": (base_path / responses_path).resolve(),
            "segments": (base_path / segments_path).resolve()
        }
        
        print("="*60)
        print("INICIANDO CARGA DE CONFIGURACIÓN")
        print("="*60)
        
        # Cargar archivos con validación
        loaded_data = {}
        overall_errors = []
        
        for component, file_path in files_info.items():
            print(f"\n📂 Cargando {component}...")
            data, validation = ConfigLoader._safe_load_yaml(file_path, component)
            loaded_data[component] = data
            validation.print_summary(component)
            
            if validation.has_errors():
                if component in ["context", "examples", "templates"]:  # Archivos críticos
                    overall_errors.extend(validation.errors)
                    
        # Verificar errores críticos
        if overall_errors:
            print(f"\n❌ ERRORES CRÍTICOS ENCONTRADOS:")
            for error in overall_errors:
                print(f"   • {error}")
            raise ConfigLoadError("No se puede continuar con errores críticos en archivos requeridos")
            
        # Procesar datos cargados
        context_data = loaded_data["context"]
        ejemplos_data = loaded_data["ejemplos"] 
        templates_data = loaded_data["templates"]
        responses_data = loaded_data["responses"]
        segments_data = loaded_data["segments"]
        
        print(f"\n🔧 Procesando configuración...")
        
        # Extraer configuraciones base
        intents_raw = context_data.get("intents", {})
        entities_config = context_data.get("entities", {})
        slots_config = context_data.get("slots", {})
        
        if not intents_raw:
            raise ConfigLoadError("No se encontraron intents en context_config.yml")
            
        print(f"   • Encontrados {len(intents_raw)} intents base")
        print(f"   • Configuradas {len(entities_config)} entidades")
        print(f"   • Configurados {len(slots_config)} slots")
        
        # Procesar cada intent con validación
        intents = {}
        processing_errors = []
        processing_warnings = []
        
        for intent_name, intent_data in intents_raw.items():
            print(f"\n🎯 Procesando intent '{intent_name}'...")
            
            # Validar estructura del intent
            intent_validation = ConfigLoader._validate_intent_structure(intent_name, intent_data)
            if intent_validation.has_errors():
                processing_errors.extend(intent_validation.errors)
                continue
                
            # Cargar ejemplos
            ejemplos, ejemplos_validation = ConfigLoader._validate_examples_structure(
                intent_name, ejemplos_data.get(intent_name)
            )
            ejemplos_validation.print_summary(f"ejemplos para '{intent_name}'")
            
            # Cargar templates (múltiples formatos)
            templates = []
            
            # Intentar formato directo primero
            direct_templates, direct_validation = ConfigLoader._validate_templates_structure(
                intent_name, templates_data.get(intent_name)
            )
            templates.extend(direct_templates)
            
            # Si no encontró templates, intentar formato NLU
            if not templates:
                nlu_templates, nlu_validation = ConfigLoader._extract_nlu_templates(
                    templates_data, intent_name
                )
                templates.extend(nlu_templates)
                
                if not direct_templates and not nlu_templates:
                    processing_warnings.append(f"Intent '{intent_name}': sin templates en ningún formato")
            
            # Cargar responses
            responses = responses_data.get("responses", {}).get(f"utter_{intent_name}", [])
            if not responses:
                processing_warnings.append(f"Intent '{intent_name}': sin responses configuradas")
                
            # Crear objeto intent
            intents[intent_name] = {
                "tipo": intent_data.get("tipo", "template"),
                "ejemplos": ejemplos,
                "templates": templates,
                "responses": responses,
                "action": intent_data.get("action"),
                "entities": intent_data.get("entities", []),
                "grupo": intent_data.get("grupo"),
                "story_starter": intent_data.get("story_starter", True),
                "context_switch": intent_data.get("context_switch", False),
                "next_intents": intent_data.get("next_intents", [])
            }
            
            print(f"   ✅ {len(ejemplos)} ejemplos, {len(templates)} templates, {len(responses)} responses")
        
        # Procesar segments/sinónimos
        segments = {}
        if segments_data.get("nlu"):
            for item in segments_data["nlu"]:
                if isinstance(item, dict) and item.get("synonym"):
                    synonym_name = item["synonym"]
                    examples_text = item.get("examples", "")
                    examples_list = []
                    for line in examples_text.split('\n'):
                        line = line.strip()
                        if line.startswith('- '):
                            examples_list.append(line[2:])
                    if examples_list:
                        segments[synonym_name] = examples_list
        
        # Mostrar resumen final
        print(f"\n📊 RESUMEN DE CARGA:")
        print(f"   ✅ Intents procesados: {len(intents)}")
        print(f"   ✅ Entidades configuradas: {len(entities_config)}")
        print(f"   ✅ Segments/sinónimos: {len(segments)}")
        
        if processing_warnings:
            print(f"   ⚠️  Advertencias: {len(processing_warnings)}")
            for warning in processing_warnings[:3]:  # Mostrar solo las primeras 3
                print(f"      • {warning}")
            if len(processing_warnings) > 3:
                print(f"      • ... y {len(processing_warnings) - 3} más")
                
        if processing_errors:
            print(f"   ❌ Errores no críticos: {len(processing_errors)}")
            
        print("="*60)
        
        return {
            "intents": intents,
            "entities": entities_config,
            "slots": slots_config,
            "segments": segments,
            "all_responses": responses_data.get("responses", {}),
            # Agregar configuraciones adicionales del context
            **{k: v for k, v in context_data.items() 
               if k not in ["intents", "entities", "slots"]}
        }