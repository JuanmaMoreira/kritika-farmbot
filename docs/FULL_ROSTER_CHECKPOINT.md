# Checkpoint estable — full roster farming 2026-10-05

Parent `656460c4b16526ced5ae46b36764240aa5ec71cb`; branch `rebuild/stable-baseline`.
Un único commit causal `fix: stabilize full roster farming session`, push autorizado a
`origin` (`https://github.com/JuanmaMoreira/kritika-farmbot.git`) tras cierre verde.
La verificación de HEAD remoto se entrega después del push; el hash del documento
no intenta contener el hash del mismo commit. No nuevas features.

## Aceptación principal exacta

- Run `e4d8ec7e6aaf403ca5f919685b22cd81`; session `6c2c6ad1abff47ffb4648262e26368bb`.
- Log local `logs/20261005T234827.311080Z_session_27ae46d4.jsonl`.
- Log SHA256 `be4cf35d6f919b7683bf61f153a9c399d4c2a68383118c694b35a6dfc86d9b89`.
- Session20:48:32.979131→21:49:50.587134 -03, 2026-10-05; elapsed61:17.608.
- 28 scopes consecutivos1..28;28 Rotation con advances_completed1..28; Session COMPLETED.
- 0 flow.failed,0 session.failed,0 runtime.failed. Cada scope tiene los cinco resultados
  BM→WB→Gold→Mailbox→DailyQuests, seguido de Rotation; no mezcla de runs.
- 26 nombres de clase distintos registrados; scopes18/21 UNKNOWN en runtime, conservados.
  USER_GT confirma roster28; no se inventan identidades ni se cambia Rotation/report.
- 25 personajes con Video0/ads_exhausted;6 Ads returned y6 efectos Sapphire frescos.
- WB28 no elegibles,0 raids/Auto inputs en este run; cobertura raid corresponde a focales
  anteriores, no se suma a esta aceptación.
- MW23 inversiones productivas en5 personajes;26 scopes observaron no-work.
- 27 scopes business-incomplete según eventos:25 daily exhaustion,13 Black Market
  inventory_full,1 Mailbox claims_leftover (pueden coincidir en un mismo scope);
  técnico válido. Whitelist informativa sapphire_effect no se modifica.
- Navigation comprobada programáticamente:3 MW BASE→QM Mailbox→Close→fresh MW→QM
  Quests→Close→fresh MW→QM Character Select;25 Lobby legítimos sin MW BASE final;
  cero restauraciones incorrectas/Lobby indebidos. Black Market11 retries frescos.

## Hashes y provenance

Código Python bot/tools y assets:522 archivos, SHA256 `ef86879e9778565fc12db80ab260aa57c33db67052fb2d6d51e184051065c699`.
Dict completo igual entre `ads_general_manual_ready_hashes.json` (pre-inicio manual)
y `closure_terminal_hashes.json` (cierre). Incluye los dos archivos productivos
independientes ya presentes en el worktree; esos hunks Summon Pet no pertenecen
a la rutina aceptada y se excluyen del commit. Validación INDEX usa sus versiones baseline.
Sin modificaciones productivas durante la campaña final. No se deduce el hash desde HEAD
baseline, pues el run usó los fixes locales posteriores. Git normaliza line endings.

Aggregate completo previo (incluyendo .env/routines.json): `a45491e6b1be583209bd0dd297aef89e7b7d2a5cb84296721d6e9dc3c4ab79af`.
Aggregate completo de cierre: `d1ae2da90ee41dd6a1b319c7d1287afc9bf254b5b2364bb4c0da78ed7f555b1f`.
Única diferencia: `routines.json` local GUI. No existe hash específico de config al
inicio de ese run; no se afirma identidad de configuración before/after. Orden seleccionado
acreditado en los28 scopes; se conserva hash de config de cierre en artifact local.
Ni .env ni routines.json ni logs/capturas/artifacts grandes entran al commit.

## Tabla28/28

