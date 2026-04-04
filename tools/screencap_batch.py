# tools/screencap_batch.py
#
# Muestra el stream en vivo del celular y guarda frames con SPACE.
# Las capturas se guardan en screencaps/batch/ con timestamp.
# Usá luego asset_capture.py con esa carpeta para capturar assets sin reconectar.
#
# Uso:
#   python tools/screencap_batch.py
#
# Teclas:
#   SPACE → guardar frame actual
#   Q     → salir

import cv2
import os
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.screen import conectar_dispositivo, capturar_pantalla

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARPETA       = os.path.join(_PROJECT_ROOT, "screencaps", "batch")
WINDOW        = "Batch Screencap  |  [SPACE] Capturar  [Q] Salir"


def main():
    os.makedirs(CARPETA, exist_ok=True)
    print("Conectando...")
    conectar_dispositivo()
    print(f"Listo. Las capturas se guardan en: {CARPETA}\n")
    print("[SPACE] Capturar frame  |  [Q] Salir\n")

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)

    while True:
        _, frame = capturar_pantalla()
        cv2.imshow(WINDOW, frame)
        key = cv2.waitKey(50) & 0xFF

        if key == ord('q') or key == ord('Q'):
            break
        elif key == ord(' '):
            ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            ruta = os.path.join(CARPETA, f"{ts}.png")
            cv2.imwrite(ruta, frame)
            print(f"[+] Guardado: {os.path.basename(ruta)}")

        if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()