# Arquitectura - Kritika FarmBot

## Visión general

El bot está dividido en capas bien definidas para mantenerlo mantenible a medida que crece.

### Capas principales (de abajo hacia arriba)

| Capa              | Archivo                | Responsabilidad |
|-------------------|------------------------|---------------|
| **Constants**     | `bot/constants.py`     | Fuente única de verdad. Contextos, botones, regiones relativas, prioridades y outcomes. |
| **Screen**        | `bot/screen.py`        | Captura de pantalla (scrcpy), template matching con OpenCV y detección básica. |
| **Context**       | `bot/context.py`       | Detecta el contexto actual del juego, subcontextos y maneja prioridades de popups. |
| **Actions**       | `bot/actions.py`       | Acciones atómicas (click en botones, clicks en menú, etc.). |
| **Flows**         | `bot/flows.py`         | Flujos de alto nivel y procesos específicos dentro de contextos. |
| **Ads**           | `bot/ads-manager.py`   | Manejo independiente de anuncios usando uiautomator2. |
| **Main**          | `main.py`              | Orquestación general y loop principal. |

## Principios clave

- **Coordenadas relativas** (0.0 - 1.0) en todo el proyecto.
- **Prioridad de contextos**: Los contextos se evalúan de mayor a menor prioridad para manejar popups inesperados.
- **Clase Boton**: Cada botón tiene `coords`, `outcomes` y `timeout`.
- **Separación clara**: `ads-manager.py` está aislado porque usa una tecnología diferente (uiautomator2).
- El bot debe ser **idempotente** y resistente a interrupciones.

## Decisiones técnicas importantes

- Uso de scrcpy en vez de ADB screenshots → latencia mucho más baja (~4ms).
- Template matching en vez de OCR pesado (por velocidad y precisión en UI del juego).
- `constants.py` es sagrado: cualquier cambio de UI debe actualizarse ahí primero.

## Cómo extender el bot (recordatorio interno)

1. Agregar nuevo contexto → `constants.py`
2. Capturar assets necesarios → carpeta `assets/ui/`
3. Actualizar detección en `context.py` si es necesario
4. Agregar acciones o flows según corresponda

---
Última actualización: 2026-04-05