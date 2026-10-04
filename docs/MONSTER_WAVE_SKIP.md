# Monster Wave SKIP — contrato actual

`IMPLEMENTATION_CONTRACT`. [GAMEPLAY_GT](GAMEPLAY_GT.md) posee mecánicas, clases físicas y tooltip; [RESOURCE_ROUTING](RESOURCE_ROUTING.md), preparación/reliefs y wiring; [CONTEXT](../CONTEXT.md), divergencias. Calibraciones y validaciones anteriores: [snapshot histórico](legacy/DOC_RESET_20260925.md), sin gates vigentes derivados de conteos.

## Activity

**USER_GT / product policy:** el propósito productivo de MW es gastar Sapphires mediante SKIP para obtener rewards. Resource routing y todos los reliefs actuales son fallbacks ante presión/capacidad; no son el objetivo del flow ni flows de limpieza standalone.

Por personaje, preparación una vez y pasadas en loop. La preparación no debe confundirse con cada pasada productiva. No hay Start manual fuera de la pasada SKIP, ni Auto Battle MW, ni countdown persistido.

```text
entry Lobby/hub → saldo fresco y sapphire_pressure_passes (flow productivo)
  <102 → no work, sin navegar/entrar a MW
  ≥102 → presupuesto mínimo esperado para salir de pressure → MW
→ normalizar Weekly Results / New Ranking si aparecen
→ comprobar SKIP al comienzo de cada personaje:
  si ACTIVE, no reactivar; si no activo, preparación necesaria para activarlo
→ seleccionar MAX una sola vez al comienzo (la selección persiste entre pasadas)
→ loop productivo de pasadas SKIP (operación de una pasada conceptualmente reusable;
  el flow productivo normal la ejecuta en loop y futuros flows podrán ejecutar
  una sola pasada sin duplicar la lógica):
  Start SKIP → resource board? → espera bounded paciente → CLEAR / insufficient sapphires / blocker observado
→ saldo fresco tras cada CLEAR; recalcular pressure hasta <102
→ resultado/superficie verificada; caller pide el próximo handoff
```

Activity admite como máximo dos acknowledgements de entrada, sin suponer orden/coexistencia. Preparación (compra/activación/selección MAX) es single-attempt por personaje: no repite compra/activación/MAX por timeout. Cada pasada SKIP observa su propio resultado. Cancelación/contradicciones paran; las navegaciones externas conservan sus guards bounded.

En entrada/reentrada MW: MODAL conocido → normalizar primero (`popup.monster_wave_weekly_results` / `AcknowledgeMonsterWaveWeekly`, Previous Season Rewards; `popup.monster_wave_new_ranking` / `AcknowledgeMonsterWaveRanking`). El source verificado de `OpenMonsterWave` efectivo y el landmark fresco inequívoco del MODAL autorizan sólo su ACK aunque la BASE sea UNKNOWN; no fabrican `screen.monster_wave`. Tras cada ACK se verifica el cambio/desaparición en snapshot fresco y se reevalúa desde arriba. Sólo sin MODAL pendiente, si la BASE sigue irresuelta y falta una señal necesaria cuya ROI intersecta H&H, se intenta recovery on-demand una vez. CONFIRMED → dismiss → ABSENT fresco → reevaluar entrada completa, incluidos MODAL; no se repite Open ni se navega. Un fallo de executor, contradicción, stale o modal desconocido no autoriza ACK ni este recovery.

- Si SKIP está NEEDS_TICKETS, Productive MW usa Fill All para completar 30/30 con Gold, verifica READY, activa SKIP y continúa. Faltar tickets no es condición terminal.
- Fill All se usa exactamente una vez por preparación y nunca ticket por ticket; luego READY verificado permite activar. ACTIVE directo omite compra y activación. No simular saldo ni timer entre personajes. Si el juego rechaza la compra por Gold insuficiente, fallo cerrado sin repetir compra ni inventar saldo.
- MAX consume como máximo 100 Sapphires por pasada. El flow productivo usa `sapphire_pressure_passes` para aliviar hasta <102; no intenta vaciar el saldo por objetivo ni da por probado el decremento. MAX se despacha como dos taps consecutivos de un intent una sola vez al comienzo del personaje; no es un retry ni se repite por pasada. Implementación actual comprueba ACTIVE, MAX, controles adyacentes visibles y tooltip ausente antes de Start. Tooltip persistente termina por espera bounded, sin taps compensatorios. Esta implementación no convierte OCR/títulos decorativos en GT ni exige nuevo framework.
- En cada resource board: sin presión → YES para permitir ejecutar el SKIP; con presión → NO para cancelar, ejecutar los reliefs necesarios, restaurar MW y reintentar la intención productiva.
- Después de YES, esperar de forma bounded pero paciente mediante polling aproximadamente cada 1 s; no asumir una latencia fija de 5 s.
- Sapphires consumidos se contabilizan sólo después de una señal de éxito confirmada, actualmente `CLEAR` u otra señal futura establecida. `CLEAR` se reconoce, confirma y continúa/retorna según el loop; si falla el retorno, no ocultar el fallo técnico con el evento de gameplay.
- `insufficient sapphires` queda como terminal/fallback defensivo; usa No, nunca compra premium. No hace falta provocar deliberadamente una pasada extra si el saldo inicial permitió calcular las pasadas.
- `yield_resource_board=False` conserva respuesta Yes/No configurada. Con `True`, RESOURCE_BOARD_PENDING entrega popup abierto y `board_sequence` fresca sin Yes/No/Back posteriores; el caller debe consumirlo conforme a la regla YES-sin-presión / NO-con-presión anterior.

