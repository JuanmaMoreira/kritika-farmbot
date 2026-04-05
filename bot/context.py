# bot/context.py

from bot.screen import find_image_on_screen, capturar_pantalla
from bot.constants import CONTEXTOS_DEFINIDOS, MENU_RAPIDO

# --------------------
# Estado global
# --------------------

contexto_actual    = None   # ej: "lobby", "stage_normal"
subcontexto_actual = None   # ej: "ep-14"  — None si el contexto no tiene subcontexto
menu_abierto       = None   # ej: "world-map"  — None si no hay menú abierto


# --------------------
# Clases de modelo
# --------------------

class Boton:
    """
    Representa un botón interactuable dentro de un contexto o menú.

    Atributos:
        nombre      identificador del botón
        coords      (x, y) en coordenadas relativas (0.0-1.0)
        outcomes    dict de posibles resultados tras clickearlo.
                    Claves: nombre de contexto, menú o subcontexto resultante.
                    Valores: "ok" | "retry" | "abort"
                        "ok"    → resultado esperado, continuar flow
                        "retry" → sigo en origen, reintentar click
                        "abort" → contexto inesperado, abortar flow
        timeout     segundos máximos esperando un outcome antes de escalar
    """
    def __init__(self, nombre, coords, outcomes=None, timeout=5):
        self.nombre   = nombre
        self.coords   = coords
        self.outcomes = outcomes or {}
        self.timeout  = timeout


class Contexto:
    """
    Representa un estado reconocible del juego (ej: lobby, stage, selección de personaje).
    Se construye a partir de los datos definidos en CONTEXTOS_DEFINIDOS (constants.py).

    Atributos:
        nombre                  identificador del contexto
        imagen                  ruta al template usado para detectarlo
        region                  (x1, y1, x2, y2) en coordenadas relativas (0.0-1.0)
        threshold               confianza mínima para considerar el contexto detectado
        prioridad               entero >= 1. Mayor prioridad gana cuando varios contextos
                                matchean al mismo tiempo (ej: popup sobre lobby).
                                Default 1. Modificar manualmente en constants.py.
        menu_rapido_disponible  si el menú rápido está activo en este contexto
        menu_rapido_tipo        clave en MENU_RAPIDO_OFFSET que aplica a este contexto
        botones                 dict[str, Boton] — botones disponibles en este contexto
        menus                   menús desplegables transitorios con sus botones
        subcontexto             variantes persistentes del contexto (tipo + valores)
    """
    def __init__(self, nombre, imagen, region, threshold=0.9, prioridad=1,
                 menu_rapido_disponible=False, menu_rapido_tipo=None,
                 botones=None, menus=None, subcontexto=None):
        self.nombre                 = nombre
        self.imagen                 = imagen
        self.region                 = region
        self.threshold              = threshold
        self.prioridad              = prioridad
        self.menu_rapido_disponible = menu_rapido_disponible
        self.menu_rapido_tipo       = menu_rapido_tipo
        self.menus                  = menus     or {}
        self.subcontexto            = subcontexto

        # Construir objetos Boton desde el dict plano de constants.py
        botones_raw = botones or {}
        self.botones: dict[str, Boton] = {}
        for nombre_boton, datos in botones_raw.items():
            if isinstance(datos, dict):
                self.botones[nombre_boton] = Boton(
                    nombre   = nombre_boton,
                    coords   = datos["coords"],
                    outcomes = datos.get("outcomes", {}),
                    timeout  = datos.get("timeout", 5),
                )
            else:
                # Compatibilidad: tupla simple (x, y) sin outcomes definidos
                self.botones[nombre_boton] = Boton(
                    nombre = nombre_boton,
                    coords = datos,
                )


# Construir los objetos Contexto a partir de los datos en constants.py,
# ordenados por prioridad descendente para que detectar_contexto()
# evalúe primero los de mayor prioridad.
contextos_definidos: dict[str, Contexto] = {
    nombre: Contexto(nombre=nombre, **datos)
    for nombre, datos in CONTEXTOS_DEFINIDOS.items()
}

_contextos_por_prioridad: list[Contexto] = sorted(
    contextos_definidos.values(),
    key=lambda c: c.prioridad,
    reverse=True
)


# --------------------
# Detección
# --------------------

def detectar_contexto():
    """
    Toma una captura y la compara contra todos los contextos definidos,
    evaluándolos en orden de prioridad descendente.
    Retorna (nombre, screenshot_img) del primer contexto que coincida,
    o (None, screenshot_img) si no hay match.
    """
    _, screenshot_img = capturar_pantalla()

    for contexto_obj in _contextos_por_prioridad:
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
        if not datos.get("imagen"):
            continue
        match = find_image_on_screen(
            screenshot_img=screenshot_img,
            template_path=datos["imagen"],
            region=datos["region"],
            threshold=datos.get("threshold", contexto_obj.threshold)
        )
        if match:
            return nombre_valor

    return None


def detectar_menu_abierto(contexto_obj, screenshot_img):
    """
    Comprueba si alguno de los menús del contexto activo está abierto.
    Retorna el nombre del menú detectado, o None si ninguno está abierto.
    """
    for nombre_menu, datos_menu in contexto_obj.menus.items():
        if not datos_menu.get("imagen"):
            continue
        match = find_image_on_screen(
            screenshot_img=screenshot_img,
            template_path=datos_menu["imagen"],
            region=datos_menu["region"],
            threshold=datos_menu.get("threshold", contexto_obj.threshold)
        )
        if match:
            return nombre_menu
    return None


def actualizar_contexto():
    """
    Detecta el contexto activo en orden de prioridad y, si tiene subcontexto
    o menús definidos, también los detecta reutilizando la misma captura.
    Actualiza las variables globales contexto_actual, subcontexto_actual y menu_abierto.
    Retorna (contexto_actual, subcontexto_actual).
    """
    global contexto_actual, subcontexto_actual, menu_abierto

    nombre, screenshot_img = detectar_contexto()
    contexto_actual = nombre
    menu_abierto    = None

    if contexto_actual is None:
        subcontexto_actual = None
        return contexto_actual, subcontexto_actual

    contexto_obj       = contextos_definidos[contexto_actual]
    subcontexto_actual = detectar_subcontexto(contexto_obj, screenshot_img)
    menu_abierto       = detectar_menu_abierto(contexto_obj, screenshot_img)

    return contexto_actual, subcontexto_actual


# --------------------
# Estado de menú
# --------------------

def registrar_menu_abierto(nombre_menu):
    global menu_abierto
    menu_abierto = nombre_menu

def registrar_menu_cerrado():
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
    return contexto_actual == "select-character"

def menu_rapido_disponible():
    contexto_obj = contextos_definidos.get(contexto_actual)
    if contexto_obj is None:
        return False
    return contexto_obj.menu_rapido_disponible

def hay_menu_abierto():
    return menu_abierto is not None