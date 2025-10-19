# tests/utils/models.py
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple

class TestStatus(Enum):
    PASSED = "✅ PASSED"
    FAILED = "❌ FAILED"
    WARNING = "⚠️  WARNING"
    SKIPPED = "⏭️  SKIPPED"

@dataclass
class EntityExpectation:
    """Define una entidad esperada con más detalle para validación."""
    entity: str
    value: Optional[str] = None
    role: Optional[str] = None
    group: Optional[str] = None
    # <<< NOTA: El confidence_min se movió al validador para ser más flexible.
    # Se puede mantener aquí si prefieres validación por entidad.

    def matches(self, detected: Dict) -> Tuple[bool, Dict]:
        # <<< MEJORA: Retorna un booleano y un diccionario con detalles del match.
        details = {
            "entity_match": False,
            "value_match": False,
            "role_match": False,
            "group_match": False,
        }

        # 1. El tipo de entidad debe coincidir siempre.
        if detected.get('entity') != self.entity:
            return False, details
        details["entity_match"] = True

        # 2. Compara el valor. Si el valor esperado es '*' se acepta cualquiera.
        #    Si el valor esperado es None, no se chequea (útil para solo verificar tipo/rol).
        value_expected = self.value is not None
        value_detected = detected.get('value')
        if value_expected and self.value != '*' and value_detected != self.value:
            return False, details
        details["value_match"] = True

        # 3. Compara el rol si se especifica uno.
        role_expected = self.role is not None
        role_detected = detected.get('role')
        if role_expected and role_detected != self.role:
            return False, details
        details["role_match"] = True
        
        # 4. Compara el grupo si se especifica uno.
        group_expected = self.group is not None
        group_detected = detected.get('group')
        if group_expected and group_detected != self.group:
            return False, details
        details["group_match"] = True

        # Si todas las comprobaciones necesarias pasaron, es un match completo.
        return True, details

    def to_str(self) -> str:
        # <<< MEJORA: Helper para imprimir la entidad esperada de forma legible.
        """Genera una representación en string para los mensajes de error."""
        base = f"{self.entity}="
        # Usamos '*' si el valor es None o es el comodín explícito
        base += f"'{self.value}'" if self.value is not None and self.value != '*' else '*'

        if self.role:
            base += f" (role={self.role})"
        if self.group:
            base += f" (group={self.group})"
        return base

@dataclass
class TestCase:
    """Define un caso de prueba (sin cambios, ya estaba bien)."""
    name: str
    user_message: str
    expected_intent: str
    category: str
    expected_entities: List[EntityExpectation] = field(default_factory=list)
    expected_slots: Dict[str, Any] = field(default_factory=dict)
    intent_confidence_min: float = 0.7
    description: str = ""

@dataclass
class TestResult:
    """Resultado de un test (sin cambios, ya estaba bien)."""
    test_case: TestCase
    status: TestStatus
    actual_intent: Optional[str] = None
    intent_confidence: Optional[float] = None
    detected_entities: List[Dict] = field(default_factory=list)
    actual_slots: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    execution_time: float = 0.0
    response_text: str = ""
    
    def add_error(self, error: str):
        self.errors.append(error)
        if self.status != TestStatus.FAILED: self.status = TestStatus.FAILED
    
    def add_warning(self, warning: str):
        self.warnings.append(warning)
        if self.status == TestStatus.PASSED: self.status = TestStatus.WARNING