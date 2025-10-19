# tests/cases/test_buscar_oferta.py
from utils.models import TestCase, EntityExpectation

# --- GENERADOR DE TESTS ---
def generate_estado_tests():
    """Genera tests para todas las combinaciones de estados."""
    estados = [
        ("nuevo", ["nuevas", "recién llegadas", "novedades"]),
        ("poco_stock", ["poco stock", "últimas unidades", "stock limitado"]),
        ("vence_pronto", ["vence pronto", "próximos a vencer", "expiran hoy"])
    ]
    
    tests = []
    
    # Tests individuales
    for role, variants in estados:
        for variant in variants:
            tests.append(TestCase(
                name=f"Estado: {role} ('{variant}')",
                user_message=f"ofertas {variant}",
                expected_intent="buscar_oferta",
                expected_entities=[EntityExpectation(entity="estado", role=role)],
                category="buscar_oferta"
            ))
    
    # Tests combinados (2 estados)
    for i, (role1, vars1) in enumerate(estados):
        for role2, vars2 in estados[i+1:]:
            tests.append(TestCase(
                name=f"Estados: {role1} + {role2}",
                user_message=f"ofertas {vars1[0]} y con {vars2[0]}",
                expected_intent="buscar_oferta",
                expected_entities=[
                    EntityExpectation(entity="estado", role=role1),
                    EntityExpectation(entity="estado", role=role2)
                ],
                category="buscar_oferta"
            ))
    
    return tests

def generate_dosis_tests():
    """Genera tests para dosis (CRÍTICO - falta cobertura)."""
    return [
        # Gramaje
        TestCase(
            name="Dosis: gramaje",
            user_message="ofertas de amoxicilina 500mg",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="producto", value="amoxicilina"),
                EntityExpectation(entity="dosis", value="500mg", role="gramaje")
            ],
            category="buscar_oferta"
        ),
        # Forma
        TestCase(
            name="Dosis: forma",
            user_message="ofertas de cefalexina inyectable",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="producto", value="cefalexina"),
                EntityExpectation(entity="dosis", value="inyectable", role="forma")
            ],
            category="buscar_oferta"
        ),
        # Volumen
        TestCase(
            name="Dosis: volumen",
            user_message="ofertas de penicilina 100ml",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="producto", value="penicilina"),
                EntityExpectation(entity="dosis", value="100ml", role="volumen")
            ],
            category="buscar_oferta"
        ),
        # Combinado: gramaje + forma
        TestCase(
            name="Dosis: gramaje + forma",
            user_message="ofertas de amoxicilina 500mg en comprimidos",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="producto", value="amoxicilina"),
                EntityExpectation(entity="dosis", value="500mg", role="gramaje"),
                EntityExpectation(entity="dosis", value="comprimidos", role="forma")
            ],
            category="buscar_oferta"
        ),
    ]

