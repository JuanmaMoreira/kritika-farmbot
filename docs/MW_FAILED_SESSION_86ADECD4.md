# FAILED manual MW — 2026-10-06

## Ejecución y procedencia

- Baseline publicada: `d97e899b9fac3fbc26583d595b21abd4267b0ce9`, `rebuild/stable-baseline`.
- Log local: `logs/20261006T123851.620375Z_session_86adecd4.jsonl`.
- Run: `ff4b8797565f445695ef2cad0c2987ea`.
- Session: `c385af509b7c4b2ba214f169e8af3b7f`.
- Runtime abrió 2026-10-06 09:38:51 ART; Session empezó 09:39:05; FAILED 09:49:04.
- Request normal `character_count=28`, Basic Gold Farming, cinco steps; no Sweep ni smoke.
- Primer scope, `character_index=1`, `burst_breaker` / Burst Breaker, identidad resuelta.
- Step 3 Gold Farming, occurrence 1, actividad MW `final_investment`, attempt 2.
- Failure exacto: `mw_board_consensus_unavailable`, `legacy_error`, sin excepción de navegación.
- Failure evidence local: `failure_e6013d1403024e72bfb5c3e013f7ced5`.

`LIVE_EVIDENCE`: snapshots 6062/6072/6087 resuelven `screen.monster_wave` con
`popup.monster_wave_inventory_board`. Raw observations: MW title, SKIP process,
MAX selected, usage unobstructed, inventory board. No otro modal/base ni ambigüedad.
Capturas muestran BASE MW con resource board encima, no panel limpio disponible para Back.

## Cadena causal

1. Preparación anterior adquirió tickets, activó SKIP y seleccionó MAX. La inversión
   final entró con SKIP ACTIVE; no lo reactivó. MAX aparece seleccionado en evidencia.
   La auditoría final confirma dos selecciones reales, detalladas abajo; el FAILED
   A1 ocurre dentro del loop posterior, sin selección/repreparación adicional.
2. Último éxito: CLEAR reconocido y cerrado, seq5892, 09:48:44. Sapphire consensus
   seq5928/5942 confirmó276→176 a las09:48:48. Quedaba una entrada de pressure.
3. `monster_wave.start_skip` tuvo éxito con un input, board seq5999 a las09:48:55.
4. Primer par A1 seq6017/6026: gap0.906s, edad del segundo antes del reader1.265s.
   OCR necesitó1.157s; edad final2.422s, mayor al límite2s. Primer descarte causal,
   `fresh_mw_board_snapshot_unavailable`, evento1026. La resolución física era válida.
5. Segundo intento seq6049/6062 excedió el gap1s antes de OCR. Tercer par
   seq6072/6087 tiene timestamps1422.250/1423.734: gap1.484s. Percepción costó
   1.367/1.611s; descarte `mw_board_consensus_unavailable`, evento1034.
6. Tres intentos read-only agotados → Gold FAILED → Session FAILED, sin Rotation.
   No YES tras seq5999, ningún CLEAR final acreditado ni decremento Sapphire final.

No evidencia de sequence reuse ni snapshot de caller equivocado: todos los pares
fueron posteriores a5999 y distintos. El coste del scope, aun reducido, gastó su
propia ventana. No se atribuye el fallo al nuevo refactor Reliefs.

## Auditoría MAX antes del checkpoint

`IMPLEMENTATION_CONTRACT` + log: las transiciones `monster_wave.select_max`
298–301 (investment, source1675 →1698) y840–843 (final_investment,
source4844 →4859) terminaron `success_first_attempt`. No son dos verificaciones
read-only: `VerifiedTransition.execute` despacha siempre la acción antes del wait;
`ActionExecutor.execute(SelectMonsterWaveMax)` hace los dos taps consecutivos del
control según GT. La telemetría de estas transiciones no registra `action.dispatched`
porque ese executor se llamó sin EventSink; la atribución se apoya en la ruta de
código vigente del run y las dos transiciones completadas, no en eventos inventados.

