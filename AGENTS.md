# Instrucciones operativas

Estas reglas son permanentes para cualquier trabajo de Codex en este repositorio.

## Lectura documental eficiente

1. Leer siempre `AGENTS.md`.
2. No cargar automáticamente completos `CONTEXT.md`, `ROADMAP.md` y `ARCHITECTURE.md`.
3. Antes de leer un documento largo, inspeccionar headings, buscar los términos de la tarea y abrir sólo las secciones necesarias.
4. Usar `CONTEXT.md` para el estado técnico actual y las decisiones funcionales vigentes.
5. Usar `ROADMAP.md` principalmente para trabajo activo, siguiente y dependencias relacionadas.
6. Consultar `ARCHITECTURE.md` sólo cuando la tarea afecte componentes, contratos, data flow o límites entre capas.
7. Consultar `docs/HISTORY.md`, `docs/legacy/` u otros documentos históricos únicamente cuando hagan falta antecedentes.
8. No cargar cronología histórica cuando el código y los contratos actuales basten.
9. Antes de editar un archivo largo, localizar el heading/rango vigente y aplicar patches pequeños sobre texto verificado. Si falla el contexto, releer sólo esa región y reintentar de forma acotada; no construir patches grandes desde texto recordado.

## Fuentes de verdad

- El código y los tests determinan qué está implementado.
- `CONTEXT.md` resume estado real y decisiones cerradas.
- `ARCHITECTURE.md` define diseño, contratos y responsabilidades vigentes.
- `ROADMAP.md` concentra trabajo activo y futuro; lo completado aparece sólo como índice breve.
- `docs/HISTORY.md` conserva etapas, experimentos y evidencia anteriores; no se lee por defecto.
- `CHANGELOG.md` registra milestones, migraciones y capacidades importantes, no actividad diaria.

Si la documentación contradice al código, no inventar una resolución: señalar la discrepancia y corregirla cuando entre en el alcance.

## Entorno local de agentes

- Consultar `AGENT_LOCAL.md` antes de redescubrir Python, ADB o scrcpy-server.
- Usar las rutas registradas allí y redescubrir una herramienta sólo si su ruta deja de funcionar.
- `AGENT_LOCAL.md` es machine-local, no contiene secretos ni device serials y nunca se versiona.
- `AGENT_LOCAL.example.md` documenta el formato portable.
- No asumir que `python` o `adb` están en `PATH`.
- Desde la raíz, ejecutar las tools Python que importan módulos internos como módulos: `& <PYTHON_EXE> -m tools.nombre <args>`, preferentemente mediante `.\tools\agent_run.ps1 tools.nombre <args>`. No usar `python path/to/tool.py` salvo que la tool declare explícitamente un import path independiente.

## Límites de arquitectura 0.2

- Perception observa y emite semántica; no navega ni decide gameplay.
- `ContextResolver` resuelve observaciones; no captura, no ejecuta acciones y no conserva policy de flows.
- Los flows contienen intención de negocio y solicitan acciones semánticas; no hacen matching ni llaman ADB directamente.
- `ActionExecutor` traduce intents validados a input físico; no reconoce pantallas ni decide qué jugar o comprar.
- `AdbClient` es el único límite activo de comandos ADB.
- Al implementar o modificar un camino de interacción, auditar también sus acciones preexistentes afectadas: buscar toda postcondición observable fiable y verificarla antes de continuar; no asumir éxito sólo porque se envió input ni inventar señales débiles. Si el efecto no es verificable, documentarlo explícitamente y aplicar policy conservadora.
- Rotation es transversal al orquestador y no pertenece a ningún flow.
- `AdsManager` permanece desacoplado de la percepción normal del juego.
- No volver a concentrar configuración, percepción y acciones en `constants.py` ni en otro archivo monolítico.
- Tratar el código legacy como conocimiento preservado, no como arquitectura runtime objetivo.
- Derivar geometría desde `frame.shape`; no hardcodear resoluciones, device IDs ni paths absolutos portables.
- Mantener lifecycle y cleanup explícitos para sources, procesos, sockets y forwards adquiridos.

