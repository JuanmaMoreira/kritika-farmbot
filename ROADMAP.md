# Pendientes

Orden de trabajo; estado real en [CONTEXT](CONTEXT.md), contratos físicos en [GAMEPLAY_GT](docs/GAMEPLAY_GT.md), wiring pendiente en [RESOURCE_ROUTING](docs/RESOURCE_ROUTING.md).

1. **P0 Craft:** separar identidad de economía; sustituir título OCR duro por landmark seguro fuera de CHAT/Heaven & Hell. Revisar Hero Weapon count expuesto y rate; Armor/Accessory no deben gatear una operación Weapon. Conservar guards económicos necesarios.
2. **Validación dirigida:** tests/replays de lo afectado; evaluator incremental sólo si cambia percepción. Reutilizar resultados vigentes; fixtures Rotation ausentes se reportan aparte.
3. **Un smoke MW live autorizado:** detener en primera divergencia causal, sin reconfirmar transiciones GT ni campañas por rama.
4. **Fix mínimo de esa divergencia**, repetir sólo validación invalidada y el siguiente smoke útil. No ampliar arquitectura.
5. **Cerrar L2/MW productivo:** completar callbacks reales pendientes Keys/Materials/Gold recovery y entrada blocker Craft→Combine→Craft, sin rutas nuevas desde Craft limpio. Validar la integración requerida, no confundir componentes standalone con producto completo ni autorizar Sell implícitamente.
6. **Follow-ups separados:** lifecycle automático de SKIP y bug Run Session Daily/eligibility por wrapper productivo. Definir alcance cuando se aborden; Fill All con Gold insuficiente sigue UNKNOWN de baja prioridad y no bloquea MW.
7. **Estabilización/release** cuando la integración real esté completa; checkpoint y validación amplia sólo entonces si corresponden.

Después y sin bloquear lo anterior: scopes/reuse adicionales sólo con necesidad medible, landmark Lobby menos dependiente de temporada, nuevos flows (Tower/Arena) con GT y slice propio. No hay compromiso con scheduler, farming planner o framework general de navegación/recovery.