| # | Character | BM | WB | Auto | Gold | Ads | MW | Mailbox | Quests | Routing | Rotation | Technical | Elapsed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Halo Mage | completed | not eligible | â€” | completed | 0 effects; exhausted | 2 productive / 0 no-work | completed | completed | lobby OK | 1 | COMPLETED | 92.0s |
| 2 | Elemental Fairy | completed | not eligible | â€” | completed | 0 effects; exhausted | 0 productive / 1 no-work | completed | completed | lobby OK | 1 | COMPLETED | 100.3s |
| 3 | Noblia | completed | not eligible | â€” | completed | 0 effects; exhausted | 0 productive / 1 no-work | completed | completed | lobby OK | 1 | COMPLETED | 108.6s |
| 4 | Steam Walker | completed | not eligible | â€” | completed | 2 effects | 8 productive / 1 no-work | completed | completed | monster_wave OK | 1 | COMPLETED | 444.8s |
| 5 | Telumpel | completed | not eligible | â€” | completed | 2 effects | 6 productive / 1 no-work | completed | completed | monster_wave OK | 1 | COMPLETED | 384.3s |
| 6 | Eclair | completed | not eligible | â€” | completed | 0 effects; exhausted | 0 productive / 1 no-work | completed | completed | lobby OK | 1 | COMPLETED | 114.9s |
| 7 | Wandering Master | completed | not eligible | â€” | completed | 0 effects; exhausted | 0 productive / 1 no-work | completed | completed | lobby OK | 1 | COMPLETED | 88.1s |
| 8 | Shadow Mage | completed | not eligible | â€” | completed | 0 effects; exhausted | 0 productive / 1 no-work | completed | completed | lobby OK | 1 | COMPLETED | 112.8s |
| 9 | Blood Demon | completed | not eligible | â€” | completed | 0 effects; exhausted | 0 productive / 1 no-work | completed | completed | lobby OK | 1 | COMPLETED | 106.5s |
| 10 | Galaxy Lord | completed | not eligible | â€” | completed | 0 effects; exhausted | 0 productive / 1 no-work | completed | completed | lobby OK | 1 | COMPLETED | 116.0s |
| 11 | Rang | completed | not eligible | â€” | completed | 0 effects; exhausted | 0 productive / 1 no-work | completed | completed | lobby OK | 1 | COMPLETED | 84.5s |
| 12 | Strike Archer | completed | not eligible | â€” | completed | 0 effects; exhausted | 0 productive / 1 no-work | completed | completed | lobby OK | 1 | COMPLETED | 105.7s |
| 13 | Hastati | completed | not eligible | â€” | completed | 0 effects; exhausted | 0 productive / 1 no-work | completed | completed | lobby OK | 1 | COMPLETED | 110.6s |
| 14 | Dark Valkyrie | completed | not eligible | â€” | completed | 0 effects; exhausted | 0 productive / 1 no-work | completed | completed | lobby OK | 1 | COMPLETED | 106.3s |
| 15 | Ice Warlock | completed | not eligible | â€” | completed | 2 effects | 5 productive / 1 no-work | completed | completed | monster_wave OK | 1 | COMPLETED | 358.0s |
| 16 | Eilla | completed | not eligible | â€” | completed | 0 effects; exhausted | 0 productive / 1 no-work | completed | completed | lobby OK | 1 | COMPLETED | 109.8s |
| 17 | Lina | completed | not eligible | â€” | completed | 0 effects; exhausted | 0 productive / 1 no-work | completed | completed | lobby OK | 1 | COMPLETED | 73.2s |
| 18 | UNKNOWN | completed | not eligible | â€” | completed | 0 effects; exhausted | 0 productive / 1 no-work | completed | completed | lobby OK | 1 | COMPLETED | 97.5s |
| 19 | Berserker | completed | not eligible | â€” | completed | 0 effects; exhausted | 0 productive / 1 no-work | completed | completed | lobby OK | 1 | COMPLETED | 108.2s |
| 20 | Blade Dancer | completed | not eligible | â€” | completed | 0 effects; exhausted | 0 productive / 1 no-work | completed | completed | lobby OK | 1 | COMPLETED | 73.9s |
| 21 | UNKNOWN | completed | not eligible | â€” | completed | 0 effects; exhausted | 0 productive / 1 no-work | completed | completed | lobby OK | 1 | COMPLETED | 86.5s |
| 22 | Kaiserin | completed | not eligible | â€” | completed | 0 effects; exhausted | 0 productive / 1 no-work | completed | completed | lobby OK | 1 | COMPLETED | 112.3s |
| 23 | Dimension Manipulator | completed | not eligible | â€” | completed | 0 effects; exhausted | 2 productive / 0 no-work | completed | completed | lobby OK | 1 | COMPLETED | 142.8s |
| 24 | Monk | completed | not eligible | â€” | completed | 0 effects; exhausted | 0 productive / 1 no-work | completed | completed | lobby OK | 1 | COMPLETED | 85.4s |
| 25 | Mystic Wolf Guardian | completed | not eligible | â€” | completed | 0 effects; exhausted | 0 productive / 1 no-work | completed | completed | lobby OK | 1 | COMPLETED | 100.4s |
| 26 | Cat Acrobat | completed | not eligible | â€” | completed | 0 effects; exhausted | 0 productive / 1 no-work | completed | completed | lobby OK | 1 | COMPLETED | 103.8s |
| 27 | Crimson Assassin | completed | not eligible | â€” | completed | 0 effects; exhausted | 0 productive / 1 no-work | completed | completed | lobby OK | 1 | COMPLETED | 75.2s |
| 28 | Flame Striker | completed | not eligible | â€” | completed | 0 effects; exhausted | 0 productive / 1 no-work | completed | completed | lobby OK | 1 | COMPLETED | 75.2s |