Hay violación del contrato de selección única por personaje: la segunda preparación
ejecutaba `select_max` incondicionalmente aun con MAX persistente. Fix mínimo en
`MonsterWaveActivity.prepare`: si la entrada fresca acredita MAX seleccionado y
controles limpios, conservarlo; si acredita MAX pero falta readiness, fallar sin
retap. Sólo la rama de selección inicial mantiene los dos taps GT y verificación.
Sin latch nuevo, cambio del loop, bounds, cancelación, SKIP ni Sapphire accounting.
Regresión con dos activities/preparaciones independientes y tres passes verifica
una sola selección; otra protege selected-MAX sin controles. No nuevo smoke económico.

## Board y decisión siguiente

Replay real del reader en6072/6087 lee filas concordantes:

| Resource | Lectura |
| --- | --- |
| Brawler's Badges | hard pressure rojo; imagen muestra350/106 |
| Weapon Material |738/999 |
| Hero Weapon Material |67/999 |
| Bronze Key |238/499 |
| Silver Key |80/499 |

Badge pressure no tiene ruta Arena productiva. Ninguna fila gestionada alcanza su
entry threshold. Planner vigente: `NO_PREREQUISITES`; la continuación correcta es
YES una vez + `finish_pass` existente. Success físico seguiría requiriendo CLEAR y
consenso Sapphire nuevo;76 no se acredita por restar100.

## Fix y regresión

`MonsterWaveBoardPerception` se usa únicamente en el observer A1. Memoiza outputs
de `LocalCvDetector` puro por ROI grayscale exactamente igual y geometría igual,
con un entry por detector. El dominio memoizado coincide con los pixels que lee
su matching. Cualquier cambio invalida; specialized detectors siempre se ejecutan.
El batch y la resolución se reconstruyen con sequence/timestamp del frame nuevo.

No modifica templates, ROI, thresholds, resolver, spacing1s, edad2s, waits3s ni los
tres intentos existentes. No amplía ventanas, ni añade Back, tap, sleep o retry.
La memoización reduce trabajo repetido de chrome estático antes del reader; no
convierte observations viejas en facts nuevos cuando cambian pixels.

Evidencia curada portable: `tests/fixtures/mw_session_86adecd4`, capturas originales
del bundle de failure (960x433), raw observations y manifest con timings exactos.
`test_mw_failed_session_replay.py` reproduce old FAILED y fixed YES→finish con esas
escenas y latencia agregada modelada; el reader real verifica las cinco filas.
No se presenta esa simulación temporal como una calibración de templates nativos
ni como prueba de CLEAR físico nuevo. Tests extra invalidan cache por pixels y
mantienen identidades nuevas. Callers/guards conservan sus regresiones existentes.

## Validación live y límites

Smoke read-only productivo disponible en `tools.mw_board_readonly_smoke.py`: sólo
adquiere el board ya abierto, guarda timings/filas y cierra el owner de captura en
finally del runtime; cero inputs. Primer intento encontró frame vertical2712x1224
incompatible con templates horizontales, antes de cualquier input; se solicitó steer.
Tras «listo», smoke nativo 2026-10-06 10:38:28 ART, run
`e4f2d003e10146d0ac2e0609b535aa7a`, seq40/43: gap0.297s, edad final0.875s,
reader0.375s, cinco filas concordantes iguales al failure, accepted=true. Artifact
`artifacts/reliefs-mw-audit/readonly-live-result.json`; runtime.closed confirmado.
La adquisición causal queda verificada live sin inputs. La continuación económica
YES→finish está cubierta por replay; no se pidió ni acreditó un CLEAR físico nuevo.
No se inició otro28/28 ni se consumieron recursos.

Paridad offline sobre el frame nativo1224x2712 del mismo smoke: observaciones
idénticas entre percepción original, memoización fría y repetición exacta; batches
con sequence/timestamp nuevos.81 detectores puros reutilizados, coste0.354s frío
frente a0.104s repetido. Artifact `artifacts/reliefs-mw-audit/native-parity.json`.

Validación GUI real Light/Dark1100x760 y760x560, scroll hasta Treasure, Step Settings
sin relief controls, cuatro tabs y Save/reopen idéntico: artifact local
`artifacts/reliefs_gui_b810a723/audit.json`. No inicia Session ni toca el teléfono.
