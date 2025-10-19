# tests/utils/coverage.py
from typing import List, Dict, Set
from .models import TestCase

class CoverageAnalyzer:
    """Analiza la cobertura de features del NLU en los tests."""
    
    # Define todas las features que tu NLU soporta
    EXPECTED_FEATURES = {
        "estados": {"nuevo", "poco_stock", "vence_pronto", "en_oferta"},
        "dosis_roles": {"gramaje", "forma", "volumen"},
        "grupos": {"descuento_filter", "bonificacion_filter", "precio_filter", "stock_filter"},
        "comparadores": {"gt", "gte", "lt", "lte"},
        "entity_types": {"producto", "categoria", "empresa", "animal", "sintoma", "dosis", "estado"}
    }
    
    @staticmethod
    def calculate_coverage(tests: List[TestCase]) -> Dict[str, Dict]:
        """Calcula qué % de features están cubiertas por los tests."""
        coverage = {
            "estados": set(),
            "dosis_roles": set(),
            "grupos": set(),
            "comparadores": set(),
            "entity_types": set()
        }
        
        for test in tests:
            for entity in test.expected_entities:
                # Registrar tipo de entidad
                coverage["entity_types"].add(entity.entity)
                
                # Registrar roles específicos
                if entity.entity == "estado" and entity.role:
                    coverage["estados"].add(entity.role)
                if entity.entity == "dosis" and entity.role:
                    coverage["dosis_roles"].add(entity.role)
                if entity.entity == "comparador" and entity.role:
                    coverage["comparadores"].add(entity.role)
                
                # Registrar grupos
                if entity.group:
                    coverage["grupos"].add(entity.group)
        
        # Calcular porcentajes
        results = {}
        for feature_type, covered in coverage.items():
            expected = CoverageAnalyzer.EXPECTED_FEATURES.get(feature_type, set())
            if expected:
                percentage = (len(covered) / len(expected)) * 100 if expected else 0
                results[feature_type] = {
                    "covered": covered,
                    "expected": expected,
                    "missing": expected - covered,
                    "percentage": percentage,
                    "count": f"{len(covered)}/{len(expected)}"
                }
        
        return results
    
    @staticmethod
    def print_coverage_report(coverage: Dict[str, Dict], use_colors: bool = True):
        """Imprime un reporte visual de cobertura."""
        from .bot_client import Config  # Importar colores
        
        print(f"\n{Config.Colors.HEADER}{'='*80}")
        print("📊 TEST COVERAGE REPORT")
        print(f"{'='*80}{Config.Colors.ENDC}\n")
        
        for feature_type, data in coverage.items():
            percentage = data["percentage"]
            
            # Elegir color según porcentaje
            if percentage >= 80:
                color = Config.Colors.OKGREEN
            elif percentage >= 50:
                color = Config.Colors.WARNING
            else:
                color = Config.Colors.FAIL
            
            bar_length = 30
            filled = int(bar_length * percentage / 100)
            bar = "█" * filled + "░" * (bar_length - filled)
            
            print(f"{Config.Colors.OKCYAN}{feature_type.upper().replace('_', ' ')}:{Config.Colors.ENDC}")
            print(f"  {color}[{bar}] {percentage:.1f}%{Config.Colors.ENDC} ({data['count']})")
            
            if data["missing"]:
                print(f"  {Config.Colors.WARNING}⚠️  Missing: {', '.join(sorted(data['missing']))}{Config.Colors.ENDC}")
            else:
                print(f"  {Config.Colors.OKGREEN}✅ Fully covered{Config.Colors.ENDC}")
            print()
        
        # Resumen general
        avg_coverage = sum(d["percentage"] for d in coverage.values()) / len(coverage)
        overall_color = Config.Colors.OKGREEN if avg_coverage >= 80 else Config.Colors.WARNING if avg_coverage >= 50 else Config.Colors.FAIL
        
        print(f"{Config.Colors.HEADER}{'='*80}")
        print(f"{overall_color}OVERALL COVERAGE: {avg_coverage:.1f}%{Config.Colors.ENDC}")
        print(f"{Config.Colors.HEADER}{'='*80}{Config.Colors.ENDC}\n")