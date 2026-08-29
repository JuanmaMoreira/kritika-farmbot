# Instrucciones operativas

Reglas permanentes para cualquier trabajo de Codex en este repositorio.

## Fuentes y lectura

- Leer siempre `AGENTS.md`.
- Código y tests determinan qué está implementado. `CONTEXT.md` resume el estado actual, `ARCHITECTURE.md` los contratos vigentes, `ROADMAP.md` el trabajo próximo y `docs/HISTORY.md` los antecedentes.
- No cargar completos `CONTEXT.md`, `ROADMAP.md` o `ARCHITECTURE.md` por defecto: inspeccionar headings, buscar términos y leer sólo las secciones necesarias. Consultar historia únicamente cuando haga falta trazabilidad.
- Si documentación y código discrepan, señalar la contradicción y corregirla cuando esté dentro del alcance; no inventar una resolución.
- Antes de editar un archivo largo, localizar y releer el rango vigente. Aplicar patches pequeños sobre texto verificado.

## Entorno local

- Consultar `AGENT_LOCAL.md` antes de redescubrir Python, ADB o scrcpy-server. No asumir que están en `PATH`.
- `AGENT_LOCAL.md` es machine-local, no contiene secretos ni seriales y nunca se versiona; `AGENT_LOCAL.example.md` documenta su formato.
- Ejecutar tools Python que importan módulos internos desde la raíz y como módulos, preferentemente con `./tools/agent_run.ps1 tools.nombre <args>`. No usar `python path/to/tool.py` salvo que la tool declare un import path independiente.
- No hardcodear resoluciones, device IDs ni paths absolutos portables. Derivar geometría de `frame.shape` y mantener lifecycle/cleanup explícitos para sources, procesos, sockets y forwards.

## Límites de arquitectura

- Perception observa y emite semántica; no navega ni decide gameplay.
- `ContextResolver` resuelve observaciones; no captura, ejecuta acciones ni conserva policy de flows.
- Los flows contienen intención de negocio y solicitan operaciones semánticas; no hacen matching ni llaman ADB directamente.
- `ActionExecutor` traduce intents validados a input físico; no reconoce pantallas ni decide qué jugar o comprar. `AdbClient` es el único límite activo de comandos ADB.
- Rotation es transversal al orquestador y no pertenece a ningún flow. `AdsManager` permanece desacoplado de la percepción normal del juego.
- Toda acción con postcondición observable fiable debe verificarse antes de continuar. Si no existe una señal robusta, documentarlo y usar policy conservadora.
- Todo retry debe estar bounded y protegido por un estado fresco (`state-guarded`) que autorice exactamente repetir esa acción. `UNKNOWN` nunca autoriza input ni retry.
- No volver a concentrar configuración, percepción y acciones en `constants.py` ni otro archivo monolítico. Tratar legacy como conocimiento preservado, no como arquitectura runtime objetivo.

## Alcance y diseño

- No expandir el alcance ni implementar features fuera del trabajo activo sin una necesidad concreta. Evitar abstracciones, configurabilidad y recovery anticipados sin consumidor o evidencia.
- Discutir intención de negocio, outcomes y policy con el usuario antes de una implementación grande de flows o gameplay.
- Preferir componentes deterministas, pequeños y testeables sin hardware. No introducir dependencias sin justificación.
- Actualizar `CONTEXT.md` cuando cambie el estado real, `ARCHITECTURE.md` cuando cambien contratos o responsabilidades y `ROADMAP.md` al completar o repriorizar trabajo. Reservar `CHANGELOG.md` para milestones, migraciones, releases o capacidades importantes.

## Git, datos y salida

- Verificar referencias antes de borrar datos, capturas o assets potencialmente valiosos.
- No versionar datasets grandes, `screencaps/`, `artifacts/`, logs, caches, `.env` ni `AGENT_LOCAL.md`. Los manifests curados y assets runtime bajo `assets/` sí pueden versionarse.
- No persistir identidad de dispositivo o usuario salvo necesidad del dato. No hacer push sin instrucción explícita ni reescribir historia. El tag `legacy-pre-hybrid` preserva el runtime anterior.
- Preservar cambios ajenos. Antes de commit, revisar `git status --short` y diff acotado; después confirmar tree limpio.
- Preferir output conciso (`pytest -q`, `git status --short`, `git diff --stat`, `git log --oneline`, `rg` acotado). Ampliar sólo el error y contexto necesarios.

## Tests y hardware

- Durante implementación, ejecutar primero tests dirigidos. Antes de commitear código, ejecutar una vez la suite hardware-free completa y las regresiones productivas relevantes.
- En calibración semántica, usar positivos, negativos relevantes, contextos visualmente próximos y regresiones conocidas como loop dirigido. Al integrar, evaluar detectores nuevos/modificados contra el corpus curado existente y detectores productivos contra evidencia nueva; reutilizar la cache incremental válida para pares viejos sin cambios.
- Al elegir futuras ROIs, evitar zonas de overlays dinámicos conocidos sólo cuando puedan ocultar o interferir realmente con el contenido observado y exista una alternativa estable. La intersección geométrica no basta: verificar layering y evidencia antes de recalibrar; si el landmark pertenece a un popup/overlay renderizado por encima del chat, no cambiar su ROI sólo por intersectarlo. Antes de promover una ROI base en la franja superior, auditar la oclusión dinámica del chat y, si no es posible salir de esa zona, exigir positivos reales con chat visible.
- Reservar el full audit desde cero para cambios de infraestructura/preprocessing compartido, recalibraciones amplias, sospecha de cache inválida o auditorías explícitas. Acelerar nunca significa retirar negativos relevantes ni relajar aceptación.
- Para docs-only o tooling que no importa runtime, validar formato, referencias y comportamiento dirigido; no repetir la suite completa sólo por Markdown. Si HEAD ya coincide con un checkpoint validado, el tree está limpio y no hubo código posterior, no volver a probar ese baseline.
- Los tests normales deben funcionar sin teléfono. Toda prueba física es separada, explícita y opt-in; no iniciar el juego ni enviar input sin autorización dentro de la tarea.
- Los smokes rutinarios de runtime/hardware se hacen sólo cuando son necesarios, son breves y los ejecuta el usuario desde la GUI productiva después de tests y commit local. Codex hace validación live guiada sólo cuando adquisición semántica, diagnóstico difícil, ground truth o un pedido explícito lo requieren.
- Una prueba física autorizada debe detenerse antes de efectos no requeridos y asegurar cleanup al finalizar o fallar.

### Human-in-the-loop

- En pruebas físicas, chat + `steer` es el canal principal. Si hace falta navegación, confirmación de pantalla, ground truth o una decisión humana, detenerse en un punto seguro, pedir la acción semánticamente y continuar sólo tras la respuesta.
- Preferir navegación normal del usuario mientras Codex observa y registra evidencia. Workbench y su teclado son instrumentación, no el canal conversacional.
- Nunca inferir confirmación humana, ground truth, causalidad o destino semántico desde un tap, una predicción o una transición visual.