## Composición real

L1 productivo consume el handoff mediante una preparación única y reanuda el mismo request. L2 local atiende Equipment/Socket después del resume; dentro del retry/relief de una misma pasada/request bloqueado no se repite board/planner/J. Cada nueva pasada del farming loop obtiene y evalúa su propio resource board fresco y puede producir una decisión/plan nuevo —rewards de una pasada pueden crear presión para la siguiente—; no reutilizar snapshot/plan entre pasadas. Componentes presentes **no** significan callbacks completos: ver RESOURCE_ROUTING. El loop productivo y la operación de una pasada reusable son contrato requerido; no declarar el loop cerrado por existir L1/L2. Un pending no consumido o MANUAL_RESOLUTION detiene SessionRunner, sin navegación ciega ni rotación. La rama No del blocker Socket post-relief tiene una policy GT diferente (tarea incompleta, siguiente personaje); no confundirla con ese terminal genérico ni declararla implementada por existir L2. Ningún relief actual es un flow de limpieza independiente; un futuro flow cuyo propósito sea limpiar recursos deberá declararse explícitamente como tal.

`MonsterWaveConfig` conserva dos booleanos, ambos false por defecto: `MW_PURCHASE_SKIP_TICKETS` y `MW_CONTINUE_WHEN_NONBLOCKING_INVENTORY_FULL`. El primero queda sin efecto en la preparación productiva (Fill All automático por USER_GT); el segundo acepta continuar con pérdida de rewards sobre límites. No hay política estratégica adicional implícita.

MW no tiene Eligibility: el badge Daily no gatea trabajo productivo. ProductiveMonsterWaveFlow
usa readiness fresca en Lobby antes de navegar y en hub reutilizado; <102 devuelve COMPLETED
con `monster_wave.no_work`, sin entrada/preparación/MAX. Saldo en pressure se verifica de nuevo
en prepare; después de cada CLEAR exige consenso fresco y recalcula con la misma primitive
que Stages/Gold Farming. UNKNOWN falla cerrado. Ejemplos: 101→0, 102→1, 201→1→101,
299→2→99, 300→2→100. No mínimo Daily de cuatro ni balance simulado. La API bare de compatibilidad
conserva sus primitivas; no define la estrategia económica productiva. WB mantiene Eligibility
y readiness propias; ejecutar MW no acredita elegibilidad WB/ToT.

El detector/fact del badge se conserva por sus consumidores independientes: contratos de contexto del hub/World Boss, scope de World Boss y corpus semántico compartido; no decide ejecución MW.

## Gaps reales

Craft, Keys/Gold, Materials y los callers Equipment/Socket están conectados; validación y límites concretos en CONTEXT/RESOURCE_ROUTING. Fill All con Gold insuficiente permanece UNKNOWN de baja prioridad; no adquirir ni bloquear MW por ello. Existe un MODAL adicional `Point Reward` (**USER_GT**, clase física establecida) que puede aparecer por encima de CLEAR al cruzar ciertos conquest points; el loop de resultado SKIP lo reconoce por su título, lo confirma con su OK y continúa con CLEAR mediante su lógica existente (`AcknowledgeMonsterWavePointsReward` → snapshot fresco → `AcknowledgeMonsterWaveClear`). Landmark del título literal nativo adquirido el 2026-10-02, excluye el glow de CLEAR y el reward variable. Evaluator incremental: positivo 0.99998, máximo negativo 0.28619 en 102 pares; replay full distingue Point antes de OK y CLEAR después. ACK live verificado antes de CLEAR. No inventar dismiss/ordering técnico más allá de este GT. No se exige repetir GT ni suite completa antes de cada smoke.

El flow bare/productivo finaliza gameplay en MW limpio y devuelve evidencia final, sin normalizar a Lobby ni hub. Session solicita a Navigation la entrada siguiente: Back→hub para otro Battle Mode, Quick Menu→Pets/Quests/Mailbox/Character Select directo desde una BASE con capability acreditada. Quests/Mailbox cierran al origen, confirmado fresco; Rotation no impone Lobby. Battle Mode Select también permite QM, pero para llegar a Lobby gana su Back directo. Back normalmente llega al hub; la rama Inventory puede llegar a Lobby (evidencia previa). Sólo si el siguiente entry requiere hub se reabre desde ese Lobby fresco. La API Activity de compatibilidad conserva su retorno hub por defecto; PreparedActivity productivo declara las superficies finales reutilizables. Handoff nuevo validado offline; el smoke anterior acredita la relación Back, no la composición nueva.