def generate_grupo_tests():
    """Genera tests para validar grupos (descuento_filter, precio_filter, etc.)."""
    return [
        # ===== DESCUENTO FILTER - SIMPLES =====
        TestCase(
            name="Descuento: mayor a (gt)",
            user_message="ofertas con descuento mayor a 15%",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="gt", group="descuento_filter"),
                EntityExpectation(entity="cantidad_descuento", value="15", group="descuento_filter")
            ],
            category="buscar_oferta"
        ),
        TestCase(
            name="Descuento: más de (gt)",
            user_message="ofertas con más de 20% de descuento",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="gt", group="descuento_filter"),
                EntityExpectation(entity="cantidad_descuento", value="20", group="descuento_filter")
            ],
            category="buscar_oferta"
        ),
        TestCase(
            name="Descuento: menor a (lt)",
            user_message="ofertas con descuento menor a 25%",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="lt", group="descuento_filter"),
                EntityExpectation(entity="cantidad_descuento", value="25", group="descuento_filter")
            ],
            category="buscar_oferta"
        ),
        TestCase(
            name="Descuento: hasta (lte)",
            user_message="ofertas con descuento hasta 30%",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="lte", group="descuento_filter"),
                EntityExpectation(entity="cantidad_descuento", value="30", group="descuento_filter")
            ],
            category="buscar_oferta"
        ),
        TestCase(
            name="Descuento: mínimo (gte)",
            user_message="ofertas con descuento mínimo 10%",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="gte", group="descuento_filter"),
                EntityExpectation(entity="cantidad_descuento", value="10", group="descuento_filter")
            ],
            category="buscar_oferta"
        ),
        TestCase(
            name="Descuento: al menos (gte)",
            user_message="ofertas con al menos 18% de descuento",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="gte", group="descuento_filter"),
                EntityExpectation(entity="cantidad_descuento", value="18", group="descuento_filter")
            ],
            category="buscar_oferta"
        ),
        
        # ===== DESCUENTO FILTER - DOBLES (RANGOS) =====
        TestCase(
            name="Descuento: rango completo (min + max)",
            user_message="ofertas con descuento entre 10% y 25%",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="gte", group="descuento_filter"),
                EntityExpectation(entity="cantidad_descuento", value="10", group="descuento_filter"),
                EntityExpectation(entity="comparador", role="lte", group="descuento_filter"),
                EntityExpectation(entity="cantidad_descuento", value="25", group="descuento_filter")
            ],
            category="buscar_oferta"
        ),
        TestCase(
            name="Descuento: mayor y menor (gt + lt)",
            user_message="ofertas con descuento mayor a 5% y menor a 20%",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="gt", group="descuento_filter"),
                EntityExpectation(entity="cantidad_descuento", value="5", group="descuento_filter"),
                EntityExpectation(entity="comparador", role="lt", group="descuento_filter"),
                EntityExpectation(entity="cantidad_descuento", value="20", group="descuento_filter")
            ],
            category="buscar_oferta"
        ),
        
        # ===== PRECIO FILTER - SIMPLES =====
        TestCase(
            name="Precio: hasta (lte)",
            user_message="ofertas con precio hasta 2000",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="lte", group="precio_filter"),
                EntityExpectation(entity="precio", value="2000", group="precio_filter")
            ],
            category="buscar_oferta"
        ),
        TestCase(
            name="Precio: menor a (lt)",
            user_message="ofertas con precio menor a 1500",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="lt", group="precio_filter"),
                EntityExpectation(entity="precio", value="1500", group="precio_filter")
            ],
            category="buscar_oferta"
        ),
        TestCase(
            name="Precio: mayor a (gt)",
            user_message="ofertas con precio mayor a 1000",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="gt", group="precio_filter"),
                EntityExpectation(entity="precio", value="1000", group="precio_filter")
            ],
            category="buscar_oferta"
        ),
        TestCase(
            name="Precio: mínimo (gte)",
            user_message="ofertas con precio mínimo 800",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="gte", group="precio_filter"),
                EntityExpectation(entity="precio", value="800", group="precio_filter")
            ],
            category="buscar_oferta"
        ),
        
        # ===== PRECIO FILTER - DOBLES =====
        TestCase(
            name="Precio: rango (min + max)",
            user_message="ofertas con precio entre 500 y 2500",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="gte", group="precio_filter"),
                EntityExpectation(entity="precio", value="500", group="precio_filter"),
                EntityExpectation(entity="comparador", role="lte", group="precio_filter"),
                EntityExpectation(entity="precio", value="2500", group="precio_filter")
            ],
            category="buscar_oferta"
        ),
        
        # ===== BONIFICACION FILTER - SIMPLES =====
        TestCase(
            name="Bonificación: mayor a (gt)",
            user_message="ofertas con bonificación mayor a 3 unidades",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="gt", group="bonificacion_filter"),
                EntityExpectation(entity="cantidad_bonificacion", value="3", group="bonificacion_filter")
            ],
            category="buscar_oferta"
        ),
        TestCase(
            name="Bonificación: mínimo (gte)",
            user_message="ofertas con bonificación mínima de 2",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="gte", group="bonificacion_filter"),
                EntityExpectation(entity="cantidad_bonificacion", value="2", group="bonificacion_filter")
            ],
            category="buscar_oferta"
        ),
        TestCase(
            name="Bonificación: hasta (lte)",
            user_message="ofertas con bonificación hasta 5",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="lte", group="bonificacion_filter"),
                EntityExpectation(entity="cantidad_bonificacion", value="5", group="bonificacion_filter")
            ],
            category="buscar_oferta"
        ),
        
        # ===== BONIFICACION FILTER - DOBLES =====
        TestCase(
            name="Bonificación: rango (min + max)",
            user_message="ofertas con bonificación entre 2 y 6 unidades",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="gte", group="bonificacion_filter"),
                EntityExpectation(entity="cantidad_bonificacion", value="2", group="bonificacion_filter"),
                EntityExpectation(entity="comparador", role="lte", group="bonificacion_filter"),
                EntityExpectation(entity="cantidad_bonificacion", value="6", group="bonificacion_filter")
            ],
            category="buscar_oferta"
        ),
        
        # ===== STOCK FILTER - SIMPLES =====
        TestCase(
            name="Stock: mayor a (gt)",
            user_message="ofertas con stock mayor a 50",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="gt", group="stock_filter"),
                EntityExpectation(entity="cantidad_stock", value="50", group="stock_filter")
            ],
            category="buscar_oferta"
        ),
        TestCase(
            name="Stock: mínimo (gte)",
            user_message="ofertas con stock mínimo 30 unidades",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="gte", group="stock_filter"),
                EntityExpectation(entity="cantidad_stock", value="30", group="stock_filter")
            ],
            category="buscar_oferta"
        ),
        TestCase(
            name="Stock: menor a (lt)",
            user_message="ofertas con stock menor a 100",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="lt", group="stock_filter"),
                EntityExpectation(entity="cantidad_stock", value="100", group="stock_filter")
            ],
            category="buscar_oferta"
        ),
        
        # ===== STOCK FILTER - DOBLES =====
        TestCase(
            name="Stock: rango (min + max)",
            user_message="ofertas con stock entre 20 y 80 unidades",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="gte", group="stock_filter"),
                EntityExpectation(entity="cantidad_stock", value="20", group="stock_filter"),
                EntityExpectation(entity="comparador", role="lte", group="stock_filter"),
                EntityExpectation(entity="cantidad_stock", value="80", group="stock_filter")
            ],
            category="buscar_oferta"
        ),
        
        # ===== COMBINACIONES MÚLTIPLES (DIFERENTES GRUPOS) =====
        TestCase(
            name="Multi: descuento + precio",
            user_message="ofertas con descuento mayor a 15% y precio hasta 2000",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="gt", group="descuento_filter"),
                EntityExpectation(entity="cantidad_descuento", value="15", group="descuento_filter"),
                EntityExpectation(entity="comparador", role="lte", group="precio_filter"),
                EntityExpectation(entity="precio", value="2000", group="precio_filter")
            ],
            category="buscar_oferta"
        ),
        TestCase(
            name="Multi: descuento + bonificación",
            user_message="ofertas con descuento mínimo 10% y bonificación de al menos 3",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="gte", group="descuento_filter"),
                EntityExpectation(entity="cantidad_descuento", value="10", group="descuento_filter"),
                EntityExpectation(entity="comparador", role="gte", group="bonificacion_filter"),
                EntityExpectation(entity="cantidad_bonificacion", value="3", group="bonificacion_filter")
            ],
            category="buscar_oferta"
        ),
        TestCase(
            name="Multi: precio + stock",
            user_message="ofertas con precio menor a 1800 y stock mayor a 40",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="lt", group="precio_filter"),
                EntityExpectation(entity="precio", value="1800", group="precio_filter"),
                EntityExpectation(entity="comparador", role="gt", group="stock_filter"),
                EntityExpectation(entity="cantidad_stock", value="40", group="stock_filter")
            ],
            category="buscar_oferta"
        ),
        TestCase(
            name="Multi: descuento + precio + stock",
            user_message="ofertas con descuento mayor a 20%, precio hasta 2500 y stock mínimo 30",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="gt", group="descuento_filter"),
                EntityExpectation(entity="cantidad_descuento", value="20", group="descuento_filter"),
                EntityExpectation(entity="comparador", role="lte", group="precio_filter"),
                EntityExpectation(entity="precio", value="2500", group="precio_filter"),
                EntityExpectation(entity="comparador", role="gte", group="stock_filter"),
                EntityExpectation(entity="cantidad_stock", value="30", group="stock_filter")
            ],
            category="buscar_oferta"
        ),
        
        # ===== VARIANTES COLOQUIALES =====
        TestCase(
            name="Coloquial: más de (descuento)",
            user_message="ofertas con más de 25% off",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="gt", group="descuento_filter"),
                EntityExpectation(entity="cantidad_descuento", value="25", group="descuento_filter")
            ],
            category="buscar_oferta"
        ),
        TestCase(
            name="Coloquial: como máximo",
            user_message="ofertas con precio como máximo 3000",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="lte", group="precio_filter"),
                EntityExpectation(entity="precio", value="3000", group="precio_filter")
            ],
            category="buscar_oferta"
        ),
        TestCase(
            name="Coloquial: por lo menos",
            user_message="ofertas con descuento de por lo menos 12%",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="gte", group="descuento_filter"),
                EntityExpectation(entity="cantidad_descuento", value="12", group="descuento_filter")
            ],
            category="buscar_oferta"
        ),
    ]

