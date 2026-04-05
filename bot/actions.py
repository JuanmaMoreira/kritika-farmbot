# bot/actions.py

import time

from bot.screen import click_at
from bot.constants import MENU_RAPIDO, MENU_RAPIDO_OFFSET
import bot.context as context
from bot.context import actualizar_contexto, Boton


# --------------------
# Outcome
# --------------------

# Valores posibles de Boton.outcomes:
#   "ok"    → resultado esperado, continuar flow
#   "retry" → sigo en origen, reintentar click
#   "abort" → contexto inesperado, abortar flow


def _esperar_outcome(boton: Boton, contexto_origen: str):
    """
    Espera hasta que el estado del juego cambie a alguno de los outcomes
    definidos en el botón. Evalúa contexto, subcontexto y menú abierto.

    Retorna el valor del outcome matcheado ("ok", "retry", "abort"),
    o None si venció el timeout sin match.
    """
    inicio = time.time()

    while time.time() - inicio < boton.timeout:
        actualizar_contexto()

        # Evaluar contexto activo
        if context.contexto_actual in boton.outcomes:
            return boton.outcomes[context.contexto_actual]

        # Evaluar subcontexto activo
        if context.subcontexto_actual in boton.outcomes:
            return boton.outcomes[context.subcontexto_actual]

        # Evaluar menú abierto
        if context.menu_abierto in boton.outcomes:
            return boton.outcomes[context.menu_abierto]

        time.sleep(0.3)

    print(f"[WARN] _esperar_outcome: timeout en botón '{boton.nombre}' "
          f"(contexto: '{context.contexto_actual}', "
          f"sub: '{context.subcontexto_actual}', "
          f"menú: '{context.menu_abierto}')")
    return None


# --------------------
# Botones de contexto
# --------------------

def click_boton(nombre, max_intentos=3):
    """
    Clickea un botón del contexto activo y espera su outcome.

    Prioridad de búsqueda:
        1. Botones del subcontexto activo
        2. Botones del contexto activo

    Comportamiento según outcome:
        "ok"    → retorna True
        "retry" → reintenta hasta max_intentos, luego retorna False
        "abort" → retorna False inmediatamente
        None    → timeout, retorna False

    Si el botón no tiene outcomes definidos, solo clickea y retorna True.
    """
    if context.contexto_actual is None:
        print("[ERROR] click_boton: no hay contexto activo.")
        return False

    contexto_obj = context.contextos_definidos[context.contexto_actual]
    boton = None

    # Buscar en subcontexto activo primero
    if context.subcontexto_actual and contexto_obj.subcontexto:
        datos_sub = contexto_obj.subcontexto["valores"].get(context.subcontexto_actual, {})
        botones_sub = datos_sub.get("botones", {})
        if nombre in botones_sub:
            coords = botones_sub[nombre]
            boton  = Boton(nombre=nombre, coords=coords)

    # Buscar en contexto
    if boton is None:
        if nombre in contexto_obj.botones:
            boton = contexto_obj.botones[nombre]

    if boton is None:
        print(f"[ERROR] click_boton: botón '{nombre}' no encontrado "
              f"en contexto '{context.contexto_actual}'.")
        return False

    # Si no tiene outcomes, solo clickear
    if not boton.outcomes:
        click_at(*boton.coords)
        return True

    contexto_origen = context.contexto_actual

    for intento in range(max_intentos):
        click_at(*boton.coords)
        outcome = _esperar_outcome(boton, contexto_origen)

        if outcome == "ok":
            return True

        if outcome == "abort":
            print(f"[ERROR] click_boton: outcome 'abort' en botón '{nombre}'. "
                  f"Contexto inesperado: '{context.contexto_actual}'.")
            return False

        if outcome == "retry":
            print(f"[WARN] click_boton: intento {intento + 1}/{max_intentos} "
                  f"— reintentando '{nombre}'...")
            continue

        # timeout
        print(f"[ERROR] click_boton: timeout esperando outcome de '{nombre}' "
              f"tras {intento + 1} intento(s).")
        return False

    print(f"[ERROR] click_boton: '{nombre}' agotó {max_intentos} intentos.")
    return False


# --------------------
# Botones de menú
# --------------------

def click_boton_menu(nombre_menu, nombre_boton):
    """
    Clickea un botón dentro de un menú desplegable del contexto activo.
    Los botones de menú no tienen outcomes — el flow maneja lo que sigue.
    Retorna True si encontró y clickeó, False si no.
    """
    if context.contexto_actual is None:
        print("[ERROR] click_boton_menu: no hay contexto activo.")
        return False

    contexto_obj = context.contextos_definidos[context.contexto_actual]

    if nombre_menu not in contexto_obj.menus:
        print(f"[ERROR] click_boton_menu: menú '{nombre_menu}' no existe "
              f"en contexto '{context.contexto_actual}'.")
        return False

    botones_menu = contexto_obj.menus[nombre_menu].get("botones", {})

    if nombre_boton not in botones_menu:
        print(f"[ERROR] click_boton_menu: botón '{nombre_boton}' no existe "
              f"en menú '{nombre_menu}'.")
        return False

    coords = botones_menu[nombre_boton]
    click_at(*coords)
    return True


# --------------------
# Menú rápido
# --------------------

def click_boton_menu_rapido(nombre_boton):
    """
    Clickea un botón del menú rápido aplicando el offset del contexto activo.
    Retorna True si encontró y clickeó, False si no.
    """
    if context.contexto_actual is None:
        print("[ERROR] click_boton_menu_rapido: no hay contexto activo.")
        return False

    contexto_obj = context.contextos_definidos[context.contexto_actual]

    if not contexto_obj.menu_rapido_disponible:
        print(f"[ERROR] click_boton_menu_rapido: menú rápido no disponible "
              f"en '{context.contexto_actual}'.")
        return False

    if nombre_boton not in MENU_RAPIDO["botones"]:
        print(f"[ERROR] click_boton_menu_rapido: botón '{nombre_boton}' "
              f"no existe en el menú rápido.")
        return False

    tipo   = contexto_obj.menu_rapido_tipo
    offset = MENU_RAPIDO_OFFSET.get(tipo, (0, 0))
    coords = MENU_RAPIDO["botones"][nombre_boton]

    # Aplicar offset (relativo también)
    x = coords[0] + offset[0]
    y = coords[1] + offset[1]
    click_at(x, y)
    return True