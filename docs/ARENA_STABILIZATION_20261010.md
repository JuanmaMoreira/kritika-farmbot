# Arena Farming / Arena VP — auditoría y validación local 2026-10-10

HEAD inspeccionado antes de editar: `56b472d0e008d7e9d2b8f6842491c7feced095a0`,
rama `rebuild/stable-baseline`. Sin commit/push. Había modificaciones independientes
de Ads, Sell, MW readiness, Summon, Gold tools, fixtures y documentación; se preservan.
Los fixes de Muse post-Clear/post-Claim ya estaban en el worktree.

## A. Dos sesiones nuevas: identidad y reconstrucción

Los timestamps siguientes son UTC. Para eventos diferidos del ciclo, `created_at`
es el momento causal; `timestamp` puede ser la publicación al cerrar el owner.
Reconstrucción compacta completa: `artifacts/arena_stability_20261010/historical_audit.json`.

| | Ice Warlock / Drakenn10 | Eilla / Drakenn27 |
| --- | --- | --- |
| Log | `logs/20261010T024716.317077Z_session_16fdb15e.jsonl` | `logs/20261010T072147.067075Z_session_a81d6af4.jsonl` |
| Run | `7791cdd9924246298a7729036912eb64` | `27d36db3dfc84ff6bfbf2a2787eb5410` |
| Session | `cee3791e0bfc45da8a57040b7afc15d2` | `3670e8d752834ce59976862b6a6d0061` |
| Identidad estable | `ice_warlock` | `eilla` |
| Runtime | 02:47:16.382538→04:07:07.427779 (79m51s) | 07:21:47.143439→08:26:54.184188 (65m07s) |
| Personajes planificados/procesados | 2/1 | 4/1 |
| Manual acreditados / MW / Arena | 8 / 6 / 6 | 8 / 5 / 5 |
| Stamina consumida / máximo / restante | 480 / 600 / 120 | 480 / 600 / 120 |
| Compra Stamina / K Coins | 300 / 1200; saldo observado320→620 | 500 / 2000; saldo observado148→648 |
| Recursos iniciales Badge / Sapphire | 2 / 39 | 2 / 15 |
| Últimos recursos acreditados | 2 / 33 | 2 / 46 |
| Interrupción | operación21, preparación Manual | operación19, preparación Manual |

Ambas usan rutina `a360`, id `61b225b73b6c44278955dac6b4a90f0f`:
Black Market → Arena Farming Cycle → Daily Quests → Mailbox. Arena es occurrence1,
step2; las dos últimas actividades no se alcanzan. Shared Meteorites ON, target
Manual `abyssal_rion_09`; setup acreditado, lifecycle final INTERRUPTED y sin cleanup.
La restauración manual sigue correspondiendo al usuario.

El archivo actual `routines.json` fue escrito07:21:42Z, cinco segundos antes de Eilla:
Badge60, Sapphire60, zero-win80, máximo600. Sus decisiones son compatibles con él.
No existe snapshot de configuración embebido en esos runs: no se puede afirmar el
valor exacto anterior de Ice Warlock. Su routing requiere mínimo Sapphire >99 y ≤111
(compatible con100); Eilla >57 y ≤73 (compatible con60). Es una inferencia de decisiones,
no una fuente para cambiar policy. El máximo600 sí figura explícitamente en terminales.
Los nuevos ciclos registran configuración efectiva en `arena.farming.started`.

Secuencia completa de operaciones (`M` Manual, `W` MW, `A` Arena):

- Ice Warlock: M,W,A,M,M,W,A,M,W,A,M,M,W,A,M,W,A,M,W,A,**M interrumpido**.
- Eilla: M,M,W,A,M,W,A,M,W,A,M,M,W,A,M,W,A,M,**M interrumpido**.

Los pares Sapphire antes→después de cada M/W y todos los saldos frescos figuran en
la reconstrucción JSON; no se infieren balances para autorizar operaciones.
Eilla usa MW con73 Sapphire y observa0 después: no hay contradicción que requiera
cambiar thresholds ni convertir un saldo menor a100 en error técnico.

| Run / batch (operación) | Dificultad | Used / won | Próxima | Decisión |
| --- | --- | --- | --- | --- |
| Ice1 (3) | HARD | 104/104 | HARD | collect_recent_batches |
| Ice2 (7) | HARD | 104/96 | NORMAL | adjacent_uncertainty |
| Ice3 (10) | NORMAL | 104/88 | NORMAL | collect_recent_batches |
| Ice4 (14) | NORMAL | 104/88 | HARD | recent_reward_advantage |
| Ice5 (17) | HARD | 104/96 | HARD | collect_recent_batches |
| Ice6 (20) | HARD | 104/64 | HARD | hysteresis_hold |
| Eilla1 (4) | HARD | 104/72 | HARD | collect_recent_batches |
| Eilla2 (7) | HARD | 104/96 | NORMAL | adjacent_uncertainty |
| Eilla3 (10) | NORMAL | 88/80 | NORMAL | collect_recent_batches |
| Eilla4 (14) | NORMAL | 104/104 | HARD | recent_reward_advantage |
| Eilla5 (17) | HARD | 104/80 | HARD | collect_recent_batches |

