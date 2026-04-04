# bot/flows.py
#
# Flujos orquestados: secuencias fijas y loopeables que combinan acciones,
# verifican contexto esperado y manejan imprevistos contextuales.
#
# Cada flow asume un punto de entrada conocido y un camino esperado.
# No toman decisiones de navegación global — eso es responsabilidad de main.py.

import time

from bot.screen import (
    capturar_pantalla, find_image_on_screen, find_all_on_screen,
    swipe_from_to, click_at
)
import bot.context as context
from bot.actions import click_boton, click_boton_menu_rapido, esperar_contexto, navegar_a
from bot.constants import CONTEXTOS_DEFINIDOS

# --------------------
# Constantes de TOT
# --------------------

# Región del área scrolleable de TOT (zona del zig-zag, excluyendo tabs y footer)
TOT_REGION_SCROLL = (77, 155, 460, 510)

# Coordenadas de swipe para scroll en TOT
# ARRIBA: arrastra dedo hacia abajo → muestra pisos con números menores (hacia el piso 1)
# ABAJO:  arrastra dedo hacia arriba → muestra pisos con números mayores
TOT_SWIPE_ARRIBA      = (270, 250, 270, 420)
TOT_SWIPE_ABAJO       = (270, 420, 270, 250)
TOT_SWIPE_DURATION_MS = 400
TOT_SWIPE_PAUSA       = 1.0

# Máximo de swipes hacia pisos menores antes de considerar torre completa
TOT_MAX_SWIPES = 20

# Asset de la etiqueta de recompensa disponible en un piso
TOT_ASSET_RECOMPENSA     = "assets/ui/tot-recompensa-id.png"
TOT_THRESHOLD_RECOMPENSA = 0.7

# Asset del fondo de la torre (franja del piso 1) para detectar límite inferior
TOT_ASSETS_FONDO = [
    "assets/ui/tot-bottom-id.png",
    "assets/ui/tot-bottom-selected-id.png",
]
TOT_THRESHOLD_FONDO = 0.85
TOT_REGION_FONDO = (99, 398, 466, 510)
TOT_THRESHOLD_FONDO = 0.65

# Assets de pisos completados por tipo de torre
TOT_ASSETS_PISOS = {
    "physical": [
        "assets/ui/physical-floor-id.png",
        "assets/ui/mix-floor-id.png",
    ],
    "magical": [
        "assets/ui/magical-floor-id.png",
        "assets/ui/mix-floor-id.png",
    ],
}
TOT_THRESHOLD_PISOS = 0.85

# Intervalo de polling mientras esperamos que termine el auto-repeat
TOT_INTERVALO_ESPERA = 15  # segundos


# --------------------
# Helpers de TOT
# --------------------

def _swipe(coords):
    """Ejecuta un swipe y espera la pausa configurada."""
    x1, y1, x2, y2 = coords
    swipe_from_to(x1, y1, x2, y2, duration_ms=TOT_SWIPE_DURATION_MS)
    time.sleep(TOT_SWIPE_PAUSA)


def _buscar_recompensas(screenshot_img):
    """
    Busca todos los íconos de recompensa disponible visibles en el área de TOT.
    Retorna lista de (x, y) ordenada por Y ascendente (arriba primero, abajo al final).
    """
    return find_all_on_screen(
        screenshot_img=screenshot_img,
        template_path=TOT_ASSET_RECOMPENSA,
        region=TOT_REGION_SCROLL,
        threshold=TOT_THRESHOLD_RECOMPENSA
    )


def _contar_pisos_completados(screenshot_img, tipo_torre):
    """
    Cuenta cuántos íconos de piso completado (sin recompensa) hay visibles.
    tipo_torre: "physical" | "magical"
    """
    total = 0
    for asset in TOT_ASSETS_PISOS[tipo_torre]:
        total += len(find_all_on_screen(
            screenshot_img=screenshot_img,
            template_path=asset,
            region=TOT_REGION_SCROLL,
            threshold=TOT_THRESHOLD_PISOS
        ))
    return total


def _hay_fondo(screenshot_img):
    for asset in TOT_ASSETS_FONDO:
        match = find_image_on_screen(
            screenshot_img=screenshot_img,
            template_path=asset,
            region=TOT_REGION_FONDO,
            threshold=TOT_THRESHOLD_FONDO
        )
        if match:
            return True
    return False


