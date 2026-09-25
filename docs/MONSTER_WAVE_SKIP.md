# Monster Wave SKIP — contrato actual

`IMPLEMENTATION_CONTRACT`. [GAMEPLAY_GT](GAMEPLAY_GT.md) posee mecánicas, clases físicas y tooltip; [RESOURCE_ROUTING](RESOURCE_ROUTING.md), preparación/reliefs y wiring; [CONTEXT](../CONTEXT.md), divergencias. Calibraciones y validaciones anteriores: [snapshot histórico](legacy/DOC_RESET_20260925.md), sin gates vigentes derivados de conteos.

## Activity

Una invocación ejecuta un proceso SKIP MAX. La cantidad resuelta por el juego no crea un loop del bot. No hay Start manual, Auto Battle MW, countdown persistido ni farming loop.

```text
hub → MW → normalizar Weekly Results / New Ranking si aparecen
→ observar NEEDS_TICKETS / READY / ACTIVE
→ comprar faltantes si se permite → activar si READY
→ double tap MAX → verificar estado funcional fresco → Start SKIP una vez
→ CLEAR / insufficient sapphires / resource board / blocker observado
→ handling de ese resultado y retorno contractual
```

Activity admite como máximo dos acknowledgements de entrada, sin suponer orden/coexistencia. Cada operación SKIP es single-attempt: no repite compra/activación/MAX/Start/confirmaciones por timeout. Cancelación/contradicciones paran; las navegaciones externas conservan sus guards bounded.

- NEEDS_TICKETS con compra deshabilitada termina con `tickets_missing_purchase_disabled`.
- Compra habilitada usa Fill All una vez y exige tickets completos frescos; luego READY permite activar. ACTIVE directo omite compra y activación. No simular saldo ni timer entre personajes.
- MAX se despacha como dos taps consecutivos de un intent; no es un retry. Implementación actual comprueba ACTIVE, MAX, controles adyacentes visibles y tooltip ausente antes de Start. Tooltip persistente termina por espera bounded, sin taps compensatorios. Esta implementación no convierte OCR/títulos decorativos en GT ni exige nuevo framework.
- Insufficient sapphires usa No, nunca compra premium. CLEAR se reconoce, confirma y retorna; si falla el retorno, no ocultar el fallo técnico con el evento de gameplay.
- `yield_resource_board=False` conserva respuesta Yes/No configurada. Con `True`, RESOURCE_BOARD_PENDING entrega popup abierto y `board_sequence` fresca sin Yes/No/Back posteriores; el caller debe consumirlo.

## Composición real

L1 productivo consume el handoff mediante una preparación única y reanuda el mismo request. L2 local atiende Equipment/Socket después del resume; no repetir board/planner/J. Componentes presentes **no** significan callbacks completos: ver RESOURCE_ROUTING. Un pending no consumido o MANUAL_RESOLUTION detiene SessionRunner, sin navegación ciega ni rotación. La rama No del blocker Socket post-relief tiene una policy GT diferente (tarea incompleta, siguiente personaje); no confundirla con ese terminal genérico ni declararla implementada por existir L2.

`MonsterWaveConfig` conserva dos booleanos, ambos false por defecto: `MW_PURCHASE_SKIP_TICKETS` y `MW_CONTINUE_WHEN_NONBLOCKING_INVENTORY_FULL`. El primero autoriza Fill All; el segundo acepta continuar con pérdida de rewards sobre límites. No hay política estratégica adicional implícita.

Contrato Daily: badge MW en el hub antes de actividad; ausencia estable omite, UNKNOWN no equivale a ausencia. Cuando se invoca con `daily_sapphires=True`, lee saldo fresco MW antes de compra/activación/MAX/Start: 0–3 devuelve business incomplete sin iniciar intento; ≥4 permite seguir; OCR inconcluso falla cerrado. Manual no impone ese mínimo. **Limitación actual:** Run Session prepara por tipo MonsterWaveFlow y omite el wrapper ProductiveMonsterWaveFlow; no declarar Daily productivo integrado hasta corregir ese binding separado.

## Gaps reales

Primero P0 Craft y callbacks de preparación/relief descritos en CONTEXT/RESOURCE_ROUTING; luego cierre físico L2. Lifecycle automático ante expiración SKIP sigue pendiente: pérdida de ACTIVE impide Start, no reactiva automáticamente. Fill All con Gold insuficiente permanece UNKNOWN de baja prioridad; no adquirir ni bloquear MW por ello. No se exige repetir GT ni suite completa antes de cada smoke.