Totales: Ice624/536 (85,90%); Eilla504/432 (85,71%). El controller actúa según
resultados acreditados. No causa las interrupciones.

### Primera divergencia causal compartida

Start de Manual recibe Equipment Inventory Full. Combine termina
`no_relief_available`: Transmute/Ethereal/Fuse no tienen trabajo autorizado.
Retorna correctamente al caller; el coordinador selecciona Sell como fallback.
Su adapter Stages sale al Lobby y llama `OpenQuickMenu` con(.194,.0564), una
hitbox de cabecera de otro contexto. No abre Quick Menu desde ese Lobby.

- Ice: input04:07:00.440Z, source48593; espera `MENU_QUICK`6s, termina04:07:07.
- Eilla: input08:26:47.598Z, source39524; la misma espera termina08:26:54.

El timeout es consecuencia del input incorrecto, no falta de recursos, del controller
ni del resultado Arena. Ninguno alcanza Sell ni vuelve a Start antes de detenerse.
La captura focal reprodujo Lobby→tap viejo→Lobby, y después acreditó el control
Inventory directo(.655,.75) con el reader propietario de Sell. El resolver global
no posee un contexto Inventory equivalente: la verificación corresponde a ese reader.

Corrección local: `StagesReliefs` compone Lobby→Inventory directo y conserva los
barriers de secuencia/tiempo y el retorno del owner. No introduce retries de inputs.
`stages.equipment_relief_result` publica etapa, outcome/error y retorno al caller.
Manual y terminal del ciclo conservan detalle; Session Report muestra Intervention.

Crimson Assassin había acreditado4batches,6Manual/4MW y Shared11/11 de setup/cleanup.
Eso no ejercitaba este fallback roto. Los anteriores incidentes Monk
(`002611…2e449f28`, Sapphire post-Clear) y Dark Valkyrie (`020053…a770c7df`,
post-Claim) son distintos. Los fixes Penance y el controller permanecen intactos.

### Revisión de Muse y causas transversales

Se conservan recuperaciones pasivas: MW hasta12s/6rondas, recursos Lobby3frames,
post-Claim4frames, dos observaciones concordantes y color/gris con gates originales.
Las ROIs pueden ser ocluidas temporalmente; no se acredita aritmética ni se baja
confianza para suplirlas. Los límites incluyen inicialización y captura, y rechazan
confirmaciones que terminen después del deadline. ADB recibe tiempo restante.
Una llamada síncrona OCR ya en curso finaliza antes de comprobar cancelación/deadline;
no se agrega un worker ni se acepta su resultado tardío.

Un `FAILURE` técnico del fact reader MW termina inmediatamente como error técnico;
no se vuelve agotamiento funcional ni se repite como un miss OCR. Diagnósticos Lobby
distinguen contexto/resolver, overlays, edad antes/después de OCR, ilegibilidad,
desacuerdo color/gris, desacuerdo entre observaciones y deadline/no consenso.

`refresh_native` antes publicaba el screencap y devolvía `get_frame`: si el receiver
había publicado algo más nuevo, podía devolver pixels stream en lugar del PNG nativo.
La regresión de concurrencia lo demuestra; no atribuye esa carrera retrospectivamente
a los dos timeouts. Ahora devuelve el PNG adquirido, con tiempo de inicio conservador,
secuencia compartida única y memoria independiente, sin reemplazar un buffer más reciente.
Arena tolera un buffer con secuencia menor que su cursor solicitando captura fresca.

## B. Arena VP en Character State

`ArenaVictoryPointReader` posee ROI(.489,.228,.633,.270), label+total exclusivamente
de Arena BASE. Color/gris, confianza≥.95, una línea, formato entero o miles agrupados;
contexto selection sin ranking/QM, edad≤4s antes/después y cancelación.
Intenta OCR incluso si chat intersecta. Un prefijo limpio puede sobrevivir a una
oclusión (128795→12); el backdrop expuesto enmascarando texto variable rechaza ese
negativo. Assets runtime pequeños y manifest hashado conservan procedencia de0/128795,
modal ranking negativo y oclusión sintética. Raw/frames grandes quedan en artifacts.

Frame único tras Auto Repeat con `batch_result`, al retornar Challenge→Arena BASE.
La revisión del checkpoint difiere el OCR hasta acreditar el retorno normal al
Lobby: usa ese frame sólo si mantiene edad≤4s, sin gastar freshness de los Back
ni crear otra espera por un fallo informativo. Standalone y Farming usan la
misma factory. Sin esa navegación se omite; Single no lee. No hay taps extra,
reentrada desde Lobby, adquisición de Acquired VP ni relación con routing/winrates.
Fallar no modifica éxito ni borra el dato anterior; Back mantiene su freshness normal.

SQLite schema2 migra1 conservadoramente: `arena_vp` entero nullable,
`arena_vp_observed_at` y `arena_vp_period`, fila por identidad estable. Guarda también
historia `ARENA_BASE_OCR`. GUI ordena por entero y muestra154260→154k, cero→0k,
ausencia→—. Reiniciar Session/app conserva datos válidos de la semana.

