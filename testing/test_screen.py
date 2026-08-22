# test_screen.py
import cv2
import time
from bot.screen import conectar_dispositivo, capturar_pantalla

print("Conectando...")
conectar_dispositivo()

print("Capturando frame...")
_, img = capturar_pantalla()

print(f"Frame: {img.shape}")
cv2.imwrite("test_frame.png", img)
print("Guardado en test_frame.png")

print("Midiendo velocidad de captura_pantalla()...")
tiempos = []
for _ in range(30):
    t0 = time.time()
    _, img = capturar_pantalla()
    tiempos.append(time.time() - t0)

promedio = sum(tiempos) / len(tiempos)
print(f"  Promedio: {promedio*1000:.1f}ms")
print(f"  Mínimo:   {min(tiempos)*1000:.1f}ms")
print(f"  Máximo:   {max(tiempos)*1000:.1f}ms")
print(f"  FPS efectivos: {1/promedio:.1f}")