# tools/asset_capture.py
#
# Herramienta para capturar assets, regiones de búsqueda y coordenadas de botones.
# Todas las coordenadas y regiones se imprimen en formato RELATIVO (0.0-1.0)
# respecto a la resolución de la imagen procesada (RESOLUCION_BASE).
#
# Uso:
#   python tools/asset_capture.py                    # modo dispositivo: captura desde el celu
#   python tools/asset_capture.py screencaps/batch/  # modo carpeta: usa imágenes de disco
#
# Modos (se alternan automáticamente en orden, o podés saltearte pasos con S):
#
#   [1] Template  → dibujá un rectángulo verde sobre el elemento a reconocer.
#                   Pedí un nombre → guarda el recorte en assets/ui/ e imprime "imagen":
#   [2] Región    → dibujá un rectángulo azul sobre la zona de búsqueda.
#                   Imprime "region": en coordenadas relativas lista para pegar en constants.py.
#   [3] Botones   → click izquierdo simple sobre cada botón.
#                   Imprime "nombre": (x, y) en coordenadas relativas.
#                   Click derecho para terminar el modo botones.
#
# Teclas globales:
#   S  → saltar al siguiente modo sin completar el actual
#   R  → siguiente imagen (modo carpeta) o nuevo screencap (modo dispositivo)
#   Q  → salir

import cv2
import subprocess
import socket
import struct
import os
import sys
import time
import av

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.constants import DISPOSITIVO_ADB, SCRCPY_SERVER_PATH, RESOLUCION_BASE

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR    = os.path.join(_PROJECT_ROOT, "assets", "ui")
WINDOW_NAME   = "Asset Capture  |  [S] Saltar paso  [R] Siguiente  [Q] Salir"

PUERTO  = 27183
MAX_PTS = 1 << 62

# Resolución de la imagen que se está procesando.
# En modo dispositivo se detecta automáticamente.
# En modo carpeta se lee del tamaño real de la imagen.
# Se usa para calcular coordenadas relativas.
_img_w = None
_img_h = None

# ---------------------------------------------------------------------------
# Estado global
# ---------------------------------------------------------------------------

drawing       = False
start_x       = start_y = 0
end_x         = end_y   = 0
step          = 1
img_display   = None
img_base      = None
pending_rect  = None
pending_click = None


# ---------------------------------------------------------------------------
# Helpers de coordenadas
# ---------------------------------------------------------------------------

def _a_relativo_punto(x, y):
    return (round(x / _img_w, 4), round(y / _img_h, 4))

def _a_relativo_region(x1, y1, x2, y2):
    return (
        round(x1 / _img_w, 4),
        round(y1 / _img_h, 4),
        round(x2 / _img_w, 4),
        round(y2 / _img_h, 4),
    )


# ---------------------------------------------------------------------------
# Captura — modo dispositivo
# ---------------------------------------------------------------------------

def _recvall(sock, n):
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise RuntimeError("Socket cerrado por el server.")
        data += chunk
    return data