def generate_edge_cases():
    return [
        # Errores ortográficos
        TestCase(
            name="Edge: error ortográfico en estado",
            user_message="ofertas nuebas",  # "nuebas" en vez de "nuevas"
            expected_intent="buscar_oferta",
            expected_entities=[EntityExpectation(entity="estado", role="nuevo")],
            category="buscar_oferta"
        ),
        # Múltiples comparadores del mismo grupo
        TestCase(
            name="Edge: rango con mínimo y máximo",
            user_message="ofertas con descuento mínimo 10% y máximo 30%",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="comparador", role="gte", group="descuento_filter"),
                EntityExpectation(entity="cantidad_descuento", value="10", group="descuento_filter"),
                EntityExpectation(entity="comparador", role="lte", group="descuento_filter"),
                EntityExpectation(entity="cantidad_descuento", value="30", group="descuento_filter")
            ],
            category="buscar_oferta"
        ),
    ]

def generate_regression_tests():
    """Tests específicos para bugs encontrados."""
    return [
        # Bug: Test #8 detecta buscar_producto en vez de buscar_oferta
        TestCase(
            name="Regresión: categoría + estados → buscar_OFERTA",
            user_message="ofertas de antibióticos nuevos con poco stock para perros",
            expected_intent="buscar_oferta",  # NO buscar_producto
            expected_entities=[
                EntityExpectation(entity="categoria", value="antibióticos"),
                EntityExpectation(entity="estado", role="nuevo"),
                EntityExpectation(entity="estado", role="poco_stock"),
                EntityExpectation(entity="animal", value="perros")
            ],
            category="buscar_oferta"
        ),
        # Bug: Roles 'new' y 'old' en vez de 'nuevo' y 'poco_stock'
        TestCase(
            name="Regresión: roles correctos para estados",
            user_message="quiero ofertas nuevas y con poco stock",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="estado", role="nuevo"),  # NO 'new'
                EntityExpectation(entity="estado", role="poco_stock")  # NO 'old'
            ],
            category="buscar_oferta"
        ),
    ]

def get_tests():
    """Función principal que retorna TODOS los tests."""
    return [
        # Tests básicos (mantener los actuales)
        TestCase(
            name="Búsqueda simple de ofertas",
            user_message="ofertas",
            expected_intent="buscar_oferta",
            category="buscar_oferta"
        ),
        
        # Agregar tests generados
        *generate_estado_tests(),
        *generate_dosis_tests(),
        *generate_grupo_tests(),
        *generate_regression_tests(),
        
        # Tests complejos existentes
        TestCase(
            name="Complejo: proveedor + estado + animal",
            user_message="ofertas de Zoetis nuevas para perros",
            expected_intent="buscar_oferta",
            expected_entities=[
                EntityExpectation(entity="empresa", value="Zoetis", role="proveedor"),
                EntityExpectation(entity="estado", role="nuevo"),
                EntityExpectation(entity="animal", value="perros")
            ],
            category="buscar_oferta"
        ),
    ]