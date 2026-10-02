# Pendientes

Estado real en [CONTEXT](CONTEXT.md); UI física en [GAMEPLAY_GT](docs/GAMEPLAY_GT.md); routing único en [RESOURCE_ROUTING](docs/RESOURCE_ROUTING.md).

## Monster Wave — etapa cerrada 2026-10-02

**Estable para esta versión.** Smoke final `mw_final_native_d1e5d83e`: COMPLETED, tres CLEAR, 253/253 Sapphires, Lobby, sin flow.failed. WB→MW, Keys/Gold, Materials/Craft, Socket, Point Reward y Equipment Combine-first/Bulk tail-first/retorno al mismo pass cuentan con evidencia live. Checkpoint local único autorizado; sin push. El loop autónomo live terminó; no quedan bugs productivos conocidos pendientes dentro del alcance aceptado.

## Deuda posterior aceptada

1. Expansión Equipment +4 positiva live sólo ante necesidad real: mecánica adquirida y tests verdes; no provocar compras preventivas para validación.
2. Poor/Normal visual positivo y Ethereal Enhance positivo cuando sean necesarios. Policy conocida, evidencia insuficiente falla cerrado.
3. Sell CV y conservación lógica implementados por autorización posterior; adquirir live continuidad entre Bulks sólo si sigue Full naturalmente. Ver [Protected-block scan acceleration](#protected-block-scan-acceleration).
4. Lifecycle de SKIP tras pausas de diagnóstico muy largas.
5. Portabilidad/publicación del corpus nativo local.
6. Fill All con Gold insuficiente UNKNOWN, baja prioridad.

Estos puntos no bloquean la versión ni reabren la estabilización. No hay compromiso con scheduler, farming planner, navigation graph general ni optimización de flows ajenos.


## Protected-block scan acceleration

Implementado por autorización expresa 2026-10-02. CV sólo descubre/salta equivalentes de un anchor fuerte protegido. NCC BGR, ±2 px, ROI relativa al slot `[-.027,-.063,+.027,+.028]`, sin CP y manteniendo marco/tier. Threshold .90 calibrado: same-frame intra p5 .94522 frente inter max .83183; interior confunde tipos (inter .965), descartada. Dos fases alrededor del panel cubren glow; ambiguo/missing falla al scan secuencial, no al relief.

LIVE: protected scan66 slots/4 paneles/62 saltados/3 bloques/0fallback en10.234 s. Bulk natural141→127 en7.703 s con dos panel opens (discovery y guard consumptivo), una confirmación, sin expansión. Primera Bulk libera capacidad; no se fuerza otra Full para validar continuidad lógica.

USER_GT Bulk preserva orden: invalidar pixels/geometría y transformar rangos protegidos con delta fresco. Región expuesta y next logical index guían navegación; delta/modelo contradictorio o expansión/contexto distinto borran modelo. Tests de varias Bulks, nuevos candidatos fuertes, E+, fallback e invalidación verdes. Policy/guard fuerte/popup/confirm único sin cambios. Evaluator24 frames/276same/108different/0false skips; fixtures20 icon crops curados.

## Stages Daily ads-only — etapa cerrada 2026-10-02

**Funcional y cerrada para esta versión.** `stages_progress_smoke` / `f1c24b514e4e40128d5875a7c1ed74f4`: COMPLETED, Sapphires 5→479, Stamina 440→140, Lobby limpio, sin flow.failed. Stages navigation, Claims, Mao, Penance/300 MAX, Stamina purchase, same-character recovery, AdsManager básico/transversal, Keys phase y Sell block scan/logical transform están implementados; no son pendientes.

No ampliar a combate normal, auto battle, repeat manual, consumo x4 manual ni framework de episodios/stages. No repetir smokes ni buscar variantes durante el cierre.

### Deuda futura no bloqueante de esta etapa

1. Multipart/triple: progreso/reset tested; no volvió a aparecer naturalmente post-fix. ~60 s no prueba finalización; contrato de progreso/fallback en ARCHITECTURE.
2. No Ads Available temporal nativo y cadena recovery live completa; policy 3 intentos + un reset MISMO personaje + 2 intentos implementada. Reset aislado pasó; no Rotation.
3. Sell logical transform entre varias Bulks mientras sigue Full: tests verdes; falta condición live natural. No provocar Equipment Full.
4. `mw_relief_exit_failed` histórico: evidencia preservada, sin reapertura general MW.
5. Count test de catálogo obsoleto (57 esperado / 58 baseline); no ocultarlo cambiando runtime.
6. Combate/manual Stages: fuera de scope, sólo posible frente futuro explícito.

Próximo frente por definir. Evidencia y límites actuales en CONTEXT; no gastar ads sólo para ampliar corpus ni implementar esta deuda en el cierre.
