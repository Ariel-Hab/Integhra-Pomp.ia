from scripts.config_loader import ConfigLoader
from bot.entrenador.data_generator.nlu_generator import NLUGenerator
from bot.entrenador.importer import generar_lookup_tables

# Cargar config
config = ConfigLoader.cargar_config()
print(f"Segments cargados: {list(config.get('segments', {}).keys())}")

# Cargar lookup tables
lookup = generar_lookup_tables("bot/data")

# Generar ejemplos de prueba solo para buscar_producto
test_config = {"buscar_producto": config["intents"]["buscar_producto"]}
test_config["segments"] = config.get("segments", {})

ejemplos = NLUGenerator.generar_ejemplos(
    config=test_config,
    lookup=lookup,
    custom_limits={"buscar_producto": 10}  # Solo 10 para prueba
)

print("\n--- EJEMPLOS GENERADOS ---")
for ejemplo, intent in ejemplos:
    print(f"{intent}: {ejemplo}")