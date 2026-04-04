# bot/screen.py

import cv2
import subprocess
import datetime
import threading
import numpy as np
import os
import time
import socket
import struct
import av

from bot.constants import DISPOSITIVO_ADB, SCRCPY_SERVER_PATH, DEFAULT_DELAY, DEBUG, RESOLUCION_BASE

# --------------------
# Stream de scrcpy
# --------------------

class ScrcpyStream:
    """
    Mantiene una conexión activa con el server de scrcpy y consume el stream
    H.264 en un thread de background. capturar_pantalla() lee el último frame
    disponible sin bloquear, sin hacer ninguna llamada de red en el momento.

    Uso:
        stream = ScrcpyStream()
        stream.iniciar()
        ...
        img = stream.ultimo_frame()   # numpy array BGR, listo para OpenCV
        ...
        stream.detener()
    """

    PUERTO          = 27183
    MAX_PTS         = 1 << 62   # filtra valores especiales de scrcpy (0xFF..., 0x80...)
    TIMEOUT_SOCKET  = 10        # segundos para la conexión inicial

    def __init__(self):
        self._proc       = None   # proceso adb shell con el server
        self._sock       = None   # socket TCP al server
        self._codec      = None   # decodificador H.264 (PyAV)
        self._frame      = None   # último frame BGR decodificado
        self._lock       = threading.Lock()
        self._thread     = None
        self._corriendo  = False

    # --------------------
    # Ciclo de vida
    # --------------------

    def iniciar(self):
        """
        Pushea el server jar, levanta el proceso adb shell, abre el socket,
        lee el metadata inicial y arranca el thread de decodificación.
        Lanza RuntimeError si algo falla.
        """
        self._pushear_server()
        self._forward_puerto()
        self._proc  = self._lanzar_server()
        time.sleep(2)
        self._sock  = self._conectar_socket()
        self._leer_metadata()
        self._codec = av.CodecContext.create("h264", "r")

        self._corriendo = True
        self._thread    = threading.Thread(target=self._loop_decodificacion, daemon=True)
        self._thread.start()

        # Esperar el primer frame antes de retornar
        self._esperar_primer_frame()
        print("[SCRCPY] Stream iniciado correctamente.")

    def detener(self):
        """Detiene el thread, cierra el socket y termina el proceso del server."""
        self._corriendo = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        if self._proc:
            self._proc.terminate()
        print("[SCRCPY] Stream detenido.")

    def reiniciar(self):
        """Detiene y vuelve a iniciar el stream. Útil ante desconexiones."""
        print("[SCRCPY] Reiniciando stream...")
        self.detener()
        time.sleep(2)
        self.iniciar()

    # --------------------
    # Acceso al frame
    # --------------------

    def ultimo_frame(self):
        """
        Retorna el último frame BGR decodificado como numpy array (H, W, 3).
        Retorna None si todavía no hay ningún frame disponible.
        """
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def esta_vivo(self):
        """Retorna True si el thread de decodificación sigue corriendo."""
        return self._corriendo and self._thread is not None and self._thread.is_alive()

    # --------------------
    # Internos: setup
    # --------------------

    def _pushear_server(self):
        r = subprocess.run(
            ["adb", "-s", DISPOSITIVO_ADB, "push",
             SCRCPY_SERVER_PATH, "/data/local/tmp/scrcpy-server.jar"],
            capture_output=True
        )
        if r.returncode != 0:
            raise RuntimeError(f"[SCRCPY] Error al pushear server jar: {r.stderr.decode()}")

    def _forward_puerto(self):
        subprocess.run(
            ["adb", "-s", DISPOSITIVO_ADB, "forward",
             f"tcp:{self.PUERTO}", "localabstract:scrcpy"],
            capture_output=True, check=True
        )

    def _lanzar_server(self):
        return subprocess.Popen(
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
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

    def _conectar_socket(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.TIMEOUT_SOCKET)
        sock.connect(("127.0.0.1", self.PUERTO))
        sock.settimeout(None)   # blocking sin timeout para el thread
        return sock

    def _leer_metadata(self):
        """Lee y descarta el bloque de metadata inicial del protocolo scrcpy."""
        self._recvall(1)    # dummy byte
        self._recvall(64)   # device name
        self._recvall(4)    # codec
        self._recvall(4)    # width
        self._recvall(4)    # height

    def _esperar_primer_frame(self, timeout=10):
        inicio = time.time()
        while time.time() - inicio < timeout:
            if self.ultimo_frame() is not None:
                return
            time.sleep(0.05)
        raise RuntimeError("[SCRCPY] Timeout esperando el primer frame.")

    # --------------------
    # Internos: decodificación
    # --------------------

    def _loop_decodificacion(self):
        """
        Thread de background: lee packets del socket, los decodifica con PyAV
        y actualiza self._frame con el resultado más reciente.
        """
        while self._corriendo:
            try:
                header = self._recvall(12)
                pts    = struct.unpack(">Q", header[0:8])[0]
                size   = struct.unpack(">I", header[8:12])[0]

                if pts >= self.MAX_PTS:
                    pts = None

                payload = self._recvall(size)
                packet  = av.Packet(payload)
                if pts is not None:
                    packet.pts = pts

                try:
                    for frame in self._codec.decode(packet):
                        img = frame.to_ndarray(format="bgr24")
                        with self._lock:
                            self._frame = img
                except Exception:
                    pass  # packet SPS/PPS u otros no-frame, ignorar

            except Exception as e:
                if self._corriendo:
                    print(f"[SCRCPY] Error en loop de decodificación: {e}")
                    self._corriendo = False

    def _recvall(self, n):
        """Recibe exactamente n bytes del socket."""
        data = b""
        while len(data) < n:
            chunk = self._sock.recv(n - len(data))
            if not chunk:
                raise RuntimeError("Socket cerrado por el server.")
            data += chunk
        return data


# --------------------
# Instancia global
# --------------------

_stream: ScrcpyStream = None

# Resolución real del dispositivo activo, detectada al iniciar el stream.
# Se usa para escalar coordenadas y templates desde RESOLUCION_BASE.
_resolucion_actual: tuple = None


# --------------------
# Escalado
# --------------------

def _escalar_region(region):
    """
    Convierte una región relativa (x1, y1, x2, y2) en coordenadas absolutas
    según la resolución actual del dispositivo.
    """
    rx1, ry1, rx2, ry2 = region
    w, h = _resolucion_actual
    return (int(rx1 * w), int(ry1 * h), int(rx2 * w), int(ry2 * h))


def _escalar_punto(punto):
    """
    Convierte un punto relativo (x, y) en coordenadas absolutas
    según la resolución actual del dispositivo.
    """
    rx, ry = punto
    w, h = _resolucion_actual
    return (int(rx * w), int(ry * h))


def _escalar_template(template_gray):
    """
    Redimensiona un template en escala de grises al ratio entre la resolución
    actual y la base. Si las resoluciones coinciden, retorna el template sin cambios.
    """
    base_w, base_h = RESOLUCION_BASE
    actual_w, actual_h = _resolucion_actual

    if (actual_w, actual_h) == (base_w, base_h):
        return template_gray

    ratio_w = actual_w / base_w
    ratio_h = actual_h / base_h
    nuevo_w = max(1, int(template_gray.shape[1] * ratio_w))
    nuevo_h = max(1, int(template_gray.shape[0] * ratio_h))

    return cv2.resize(template_gray, (nuevo_w, nuevo_h), interpolation=cv2.INTER_AREA)


# --------------------
# Conexión ADB
# --------------------

def conectar_dispositivo():
    """
    Verifica que el dispositivo esté conectado por USB e inicia el stream de scrcpy.
    Detecta la resolución real del dispositivo y la almacena en _resolucion_actual
    para escalar coordenadas y templates durante la sesión.
    Debe llamarse una vez al inicio, antes de cualquier captura o click.
    Lanza RuntimeError si el dispositivo no se encuentra o el stream no levanta.
    """
    global _stream, _resolucion_actual

    resultado = subprocess.run(
        ["adb", "devices"], capture_output=True, text=True
    )
    if DISPOSITIVO_ADB not in resultado.stdout:
        raise RuntimeError(
            f"[ADB] Dispositivo '{DISPOSITIVO_ADB}' no encontrado. ¿Está conectado por USB?"
        )
    print(f"[ADB] Dispositivo encontrado: {DISPOSITIVO_ADB}")

    # Detectar resolución real del dispositivo
    r = subprocess.run(
        ["adb", "-s", DISPOSITIVO_ADB, "shell", "wm", "size"],
        capture_output=True, text=True
    )
    # Salida esperada: "Physical size: 1224x2712"
    linea = r.stdout.strip().split(":")[-1].strip()
    w, h  = map(int, linea.split("x"))
    _resolucion_actual = (w, h)
    print(f"[ADB] Resolución detectada: {w}x{h} (base: {RESOLUCION_BASE[0]}x{RESOLUCION_BASE[1]})")

    _stream = ScrcpyStream()
    _stream.iniciar()


# --------------------
# Captura de pantalla
# --------------------

def capturar_pantalla():
    """
    Retorna el frame más reciente del stream de scrcpy.
        - DEBUG=True:  guarda el frame en screencaps/ con timestamp y retorna (ruta_png, imagen_cv2).
        - DEBUG=False: retorna (None, imagen_cv2).
    Lanza RuntimeError si el stream no está activo o no hay frame disponible.
    """
    if _stream is None or not _stream.esta_vivo():
        raise RuntimeError("[SCRCPY] El stream no está activo. Llamar conectar_dispositivo() primero.")

    imagen = _stream.ultimo_frame()
    if imagen is None:
        raise RuntimeError("[SCRCPY] No hay frame disponible todavía.")

    if DEBUG:
        carpeta = "screencaps"
        os.makedirs(carpeta, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        ruta_png  = os.path.join(carpeta, f"screencap_{timestamp}.png")
        cv2.imwrite(ruta_png, imagen)
        return ruta_png, imagen

    return None, imagen


# --------------------
# Reconocimiento de imágenes
# --------------------

def find_image_on_screen(screenshot_img, template_path, region=None, threshold=0.8):
    """
    Busca una imagen template dentro de una captura ya cargada.
    Retorna (center_x, center_y) del mejor match en coordenadas absolutas, o None.

    Parámetros:
        screenshot_img: imagen OpenCV (BGR) de la pantalla completa.
        template_path:  ruta al archivo de imagen template.
        region:         (x1, y1, x2, y2) en coordenadas RELATIVAS (0.0-1.0).
                        Si es None, busca en toda la pantalla.
        threshold:      nivel mínimo de confianza (0.0-1.0).
    """
    template = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if template is None:
        raise FileNotFoundError(f"No se encontró la imagen template en: {template_path}")

    screenshot_gray = cv2.cvtColor(screenshot_img, cv2.COLOR_BGR2GRAY)
    template_gray   = _escalar_template(cv2.cvtColor(template, cv2.COLOR_BGR2GRAY))

    if region is not None:
        x1, y1, x2, y2 = _escalar_region(region)
        x1 = max(0, x1); y1 = max(0, y1)
        x2 = min(screenshot_gray.shape[1], x2)
        y2 = min(screenshot_gray.shape[0], y2)

        recorte = screenshot_gray[y1:y2, x1:x2]

        if recorte.shape[0] == 0 or recorte.shape[1] == 0:
            if DEBUG:
                print(f"[DEBUG] Región inválida o fuera de pantalla: {region}")
            return None

        if DEBUG:
            cv2.imwrite("debug_recorte.png", recorte)
            cv2.imshow("Region de Interes", recorte)
            cv2.waitKey(0)

        res = cv2.matchTemplate(recorte, template_gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        if DEBUG:
            print(f"[DEBUG] Match en región {region}: {max_val:.2f} (umbral: {threshold:.2f})")
            if max_val >= threshold:
                h_t, w_t     = template_gray.shape
                top_left     = (max_loc[0] + x1, max_loc[1] + y1)
                bottom_right = (top_left[0] + w_t, top_left[1] + h_t)
                debug_img    = cv2.cvtColor(screenshot_gray, cv2.COLOR_GRAY2BGR)
                cv2.rectangle(debug_img, top_left, bottom_right, (0, 255, 0), 2)
                cv2.imshow("Match encontrado", debug_img)
                cv2.waitKey(0)

        if max_val >= threshold:
            h_t, w_t = template_gray.shape
            center_x = max_loc[0] + x1 + w_t // 2
            center_y = max_loc[1] + y1 + h_t // 2
            return (center_x, center_y)

    else:
        res = cv2.matchTemplate(screenshot_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        if DEBUG:
            print(f"[DEBUG] Match en pantalla completa: {max_val:.2f} (umbral: {threshold:.2f})")
            if max_val >= threshold:
                h_t, w_t     = template_gray.shape
                bottom_right = (max_loc[0] + w_t, max_loc[1] + h_t)
                debug_img    = cv2.cvtColor(screenshot_gray, cv2.COLOR_GRAY2BGR)
                cv2.rectangle(debug_img, max_loc, bottom_right, (0, 255, 0), 2)
                cv2.imshow("Match encontrado (pantalla completa)", debug_img)
                cv2.waitKey(0)

        if max_val >= threshold:
            h_t, w_t = template_gray.shape
            center_x = max_loc[0] + w_t // 2
            center_y = max_loc[1] + h_t // 2
            return (center_x, center_y)

    return None


def find_all_on_screen(screenshot_img, template_path, region=None, threshold=0.8):
    """
    Busca todas las ocurrencias de un template dentro de una captura ya cargada.
    Usa supresión de no-máximos para evitar duplicados en zonas solapadas.
    Retorna lista de (center_x, center_y) en coordenadas absolutas, ordenada
    por Y ascendente. Lista vacía si no hay matches.

    Parámetros:
        screenshot_img: imagen OpenCV (BGR) de la pantalla completa.
        template_path:  ruta al archivo de imagen template.
        region:         (x1, y1, x2, y2) en coordenadas RELATIVAS (0.0-1.0).
                        Si es None, busca en toda la pantalla.
        threshold:      nivel mínimo de confianza (0.0-1.0).
    """
    template = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if template is None:
        raise FileNotFoundError(f"No se encontró la imagen template en: {template_path}")

    screenshot_gray = cv2.cvtColor(screenshot_img, cv2.COLOR_BGR2GRAY)
    template_gray   = _escalar_template(cv2.cvtColor(template, cv2.COLOR_BGR2GRAY))
    h_t, w_t        = template_gray.shape

    if region is not None:
        x1, y1, x2, y2 = _escalar_region(region)
        x1 = max(0, x1); y1 = max(0, y1)
        x2 = min(screenshot_gray.shape[1], x2)
        y2 = min(screenshot_gray.shape[0], y2)
        recorte  = screenshot_gray[y1:y2, x1:x2]
        offset_x = x1
        offset_y = y1
    else:
        recorte  = screenshot_gray
        offset_x = 0
        offset_y = 0

    if recorte.shape[0] == 0 or recorte.shape[1] == 0:
        return []

    res       = cv2.matchTemplate(recorte, template_gray, cv2.TM_CCOEFF_NORMED)
    locations = np.where(res >= threshold)
    puntos    = list(zip(locations[1], locations[0]))

    if not puntos:
        return []

    puntos_filtrados = []
    usado            = [False] * len(puntos)

    for i, (px, py) in enumerate(puntos):
        if usado[i]:
            continue
        mejor_score = res[py, px]
        mejor_idx   = i
        for j, (qx, qy) in enumerate(puntos):
            if usado[j] or j == i:
                continue
            if abs(qx - px) < w_t and abs(qy - py) < h_t:
                if res[qy, qx] > mejor_score:
                    mejor_score = res[qy, qx]
                    mejor_idx   = j
                usado[j] = True
        usado[mejor_idx] = True
        bx, by = puntos[mejor_idx]
        puntos_filtrados.append((
            bx + offset_x + w_t // 2,
            by + offset_y + h_t // 2
        ))

    puntos_filtrados.sort(key=lambda p: p[1])

    if DEBUG:
        print(f"[DEBUG] find_all_on_screen: {len(puntos_filtrados)} matches en '{template_path}'")

    return puntos_filtrados


# --------------------
# Clicks
# --------------------

def click_at(x, y, delay=DEFAULT_DELAY):
    """
    Hace tap en (x, y) del dispositivo vía ADB.
    Acepta coordenadas relativas (float 0.0-1.0) o absolutas (int).
    Las relativas se escalan automáticamente a la resolución actual.
    """
    time.sleep(delay)
    if isinstance(x, float) or isinstance(y, float):
        x, y = _escalar_punto((x, y))
    subprocess.run(
        ["adb", "-s", DISPOSITIVO_ADB, "shell", "input", "tap", str(x), str(y)],
        capture_output=True
    )


def click_if_found(template_path, region=None, clicks=1, delay=DEFAULT_DELAY, threshold=0.8):
    """
    Captura pantalla, busca el template, y si lo encuentra hace click en el centro.
    Retorna True si encontró y clickeó, False si no.
    """
    _, screenshot_img = capturar_pantalla()
    match = find_image_on_screen(screenshot_img, template_path, region=region, threshold=threshold)
    if match:
        x, y = match
        for _ in range(clicks):
            click_at(x, y, delay=delay)
        return True
    return False


def is_image_on_screen(template_path, region=None, threshold=0.8):
    """
    Retorna True si el template aparece en pantalla, False si no.
    """
    _, screenshot_img = capturar_pantalla()
    return find_image_on_screen(screenshot_img, template_path, region=region, threshold=threshold) is not None


# --------------------
# Swipe
# --------------------

def swipe_from_to(x1, y1, x2, y2, duration_ms=300, delay=DEFAULT_DELAY):
    """
    Ejecuta un gesto de swipe vía ADB desde (x1, y1) hasta (x2, y2).
    Acepta coordenadas relativas (float 0.0-1.0) o absolutas (int).
    duration_ms controla la velocidad del swipe.
    """
    time.sleep(delay)
    if isinstance(x1, float) or isinstance(y1, float):
        x1, y1 = _escalar_punto((x1, y1))
    if isinstance(x2, float) or isinstance(y2, float):
        x2, y2 = _escalar_punto((x2, y2))
    subprocess.run(
        ["adb", "-s", DISPOSITIVO_ADB, "shell",
         "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms)],
        capture_output=True
    )