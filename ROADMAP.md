# Pendientes

Estado real en [CONTEXT](CONTEXT.md); UI física en [GAMEPLAY_GT](docs/GAMEPLAY_GT.md); routing único en [RESOURCE_ROUTING](docs/RESOURCE_ROUTING.md).

## Monster Wave — etapa cerrada 2026-10-02

**Estable para esta versión.** Smoke final `mw_final_native_d1e5d83e`: COMPLETED, tres CLEAR, 253/253 Sapphires, Lobby, sin flow.failed. WB→MW, Keys/Gold, Materials/Craft, Socket, Point Reward y Equipment Combine-first/Bulk tail-first/retorno al mismo pass cuentan con evidencia live. Checkpoint local único autorizado; sin push. El loop autónomo live terminó; no quedan bugs productivos conocidos pendientes dentro del alcance aceptado.

## Deuda posterior aceptada

1. Expansión Equipment +4 positiva live sólo ante necesidad real: mecánica adquirida y tests verdes; no provocar compras preventivas para validación.
2. Poor/Normal visual positivo y Ethereal Enhance positivo cuando sean necesarios. Policy conocida, evidencia insuficiente falla cerrado.
3. Perfilar el scan Sell protegido antes de optimizarlo. Implementación correcta y bounded; descartar scan/index tras cada Bulk/expansión sigue obligatorio.
4. Lifecycle de SKIP tras pausas de diagnóstico muy largas.
5. Portabilidad/publicación del corpus nativo local.
6. Fill All con Gold insuficiente UNKNOWN, baja prioridad.

Estos puntos no bloquean la versión ni reabren la estabilización. No hay compromiso con scheduler, farming planner, navigation graph general ni optimización de flows ajenos.
