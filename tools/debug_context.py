# tools/debug_context.py
#
# Herramienta de debugging para verificar la detección de contextos y subcontextos.
#
# Toma un screencap, corre todos los contextos definidos contra él y muestra:
#   - Tabla en consola con la confianza obtenida vs threshold de cada contexto/subcontexto.
#   - Ventana OpenCV con los matches que superaron el threshold marcados con un rectángulo.
#
# Uso:
#   python tools/debug_context.py

import cv2
import subprocess
import numpy as np
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.constants import CONTEXTOS_DEFINIDOS, DISPOSITIVO_ADB

WINDOW_NAME = "Debug — Contextos detectados  |  [Q] Salir"
COLOR_MATCH  = (0, 220, 0)    # verde  — superó el threshold
COLOR_NOMATCH = (0, 60, 220)  # rojo   — no superó el threshold
COLOR_SUB    = (220, 180, 0)  # celeste — subcontexto


# --------------------
# ADB
# --------------------

def conectar():
    cmd = f"adb -s {DISPOSITIVO_ADB} get-serialno"
    r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    salida = r.stdout.decode().strip()
    if salida != DISPOSITIVO_ADB:
        error = r.stderr.decode().strip() or salida
        raise RuntimeError(f"No se pudo conectar: {error}")
    print(f"[ADB] Dispositivo listo: {DISPOSITIVO_ADB}\n")


