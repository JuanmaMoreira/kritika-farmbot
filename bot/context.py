# bot/context.py

from bot.screen import find_image_on_screen, capturar_pantalla
from bot.constants import CONTEXTOS_DEFINIDOS

# --------------------
# Estado global
# --------------------

contexto_actual    = None   # ej: "lobby", "stage_normal"
subcontexto_actual = None   # ej: "ep-14"  — None si el contexto no tiene subcontexto
menu_abierto       = None   # ej: "world-map"  — None si no hay menú abierto


class Contexto:
    """
    Representa un estado reconocible del juego (ej: lobby, stage, selección de personaje).
    Se construye a partir de los datos definidos en CONTEXTOS_DEFINIDOS (constants.py).

    Atributos:
        nombre                  identificador del contexto (coincide con la clave del dict)
        imagen                  ruta al template usado para detectarlo
        region                  (x1, y1, x2, y2) zona de la pantalla donde buscar el template
        threshold               confianza mínima para considerar el contexto detectado
        menu_rapido_disponible  si el menú rápido está activo en este contexto
        menu_rapido_tipo        clave en MENU_RAPIDO_OFFSET que aplica a este contexto
        botones                 coordenadas (x, y) de botones siempre disponibles en este contexto
        menus                   menús desplegables transitorios con sus botones
        subcontexto             variantes persistentes del contexto (tipo + valores)
    """
    def __init__(self, nombre, imagen, region, threshold=0.9,
                 menu_rapido_disponible=False, menu_rapido_tipo=None,
                 botones=None, menus=None, subcontexto=None):
        self.nombre                 = nombre
        self.imagen                 = imagen
        self.region                 = region
        self.threshold              = threshold
        self.menu_rapido_disponible = menu_rapido_disponible
        self.menu_rapido_tipo       = menu_rapido_tipo
        self.botones                = botones  or {}
        self.menus                  = menus    or {}
        self.subcontexto            = subcontexto  # None o {"tipo": str, "valores": dict}


# Construir los objetos Contexto a partir de los datos en constants.py
contextos_definidos = {
    nombre: Contexto(nombre=nombre, **datos)
    for nombre, datos in CONTEXTOS_DEFINIDOS.items()
}


# --------------------
# Detección
# --------------------

def detectar_contexto():
    """
    Toma una captura y la compara contra todos los contextos definidos.
    Retorna (nombre, screenshot_img) del primer contexto que coincida,
    o (None, screenshot_img) si no hay match.
    """
    _, screenshot_img = capturar_pantalla()

    for contexto_obj in contextos_definidos.values():
        match = find_image_on_screen(
            screenshot_img=screenshot_img,
            template_path=contexto_obj.imagen,
            region=contexto_obj.region,
            threshold=contexto_obj.threshold
        )
        if match:
            return contexto_obj.nombre, screenshot_img

    return None, screenshot_img


def detectar_subcontexto(contexto_obj, screenshot_img):
    """
    Dado un contexto que tiene subcontexto definido, detecta cuál variante está activa.
    Retorna el nombre del valor detectado, o None si no matchea ninguno o no hay subcontexto.
    """
    if not contexto_obj.subcontexto:
        return None

    for nombre_valor, datos in contexto_obj.subcontexto["valores"].items():
        match = find_image_on_screen(
            screenshot_img=screenshot_img,
            template_path=datos["imagen"],
            region=datos["region"],
            threshold=datos.get("threshold", contexto_obj.threshold)
        )
        if match:
            return nombre_valor

    return None


def actualizar_contexto():
    """
    Detecta el contexto activo y, si tiene subcontexto definido, también lo detecta.
    Actualiza las variables globales contexto_actual y subcontexto_actual.
    Resetea menu_abierto (un nuevo screencap implica que no sabemos el estado del menú).
    Retorna (contexto_actual, subcontexto_actual).
    """
    global contexto_actual, subcontexto_actual, menu_abierto

    nombre, screenshot_img = detectar_contexto()
    contexto_actual = nombre
    menu_abierto    = None  # al re-detectar contexto, reseteamos el estado del menú

    if contexto_actual is None:
        subcontexto_actual = None
        return contexto_actual, subcontexto_actual

    contexto_obj = contextos_definidos[contexto_actual]
    subcontexto_actual = detectar_subcontexto(contexto_obj, screenshot_img)

    return contexto_actual, subcontexto_actual


# --------------------
# Estado de menú
# --------------------

def registrar_menu_abierto(nombre_menu):
    """Registra que un menú desplegable fue abierto. Lo llama actions.py al abrir un menú."""
    global menu_abierto
    menu_abierto = nombre_menu


def registrar_menu_cerrado():
    """Registra que el menú desplegable fue cerrado."""
    global menu_abierto
    menu_abierto = None


# --------------------
# Consultas
# --------------------

def obtener_contexto():
    return contexto_actual

def obtener_subcontexto():
    return subcontexto_actual

def obtener_menu_abierto():
    return menu_abierto

def es_lobby():
    return contexto_actual == "lobby"

def es_seleccion_de_personaje():
    return contexto_actual == "seleccion_de_personaje"

def menu_rapido_disponible():
    """Retorna True si el contexto actual tiene el menú rápido disponible."""
    contexto_obj = contextos_definidos.get(contexto_actual)
    if contexto_obj is None:
        return False
    return contexto_obj.menu_rapido_disponible

def hay_menu_abierto():
    """Retorna True si hay un menú desplegable abierto actualmente."""
    return menu_abierto is not None