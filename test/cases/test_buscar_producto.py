# tests/cases/test_buscar_producto.py
from utils.models import TestCase, EntityExpectation

def get_tests():
    return [
        TestCase(
            name="Buscar producto por nombre", user_message="busco ivermectina", expected_intent="buscar_producto",
            expected_entities=[EntityExpectation(entity="producto", value="ivermectina")],
            category="buscar_producto"
        ),
        TestCase(
            name="Buscar productos por categoría y animal", user_message="qué vacunas para perros tenés?", expected_intent="buscar_producto",
            expected_entities=[
                EntityExpectation(entity="categoria", value="vacunas"),
                EntityExpectation(entity="animal", value="perros")
            ],
            category="buscar_producto"
        ),
        TestCase(
            name="Buscar producto con cantidad", user_message="necesito 3 cajas de amoxicilina", expected_intent="buscar_producto",
            expected_entities=[
                EntityExpectation(entity="cantidad", value="3"),
                EntityExpectation(entity="producto", value="amoxicilina")
            ],
            category="buscar_producto"
        ),
        TestCase(
            name="Buscar producto con dosis (gramaje)", user_message="tenés amoxicilina de 500mg?", expected_intent="buscar_producto",
            expected_entities=[
                EntityExpectation(entity="producto", value="amoxicilina"),
                EntityExpectation(entity="dosis", value="500mg", role="gramaje")
            ],
            category="buscar_producto"
        ),
        TestCase(
            name="Buscar producto con dosis (forma)", user_message="cefalexina en comprimidos", expected_intent="buscar_producto",
            expected_entities=[
                EntityExpectation(entity="producto", value="cefalexina"),
                EntityExpectation(entity="dosis", value="comprimidos", role="forma")
            ],
            category="buscar_producto"
        ),
    ]