## Alcance y cambios

- No expandir el alcance ni implementar features fuera del trabajo activo sin necesidad concreta.
- No introducir dependencias sin justificación.
- Preferir componentes deterministas y testeables sin hardware.
- Actualizar `CONTEXT.md` cuando cambie el estado real o se cierre una decisión importante.
- Actualizar `ARCHITECTURE.md` cuando cambien diseño o responsabilidades.
- Actualizar `ROADMAP.md` al completar o repriorizar trabajo.
- Actualizar `CHANGELOG.md` sólo para milestones, migraciones, releases o capacidades importantes.

## Git y datos

- Verificar referencias antes de borrar datos, capturas o assets potencialmente valiosos.
- No versionar datasets grandes, `screencaps/`, `artifacts/`, logs, caches, `.env` ni `AGENT_LOCAL.md`.
- Los manifests curados y los assets runtime bajo `assets/` sí pueden versionarse.
- No hardcodear ni persistir identidad de dispositivo o usuario cuando no sea parte necesaria del dato.
- No hacer push salvo instrucción explícita y no reescribir historia Git salvo instrucción explícita.
- El tag `legacy-pre-hybrid` preserva el estado anterior al rediseño 0.2.

## Salida de herramientas

- Preferir output conciso: `pytest -q`, `git status --short`, `git diff --stat`, `git log --oneline` y búsquedas `rg` acotadas.
- No imprimir por defecto archivos, logs, diffs, árboles del repo ni output exitoso completos.
- Ante un fallo, ampliar sólo el error y el contexto necesarios.
- Para documentos largos, buscar heading o término y leer el rango relevante.

## Política de tests

- Durante implementación, ejecutar primero tests dirigidos y ampliar según el área modificada.
- Antes de commitear cambios de código, ejecutar una vez la suite hardware-free completa y las regresiones productivas relevantes.
- Para cambios docs-only o tooling que no importa runtime, validar formato, referencias y comportamiento dirigido; no ejecutar automáticamente cientos de tests sin razón técnica.
- Si `HEAD` coincide con un checkpoint ya validado, el tree está limpio y no hubo cambios, no repetir la suite sólo para volver a demostrar ese baseline.
- La optimización de ejecuciones redundantes no reduce la cobertura exigida al cerrar cambios de código.

## Trabajo con hardware

- Los tests normales deben funcionar sin teléfono; toda prueba física es separada, identificada y opt-in.
- No iniciar el juego ni enviar taps, swipes, keyevents u otro input físico sin autorización expresa dentro de la tarea.
- Una prueba autorizada debe detenerse antes de una acción con efecto no requerido y asegurar cleanup al finalizar o fallar.
- Los smokes rutinarios de runtime/hardware los ejecuta el usuario desde la GUI productiva después de que Codex implemente, valide con tests dirigidos, ejecute la suite hardware-free completa, haga commit local y entregue instrucciones mínimas.
- Codex reserva las pruebas live guiadas para adquisición semántica, ground truth humano, diagnóstico difícil o pedido explícito del usuario; no repite de oficio un smoke rutinario ya delegable a la GUI.

### Protocolo human-in-the-loop

- En pruebas físicas, chat + `steer` es el canal principal con el usuario.
- Si hace falta navegación, confirmación de pantalla, ground truth o una decisión humana, detenerse en un punto seguro, pedir la acción semánticamente por chat y continuar sólo tras la respuesta.
- No usar `stdin`, menús de terminal, códigos numéricos ni secuencias abstractas de teclas como canal principal.
- Workbench y su teclado son instrumentación; exigir interacción directa sólo cuando sea lo validado o sea necesaria para registrar ground truth, explicándolo antes por chat.
- Preferir navegación normal del usuario en el dispositivo mientras Codex observa y registra evidencia.
- Nunca inferir confirmación humana, ground truth, causalidad o destino semántico desde un tap, una predicción o una transición visual.