def capturar_desde_dispositivo():
    subprocess.run(
        ["adb", "-s", DISPOSITIVO_ADB, "push",
         SCRCPY_SERVER_PATH, "/data/local/tmp/scrcpy-server.jar"],
        capture_output=True
    )
    subprocess.run(
        ["adb", "-s", DISPOSITIVO_ADB, "forward",
         f"tcp:{PUERTO}", "localabstract:scrcpy"],
        capture_output=True
    )
    proc = subprocess.Popen(
        ["adb", "-s", DISPOSITIVO_ADB, "shell",
         "CLASSPATH=/data/local/tmp/scrcpy-server.jar",
         "app_process", "/",
         "com.genymobile.scrcpy.Server",
         "3.3.4",
         "tunnel_forward=true",
         "video_bit_rate=2000000",
         "max_size=0",
         "audio=false",
         "control=false"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    time.sleep(2)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect(("127.0.0.1", PUERTO))

    _recvall(sock, 1)   # dummy
    _recvall(sock, 64)  # device name
    _recvall(sock, 4)   # codec
    _recvall(sock, 4)   # width
    _recvall(sock, 4)   # height

    codec  = av.CodecContext.create("h264", "r")
    imagen = None

    for _ in range(50):
        header  = _recvall(sock, 12)
        pts     = struct.unpack(">Q", header[0:8])[0]
        size    = struct.unpack(">I", header[8:12])[0]
        if pts >= MAX_PTS:
            pts = None
        payload = _recvall(sock, size)
        packet  = av.Packet(payload)
        if pts is not None:
            packet.pts = pts
        try:
            for frame in codec.decode(packet):
                imagen = frame.to_ndarray(format="bgr24")
                break
        except Exception:
            pass
        if imagen is not None:
            break

    sock.close()
    proc.terminate()

    if imagen is None:
        raise RuntimeError("No se obtuvo ningún frame.")
    return imagen


# ---------------------------------------------------------------------------
# Captura — modo carpeta
# ---------------------------------------------------------------------------

def cargar_imagenes_carpeta(carpeta):
    extensiones = (".png", ".jpg", ".jpeg")
    archivos = sorted([
        os.path.join(carpeta, f)
        for f in os.listdir(carpeta)
        if f.lower().endswith(extensiones)
    ])
    if not archivos:
        raise RuntimeError(f"No se encontraron imágenes en: {carpeta}")
    return archivos


# ---------------------------------------------------------------------------
# Mouse callback
# ---------------------------------------------------------------------------

def mouse_callback(event, x, y, flags, param):
    global drawing, start_x, start_y, end_x, end_y, img_display, pending_rect, pending_click

    if step in (1, 2):
        if event == cv2.EVENT_LBUTTONDOWN:
            drawing = True
            start_x, start_y = x, y
            end_x,   end_y   = x, y

        elif event == cv2.EVENT_MOUSEMOVE and drawing:
            end_x, end_y = x, y
            img_display  = img_base.copy()
            color = (0, 255, 0) if step == 1 else (255, 100, 0)
            cv2.rectangle(img_display, (start_x, start_y), (end_x, end_y), color, 2)
            cv2.imshow(WINDOW_NAME, img_display)

        elif event == cv2.EVENT_LBUTTONUP:
            drawing = False
            x1, x2 = sorted([start_x, end_x])
            y1, y2 = sorted([start_y, end_y])
            if x2 - x1 < 5 or y2 - y1 < 5:
                print("[!] Rectángulo demasiado pequeño, intentá de nuevo.")
                return
            pending_rect = (x1, y1, x2, y2)

    elif step == 3:
        if event == cv2.EVENT_LBUTTONDOWN:
            pending_click = (x, y)
        elif event == cv2.EVENT_RBUTTONDOWN:
            print("[+] Modo botones finalizado.\n")
            advance_step()


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def handle_template(x1, y1, x2, y2):
    global img_base, img_display

    recorte = img_base[y1:y2, x1:x2]
    nombre  = input("\nNombre del asset (sin extensión): ").strip()
    if not nombre:
        print("[!] Nombre vacío, asset descartado.")
        return

    os.makedirs(ASSETS_DIR, exist_ok=True)
    ruta          = os.path.join(ASSETS_DIR, f"{nombre}.png")
    ruta_relativa = os.path.relpath(ruta, _PROJECT_ROOT).replace(os.sep, "/")
    cv2.imwrite(ruta, recorte)
    print(f'[+] Asset guardado: {ruta}')
    print(f'    "imagen": "{ruta_relativa}",')

    img_base = img_display.copy()
    cv2.rectangle(img_base, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.putText(img_base, nombre, (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    img_display = img_base.copy()
    cv2.imshow(WINDOW_NAME, img_display)

    advance_step()


def handle_region(x1, y1, x2, y2):
    global img_base, img_display

    rx1, ry1, rx2, ry2 = _a_relativo_region(x1, y1, x2, y2)
    print(f'[+] Región de búsqueda:')
    print(f'    "region": ({rx1}, {ry1}, {rx2}, {ry2}),')

    img_base = img_display.copy()
    cv2.rectangle(img_base, (x1, y1), (x2, y2), (255, 100, 0), 2)
    cv2.putText(img_base, "region", (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 100, 0), 1)
    img_display = img_base.copy()
    cv2.imshow(WINDOW_NAME, img_display)

    advance_step()


def handle_button_click(x, y):
    global img_base, img_display

    nombre = input(f"\nNombre del botón en ({x}, {y}): ").strip()
    if not nombre:
        print("[!] Nombre vacío, botón descartado.")
        return

    rx, ry = _a_relativo_punto(x, y)
    print(f'    "{nombre}": ({rx}, {ry}),')

    img_base = img_display.copy()
    cv2.circle(img_base, (x, y), 6, (0, 165, 255), -1)
    cv2.putText(img_base, nombre, (x + 10, y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1)
    img_display = img_base.copy()
    cv2.imshow(WINDOW_NAME, img_display)


def advance_step():
    global step
    step += 1
    if step == 2:
        print("\n--- Paso 2: dibujá la región de búsqueda (rectángulo azul). [S] para saltar ---")
    elif step == 3:
        print("\n--- Paso 3: click izquierdo en cada botón. Click derecho para terminar. [S] para saltar ---")
    elif step > 3:
        print("\n--- Asset completo. Podés marcar otro o presionar [R] para siguiente imagen ---")
        step = 1


def print_step_instructions():
    if step == 1:
        print("\n--- Paso 1: dibujá el template (rectángulo verde). [S] para saltar ---")
    elif step == 2:
        print("\n--- Paso 2: dibujá la región de búsqueda (rectángulo azul). [S] para saltar ---")
    elif step == 3:
        print("\n--- Paso 3: click izquierdo en cada botón. Click derecho para terminar. [S] para saltar ---")


# ---------------------------------------------------------------------------
# Loop principal de una imagen
# ---------------------------------------------------------------------------

def procesar_imagen(imagen):
    """Abre la ventana de captura sobre una imagen. Retorna True para continuar, False para salir."""
    global img_base, img_display, step, pending_rect, pending_click, _img_w, _img_h

    _img_h, _img_w = imagen.shape[:2]
    img_base      = imagen.copy()
    img_display   = imagen.copy()
    step          = 1
    pending_rect  = None
    pending_click = None

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(WINDOW_NAME, mouse_callback)
    cv2.imshow(WINDOW_NAME, img_display)

    print_step_instructions()
    print("[R] Siguiente imagen  |  [Q] Salir\n")

    while True:
        key = cv2.waitKey(20) & 0xFF

        if key == ord('q') or key == ord('Q'):
            print("Saliendo.")
            cv2.destroyAllWindows()
            return False

        elif key == ord('r') or key == ord('R'):
            print("\nSiguiente imagen...\n")
            return True

        elif key == ord('s') or key == ord('S'):
            print("[S] Paso salteado.")
            advance_step()

        if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
            print("Ventana cerrada.")
            return False

        if pending_rect is not None:
            x1, y1, x2, y2 = pending_rect
            pending_rect = None
            if step == 1:
                handle_template(x1, y1, x2, y2)
            elif step == 2:
                handle_region(x1, y1, x2, y2)

        if pending_click is not None:
            x, y = pending_click
            pending_click = None
            if step == 3:
                handle_button_click(x, y)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=== Asset Capture Tool ===")
    print(f"Assets se guardarán en: {ASSETS_DIR}/")
    print(f"Resolución base: {RESOLUCION_BASE[0]}x{RESOLUCION_BASE[1]}")
    print(f"Coordenadas de salida: RELATIVAS (0.0-1.0)\n")

    modo_carpeta = len(sys.argv) > 1
    imagenes     = []
    idx          = 0

    if modo_carpeta:
        carpeta = sys.argv[1]
        try:
            imagenes = cargar_imagenes_carpeta(carpeta)
        except RuntimeError as e:
            print(f"[ERROR] {e}")
            sys.exit(1)
        print(f"[CARPETA] {len(imagenes)} imagen(es) encontrada(s) en: {carpeta}\n")
    else:
        resultado = subprocess.run(
            ["adb", "devices"], capture_output=True, text=True
        )
        if DISPOSITIVO_ADB not in resultado.stdout:
            print(f"[ERROR] Dispositivo '{DISPOSITIVO_ADB}' no encontrado.")
            sys.exit(1)
        print(f"[ADB] Dispositivo encontrado: {DISPOSITIVO_ADB}\n")

    while True:
        if modo_carpeta:
            if idx >= len(imagenes):
                print("No hay más imágenes en la carpeta.")
                break
            ruta   = imagenes[idx]
            imagen = cv2.imread(ruta)
            if imagen is None:
                print(f"[!] No se pudo leer: {ruta}, saltando.")
                idx += 1
                continue
            print(f"[{idx + 1}/{len(imagenes)}] {os.path.basename(ruta)}")
            idx += 1
        else:
            print("Tomando screencap...")
            try:
                imagen = capturar_desde_dispositivo()
            except RuntimeError as e:
                print(f"[ERROR] {e}")
                sys.exit(1)

        continuar = procesar_imagen(imagen)
        if not continuar:
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()