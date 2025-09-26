#!/usr/bin/env python3
"""
config_loader.py - ConfigLoader optimizado y compatible con templates.yml
"""

import yaml
from pathlib import Path
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass

class ConfigLoadError(Exception):
    """Excepción específica para errores de carga de configuración"""
    pass

@dataclass
class LoadStats:
    intents_total: int = 0
    intents_loaded: int = 0
    segments_loaded: int = 0
    total_warnings: int = 0
    total_errors: int = 0

class ConfigLoader:

    @staticmethod
    def _load_yaml_safe(file_path: Path, context_name: str) -> Tuple[Dict[str, Any], List[str]]:
        errors = []
        try:
            if not file_path.exists():
                errors.append(f"❌ [{context_name}] Archivo no encontrado: {file_path}")
                return {}, errors

            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}

            if not isinstance(data, dict):
                errors.append(f"❌ [{context_name}] Formato inválido: debe ser dict")
                return {}, errors

            return data, errors

        except yaml.YAMLError as e:
            errors.append(f"❌ [{context_name}] Error YAML: {str(e)[:100]}")
            return {}, errors
        except Exception as e:
            errors.append(f"❌ [{context_name}] Error inesperado: {str(e)[:100]}")
            return {}, errors

    @staticmethod
    def _validate_and_extract_list_data(data: Any, context: str, item_name: str) -> Tuple[List[str], List[str]]:
        errors = []
        if isinstance(data, list):
            return [item for item in data if isinstance(item, str) and item.strip()], errors
        elif isinstance(data, str):
            if "|" in data:
                items = [item.strip() for item in data.split("|") if item.strip()]
                return items, errors
            elif "\n" in data:
                items = [item.strip().lstrip("- ") for item in data.split("\n") if item.strip()]
                return items, errors
            else:
                return [data.strip()] if data.strip() else [], errors
        else:
            errors.append(f"⚠️ [{context}] {item_name} - formato no reconocido")
            return [], errors

    @staticmethod
    def _process_intent(intent_name: str, intent_config: Dict[str, Any], all_data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        errors = []

        # --- 1. Extraer ejemplos
        ejemplos = []
        ejemplos_data = all_data.get("ejemplos", {})
        if intent_name in ejemplos_data:
            examples, item_errors = ConfigLoader._validate_and_extract_list_data(
                ejemplos_data[intent_name], "EJEMPLOS", intent_name
            )
            ejemplos.extend(examples)
            errors.extend(item_errors)
        else:
            errors.append(f"⚠️ [EJEMPLOS] {intent_name} - sin ejemplos definidos")

        # --- 2. Extraer templates de todos los grupos
        templates = []
        templates_data = all_data.get("templates", {})
        for group_name, group_data in templates_data.items():
            if isinstance(group_data, dict) and intent_name in group_data:
                t_list, t_errors = ConfigLoader._validate_and_extract_list_data(
                    group_data[intent_name],
                    f"TEMPLATES_{group_name.upper()}",
                    intent_name
                )
                templates.extend(t_list)
                errors.extend(t_errors)
        if not templates:
            errors.append(f"⚠️ [TEMPLATES] {intent_name} - sin templates definidos")

        # --- 3. Extraer responses
        responses = []
        responses_data = all_data.get("responses", {})
        all_responses = responses_data.get("responses", {}) if isinstance(responses_data, dict) else {}
        response_key = f"utter_{intent_name}"
        if response_key in all_responses:
            responses = all_responses[response_key]
            if not isinstance(responses, list):
                responses = []
                errors.append(f"⚠️ [RESPONSES] {intent_name} - formato inválido")
        else:
            errors.append(f"⚠️ [RESPONSES] {intent_name} - sin responses definidos")

        # --- 4. Construir intent final
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
                errors.extend(item_errors)

        return segments, errors

    @staticmethod
    def cargar_config(context_path: str) -> Dict[str, Any]:
        context_file = Path(context_path)
        if not context_file.is_absolute():
            base_path = Path(__file__).parent.parent
            context_file = (base_path / context_path).resolve()


        context_data, context_errors = ConfigLoader._load_yaml_safe(context_file, "CONTEXT")
        if context_errors:
            raise ConfigLoadError(f"Errores críticos cargando context_config.yml: {context_errors}")

        context_dir = context_file.parent
        files_config = context_data.get("files", {})

        file_paths = {
            "ejemplos": context_dir / files_config.get("examples", "examples.yml"),
            "templates": context_dir / files_config.get("templates", "templates.yml"),
            "responses": context_dir / files_config.get("responses", "responses.yml"),
            "segments": context_dir / files_config.get("segments", "segments.yml")
        }

        all_data = {"context": context_data}
        all_errors = []

        for file_type, file_path in file_paths.items():
            data, errors = ConfigLoader._load_yaml_safe(file_path, file_type.upper())
            all_data[file_type] = data
            all_errors.extend(errors)

        intents_config = context_data.get("intents", {})
        entities_config = context_data.get("entities", {})
        slots_config = context_data.get("slots", {})

        if not intents_config:
            raise ConfigLoadError("❌ [CONFIG] No se encontraron intents en configuración")

        intents = {}
        stats = LoadStats()
        stats.intents_total = len(intents_config)

        for intent_name, intent_config in intents_config.items():
            intent_data, intent_errors = ConfigLoader._process_intent(intent_name, intent_config, all_data)
            if intent_data:
                intents[intent_name] = intent_data
                stats.intents_loaded += 1
            stats.total_errors += sum(1 for e in intent_errors if e.startswith("❌"))
            stats.total_warnings += sum(1 for e in intent_errors if e.startswith("⚠️"))
            all_errors.extend(intent_errors)

        segments, segments_errors = ConfigLoader._process_segments(all_data.get("segments", {}))
        stats.segments_loaded = len(segments)
        all_errors.extend(segments_errors)

        # Verificar intents sin ejemplos ni templates
        intents_sin_contenido = [
            f"{name} (ejemplos: {len(data['ejemplos'])}, templates: {len(data['templates'])})"
            for name, data in intents.items()
            if not data["ejemplos"] and not data["templates"]
        ]
        if intents_sin_contenido:
            raise ConfigLoadError(f"❌ Intents sin contenido: {intents_sin_contenido}")

        return {
            "intents": intents,
            "entities": entities_config,
            "slots": slots_config,
            "segments": segments,
            "all_responses": all_data.get("responses", {}).get("responses", {}),
            "stats": stats,
            "load_errors": all_errors,
            **{k: v for k, v in context_data.items() if k not in ["intents", "entities", "slots", "files"]}
        }
