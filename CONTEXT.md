# Estado actual — Kritika FarmBot

## Checkpoint Monster Wave — 2026-10-02

**MW estable para esta versión; etapa de estabilización cerrada.** El loop autónomo de debugging live terminó. Rama `rebuild/stable-baseline`; checkpoint local `feat: stabilize productive monster wave flow`, sin push. Código y tests son autoridad de implementación; [GAMEPLAY_GT](docs/GAMEPLAY_GT.md) fija la UI física y [RESOURCE_ROUTING](docs/RESOURCE_ROUTING.md) el routing económico. No repetir smokes ni provocar deuda aceptada durante el cierre.

Smoke final del código vigente: `mw_final_native_d1e5d83e` → COMPLETED → **3 CLEAR, 253/253 Sapphires, Lobby, sin flow.failed**. Runtime productivo normal, sin guards diagnósticos; recursos del runtime cerrados.

## Ramas live verificadas

| Evidencia | Cobertura vigente |
| --- | --- |
| `d1712918` | WB → MW, cuatro CLEAR, 362/362, Keys, Point Reward y Lobby |
| `84b71faf` | Materials 852→52→12, Craft, Socket, retorno al mismo pass, dos CLEAR y 138/138 |
| `d4b4bef4` | Craft Full → Combine, capacidad 135/128→124/128, Craft 318→24, segundo Back a Lobby esperado |
| `mw_confirm_resume_778e091f` | Keys Full post-confirm → ACK → Gold drain → retry causal único SUCCESS; Transmute/Ethereal positivos |
| `mw_fuse_resume_f1c75c3d` | Resultado Fuse reconciliado sin repetir confirmación; Equipment Full → Combine → fresh 162/128 → cinco Bulk → 127/128; mismo pass, Point Reward y cuatro CLEAR 396/396. Falló sólo la salida final a Lobby; no presentar este run como completamente verde |
| `mw_exit_inventory_native_3bf4119d` | Salida corregida Inventory → MW → Lobby → hub, validación nativa sin consumo |
| `mw_final_native_d1e5d83e` | Smoke final aceptado, código vigente, tres CLEAR 253/253 y cierre completo |

Logs/capturas nativas y resultados detallados permanecen locales; manifests curados y assets runtime forman parte del checkpoint. La evidencia previa sigue válida: no hubo cambios productivos posteriores al smoke final durante el cierre documental.

## Contratos vigentes

- MW usa precheck fresco de Sapphires en el hub, preparación SKIP una vez, MAX, board/plan nuevo por pasada y accounting sólo tras CLEAR confirmado. No usa Eligibility ni el badge Daily como gate. CLI/GUI y sesión WB→MW comparten la composición productiva.
- Craft conserva entrada directa/caller natural, **sin MW→Inventory→MW preflight**. Capacidad se consulta sólo por necesidad real. `Craft→Inventory→Back→Craft→Back→Lobby` es una postcondition normal determinista; navegación normal restaura MW y el mismo pass sin repetir una intención consumida.
- Equipment Full: **Combine → fresh Item Count → si sigue Full, Bulk Sell tail-first → sin candidato accesible permitido, siguiente fila +4 con Karats → fresh capacity y reinicio**. Item Count determina el prefix seleccionable, distinto de la lista total ordenada por poder. HAVE<NEED termina inmediatamente. Ningún índice/scan sobrevive a Bulk o expansión; cada compra añade sólo una fila secuencial.
- Legendary e inferior son descartables sin policy por level/enhancement/duplicados. Ethereal configurable por nueve tipos y Enhance aparte; default protege Weapon/Earrings/Necklace/Ring y permite Helmet/Chest/Pants/Gloves/Boots. Todo Ethereal+ siempre protegido. Sólo Bulk, con panel/popup redundantes; UNKNOWN/AMBIGUOUS/contradicción no autoriza consumo.
- Keys: CV establece identidad/geometría; OCR sólo lee pares variables. Dos lecturas completas, frescas, consecutivas y concordantes; hasta tres intentos por transitorio. Reuse sólo del consenso exacto SUCCESS válido/fresco. Perfil nativo: **40→4 OCR, 6.02→1.151 s** (snapshot 1.015 s, reader .134 s).
- C4 y demás consumos: una confirmación por intent, barrera temporal después del dispatch y efecto fresco; frames previos/durante dispatch no prueban completion. Timeout/inconclusión no permite repetir; reconciliar antes de otro intent.

## Validación reutilizable

Regresión proporcional: 71 módulos/1931 casos, 1928 verdes inicialmente y tres expectativas stale reparadas; sólo sus tres módulos repetidos, **84/84 verdes**. Equipment Sell evaluator **14/14**; Point Reward incremental **102 frames** y Fuse **213 frames**, sin wrong. Cierre: snapshot exacto del commit validado con **39/39 tests** de Flow Registry y recuperación compartida, tras separar únicamente la integración independiente de Summon Pet Daily. 35 referencias documentales válidas y sintaxis de los 89 Python cambiados correcta. Diff check limpio. Sin nuevos smokes ni cambios productivos durante el cierre.

## Deuda aceptada, no bloqueante

1. Expansión Equipment +4 positiva live: mecánica/fila/coste/popup adquiridos y tests verdes; no se provocó una compra innecesaria.
2. Poor/Normal visual positivo y Ethereal Enhance positivo: policy conocida; evidencia insuficiente mantiene fail-closed.
3. Perfil/optimización posterior del scan Sell protegido: correcto y bounded, último loop 249.94 s con cinco Bulk.
4. Lifecycle de SKIP tras pausas de diagnóstico muy largas.
5. Portabilidad/publicación del corpus nativo local.
6. Fill All con Gold insuficiente sigue UNKNOWN, baja prioridad.

No implementar estas deudas dentro del cierre. Otros flows y planes futuros conservan sus límites existentes; no ampliar alcance a scheduler, planner de farming o navigation graph general.

## Worktree preservado

El worktree ya era amplio antes de MW. El checkpoint incluye MW y dependencias causales, no todo cambio local. Se preservan fuera de él la eliminación previa de `Kritika_FarmBot_Plan_Preparacion_Codex_Astra.md`, los scripts anteriores `check_eval.py`, `fix_tests.py`, `test_live.py`, `test_wait.py`, y la integración independiente de Summon Pet Daily. No reset/clean ni borrado de evidencia. Los artefactos ignorados de diagnóstico quedan locales.

Entorno machine-local en `AGENT_LOCAL.md`. Fixtures Rotation ausentes bajo `artifacts/failure_evidence/` son un gap ambiental previo ajeno a MW, no deuda nueva ni blocker de esta versión.
