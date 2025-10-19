# tests/test_suite.py
from cases import test_buscar_oferta, test_buscar_producto, test_modificaciones, test_conversacional

def get_all_tests():
    """Agrega tests desde todos los módulos de casos de prueba."""
    all_tests = []
    all_tests.extend(test_buscar_oferta.get_tests())
    all_tests.extend(test_buscar_producto.get_tests())
    all_tests.extend(test_modificaciones.get_tests())
    all_tests.extend(test_conversacional.get_tests())
    return all_tests 

def get_all_categories():
    """Obtiene dinámicamente todas las categorías de los tests."""
    return sorted(list(set(t.category for t in get_all_tests())))