USER_GT: lunes, mismo reset WB, cálculo previo30min; fuente de fase UTC:
GAMEPLAY_GT, countdown observado2026-10-06T02:15:52Z→reset07:00Z /04:00 -03,
precisión1min. Reutiliza anchor WB persistido y recalibración estacional; sólo sin
anchor usa esa referencia curada. Período = fecha del lunes según esa fase, estable
ante pequeños ajustes de countdown. Catch-up al iniciar/leer y timers ya existentes
invalidan todas las semanas previas incluso si la app estuvo cerrada. Observación
capturada antes del reset no escribe en la nueva semana. No existe polling nuevo.

## C. Validación y límites

Pruebas dirigidas cubren relief real, recuperación pasiva/cancelación/deadline,
captura concurrente/copia independiente, controller/ledger/reinicio seguro,
proyección Session Report, VP parsing/oclusión/navigation/errores, identidad,
migración, reinicio y límites del lunes. Evaluators incrementales locales sin teléfono:
Arena Farming9/9, VP6/6, cero errores (último incremental reutiliza5).
Grupo principal402passed; grupo posterior307passed; regresiones finales116passed,
VP/GUI33passed y nuevo borde temporal VP21passed. Los grupos se superponen, no se
suman como tests únicos. La primera ejecución con tmp/cache fuera del árbol falló
por permisos ambientales; basetemp en artifacts y cache desactivado resolvieron
esa limitación. No es una regresión del código.

### Live y dispositivo final

- `inventory_route2`, run `64f5…`: Lobby→Inventory113/112→Lobby acreditado;
  sin vender ni tocar Shared. El primer probe del tap viejo había conservado Lobby.
- `representative01`, run `e37530b4ae4849d0a712e1466aca9df3`,15:23:17→15:24:54Z:
  la ruta corregida sí llega a Inventory. Sell normal autorizado reduce113→107;
  al reintentar preparación aparece primera divergencia nueva: Support Activated
  no detectado en ese frame, `caller.retry_after_sell`. MANUAL con0Stamina y sin
  nuevo Start. Captura final muestra Activated; replay posterior score.99656,
  por lo que no se baja threshold ni se repite compra. `MaoSupport` ahora observa
  pasivamente el estado ya existente hasta6s cuando no detecta active/ready/needs.
  Regresión prueba recuperación hacia active sin input y timeout sin compra.
  No se fuerza otro Inventory Full para reproducir artificialmente esta animación.
  Se retorna desde config conocido al Lobby con navegación existente.
- `representative02`, run `d62dc9b8207b484bbcdddb2444399ff1`, Session
  `d9d24df09b1d46728e983ff4c28f9bb2`,15:28:03→15:42:40Z: **COMPLETED** por
  límite autorizado4operaciones.2Manual Chaos06 (531→471→411Stamina), Sapphire
  51→75→107; MW100Sapphire, Badge2→106; HARD104used/88won; vuelve Lobby con
  Badge2/Sapphire7. Presupuesto120/120, probe siguiente positivo. Sin Shared setup.
  No equivale a una sesión larga liberando Shared; es validación representativa
  de los owners y handoffs afectados. ROI VP inicial más ancha incluyó parte de
  Overall Rank (`182,0700` / `182,070C`): omite correctamente y ciclo sigue COMPLETED.
  Se recorta a.633 sin bajar confianza; el frame real acredita182070 en replay.
- `vp_focal`, run `cc3f9349dcbe486883de299d6280f815`, Session
  `2881836b71154740b2b3db64fa4f3a90`,15:46:13→15:48:34Z: **COMPLETED**,0Stamina,
  dos operaciones y techo8badges. Config sólo del smoke: mínimoBadge8/Sapphire1;
  no altera rutina guardada. Preflight fresco Badge2/Sapphire7. MW observa Badge12 /
  Sapphire0; HARD8used/0won retorna al Lobby conBadge4. El batch pequeño no autoriza
  regla de80badges ni cambia el adaptativo. A las15:48:19Z el hook productivo guarda
  **Eilla182050**, observación15:48:18.818101Z, semana`2026-10-05`.
  Reapertura SQLite confirma valor/timestamp/período, schema2 y otros27sin VP.
  GUI proyecta182k; captura confirma texto total182,050. No se suma desde rewards.

Todos los runtimes de adquisición/smoke cerrados por sus context managers.
Último estado físico acreditado: Eilla clean Lobby, Badge4/Sapphire0; sin operación
física pendiente. No se restaura Shared de las sesiones históricas desde incertidumbre.
Último runtime cerrado15:48:34.949708Z. HEAD y staged conservados; diff --check limpio.

Sin campaña28/28, cambios del adaptativo ni restauración Shared desde incertidumbre.
La validación acotada prueba las rutas afectadas, no garantiza toda sesión futura
de duración arbitraria ni adquiere un reset físico del lunes ya definido por USER_GT.
La evidencia de una nueva sesión continua600Stamina sigue pendiente del uso ordinario.
Revisión y aislamiento del checkpoint: [informe](ARENA_STABILIZATION_CHECKPOINT_20261010.md).