## Runs rojos posteriores al parent (historia inmutable)

Duraciones son de Session; las cifras de validación son invocaciones separadas,
no se suman. Reconstrucción/eventos/failure evidence/focales y auxiliares rojos:
[auditoría causal](COMBINED_28_ACCEPTANCE_AUDIT.md).

| Run / Session | Log | Scope / Flow | Primera divergencia / causa | Fix | Validación causal |
| --- | --- | --- | --- | --- | --- |
| `783b9af222a14fa59561ccdde928216b` / `e2c4b47466c04f0d9b14ba8fab03a6dd` | `20261005T140313.234892Z_session_72bd9da9.jsonl` | #4 Steam Walker / WB (3 completed) | Raid Complete fresco tras tap sin salida; retry guard rechazó estado recuperable | Retry bounded sólo desde Raid Complete fresco; sin repetir Start | 272 tests; replay driver; focal WB/Rotation |
| `7c27fa66b0fe4b84a2026b09fc865801` / `70a3b1e4f70c4f2db5369e39c9e06320` | `20261005T153038.248412Z_session_fcbf2fa7.jsonl` | #5 Galaxy Lord / Quests (4 completed) | Toast MAX ocultó Daily aunque Quests seguía resuelto; abort antes de efecto | Espera pasiva del tab, sin segundo Claim; contradicción sigue abortando | 92 tests;3 replays semánticos; focal QM |
| `e950b7ba8dd34a8f994f4fc84051df30` / `ce3e43c1de69406aa2694bf4a3c558d5` | `20261005T165358.677970Z_session_166fdcaa.jsonl` | #5 Ice Warlock / WB Sell (4 completed) | Detail fuerte sin cambio, NCC.998975<.999 rechazó continuidad | Consenso semántico fuerte fresco al miss; policy/popup/confirm intactos | 23 directos;815 afectados; focal .998960 y128→127 |
| `9e98aa1fc019434f8749aaa3c4e55586` / `edadabb62e104cbdac322bd0e5b349cf` | `20261005T175845.466159Z_session_4ff09003.jsonl` | #2 Lina / Gold Keys (1 completed) | Karat+reward local con título cubierto; espera hasta timeout | Finalizer lateral existente bajo autoridad local fresca; cero premium | 71 directos;338 afectados; replay y focal |
| `404e5d31e5974f7da80208c739ab8739` / `d291501d507b4c81af681ea45a519645` | `20261005T183419.396311Z_session_6aa08c50.jsonl` | #1 Lina / MW (0 completed) | HUD3 leído como③, parser rechaza efecto | Grayscale sólo MW; ROI/parser/confidence/consenso intactos | 77 directos;530 afectados;30 crops; focal3 |
| `d5604ea5ec5a4228b2b8d68c166265c5` / `1209487bb32e40ebae3aaee6bda2424b` | `20261005T184728.628013Z_session_fa1e054f.jsonl` | #4 Blade Dancer / Sell (3 completed) | Nombre Phantom Sword envuelto: primer ROI sin ] | Segunda línea sólo tras prefijo fuerte incompleto; scope Bulk independiente | 203 directos;685 afectados; replay nativo; efecto149→139 |
| `810a66e4bfba4ddb859c64fe7c2a0a72` / `719b4e4edcad45c8816e52ba5d84322c` | `20261005T210854.344069Z_session_0db54e8e.jsonl` | #8 Crimson Assassin / Gold Keys (7 completed) | Tras OpenOnce verificado, flash UNKNOWN rechazado inmediatamente | Espera pasiva fresca bounded5 s a misma autoridad Gold/Karat; sin repetir open | 77 directos;451 afectados; replay flash; focal95 inputs/0 premium |
| `5ba8bdaa202b4a87a67355ffa50ae19e` / `f68e12b17c544b2bbbc22e5ac372d069` | `20261005T230857.999888Z_session_0cb75379.jsonl` | #2 Flame Striker / Gold Ads (1 completed) | Reward granted X acreditado no reconocido; template dependiente del fondo; stall con0 closes | Primitivas SDK enmascaradas y texto chrome exacto; terminal fresco inmediato | 196 afectados; replay17 frames; integración final6 Ads con efecto |

