import logging
from actions.helpers import validate_entities_for_intent
from actions.conversation_state import SuggestionManager, get_improved_suggestions

logger = logging.getLogger(__name__)

class EntityValidator:
    """Valida entidades detectadas por el NLU y sugiere correcciones si son inválidas."""

    @staticmethod
    def validate_entities(tracker, intent_name, dispatcher):
        """
        Valida las entidades detectadas en el tracker según el intent,
        sugiere correcciones si existen, o informa si no se encontraron coincidencias.
        """
        try:
            entities = tracker.latest_message.get("entities", [])
            if not entities:
                return {
                    "valid_params": {},
                    "has_suggestions": False,
                    "suggestion_data": None,
                    "has_errors": False,
                    "errors": []
                }

            helper_result = validate_entities_for_intent(
                entities, intent_name, min_length=2, check_fragments=True
            )

            all_messages = []
            suggestions_data = []

            if helper_result["has_suggestions"]:
                for item in helper_result["suggestions"]:
                    entity_type = item.get("entity_type")
                    raw_value = item.get("raw_value")
                    suggestions_list = item.get("suggestions", [])

                    if suggestions_list:
                        best = suggestions_list[0]
                        all_messages.append(f"'{raw_value}' no es válido. ¿Querías decir '{best}'?")
                        
                        suggestion_data = SuggestionManager.create_entity_suggestion(
                            raw_value, entity_type, best,
                            {"intent": tracker.get_intent_of_latest_message()}
                        )
                        suggestions_data.append(suggestion_data)
                    else:
                        # Buscar coincidencias por similitud
                        similar_message = EntityValidator._handle_no_direct_suggestion(raw_value, entity_type)
                        all_messages.append(similar_message)

            if all_messages:
                dispatcher.utter_message("\n".join(all_messages))

            return {
                "valid_params": helper_result["valid_params"],
                "has_suggestions": len(suggestions_data) > 0,
                "suggestion_data": suggestions_data[0] if suggestions_data else None,
                "has_errors": helper_result["has_errors"] and len(suggestions_data) == 0,
                "errors": helper_result["errors"] if len(suggestions_data) == 0 else []
            }

        except Exception as e:
            logger.error(f"[EntityValidator] Error: {e}", exc_info=True)
            dispatcher.utter_message("Error validando entidades.")
            return {
                "valid_params": {},
                "has_suggestions": False,
                "suggestion_data": None,
                "has_errors": True,
                "errors": ["Error validando entidades."]
            }

    @staticmethod
    def _handle_no_direct_suggestion(raw_value: str, entity_type: str) -> str:
        """Si no hay sugerencia directa, busca coincidencias similares."""
        try:
            suggestions = get_improved_suggestions(raw_value, entity_type, max_suggestions=3)
            if not suggestions:
                return f"'{raw_value}' no está registrado como {entity_type}."
            best = suggestions[0]["suggestion"]
            return f"'{raw_value}' no está registrado como {entity_type}. ¿Querías decir '{best}'?"
        except Exception as e:
            logger.error(f"[EntityValidator] Error generando sugerencia similar: {e}")
            return f"'{raw_value}' no está registrado como {entity_type}."