def _navegar_piso_mas_bajo_con_recompensa(tipo_torre):
    """
    Scrollea en TOT hasta encontrar el piso más bajo con recompensa disponible.
    tipo_torre: "physical" | "magical"
    Retorna (x, y) del piso a clickear, o None si la torre está completa.

    Algoritmo:
        - Hay recompensas Y hay pisos completados → zona correcta, tomar la recompensa más baja.
        - Solo recompensas y se ve el fondo (piso 1) → tomar la recompensa más baja.
        - Solo recompensas sin fondo visible → scrollear hacia pisos menores.
        - Sin recompensas → scrollear hacia pisos mayores.
        - Si scrolleando hacia pisos mayores llegamos al tope sin recompensas → torre completa.
    """
    swipes_arriba = 0
    swipes_abajo  = 0

    for _ in range(TOT_MAX_SWIPES * 2):
        _, screenshot_img = capturar_pantalla()
        recompensas       = _buscar_recompensas(screenshot_img)
        completados       = _contar_pisos_completados(screenshot_img, tipo_torre)
        fondo             = _hay_fondo(screenshot_img)

        if recompensas and completados > 0:
            return recompensas[-1]

        elif recompensas and completados == 0:
            if fondo:
                return recompensas[-1]
            if swipes_abajo >= 15:
                print("[WARN] _navegar: límite de swipes hacia pisos menores alcanzado.")
                return recompensas[-1]
            _swipe(TOT_SWIPE_ABAJO)
            swipes_abajo += 1

        else:
            if swipes_arriba >= TOT_MAX_SWIPES:
                return None
            _swipe(TOT_SWIPE_ARRIBA)
            swipes_arriba += 1

    return None


def _esperar_fin_autorepeat():
    """
    Espera en loop hasta que aparezca el aviso de fin de auto-repeat
    (derrota o torre completa). Cuando aparece, clickea OK y retorna.
    """
    ctx_defeated = CONTEXTOS_DEFINIDOS["tot-auto-repeat-defeated"]
    ctx_end      = CONTEXTOS_DEFINIDOS["tot-auto-repeat-end"]

    while True:
        time.sleep(TOT_INTERVALO_ESPERA)
        _, screenshot_img = capturar_pantalla()

        for ctx in (ctx_defeated, ctx_end):
            match = find_image_on_screen(
                screenshot_img=screenshot_img,
                template_path=ctx["imagen"],
                region=ctx["region"],
                threshold=ctx["threshold"]
            )
            if match:
                x, y = ctx["botones"]["ok"]
                click_at(x, y)
                return


# --------------------
# Flow de TOT
# --------------------

def _flow_torre(nombre_boton_torre, tipo_torre):
    """
    Ejecuta el flow completo para una torre del personaje activo.
    Asume que ya estamos en el contexto tot.

    nombre_boton_torre: "physical-tower" | "magical-tower"
    tipo_torre:         "physical" | "magical"

    Retorna True si se ejecutó el flow, False si la torre ya estaba completa.
    """
    click_boton(nombre_boton_torre)
    time.sleep(0.5)

    piso = _navegar_piso_mas_bajo_con_recompensa(tipo_torre)

    if piso is None:
        print(f"[TOT] Torre '{tipo_torre}' ya completa para este personaje.")
        return False

    x, y = piso
    click_at(x, y)
    time.sleep(0.5)

    click_boton("auto-repeat")

    if not esperar_contexto("tot-auto-repeat"):
        print("[ERROR] _flow_torre: no apareció el menú de auto-repeat.")
        return False

    click_boton("auto-continue")

    _esperar_fin_autorepeat()

    return True


def flow_tot(total_personajes=27):
    """
    Flow completo de TOT para todos los personajes.
    Punto de entrada: contexto seleccion_de_personaje.

    Secuencia por personaje:
        1. Seleccionar personaje.
        2. Navegar lobby → survival → tot.
        3. Torre física → buscar piso → auto-repeat → auto-continue → esperar fin.
        4. Torre mágica → ídem.
        5. Cambiar de personaje via menú rápido → repetir.
    """
    for i in range(total_personajes):
        print(f"\n[TOT] === Personaje {i + 1}/{total_personajes} ===")

        # 1. Seleccionar personaje
        if not navegar_a("select", "lobby", "seleccion_de_personaje"):
            print("[ERROR] flow_tot: no se pudo seleccionar personaje.")
            return

        # 2. Navegar a TOT
        if not navegar_a("survival", "survival", "lobby"):
            print("[ERROR] flow_tot: no se pudo navegar a survival.")
            return

        if not navegar_a("tot", "tot", "survival"):
            print("[ERROR] flow_tot: no se pudo navegar a tot.")
            return

        # 3. Torre física
        _flow_torre("physical-tower", "physical")

        # 4. Torre mágica
        if not esperar_contexto("tot"):
            print("[ERROR] flow_tot: no se llegó a tot para torre mágica.")
            return
        _flow_torre("magical-tower", "magical")

        # 5. Cambiar de personaje (excepto el último)
        if i < total_personajes - 1:
            if not esperar_contexto("tot"):
                print("[ERROR] flow_tot: no se pudo cambiar de personaje.")
                return
            click_boton("menu-rapido")
            click_boton_menu_rapido("select-character")

    print("\n[TOT] Flow completado para todos los personajes.")