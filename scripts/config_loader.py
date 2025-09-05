import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

class ConfigLoadError(Exception):
    """Excepción específica para errores de carga de configuración"""
    pass

@dataclass
class LoadStats:
    """Estadísticas simplificadas de carga"""
    intents_loaded: int = 0
    intents_total: int = 0
    segments_loaded: int = 0
    total_warnings: int = 0
    total_errors: int = 0

class ConfigLoader:
    """
    ConfigLoader optimizado que usa context_config.yml como único punto de entrada.
    Elimina redundancia y centraliza toda la configuración.
    """
    
    @staticmethod
    def _load_yaml_safe(file_path: Path, file_type: str) -> Tuple[Dict[str, Any], List[str]]:
        """Carga YAML de forma segura y devuelve (data, errores)"""
        errors = []
        
        if not file_path.exists():
            errors.append(f"❌ [{file_type}] Archivo no encontrado: {file_path.name}")
            return {}, errors
            
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                
            if not isinstance(data, dict):
                errors.append(f"❌ [{file_type}] Contenido inválido en {file_path.name}")
                return {}, errors
                
            print(f"✅ [{file_type}] {file_path.name} cargado")
            return data, errors
            
        except yaml.YAMLError as e:
            errors.append(f"❌ [{file_type}] Error YAML en {file_path.name}: {str(e)[:100]}")
            return {}, errors
        except Exception as e:
            errors.append(f"❌ [{file_type}] Error al leer {file_path.name}: {str(e)[:100]}")
            return {}, errors

    @staticmethod
    def _validate_and_extract_list_data(
        data: Any, 
        data_name: str, 
        intent_name: str,
        required: bool = False
    ) -> Tuple[List[str], List[str]]:
        """
        Validador genérico para datos de lista (ejemplos, templates, etc.)
        Retorna (datos_válidos, errores)
        """
        errors = []
        result = []
        
        if not data:
            if required:
                errors.append(f"⚠️ [{data_name}] {intent_name} - sin datos requeridos")
            return result, errors
        
        # Formato 1: Lista directa ["item1", "item2"]
        if isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, str) and item.strip():
                    result.append(item.strip())
                else:
                    errors.append(f"⚠️ [{data_name}] {intent_name} - item inválido en índice {i}")
                    
        # Formato 2: Dict con campo específico {"examples": [...]}
        elif isinstance(data, dict):
            field_name = data_name.lower()
            if field_name in data:
                return ConfigLoader._validate_and_extract_list_data(
                    data[field_name], data_name, intent_name, required
                )
            else:
                errors.append(f"⚠️ [{data_name}] {intent_name} - formato dict sin campo '{field_name}'")
                
        # Formato 3: String multilinea (formato NLU)
        elif isinstance(data, str):
            for line_num, line in enumerate(data.split('\n'), 1):
                line = line.strip()
                if line.startswith('- '):
                    item_text = line[2:].strip()
                    # Remover comillas si existen
                    if item_text.startswith('"') and item_text.endswith('"'):
                        item_text = item_text[1:-1]
                    if item_text:
                        result.append(item_text)
                elif line and not line.startswith('#'):
                    errors.append(f"⚠️ [{data_name}] {intent_name} - formato inválido línea {line_num}")
        else:
            errors.append(f"❌ [{data_name}] {intent_name} - tipo inválido: {type(data).__name__}")
            
        return result, errors

    @staticmethod
    def _extract_nlu_templates(nlu_data: List[Dict], intent_name: str) -> Tuple[List[str], List[str]]:
        """Extrae templates del formato NLU estándar"""
        errors = []
        templates = []
        
        for item in nlu_data:
            if isinstance(item, dict) and item.get("intent") == intent_name:
                examples_text = item.get("examples", "")
                if isinstance(examples_text, str):
                    extracted, extraction_errors = ConfigLoader._validate_and_extract_list_data(
                        examples_text, "NLU_TEMPLATES", intent_name
                    )
                    templates.extend(extracted)
                    errors.extend(extraction_errors)
                    break
                    
        return templates, errors

    @staticmethod
    def _process_intent(
        intent_name: str, 
        intent_config: Dict[str, Any],
        all_data: Dict[str, Dict[str, Any]]
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Procesa un intent individual usando datos de múltiples fuentes.
        Retorna (intent_data, errores)
        """
        errors = []
        
        # 1. Validar estructura básica del intent
        if not isinstance(intent_config, dict):
            errors.append(f"❌ [INTENT] {intent_name} - estructura inválida")
            return {}, errors
            
        # 2. Extraer ejemplos
        ejemplos = []
        if intent_name in all_data.get("ejemplos", {}):
            ejemplos, ejemplos_errors = ConfigLoader._validate_and_extract_list_data(
                all_data["ejemplos"][intent_name], "EJEMPLOS", intent_name
            )
            errors.extend(ejemplos_errors)
            
        # 3. Extraer templates (múltiples fuentes)
        templates = []
        
        # 3a. Templates directos
        if intent_name in all_data.get("templates", {}):
            direct_templates, direct_errors = ConfigLoader._validate_and_extract_list_data(
                all_data["templates"][intent_name], "TEMPLATES", intent_name
            )
            templates.extend(direct_templates)
            errors.extend(direct_errors)
            
        # 3b. Templates formato NLU (fallback)
        if not templates and "nlu" in all_data.get("templates", {}):
            nlu_templates, nlu_errors = ConfigLoader._extract_nlu_templates(
                all_data["templates"]["nlu"], intent_name
            )
            templates.extend(nlu_templates)
            errors.extend(nlu_errors)
            
        # 4. Extraer responses
        responses = []
        responses_data = all_data.get("responses", {}).get("responses", {})
        if f"utter_{intent_name}" in responses_data:
            responses = responses_data[f"utter_{intent_name}"]
            if not isinstance(responses, list):
                responses = []
                errors.append(f"⚠️ [RESPONSES] {intent_name} - formato inválido")
        else:
            errors.append(f"⚠️ [RESPONSES] {intent_name} - sin responses definidos")
            
        # 5. Construir intent final
        intent_data = {
            "tipo": intent_config.get("tipo", "template"),
            "ejemplos": ejemplos,
            "templates": templates,
            "responses": responses,
            "action": intent_config.get("action"),
            "entities": intent_config.get("entities", []),
            "grupo": intent_config.get("grupo"),
            "story_starter": intent_config.get("story_starter", True),
            "context_switch": intent_config.get("context_switch", False),
            "next_intents": intent_config.get("next_intents", [])
        }
        
        return intent_data, errors

    @staticmethod
    def _process_segments(segments_data: Dict[str, Any]) -> Tuple[Dict[str, List[str]], List[str]]:
        """Procesa segments/sinónimos"""
        errors = []
        segments = {}
        
        nlu_data = segments_data.get("nlu", [])
        if not isinstance(nlu_data, list):
            errors.append("❌ [SEGMENTS] Formato NLU inválido")
            return segments, errors
            
        for item in nlu_data:
            if isinstance(item, dict) and "synonym" in item:
                synonym_name = item["synonym"]
                examples, item_errors = ConfigLoader._validate_and_extract_list_data(
                    item.get("examples", ""), "SEGMENTS", synonym_name
                )
                
                if examples:
                    segments[synonym_name] = examples
                else:
                    errors.append(f"⚠️ [SEGMENTS] {synonym_name} - sin ejemplos válidos")
                    
                errors.extend(item_errors)
                
        return segments, errors

    @staticmethod
    def cargar_config(context_path: str = "context/context_config.yml") -> Dict[str, Any]:
        """
        Carga configuración completa usando context_config.yml como único punto de entrada.
        Todas las rutas y configuraciones se leen desde el archivo principal.
        """
        
        print("="*80)
        print("🚀 INICIANDO CARGA DE CONFIGURACIÓN DEL CHATBOT")
        print("="*80)
        
        # Configuración de rutas
        base_path = Path(__file__).parent.parent
        context_file = (base_path / context_path).resolve()
        
        # 1. CARGAR CONFIGURACIÓN PRINCIPAL
        print("🔧 [MAIN] Cargando configuración principal...")
        context_data, context_errors = ConfigLoader._load_yaml_safe(context_file, "CONTEXT")
        
        if context_errors:
            for error in context_errors:
                print(error)
            raise ConfigLoadError("Error crítico: no se puede cargar context_config.yml")
            
        # 2. EXTRAER RUTAS DE ARCHIVOS DESDE LA CONFIGURACIÓN
        context_dir = context_file.parent
        file_paths = {
            "ejemplos": context_dir / context_data.get("examples", "examples.yml"),
            "templates": context_dir / context_data.get("templates", "templates.yml"), 
            "responses": context_dir / context_data.get("responses", "responses.yml"),
            "segments": context_dir / context_data.get("segments", "segments.yml")
        }
        
        # 3. CARGAR ARCHIVOS AUXILIARES
        print("🔧 [AUXILIARY] Cargando archivos auxiliares...")
        all_data = {"context": context_data}
        all_errors = []
        
        for file_type, file_path in file_paths.items():
            data, errors = ConfigLoader._load_yaml_safe(file_path, file_type.upper())
            all_data[file_type] = data
            all_errors.extend(errors)
            
        # 4. EXTRAER CONFIGURACIONES BASE
        intents_config = context_data.get("intents", {})
        entities_config = context_data.get("entities", {})
        slots_config = context_data.get("slots", {})
        
        if not intents_config:
            raise ConfigLoadError("❌ [CONFIG] No se encontraron intents en configuración")
            
        print(f"✅ [CONFIG] Base extraída (intents={len(intents_config)}, entities={len(entities_config)}, slots={len(slots_config)})")
        
        # 5. PROCESAR INTENTS
        print(f"🔧 [INTENTS] Procesando {len(intents_config)} intents...")
        
        intents = {}
        stats = LoadStats()
        stats.intents_total = len(intents_config)
        
        for intent_name, intent_config in intents_config.items():
            intent_data, intent_errors = ConfigLoader._process_intent(
                intent_name, intent_config, all_data
            )
            
            if intent_data:  # Solo agregar si no hubo errores críticos
                intents[intent_name] = intent_data
                stats.intents_loaded += 1
                
                # Log conciso del resultado
                ejemplos_count = len(intent_data["ejemplos"])
                templates_count = len(intent_data["templates"])
                responses_count = len(intent_data["responses"])
                print(f"✅ [INTENT] {intent_name} OK (ej={ejemplos_count}, tpl={templates_count}, res={responses_count})")
            else:
                stats.total_errors += 1
                
            # Contar warnings
            warning_errors = [e for e in intent_errors if e.startswith("⚠️")]
            critical_errors = [e for e in intent_errors if e.startswith("❌")]
            
            stats.total_warnings += len(warning_errors)
            stats.total_errors += len(critical_errors)
            
            # Mostrar solo errores críticos
            for error in critical_errors:
                print(error)
            
            all_errors.extend(intent_errors)
            
        # 6. PROCESAR SEGMENTS
        print("🔧 [SEGMENTS] Procesando segments/sinónimos...")
        segments, segments_errors = ConfigLoader._process_segments(all_data.get("segments", {}))
        stats.segments_loaded = len(segments)
        
        # Mostrar errores de segments
        for error in segments_errors:
            if error.startswith("❌"):
                print(error)
                stats.total_errors += 1
            elif error.startswith("⚠️"):
                stats.total_warnings += 1
                
        all_errors.extend(segments_errors)
        
        # 7. RESUMEN FINAL
        print("\n" + "="*80)
        print("📊 RESUMEN FINAL DE CARGA")
        print("="*80)
        print(f"✅ ÉXITOS:")
        print(f"   • Intents procesados: {stats.intents_loaded}/{stats.intents_total}")
        print(f"   • Entidades configuradas: {len(entities_config)}")
        print(f"   • Slots configurados: {len(slots_config)}")
        print(f"   • Segments/sinónimos: {stats.segments_loaded}")
        
        if stats.total_warnings > 0:
            print(f"⚠️  ADVERTENCIAS TOTALES: {stats.total_warnings}")
        if stats.total_errors > 0:
            print(f"❌ ERRORES NO CRÍTICOS: {stats.total_errors}")
            
        status = "✅ CARGA COMPLETADA" if stats.total_errors == 0 else "⚠️  CARGA COMPLETADA CON ERRORES"
        print(f"\n{status}")
        print("="*80)
        
        # 8. CONSTRUIR RESULTADO FINAL (mismo formato que antes)
        return {
            "intents": intents,
            "entities": entities_config,
            "slots": slots_config,
            "segments": segments,
            "all_responses": all_data.get("responses", {}).get("responses", {}),
            # Metadatos de carga (mismo formato)
            "_load_stats": {
                "intents_loaded": stats.intents_loaded,
                "intents_total": stats.intents_total,
                "segments_loaded": stats.segments_loaded,
                "total_warnings": stats.total_warnings,
                "total_errors": stats.total_errors
            },
            # Configuraciones adicionales del context (mismo formato)
            **{k: v for k, v in context_data.items() 
               if k not in ["intents", "entities", "slots", "examples", "templates", "responses", "segments"]}
        }