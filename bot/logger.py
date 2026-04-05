# bot/logger.py
#
# Este módulo reemplaza los print() del proyecto por un sistema de logging.
#
# ¿Por qué usar logging en lugar de print()?
#
#   print("error!")         → aparece en consola, nada más. No sabés cuándo pasó,
#                             no podés filtrarlo, no se guarda en ningún lado.
#
#   logger.error("error!")  → aparece en consola CON timestamp y nivel,
#                             Y se guarda automáticamente en un archivo .log.
#
# Niveles disponibles (de menor a mayor gravedad):
#
#   logger.debug("...")    → detalles internos, solo útil mientras desarrollás
#   logger.info("...")     → eventos normales ("contexto detectado: lobby")
#   logger.warning("...")  → algo raro pero no crítico
#   logger.error("...")    → algo falló pero el bot puede seguir
#   logger.critical("...") → fallo grave, el bot no puede continuar
#
# Podés controlar qué nivel mínimo se muestra/guarda cambiando LOG_LEVEL abajo.
# Por ejemplo: durante desarrollo usás DEBUG para ver todo.
#              En producción subís a INFO para no llenar el log de ruido.

import logging
import os
from datetime import datetime

# ─── Configuración ────────────────────────────────────────────────────────────

LOG_LEVEL = logging.DEBUG          # Cambiá a logging.INFO en producción
LOG_DIR = "logs"
LOG_FILENAME = f"farmbot_{datetime.now().strftime('%Y%m%d')}.log"

# ─── Setup interno ────────────────────────────────────────────────────────────

os.makedirs(LOG_DIR, exist_ok=True)

# Formato: 2026-03-28 15:42:01 | ERROR    | context.py | No se detectó contexto
_formatter = logging.Formatter(
    fmt="%(asctime)s | %(levelname)-8s | %(module)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Handler 1: muestra los logs en la consola
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_formatter)

# Handler 2: guarda los logs en archivo (un archivo por día)
_file_handler = logging.FileHandler(
    os.path.join(LOG_DIR, LOG_FILENAME),
    encoding="utf-8"
)
_file_handler.setFormatter(_formatter)

# El logger principal del proyecto
logger = logging.getLogger("farmbot")
logger.setLevel(LOG_LEVEL)
logger.addHandler(_console_handler)
logger.addHandler(_file_handler)

# Evita que los mensajes se dupliquen si el módulo se importa varias veces
logger.propagate = False
