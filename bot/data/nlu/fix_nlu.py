#!/usr/bin/env python3
"""
Agrega grupos faltantes a las anotaciones de comparadores y cantidades.
"""

import re
import sys
from pathlib import Path


def infer_group(entity_name: str, context: str) -> str:
    """Infiere el grupo basándose en el contexto de la línea."""
    
    context_lower = context.lower()
    
    # Mapeo de palabras clave a grupos
    if entity_name == 'comparador':
        if any(word in context_lower for word in ['descuento', 'rebaja', 'off', 'dto']):
            return 'descuento_filter'
        elif any(word in context_lower for word in ['bonificación', 'bonificacion', 'bono', 'gratis', '2x1', '3x2']):
            return 'bonificacion_filter'
        elif any(word in context_lower for word in ['stock', 'inventario', 'disponibilidad', 'unidades']):
            return 'stock_filter'
        elif any(word in context_lower for word in ['precio', 'costo']):
            return 'precio_filter'
    
    elif entity_name == 'cantidad_descuento':
        return 'descuento_filter'
    elif entity_name == 'cantidad_bonificacion':
        return 'bonificacion_filter'
    elif entity_name == 'cantidad_stock':
        return 'stock_filter'
    elif entity_name == 'precio':
        return 'precio_filter'
    
    return None


def add_group_to_annotation(annotation: str, group: str) -> str:
    """Agrega el parámetro group a una anotación JSON."""
    
    # Si ya tiene group, no hacer nada
    if '"group"' in annotation:
        return annotation
    
    # Agregar group antes del último }
    return annotation[:-1] + f', "group": "{group}"' + annotation[-1]


def fix_line(line: str) -> tuple[str, int]:
    """Corrige una línea agregando grupos faltantes."""
    
    corrections = 0
    
    # Patrones de entidades que necesitan grupos
    entities = [
        'comparador',
        'cantidad_descuento',
        'cantidad_bonificacion',
        'cantidad_stock',
        'precio'
    ]
    
    for entity in entities:
        pattern = rf'\{{"entity": "{entity}"([^}}]*)\}}'
        
        def replacer(match):
            nonlocal corrections
            annotation = match.group(0)
            
            # Si ya tiene group, no cambiar
            if '"group"' in annotation:
                return annotation
            
            # Inferir grupo del contexto
            group = infer_group(entity, line)
            if not group:
                return annotation  # No se pudo inferir, dejar como está
            
            corrections += 1
            return add_group_to_annotation(annotation, group)
        
        line = re.sub(pattern, replacer, line)
    
    return line, corrections


def fix_file(input_path: Path, output_path: Path = None):
    """Corrige un archivo completo."""
    
    if output_path is None:
        output_path = input_path
    
    # Crear backup
    if input_path == output_path:
        backup_path = input_path.with_suffix(input_path.suffix + '.backup2')
        print(f"📦 Creando backup: {backup_path}")
        with open(input_path, 'r', encoding='utf-8') as f:
            backup_content = f.read()
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(backup_content)
    
    # Leer y procesar
    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    total_corrections = 0
    fixed_lines = []
    
    for line in lines:
        if line.strip() and not line.strip().startswith('#'):
            fixed_line, corrections = fix_line(line)
            total_corrections += corrections
            fixed_lines.append(fixed_line)
        else:
            fixed_lines.append(line)
    
    # Escribir resultado
    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(fixed_lines)
    
    return total_corrections


def main():
    if len(sys.argv) < 2:
        print("Uso: python fix_missing_groups.py <archivo_nlu.yml> [archivo_salida.yml]")
        sys.exit(1)
    
    input_file = Path(sys.argv[1])
    output_file = Path(sys.argv[2]) if len(sys.argv) > 2 else input_file
    
    if not input_file.exists():
        print(f"❌ Error: Archivo '{input_file}' no encontrado")
        sys.exit(1)
    
    print(f"\n🔧 Procesando: {input_file}")
    print("=" * 80)
    
    total = fix_file(input_file, output_file)
    
    print(f"\n✅ Total de correcciones: {total}")
    print(f"💾 Archivo guardado: {output_file}")
    
    if total > 0:
        print("\n📋 Próximos pasos:")
        print("  1. Revisar los cambios")
        print("  2. Ejecutar: rasa train nlu")
        print("  3. Correr los tests nuevamente")
    else:
        print("\n💡 No se encontraron correcciones necesarias")


if __name__ == "__main__":
    main()