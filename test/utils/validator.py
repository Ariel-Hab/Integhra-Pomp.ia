# tests/utils/validator.py

from typing import Dict, List, Any, Optional, Tuple
from .models import TestCase, TestResult, TestStatus, EntityExpectation

class TestValidator:
    """Valida los resultados de los tests comparando lo esperado con lo actual."""

    # ----------------------------------------------------
    # ▼▼▼ CAMBIO 1: AGREGAR EL MÉTODO __init__ ▼▼▼
    # ----------------------------------------------------
    def __init__(self, test_case: TestCase, bot_response: Dict[str, Any], execution_time: float):
        """
        Inicializa el validador con los datos del test y la respuesta del bot.
        """
        self.test_case = test_case
        self.bot_response = bot_response if bot_response else {}
        self.execution_time = execution_time
        
        # Extraer datos de la respuesta del bot para facilitar el acceso
        # El .get('tracker', {}) previene errores si la respuesta no tiene tracker
        tracker = self.bot_response.get('tracker', {})
        self.actual_intent = self.bot_response.get('intent', {}).get('name')
        self.intent_confidence = self.bot_response.get('intent', {}).get('confidence', 0.0)
        self.detected_entities = self.bot_response.get('entities', [])
        self.actual_slots = tracker.get('slots', {})
        
        # Usamos .get() para obtener el primer mensaje del bot de forma segura
        response_messages = self.bot_response.get('messages', [])
        self.response_text = response_messages[0].get('text', '') if response_messages else "No response text."

    # ----------------------------------------------------
    # ▼▼▼ CAMBIO 2: CREAR UN MÉTODO PRINCIPAL 'validate' ▼▼▼
    # ----------------------------------------------------
    def validate(self) -> TestResult:
        """
        Orquesta todas las validaciones y construye el objeto TestResult.
        """
        result = TestResult(
            test_case=self.test_case,
            status=TestStatus.PASSED, # Empezamos asumiendo que pasa
            actual_intent=self.actual_intent,
            intent_confidence=self.intent_confidence,
            detected_entities=self.detected_entities,
            actual_slots=self.actual_slots,
            execution_time=self.execution_time,
            response_text=self.response_text
        )

        # 1. Validar Intent
        intent_ok, intent_error = self._validate_intent()
        if not intent_ok:
            result.add_error(intent_error)

        # 2. Validar Entidades
        entity_errors, entity_warnings = self._validate_entities()
        for error in entity_errors:
            result.add_error(error)
        for warning in entity_warnings:
            result.add_warning(warning)
            
        # 3. Validar Slots
        slot_errors, slot_warnings = self._validate_slots()
        for error in slot_errors:
            result.add_error(error)
        for warning in slot_warnings:
            result.add_warning(warning)

        return result

    # ----------------------------------------------------
    # ▼▼▼ CAMBIO 3: CONVERTIR MÉTODOS ESTÁTICOS A PRIVADOS DE INSTANCIA ▼▼▼
    # ----------------------------------------------------
    # Se quita @staticmethod y se agrega 'self'. Ahora usan los datos guardados en el __init__.
    # Se marcan como "privados" (con _) porque solo deberían ser llamados por el método validate().
    
    def _validate_intent(self) -> Tuple[bool, Optional[str]]:
        """Valida que el intent detectado sea el correcto y con suficiente confianza."""
        if self.actual_intent != self.test_case.expected_intent:
            return False, f"Intent mismatch: expected '{self.test_case.expected_intent}', got '{self.actual_intent}' (confidence: {self.intent_confidence:.2f})"
        
        if self.intent_confidence < self.test_case.intent_confidence_min:
            return False, f"Intent confidence too low: {self.intent_confidence:.2f} < {self.test_case.intent_confidence_min}"
        
        return True, None
    
    def _validate_entities(self, min_entity_confidence: float = 0.8) -> Tuple[List[str], List[str]]:
        """Valida las entidades detectadas con mensajes de error detallados."""
        errors = []
        warnings = []
        expected = self.test_case.expected_entities
        detected_copy = list(self.detected_entities)
        
        # (La lógica interna de este método que ya tenías es correcta, solo la adaptamos para que sea de instancia)
        for expected_entity in expected:
            found_match = None
            best_partial_match = None 
            
            for detected_entity in detected_copy:
                matches, details = expected_entity.matches(detected_entity)
                
                if matches:
                    found_match = detected_entity
                    break
                elif details.get("entity_match"):
                    best_partial_match = (detected_entity, details)

            if found_match:
                if found_match.get('confidence_entity', 1.0) < min_entity_confidence:
                    confidence = found_match.get('confidence_entity', 0.0)
                    errors.append(f"Entity confidence too low for '{expected_entity.entity}': {confidence:.2f} < {min_entity_confidence}")
                detected_copy.remove(found_match)
            elif best_partial_match:
                detected_p, details_p = best_partial_match
                if not details_p.get("value_match"):
                    reason = f"expected value '{expected_entity.value}', got '{detected_p.get('value')}'"
                elif not details_p.get("role_match"):
                    reason = f"expected role '{expected_entity.role}', got '{detected_p.get('role', 'None')}'"
                else:
                    reason = "unknown mismatch"
                errors.append(f"Entity mismatch for '{expected_entity.entity}': {reason}")
                detected_copy.remove(detected_p)
            else:
                errors.append(f"Missing entity: {expected_entity.to_str()}")
        
        for unexpected_entity in detected_copy:
            entity_name = unexpected_entity.get('entity')
            entity_value = unexpected_entity.get('value')
            entity_role = unexpected_entity.get('role')
            role_text = f" (role={entity_role})" if entity_role else ""
            warnings.append(f"Unexpected entity: {entity_name}='{entity_value}'{role_text}")
        
        return errors, warnings
    
    def _validate_slots(self) -> Tuple[List[str], List[str]]:
        """Valida que los slots tengan los valores esperados."""
        errors = []
        warnings = []
        expected = self.test_case.expected_slots
        actual = self.actual_slots
        expected_keys = set(expected.keys())
        actual_keys = set(actual.keys())

        for slot_name, expected_value in expected.items():
            actual_value = actual.get(slot_name)
            if actual_value != expected_value:
                errors.append(f"Slot '{slot_name}' mismatch: expected '{expected_value}', got '{'Not set' if actual_value is None else actual_value}'")

        unexpected_slots = actual_keys - expected_keys
        for slot_name in unexpected_slots:
            if actual[slot_name] is not None:
                warnings.append(f"Unexpected slot set: '{slot_name}' was set to '{actual[slot_name]}'")

        return errors, warnings