## Scope exacto del checkpoint

- WB: retry de salida Raid Complete perdido, mismo driver/guard fresco bounded.
- Daily Quests: espera pasiva cuando toast MAX oculta el tab después de Claim.
- Equipment Sell: revalidación semántica del mismo detail al miss de continuidad;
  lectura de nombre envuelto en popup K Coins. Policy protegida/Bulk/expansión intactas.
- Treasure: finalización segura Karat+reward local; espera pasiva del flash de entrada.
- MW: preprocessing grayscale local del HUD Sapphire3, sin cambios de pressure.
- Ads: terminal sin edad mínima; no Back por timeout/ownership solo; primitives SDK
  enmascaradas independientes del creative y Reward granted/Next ad sólo en chrome;
  shared OCR wiring, freshness tras OCR/Android, bounds de inputs conservados.
- Tests directos/contratos y pequeños fixtures curados, dos assets de primitivas SDK,
  profile local y documentación causal. No modelos/session store, nuevas features
  ni refactor de navegación, Routine, targeted swipe, trading, stamina/Craft policies.

## Ads: cobertura y límites

Strong terminal authority→cierre inmediato, incluso5/8/12 s. Sin terminal→espera;
X genérica/content X→cero cierre. Multipart fin de parte≠fin de ad; progress/reset
renueva stall, absolute180 s, external visits bounded y fresh evidence conservados.
Next ad exacto es intermedio; no se inventa hitbox ni se pulsa por inferencia.

