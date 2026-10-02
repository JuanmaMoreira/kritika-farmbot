# Estado actual — Kritika FarmBot

## Checkpoint Stages Daily + AdsManager — 2026-10-02

**Etapa cerrada y funcional para esta versión.** Loop autónomo live terminado. Un checkpoint local conjunto de Stages/Ads, Keys phase y Sell acceleration; sin push. Rama `rebuild/stable-baseline`. Baseline anterior MW: `73313497afa21283ca50c5500f5147239d14d0e8`, `feat: stabilize productive monster wave flow`.

Smoke final aceptado `stages_progress_smoke`, run `f1c24b514e4e40128d5875a7c1ed74f4`: **COMPLETED, Sapphires 5→479, Stamina 440→140, Lobby limpio, sin flow.failed**. Lobby → preconditions → Normal → Claims x2 → Abyssal Rion/Stage 8 → Mao ACTIVE/Penance → Start/Auto/300 MAX/Video → ad → Results OK → config X → Back → Lobby. No repetir este smoke durante el cierre.

## Contratos vigentes

- **Stages ads-only:** Stamina ≥300 y Sapphires <102; saldo alto delega a MW existente y reevalúa. Stamina faltante usa Currency/Stamina con K Coins y verifica efecto fresco, sin OCR de K Coins. Un ad exitoso por ejecución; Results + Sapphire after > before. Sin combate, auto battle, repeat manual, x4 manual ni selector general de episodios/stages.
- **AdsManager transversal:** Android activity/focus concordantes y screencap nativa fresca tras inputs; chrome/progreso del SDK, sin contenido/marca/CTA. Progreso sólo mantiene observación (grace 15 s, máximo absoluto 180 s); ~60 s es fallback desconocido/estancado, no finalización. Back 1 → fresh verify → Back 2 sólo con ownership ad/external positivo; detener inputs al recuperar Kritika. Abort recuperado, indisponibilidad y recovery técnico permanecen separados. Contrato estable en [ARCHITECTURE](ARCHITECTURE.md); routing/retries en [RESOURCE_ROUTING](docs/RESOURCE_ROUTING.md).
- **Keys phase:** Bronze completo primero si cabe; de lo contrario Silver EXACT1 pre-drain mínimo → Bronze → Silver final. Fresh facts no resetean fase. C4, budgets, confirm único y Gold-full pending causal conservados.
- **Sell acceleration:** BGR NCC .90, banda .84–.90 inconclusa, dos referencias para glow; sólo discovery/block skipping. Panel/policy/popup siguen autorizando Bulk. Count/delta frescos transforman rangos lógicos protegidos después de Bulk compatible; pixels/geometría se invalidan siempre. Expansión/contexto/delta contradictorio invalidan también el modelo lógico. Scan secuencial sigue disponible. Combine-first y Ethereal+ no cambian.

MW permanece cerrado para su versión previa: `mw_final_native_d1e5d83e`, tres CLEAR, 253/253 Sapphires, Lobby sin flow.failed. No se reabrió su estabilización general. Su evidencia histórica está preservada en el baseline; [MONSTER_WAVE_SKIP](docs/MONSTER_WAVE_SKIP.md) y RESOURCE_ROUTING conservan el contrato.

## Validación reutilizable

828 tests ampliados verdes; 212 checks adicionales verdes y un count test preexistente obsoleto (OVERLAY_RULES espera 57, baseline contiene 58). Evaluator Stages 196 pares; Sell 24 frames, 276 equivalentes/108 distintos/0 falsos saltos; Ads progress replay 31 pares; margen native Socket 17 pares más negativos. Diff check limpio. No nuevos smokes en el cierre.

Sell live: 66 slots, 4 discovery panels, 62 saltados, 3 bloques, 0 fallback, 10.234 s. Full natural posterior a Stages: una Bulk 141/128→127/128, dos panel opens reales, 7.703 s, sin expansión. No atribuir a ese smoke continuidad multiBulk todavía Full.

## Deuda no bloqueante / próximo frente

1. Ad multipart/triple: progress/reset tested, no aparición natural post-fix.
2. No Ads temporal nativo y cadena retry/reset live completa; policy implementada, mismo-personaje reset aislado verificado.
3. Sell logical transform multiBulk todavía Full: tests verdes; esperar condición live natural.
4. `mw_relief_exit_failed` histórico durante prerequisite/relief, evidencia preservada; no reabrir MW general por este checkpoint.
5. Count de catálogo obsoleto, sin alterar runtime/count para ocultarlo.
6. Combate/manual Stages fuera de alcance. Deuda previa MW permanece en ROADMAP.

Próximo frente: por definir con el usuario. No continuar adquisición, optimizaciones ni debugging autónomo de esta etapa.

## Worktree preservado

Fuera del checkpoint: integración previa de Summon Pet Daily (incluido su hunk en `flow_registry.py` y tests portal), eliminación previa de `Kritika_FarmBot_Plan_Preparacion_Codex_Astra.md`, `check_eval.py`, `fix_tests.py`, `test_live.py`, `test_wait.py`. Diagnósticos/logs/capturas completas permanecen locales, sin versionar. Entorno machine-local en `AGENT_LOCAL.md`; assets runtime y fixtures regresivos curados sí pertenecen a esta etapa.
