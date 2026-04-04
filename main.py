# farmbot/main.py

from bot.screen import conectar_dispositivo
from bot.flows import flow_tot
#from bot.screen import conectar_dispositivo, capturar_pantalla
#from bot.flows import _hay_fondo

if __name__ == "__main__":
    print("Iniciando FarmBot...")

    try:
        conectar_dispositivo()
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        exit(1)

    # Flow de Tower of Tribulations para todos los personajes.
    # Punto de entrada: seleccion_de_personaje (primer personaje arriba de todo).
    flow_tot(total_personajes=27)