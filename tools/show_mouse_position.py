# python tools/show_mouse_position.py

import pyautogui
import time

print("Mueve el mouse. Presiona Ctrl+C para detener.")
time.sleep(1)

try:
    while True:
        x, y = pyautogui.position()
        position_str = f"Posición del mouse: ({x}, {y})"
        print(position_str, end="\r", flush=True)
        time.sleep(0.05)
except KeyboardInterrupt:
    print("\nFinalizado.")
