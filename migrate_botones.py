"""
migrate_botones.py
==================
Migra los botones definidos en constants.py de tuplas simples (x, y)
a la estructura completa compatible con la clase Boton:

    ANTES:  "nombre-boton": (0.12, 0.34)
    DESPUES: "nombre-boton": {"coords": (0.12, 0.34), "outcomes": {}, "timeout": 5}

Cubre los tres lugares donde pueden aparecer botones:
  1. botones del contexto principal
  2. botones dentro de menus
  3. botones dentro de subcontexto.valores (si los hay)

Uso:
    python migrate_botones.py                          # usa paths por defecto
    python migrate_botones.py ruta/a/constants.py      # path custom
    python migrate_botones.py --dry-run                # solo muestra el resultado, no escribe
    python migrate_botones.py --backup                 # guarda .bak antes de sobreescribir

El script es IDEMPOTENTE: si un botón ya tiene la estructura dict, lo deja tal cual.
"""

import ast
import sys
import re
import shutil
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT  = 5
DEFAULT_OUTCOMES = {}


# ---------------------------------------------------------------------------
# Detección y transformación de tokens en el source
# ---------------------------------------------------------------------------

def es_tupla_coords(node: ast.expr) -> bool:
    """Devuelve True si el nodo AST es una tupla de exactamente dos números."""
    if not isinstance(node, ast.Tuple):
        return False
    if len(node.elts) != 2:
        return False
    return all(isinstance(e, ast.Constant) and isinstance(e.value, (int, float))
               for e in node.elts)


def es_dict_boton(node: ast.expr) -> bool:
    """Devuelve True si el nodo ya es un dict con al menos la clave 'coords'."""
    if not isinstance(node, ast.Dict):
        return False
    keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
    return "coords" in keys


def reemplazar_tupla_en_source(source: str, lineno: int, col_offset: int,
                                end_lineno: int, end_col_offset: int,
                                x: float, y: float) -> str:
    """
    Reemplaza la tupla (x, y) en las coordenadas exactas del source
    por la estructura dict completa de Boton.
    """
    lines = source.splitlines(keepends=True)

    # Extraer el texto exacto de la tupla para verificar
    if lineno == end_lineno:
        linea = lines[lineno - 1]
        original = linea[col_offset:end_col_offset]
    else:
        # Tupla multilínea (improbable pero lo manejamos)
        original = "".join(lines[lineno - 1][col_offset:] +
                           lines[lineno:end_lineno - 1] +
                           [lines[end_lineno - 1][:end_col_offset]])

    # Formatear los números igual que el original (respetar int vs float)
    def fmt(v):
        return str(int(v)) if isinstance(v, float) and v == int(v) else repr(v)

    nuevo = (
        f'{{"coords": ({fmt(x)}, {fmt(y)}), '
        f'"outcomes": {{}}, '
        f'"timeout": {DEFAULT_TIMEOUT}}}'
    )

    # Reemplazar solo la primera aparición exacta en la posición correcta
    # Construimos el source como string plano y reemplazamos por offset
    lines_flat = source.splitlines(keepends=True)
    start_offset = sum(len(l) for l in lines_flat[:lineno - 1]) + col_offset
    end_offset   = sum(len(l) for l in lines_flat[:end_lineno - 1]) + end_col_offset

    return source[:start_offset] + nuevo + source[end_offset:]


# ---------------------------------------------------------------------------
# Lógica principal de migración
# ---------------------------------------------------------------------------

def migrar_source(source: str) -> tuple[str, int]:
    """
    Parsea el source, encuentra todas las tuplas (x, y) que son valores
    de botones, y las reemplaza por la estructura Boton.

    Retorna (source_migrado, cantidad_de_cambios).
    Proceso en reversa para no invalidar offsets.
    """
    tree = ast.parse(source)

    # Recolectamos todas las tuplas candidatas con sus ubicaciones
    candidatas = []

    for node in ast.walk(tree):
        # Buscamos asignaciones al dict CONTEXTOS_DEFINIDOS
        if not isinstance(node, ast.Dict):
            continue
        # Recorremos pares clave-valor del dict
        for k, v in zip(node.keys, node.values):
            if not isinstance(k, ast.Constant) or not isinstance(k.value, str):
                continue

            # Caso 1 y 2: clave "botones" con dict de {nombre: tupla}
            if k.value == "botones" and isinstance(v, ast.Dict):
                for bk, bv in zip(v.keys, v.values):
                    if es_tupla_coords(bv):
                        x, y = [e.value for e in bv.elts]
                        candidatas.append((bv.lineno, bv.col_offset,
                                           bv.end_lineno, bv.end_col_offset,
                                           x, y))
                    # dentro de menus, los botones también están bajo "botones"
                    # → ya los captura este mismo branch

            # Caso 3: subcontexto.valores.{nombre}.botones
            # (mismo patrón, ya cubierto por el walk general)

    if not candidatas:
        return source, 0

    # Ordenar en reversa para reemplazar desde el final sin invalidar offsets
    candidatas.sort(key=lambda c: (c[0], c[1]), reverse=True)

    cambios = 0
    for lineno, col, end_lineno, end_col, x, y in candidatas:
        source = reemplazar_tupla_en_source(source, lineno, col,
                                            end_lineno, end_col, x, y)
        cambios += 1

    return source, cambios


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    backup  = "--backup"  in args
    args = [a for a in args if not a.startswith("--")]

    constants_path = Path(args[0]) if args else Path("bot/constants.py")

    if not constants_path.exists():
        print(f"[ERROR] No se encontró: {constants_path}")
        sys.exit(1)

    source_original = constants_path.read_text(encoding="utf-8")

    # Verificar que parsea bien antes de tocar nada
    try:
        ast.parse(source_original)
    except SyntaxError as e:
        print(f"[ERROR] El archivo tiene errores de sintaxis: {e}")
        sys.exit(1)

    source_migrado, total = migrar_source(source_original)

    if total == 0:
        print("[OK] No se encontraron botones para migrar (¿ya están migrados?).")
        return

    # Verificar que el resultado también parsea bien
    try:
        ast.parse(source_migrado)
    except SyntaxError as e:
        print(f"[ERROR] El source migrado tiene errores de sintaxis: {e}")
        print("        No se escribió nada. Revisá el script.")
        sys.exit(1)

    print(f"[INFO] Botones encontrados para migrar: {total}")

    if dry_run:
        print("[DRY-RUN] No se escribió ningún archivo. Resultado:")
        print("-" * 60)
        print(source_migrado)
        return

    if backup:
        bak = constants_path.with_suffix(".py.bak")
        shutil.copy2(constants_path, bak)
        print(f"[INFO] Backup guardado en: {bak}")

    constants_path.write_text(source_migrado, encoding="utf-8")
    print(f"[OK] Migración completa. {total} botones actualizados en {constants_path}")


if __name__ == "__main__":
    main()
