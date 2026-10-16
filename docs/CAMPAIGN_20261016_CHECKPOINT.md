# Checkpoint correctivo del 16/10/2026

Baseline publicado de la campaña: `9989fd822b622f19ff6c8456dd5a5e7396b4c760`.
Rama: `rebuild/stable-baseline`. Cada corrección conserva un commit propio;
este documento registra sus validaciones y límites, sin promover la campaña
reanudada a una Session continua ni declarar una aceptación física global.

| Commit | Corrección | Aceptación y límite |
| --- | --- | --- |
| `bac627a` | WB→Socket bajo Heaven & Hell | Recovery físico acreditado en R3, evento140 de la campaña. Fuente/receipt/freshness/coverage y cancelación obligatorios; no repite Start ni ACK. |
| `46f03f7` | Terminal SDK compacta Reward granted + X | Dos landmarks conjuntos, Android ownership/foco concordantes, veto Next ad y freshness existente. Equivalencia/negativos offline; la rama Back nueva sigue pendiente de ocurrencia física natural. |
| `86a9a8f` | Causa técnica del composer Craft | Preserva CALLER_CONTEXT_FAILED/CALLER_EXECUTION_FAILED como STEP_FAILED y conserva stage/error. Excepciones inesperadas alcanzan al caller. Mantiene terminación sin nuevos inputs ni retries. No corrige ni explica la causa física desconocida de Hastati. |

## Validación reutilizada

Los bytes de código, tests y assets se contrastaron con los manifests del cierre;
no hubo invalidación que justificara repetir las pruebas. Se cambió únicamente
el campo de procedencia del fixture SDK a una ruta relativa al repositorio;
los píxeles, sus hashes y la lógica del test permanecen iguales.

- 587 pruebas finales aprobadas, en conjuntos disjuntos: 333 Ads/Stages/WB/recovery
  y 254 Craft/routing/composer/Character State/identidad/GUI.
- El primer run del segundo conjunto aprobó 222 y tuvo 32 errores de setup del
  temporal del sandbox; esas 32 aprobaron al repetir sólo su setup/tests con
  `--basetemp` dentro del workspace. No fueron fallos productivos.
- Replay SDK conservado: 5/5 frames de resolución original aceptados y 15/15
  negativos rechazados; uno de los thumbnails se rechaza conservadoramente.
- No se ejecutó gameplay ni un smoke adicional para este checkpoint.
- Ningún cambio al recognizer de identidad, guard económico, contrato Meteorites
  o configuración productiva. El USB sigue clasificado como incidente externo.

Procedencia local, excluida de Git:
`artifacts/supervision_gold28_20261016/closure/publication_validation.json`,
`targeted_tests.xml`, `state_tests.xml`, `existing_fixes_tests.xml`,
`../sdk_production_replay.json` y los manifests/bundles históricos.
El informe completo está en
`artifacts/supervision_gold28_20261016/closure/INFORME_CIERRE_20261016.md`.
Estas rutas documentan la evidencia local; no son dependencias de los tests
publicados. El fixture curado SDK pequeño sí se incluye con su manifest/hash.

## Estado de GUI y configuración antes de Arena

En este checkpoint siguen abiertos el launcher Python PID 8320 y su hijo GUI
PID 10992, creados el 16/10 a las 15:21:02−03. La procedencia acredita el código
`9989fd8` más WB/SDK anterior a los commits; el fix Craft del cierre se escribió
después. No hay atestación por módulo en memoria y esa GUI no debe tratarse como
una ejecución del nuevo HEAD. El último runtime de campaña terminó a las
19:04:30−03 (`runtime.closed`); no se inició otra Session en este checkpoint.

No se cerró, relanzó ni editó la GUI. Así se conserva también su draft en memoria.
`routines.json` mantiene el hash inicial de campaña
`ed51d0deb156f4af082488a2e72e9af05e4509bcd61c4fe76505ad0452671e4d`.
Ese JSON conserva seleccionada la rutina `arena cycle`; no prueba la selección efectiva de
una GUI abierta, cuya última Session observada fue Basic Gold Farming.

Antes del próximo relanzamiento, bajo el nuevo ownership autorizado:

1. Confirmar que no hay Session activa. Revisar y preservar el draft de la rutina
   editada mediante Save Routine cuando corresponda, o documentar sus opciones
   antes de descartar un cambio. Characters/Debug pertenecen sólo a la request
   en memoria; conservarlos aparte. No sustituir un draft por selected_id de disco.
2. Cerrar la GUI inactiva y comprobar salida de ambos procesos. Desde la raíz,
   comprobar HEAD y lanzar el módulo con el wrapper local:

   ```powershell
   git rev-parse HEAD
   .\tools\agent_run.ps1 tools.gui
   ```

   El wrapper obtiene Python/ADB/scrcpy de AGENT_LOCAL; no asumir PATH.
3. Acreditar que la nueva creación del proceso es posterior a este checkpoint y
   que sólo hay una GUI. Verificar visualmente rutina Arena efectiva, pasos,
   Reliefs, opciones y cantidad; Meteorites permanece OFF salvo nueva instrucción
   explícita. El arranque de GUI no equivale a iniciar una Session.
4. Sólo con el ownership Arena confirmado por el usuario, reacreditar conexión,
   Lobby, identidad y recursos físicos antes de empezar. Este checkpoint no hace
   esas operaciones ni toca el teléfono.

## Character State e identidad para Arena

Flame Striker, Eilla y Blade Dancer fueron reconciliados localmente por USER_GT a
Ads 0/WB YES del ciclo 5. Backup consistente y seis facts de procedencia se conservaron;
los otros 25 personajes no cambiaron. **No repetir la reconciliación.** Su epoch Ads
es 16/10 07:00Z; futuros resets legítimos siguen el reloj vigente, no esos valores
históricos fijados para siempre.

El primer identity_unknown dejó sus scopes sin asociación. Es correcto que el
store no escriba bajo UNKNOWN, pero los valores proyectados del reset quedaron
desactualizados respecto de la actividad física. La causa exacta de esos tres
misses no se reprodujo: nueve capturas curadas anteriores resolvieron 9/9.
No inferir identidad por posición de Rotation, no marcar Ads/WB pendientes por
ausencia de eventos ni usar el registro de otro personaje. Si vuelve a ocurrir,
conservar evidencia focal y separar la ejecución física del bookkeeping.
Arena VP y snapshots persistidos son informativos; los guards de recursos frescos
permanecen en sus owners y no se sustituyen por estos datos.

## Disponibilidad del siguiente ownership

No hay un bloqueo productivo demostrado que prohíba una campaña Arena acotada
con full-live-ownership. Quedan como preparación obligatoria preservar el draft,
relanzar con el HEAD publicado y acreditar el entorno/identidad. Los límites físicos
SDK/Craft y el miss de identidad se mantienen visibles; no exigen consumos extra
para publicar ni autorizan recuperaciones especulativas. Ante divergencia causal,
aplicar failure-triage y detener sólo la operación que no tenga recuperación segura.

Arena Cycle no se inició. Su arranque espera la revisión y confirmación del usuario.