Offline implementación/tests: validado. Integración28/28: validada. Broad live
short-ad/multipart after latest patch: limitada por cupo diario consumido.
Los6 ads reales cerraron con1 SDK Back cada uno y efecto Sapphire fresco; duración
AdsManager9.922–25.234 s. Todos publicaron `reward_granted_text`; cierres a7.656,
8.515 y22.406–23.016 s desde launch. Sin progreso/reset/external visit registrados
en esos6; no se declara multipart ejercitado. Esto no demuestra onset físico
de5 s ni triple explícito. La rama X circular sin texto tiene replay/GT adquirido,
sin cierre live acreditado en esta campaña final.
El usuario hará otro28 manual con reset diario; una regresión nueva se analiza
como posterior, sin borrar esta aceptación. No se fuerza trabajo/ads ni se amplía scope.

## Validación de cierre

- Worktree: una invocación afectada de76 módulos, **1860 passed,4 skipped/349.23 s**.
  Ads/Stages/WB/Auto/Quests/Sell/Treasure/Keys/MW/OCR/facts, Gold/wiring,
  Session/Routine, navegación/Rotation y consumidores compartidos. No se suman
  invocaciones anteriores; los4 skips históricos Rotation se conservan.
- INDEX exportado mediante checkout-index:38 archivos causales verificados byte
  por byte (normalización CRLF para texto), assets Stages completos. Los3 archivos
  independientes tracked usan baseline y los4 scripts locales están ausentes.
- INDEX portátil: una invocación de18 módulos, **533 passed,1 skipped,3 deselected/
  26.29 s**. Los3 deselected son tests históricos que requieren screencaps locales
  ignoradas (hub Sapphire y2 Rotation); el skip es corpus MW previo. Todos los
  fixtures nuevos/casos causales portables sí se ejecutaron.
- Primer intento INDEX:533 passed,1 skip,3 fallos por esos archivos de evidencia
  local ausentes, no por código ni por assets runtime olvidados. Las mismas ramas
  con corpus local pasaron en la invocación afectada del worktree. No se cambian
  tests/guards ni se versiona el corpus para ocultar esa limitación.
- `git diff --cached --check` y `git diff --check` sin errores; lista stage38 causal,
  8 paths independientes conservados/excluidos. Ningún asset/config productivo
  cambió después de la aceptación. Config GUI local permanece fuera del índice.

Replay Ads productivo17 frames nativos:12 no terminales,4 X circular terminales,
1 Reward granted del rojo. Replay Treasure entrada: flash archivado downsampled
resize sólo causal (no confianza nativa), positivo nativo, secuencia sintética fresca
y frontera Karat; un input Gold y cero premium. Replay frontera Karat local usa
lecturas archivadas con finalizer seguro/cero economic. Replay nativo Sell Phantom
Sword y MW3 están incluidos en los tests portables. No teléfono en cierre offline.

## Docs y deuda

Reconciliados CONTEXT, ROADMAP, ARCHITECTURE, GAMEPLAY_GT, RESOURCE_ROUTING y
COMBINED_28_ACCEPTANCE_AUDIT; sin borrar procedencia histórica.

Deuda vigente: cobertura natural amplia X sola adquirida post-latest-fix
(implementación/offline cerradas), multipart/triple explícito, No Ads temporal full
recovery, Accessories MAX/result/effect, SessionReport whitelist
`monster_wave.sapphire_effect`. Contextos SDK no adquiridos permanecen fail-closed.
ToT/Arena/Melee/Open Pets/Character State Store fuera de este cierre.

## Trabajo independiente excluido

Los8 paths mantienen hashes idénticos al estado previo a campaña7. Ningún hunk
independiente pasó a causal: flow_registry sólo contiene builder Summon Pet;
summon_pet_daily_flow y test_portal_obstruction_recovery corresponden a ese owner.
El archivo de preparación sigue borrado y los cuatro scripts siguen untracked.

```text
 D Kritika_FarmBot_Plan_Preparacion_Codex_Astra.md
 M bot/flow_registry.py
 M bot/summon_pet_daily_flow.py
 M tests/test_portal_obstruction_recovery.py
?? check_eval.py
?? fix_tests.py
?? test_live.py
?? test_wait.py
```
