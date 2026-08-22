# FULL PROJECT CONTEXT - Kritika FarmBot (Para IAs)

**Proyecto:** Bot de automatización para Kritika: The White Knights (Android físico vía USB)
**Versión actual:** 0.1.2
**Última actualización:** 2026-04-05

## Objetivo principal
Automatizar farming, progresión y actividades repetitivas del juego de forma robusta, manejando popups, contextos dinámicos y prioridades correctamente.

## Stack principal
- **Captura y visión**: scrcpy (streaming H.264 de baja latencia) + OpenCV (template matching) + numpy
- **Interacción**: ADB + coordenadas relativas
- **Anuncios**: Módulo independiente `bot/ads-manager.py` usando **uiautomator2**
- **Lenguaje**: Python 3.10+

## Estructura clave del bot
- `bot/constants.py` → **Fuente única de verdad** (contextos, botones, regiones relativas, prioridades y outcomes)
- `bot/screen.py` → Captura de pantalla, template matching y manejo de input
- `bot/context.py` → Detección inteligente de contexto actual + manejo de prioridades de popups
- `bot/actions.py` → Acciones atómicas (clicks, swipes, etc.)
- `bot/flows.py` → Flujos de alto nivel
- `bot/ads-manager.py` → Manejo separado de anuncios (no debe mezclarse con el flujo principal)

## Reglas importantes (respetar siempre)
- Todas las coordenadas deben ser **relativas** (0.0 - 1.0)
- `constants.py` es sagrado: cualquier cambio de UI del juego debe actualizarse primero ahí
- Cada `Boton` debe tener `coords`, `outcomes` y preferentemente `prioridad`
- Los contextos se evalúan en orden de **prioridad descendente** para manejar popups correctamente
- Outcomes posibles: `"ok"`, `"retry"`, `"abort"`
- El bot debe ser resistente a popups inesperados y recuperarse gracefully
- Mantener clara la separación entre el flujo principal (scrcpy + OpenCV) y `ads-manager.py` (uiautomator2)

## Reglas para realizar cambios (Obligatorias para la IA)

Cuando propongas o realices cambios en el código:

1. **Siempre** listar claramente todos los archivos que se modifican, crean o eliminan.
2. **Para cambios medianos o grandes**:
   - Incluir una entrada clara y detallada en `CHANGELOG.md` (bajo la sección correspondiente, con fecha y versión).
   - Si el cambio afecta la arquitectura, flujos, prioridades o estructura general → actualizar también `ARCHITECTURE.md` y/o `PROJECT-CONTEXT.md` si es necesario.
3. **Para cambios estructurales o importantes** (nuevos módulos, refactor grande, cambio en cómo funcionan los contextos, etc.):
   - Documentar en `ARCHITECTURE.md`
   - Actualizar `PROJECT-CONTEXT.md` (sección de estructura o reglas)
   - Actualizar este `full-project-context.md` si corresponde
4. **Para cambios pequeños** (fixes, mejoras menores):
   - Al menos agregar una entrada breve en `CHANGELOG.md`
5. Al final de cada respuesta importante, incluir una sección **"Resumen de cambios propuestos"** con:
   - Archivos modificados/creados
   - Entrada sugerida para CHANGELOG.md
   - Archivos de documentación que también deben actualizarse (si aplica)

## ROADMAP actual (Prioridades)

**Prioridad Alta (próximas 1-2 semanas):**
- Terminar de capturar **todos** los assets faltantes
- Completar y pulir `constants.py`
- Integrar completamente la lógica de prioridad + clase `Boton` en toda la estructura de `constants.py`

**Prioridad Media:**
- Crear **procesos específicos** (specific_process / subflow) que se ejecutan asumiendo que ya estamos en un contexto garantizado
- Implementar lector de números y texto en pantalla (stamina, oro, etc.)

**Prioridad Baja:**
- Sistema de logging de recursos por personaje (generar .csv con stamina, oro, items clave, etc.)

## Instrucciones para IA (importante)
1. **Siempre** lee primero este archivo completo antes de responder.
2. Respeta estrictamente la separación de responsabilidades y que `constants.py` es la fuente de verdad.
3. Sigue el orden del roadmap. No saltes a prioridades medias si la alta no está completa.
4. Prefiere soluciones basadas en template matching + coordenadas relativas.
5. Cuando propongas código, sé claro con qué archivos hay que modificar y por qué.
6. `ads-manager.py` es independiente → no lo mezcles con el flujo principal salvo que sea estrictamente necesario.

**Estado actual:** Constants.py y assets todavía incompletos → **Prioridad máxima**.