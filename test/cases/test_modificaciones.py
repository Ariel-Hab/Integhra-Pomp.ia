# tests/cases/test_modificaciones.py
from utils.models import TestCase, EntityExpectation

def get_tests():
    return [
        TestCase(
            name="Agregar filtro", user_message="agrega proveedor holliday", expected_intent="modificar_busqueda:agregar",
            expected_entities=[EntityExpectation(entity="empresa", value="holliday", role="proveedor")],
            category="modificaciones"
        ),
        TestCase(
            name="Remover filtro", user_message="saca holliday", expected_intent="modificar_busqueda:remover",
            expected_entities=[EntityExpectation(entity="empresa", value="holliday")],
            category="modificaciones"
        ),
        TestCase(
            name="Reemplazar filtro", user_message="cambiá holliday por zoetis", expected_intent="modificar_busqueda:reemplazar",
            expected_entities=[
                EntityExpectation(entity="empresa", value="holliday", role="old"),
                EntityExpectation(entity="empresa", value="zoetis", role="new")
            ],
            category="modificaciones"
        ),
        TestCase(
            name="Modificación múltiple (agregar y remover)", user_message="agrega gato y saca perro", expected_intent="modificar_busqueda:multiple",
            expected_entities=[
                EntityExpectation(entity="animal", value="gato", role="add"),
                EntityExpectation(entity="animal", value="perro", role="remove")
            ],
            category="modificaciones"
        ),
    ]