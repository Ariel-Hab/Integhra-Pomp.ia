
# tests/test_main.py

# # Ver cobertura de todos los tests
# python tests/test_main.py --coverage

# # Ver cobertura solo de buscar_oferta
# python tests/test_main.py --category buscar_oferta --coverage

# # Análisis de cobertura sin ejecutar tests (opcional)
# python tests/test_suite.py --coverage-only
import argparse
import sys
import time
from typing import List, Optional

sys.path.append('.')

from utils.models import TestCase, TestResult, TestStatus
from utils.bot_client import BotClient, Config
from utils.validator import TestValidator
from utils.coverage import CoverageAnalyzer  # ← AGREGAR
from test_suite import get_all_tests, get_all_categories

class TestRunner:
    def __init__(self, client: BotClient, verbose: bool = False):
        self.client = client
        self.verbose = verbose
        self.results: List[TestResult] = []

    # ----------------------------------------------------
    # ▼▼▼ ESTE ES EL MÉTODO QUE FALTA ▼▼▼
    # ----------------------------------------------------
    def run_test(self, test_case: TestCase) -> TestResult:
            """Ejecuta un único caso de prueba y retorna el resultado."""
            start_time = time.time()

            if Config.RESET_BETWEEN_TESTS:
                self.client.reset_context()

            # ▼▼▼ ¡ESTE ES EL CAMBIO CLAVE! ▼▼▼
            # Cambiamos send_message por parse_message
            bot_response = self.client.parse_message(test_case.user_message)
            # ▲▲▲ ¡AQUÍ ESTÁ EL CAMBIO! ▲▲▲

            execution_time = time.time() - start_time

            validator = TestValidator(test_case, bot_response, execution_time)
            result = validator.validate()

            return result
    # ----------------------------------------------------
    # ▲▲▲ FIN DEL MÉTODO QUE FALTABA ▲▲▲
    # ----------------------------------------------------

    def run_suite(self, tests: List[TestCase]):
        total = len(tests)
        print(f"\n{Config.Colors.HEADER}{'='*80}\n🧪 EXECUTING {total} TESTS\n{'='*80}{Config.Colors.ENDC}\n")
        
        for i, test_case in enumerate(tests, 1):
            print(f"{Config.Colors.OKCYAN}[{i}/{total}] {test_case.name} ({test_case.category}){Config.Colors.ENDC}")
            # Esta línea ahora funcionará correctamente
            result = self.run_test(test_case)
            self.results.append(result)
            
            status_color = {
                TestStatus.PASSED: Config.Colors.OKGREEN, 
                TestStatus.FAILED: Config.Colors.FAIL, 
                TestStatus.WARNING: Config.Colors.WARNING
            }.get(result.status, Config.Colors.ENDC)
            
            print(f"  {status_color}{result.status.value}{Config.Colors.ENDC} ({result.execution_time:.2f}s)")

            if result.errors:
                for error in result.errors: 
                    print(f"    {Config.Colors.FAIL}❌ {error}{Config.Colors.ENDC}")
            if result.warnings and self.verbose:
                for warning in result.warnings: 
                    print(f"    {Config.Colors.WARNING}⚠️  {warning}{Config.Colors.ENDC}")
            print()

def main():
    parser = argparse.ArgumentParser(description="🧪 Rasa Bot Testing Suite")
    parser.add_argument("--category", help="Run only tests of a specific category", 
                        choices=get_all_categories() + ["all"], default="all")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose mode")
    parser.add_argument("--export", help="Export results to a JSON file", metavar="PATH")
    parser.add_argument("--no-reset", action="store_true", help="Do not reset context between tests")
    parser.add_argument("--coverage", action="store_true", help="Show coverage analysis")  # ← AGREGAR
    args = parser.parse_args()

    if args.no_reset: 
        Config.RESET_BETWEEN_TESTS = False
    
    client = BotClient(Config)
    print(f"\n{Config.Colors.OKCYAN}🤖 Verifying bot availability...{Config.Colors.ENDC}")
    if not client.check_health():
        print(f"{Config.Colors.FAIL}❌ Bot is not available at {Config.BOT_URL}{Config.Colors.ENDC}")
        sys.exit(1)
    print(f"{Config.Colors.OKGREEN}✅ Bot available{Config.Colors.ENDC}")
    
    all_tests = get_all_tests()
    tests_to_run = [t for t in all_tests if args.category == "all" or t.category == args.category]
    
    # ← AGREGAR: Análisis de cobertura ANTES de ejecutar tests
    if args.coverage:
        coverage_data = CoverageAnalyzer.calculate_coverage(tests_to_run)
        CoverageAnalyzer.print_coverage_report(coverage_data)
    
    runner = TestRunner(client, verbose=args.verbose)
    runner.run_suite(tests_to_run)
    
    # ← AGREGAR: Mostrar cobertura al final también
    if args.coverage:
        coverage_data = CoverageAnalyzer.calculate_coverage(tests_to_run)
        CoverageAnalyzer.print_coverage_report(coverage_data)
    
    failed_count = sum(1 for r in runner.results if r.status == TestStatus.FAILED)
    sys.exit(1 if failed_count > 0 else 0)

if __name__ == "__main__":
    main()