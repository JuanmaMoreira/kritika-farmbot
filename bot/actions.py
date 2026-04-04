# bot/actions.py

import time

from bot.screen import click_at
from bot.constants import MENU_RAPIDO, MENU_RAPIDO_OFFSET
import bot.context as context
from bot.context import actualizar_contexto


# --------------------
# Navegación
# --------------------

def esperar_contexto(esperado, timeout=15):
    """
    Llama a actualizar_contexto() en loop hasta que el contexto activo
    sea el esperado, o hasta agotar el timeout.
    Retorna True si llegó al contexto esperado, False si venció el timeout.
    """
    inicio = time.time()
    while time.time() - inicio < timeout:
        actualizar_contexto()
        if context.contexto_actual == esperado:
            return True
        time.sleep(0.5)
    print(f"[ERROR] esperar_contexto: timeout esperando '{esperado}', activo: '{context.contexto_actual}'")
    return False


def navegar_a(nombre_boton, contexto_esperado, contexto_origen, max_intentos=3):
    """
    Hace click en un botón y verifica que se llegó al contexto esperado.
    Si no llegó pero sigue en el contexto origen, reintenta.
    Si el contexto resultante es inesperado (ni esperado ni origen), aborta.

    Retorna True si llegó al contexto esperado, False si agotó los intentos
    o se encontró en un contexto inesperado.
    """
    for intento in range(max_intentos):
        click_boton(nombre_boton)
        if esperar_contexto(contexto_esperado, timeout=5):
            return True

        # No llegó al esperado — verificar dónde estamos
        actualizar_contexto()
        if context.contexto_actual != contexto_origen:
            print(f"[ERROR] navegar_a: contexto inesperado '{context.contexto_actual}', esperaba '{contexto_origen}'")
            return False

        print(f"[WARN] navegar_a: intento {intento + 1}/{max_intentos} fallido, reintentando...")

    print(f"[ERROR] navegar_a: no se llegó a '{contexto_esperado}' tras {max_intentos} intentos.")
    return False


# --------------------
# Botones de contexto
# --------------------

def click_boton(nombre):
    """
    Clickea un botón siempre disponible en el contexto activo.
    Si el subcontexto activo tiene ese botón, tiene prioridad sobre el contexto.
    Retorna True si encontró y clickeó, False si no.
    """
    if context.contexto_actual is None:
        print("[ERROR] click_boton: no hay contexto activo.")
        return False

    contexto_obj = context.contextos_definidos[context.contexto_actual]

    # Buscar primero en botones del subcontexto activo
    if context.subcontexto_actual and contexto_obj.subcontexto:
        datos_sub   = contexto_obj.subcontexto["valores"].get(context.subcontexto_actual, {})
        botones_sub = datos_sub.get("botones", {})
        if nombre in botones_sub:
            x, y = botones_sub[nombre]
            click_at(x, y)
            return True

    # Buscar en botones del contexto
    if nombre in contexto_obj.botones:
        x, y = contexto_obj.botones[nombre]
        click_at(x, y)
        return True

    print(f"[ERROR] click_boton: botón '{nombre}' no encontrado en contexto '{context.contexto_actual}'.")
    return False


# --------------------
# Botones de menú
# --------------------

def click_boton_menu(nombre_menu, nombre_boton):
    """
    Clickea un botón dentro de un menú desplegable del contexto activo.
    No verifica si el menú está abierto — eso es responsabilidad del flow.
    Retorna True si encontró y clickeó, False si no.
    """
    if context.contexto_actual is None:
        print("[ERROR] click_boton_menu: no hay contexto activo.")
        return False

    contexto_obj = context.contextos_definidos[context.contexto_actual]

    if nombre_menu not in contexto_obj.menus:
        print(f"[ERROR] click_boton_menu: menú '{nombre_menu}' no existe en contexto '{context.contexto_actual}'.")
        return False

    botones_menu = contexto_obj.menus[nombre_menu].get("botones", {})

    if nombre_boton not in botones_menu:
        print(f"[ERROR] click_boton_menu: botón '{nombre_boton}' no existe en menú '{nombre_menu}'.")
        return False

    x, y = botones_menu[nombre_boton]
    click_at(x, y)
    return True


# --------------------
# Menú rápido
# --------------------

def click_boton_menu_rapido(nombre_boton):
    """
    Clickea un botón del menú rápido aplicando el offset del contexto activo.
    No verifica si el menú rápido está abierto — eso es responsabilidad del flow.
    Retorna True si encontró y clickeó, False si no.
    """
    if context.contexto_actual is None:
        print("[ERROR] click_boton_menu_rapido: no hay contexto activo.")
        return False

    contexto_obj = context.contextos_definidos[context.contexto_actual]

    if not contexto_obj.menu_rapido_disponible:
        print(f"[ERROR] click_boton_menu_rapido: menú rápido no disponible en '{context.contexto_actual}'.")
        return False

    if nombre_boton not in MENU_RAPIDO["botones"]:
        print(f"[ERROR] click_boton_menu_rapido: botón '{nombre_boton}' no existe en el menú rápido.")
        return False

    tipo   = contexto_obj.menu_rapido_tipo
    dx, dy = MENU_RAPIDO_OFFSET.get(tipo, (0, 0))
    x, y   = MENU_RAPIDO["botones"][nombre_boton]
    click_at(x + dx, y + dy)
    return True