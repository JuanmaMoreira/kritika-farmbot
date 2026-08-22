# CONTEXT - Kritika FarmBot

Bot de automatización para Kritika: The White Knights en Android físico (USB) usando scrcpy + OpenCV.

**Objetivo:** Automatizar farming y actividades repetitivas manejando popups y contextos dinámicos de forma robusta.

**Stack clave:**
- scrcpy (baja latencia) + OpenCV template matching
- Coordenadas siempre relativas (0.0-1.0)
- `bot/constants.py` es la **única fuente de verdad**

**Reglas obligatorias:**
- constants.py es sagrado
- Contextos se evalúan por prioridad (mayor primero)
- Outcomes: "ok", "retry", "abort"
- Separar claramente flujo principal (scrcpy/OpenCV) de `bot/ads-manager.py` (uiautomator2)
- Seguir estrictamente el ROADMAP (prioridad alta primero)

**Archivos importantes:**
- PROJECT-CONTEXT.md → contexto completo
- ROADMAP.md → prioridades actuales
- ARCHITECTURE.md → diseño de capas
- bot/constants.py → fuente de verdad

**Reglas para cambios:**
- Siempre listar archivos modificados
- Agregar entrada en CHANGELOG.md en cambios medianos/grandes
- Documentar cambios estructurales en ARCHITECTURE.md y PROJECT-CONTEXT.md

**Estado actual (Abril 2026):** Constants.py y assets incompletos → Prioridad máxima.