def capturar():
    ruta_temp = "screencaps/_temp.png"
    os.makedirs("screencaps", exist_ok=True)
    subprocess.run(f'adb -s {DISPOSITIVO_ADB} shell screencap -p /sdcard/screen.png', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    subprocess.run(f'adb -s {DISPOSITIVO_ADB} pull /sdcard/screen.png {ruta_temp}', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    img = cv2.imread(ruta_temp)
    if img is None:
        raise RuntimeError("No se pudo decodificar el screencap.")
    cv2.imwrite("screencaps/debug_last.png", img)
    return img


# --------------------
# Matching
# --------------------

def match_score(screenshot_gray, template_path, region):
    """
    Retorna la confianza máxima del template dentro de la región.
    Retorna (score, top_left_abs, (w_t, h_t)) o (score, None, None) si falla.
    """
    template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
    if template is None:
        return None, None, None

    h_s, w_s = screenshot_gray.shape
    x1, y1, x2, y2 = region
    x1 = max(0, x1); y1 = max(0, y1)
    x2 = min(w_s, x2); y2 = min(h_s, y2)

    recorte = screenshot_gray[y1:y2, x1:x2]
    if recorte.shape[0] == 0 or recorte.shape[1] == 0:
        return None, None, None

    res = cv2.matchTemplate(recorte, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)

    h_t, w_t = template.shape
    top_left_abs = (max_loc[0] + x1, max_loc[1] + y1)
    return max_val, top_left_abs, (w_t, h_t)


# --------------------
# Consola
# --------------------

def imprimir_tabla(resultados):
    """
    resultados: lista de dicts con claves:
        tipo         "contexto" | "subcontexto"
        nombre       str
        subtipo      str | None  (nombre del valor de subcontexto)
        score        float | None
        threshold    float
        superado     bool
        error        str | None
    """
    col_nombre = 34
    col_score  = 8
    col_thresh = 9
    col_estado = 10

    sep = "─" * (col_nombre + col_score + col_thresh + col_estado + 9)

    print(sep)
    print(f"  {'Contexto / Subcontexto':<{col_nombre}}  {'Score':>{col_score}}  {'Umbral':>{col_thresh}}  {'Estado':<{col_estado}}")
    print(sep)

    for r in resultados:
        if r["tipo"] == "contexto":
            nombre_col = r["nombre"]
        else:
            nombre_col = f"  └─ [{r['nombre']}] {r['subtipo']}"

        if r["error"]:
            estado = "⚠ NO EXISTE"
            score_col = "  —"
        elif r["score"] is None:
            estado = "⚠ ERROR"
            score_col = "  —"
        else:
            estado = "✔ MATCH" if r["superado"] else "✘ no match"
            score_col = f"{r['score']:.4f}"

        print(f"  {nombre_col:<{col_nombre}}  {score_col:>{col_score}}  {r['threshold']:>{col_thresh}.2f}  {estado:<{col_estado}}")

    print(sep)
    print()


# --------------------
# Visual
# --------------------

def dibujar_matches(img, resultados_vis):
    """
    resultados_vis: lista de dicts con claves:
        nombre, subtipo, superado, top_left, size, color
    """
    overlay = img.copy()

    for r in resultados_vis:
        if r["top_left"] is None:
            continue
        x, y = r["top_left"]
        w, h = r["size"]
        cv2.rectangle(overlay, (x, y), (x + w, y + h), r["color"], 2)

        etiqueta = r["nombre"] if not r["subtipo"] else f"{r['nombre']} › {r['subtipo']}"
        cv2.putText(overlay, etiqueta, (x, y - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, r["color"], 1, cv2.LINE_AA)

    return overlay


# --------------------
# Main
# --------------------

def main():
    print("=== Debug de detección de contextos ===\n")

    try:
        conectar()
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    print("Tomando screencap...")
    try:
        img = capturar()
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    screenshot_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    resultados_tabla = []
    resultados_vis   = []

    for nombre_ctx, datos in CONTEXTOS_DEFINIDOS.items():
        threshold = datos["threshold"]
        imagen    = datos["imagen"]
        region    = datos["region"]

        # — Contexto principal —
        existe = os.path.isfile(imagen)
        if not existe:
            resultados_tabla.append({
                "tipo": "contexto", "nombre": nombre_ctx, "subtipo": None,
                "score": None, "threshold": threshold, "superado": False,
                "error": "archivo no encontrado"
            })
            resultados_vis.append({
                "nombre": nombre_ctx, "subtipo": None, "superado": False,
                "top_left": None, "size": None, "color": COLOR_NOMATCH
            })
        else:
            score, top_left, size = match_score(screenshot_gray, imagen, region)
            superado = score is not None and score >= threshold
            resultados_tabla.append({
                "tipo": "contexto", "nombre": nombre_ctx, "subtipo": None,
                "score": score, "threshold": threshold, "superado": superado,
                "error": None
            })
            resultados_vis.append({
                "nombre": nombre_ctx, "subtipo": None, "superado": superado,
                "top_left": top_left if superado else None,
                "size": size, "color": COLOR_MATCH if superado else COLOR_NOMATCH
            })

        # — Subcontextos —
        subcontexto = datos.get("subcontexto")
        if subcontexto and subcontexto.get("valores"):
            for nombre_val, datos_val in subcontexto["valores"].items():
                th_sub  = datos_val.get("threshold", threshold)
                img_sub = datos_val["imagen"]
                reg_sub = datos_val["region"]

                existe_sub = os.path.isfile(img_sub)
                if not existe_sub:
                    resultados_tabla.append({
                        "tipo": "subcontexto", "nombre": nombre_ctx, "subtipo": nombre_val,
                        "score": None, "threshold": th_sub, "superado": False,
                        "error": "archivo no encontrado"
                    })
                else:
                    score_s, tl_s, sz_s = match_score(screenshot_gray, img_sub, reg_sub)
                    superado_s = score_s is not None and score_s >= th_sub
                    resultados_tabla.append({
                        "tipo": "subcontexto", "nombre": nombre_ctx, "subtipo": nombre_val,
                        "score": score_s, "threshold": th_sub, "superado": superado_s,
                        "error": None
                    })
                    resultados_vis.append({
                        "nombre": nombre_ctx, "subtipo": nombre_val, "superado": superado_s,
                        "top_left": tl_s if superado_s else None,
                        "size": sz_s, "color": COLOR_SUB if superado_s else COLOR_NOMATCH
                    })

    imprimir_tabla(resultados_tabla)

    img_resultado = dibujar_matches(img, resultados_vis)

    leyenda = [
        ("Rectangulo verde  : contexto detectado",    COLOR_MATCH),
        ("Rectangulo celeste: subcontexto detectado", COLOR_SUB),
    ]
    y_base = img_resultado.shape[0] - 10
    for texto, color in reversed(leyenda):
        cv2.putText(img_resultado, texto, (10, y_base),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
        y_base -= 18

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.imshow(WINDOW_NAME, img_resultado)
    print("Presioná cualquier tecla o cerrá la ventana para salir.")
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
