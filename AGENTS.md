# Instrucciones operativas

Reglas permanentes para cualquier trabajo de agentes en este repositorio. Mantener este archivo como contexto operativo; la historia y el estado detallado viven en la documentación del proyecto.

## Fuentes y alcance

- Leer siempre `AGENTS.md`. Código y tests determinan qué está implementado; `CONTEXT.md` resume el estado, `ARCHITECTURE.md` los contratos, `ROADMAP.md` el trabajo próximo y `docs/HISTORY.md` los antecedentes.
- No cargar completos `CONTEXT.md`, `ROADMAP.md` o `ARCHITECTURE.md` por defecto: inspeccionar headings, buscar términos y leer sólo las secciones necesarias. Consultar historia sólo para trazabilidad.
- Si documentación y código discrepan, señalar la contradicción y corregirla únicamente si está dentro del alcance; no inventar una resolución.
- Antes de editar un archivo largo, localizar y releer el rango vigente. Usar patches pequeños sobre texto verificado.
- Mantener prompts e informes compactos; referenciar checkpoints y evidencia ya documentados en vez de repetirlos.

## Cambio mínimo basado en evidencia

- Seguir este orden: `evidencia observada → primera divergencia causal → clasificación → cambio mínimo → validación afectada → stop`.
- No mejorar sistemas vecinos “ya que estamos”, convertir un bug local en refactor transversal ni añadir configurabilidad, recovery o abstracciones sin un consumidor y evidencia actuales.
- No crear state machines, lifecycle frameworks, policies, coordinadores o abstracciones transversales por valor potencial futuro. Exigir varios casos reales que demuestren una necesidad compartida.
- Si la causa parece arquitectónica, detener la implementación, exponer evidencia y propuesta, y acordar el cambio antes de ampliar el alcance.
- Discutir intención de negocio, outcomes y policy con el usuario antes de una implementación grande de flows o gameplay.

## Responsabilidades y diseño

- Explicar cada input físico principalmente por `estado observado actual + intención actual del flow + transición/recovery explícito`. Si requiere múltiples caches, leases, fallbacks, policies o estado oculto, revisar el diseño.
- Perception observa y emite semántica; no navega ni decide gameplay. Los hot paths deben evitar trabajo perceptivo irrelevante; percepción global/exhaustiva pertenece principalmente a discovery, recovery o evaluación.
- `ContextResolver` resuelve observaciones; no captura, ejecuta acciones ni conserva policy de flows.
- Los flows contienen intención de negocio y solicitan operaciones semánticas; no hacen matching ni llaman ADB.
- Transition/action verifica si ocurrió el efecto esperado. Recovery vuelve a un estado conocido. La policy de sesión decide qué hacer con el resultado del flow.
- `ActionExecutor` traduce intents validados a input físico; no reconoce pantallas ni decide qué jugar o comprar. `AdbClient` es el único límite activo de comandos ADB.
- Rotation es transversal al orquestador y no pertenece a un flow. `AdsManager` permanece desacoplado de la percepción normal.
- Verificar toda postcondición observable fiable. Si no existe una señal robusta, documentarlo y usar policy conservadora.
- Todo retry debe ser bounded y estar autorizado por estado fresco para repetir exactamente esa acción. `UNKNOWN` y `AMBIGUOUS` nunca autorizan input ni retry.
- Evitar archivos monolíticos que vuelvan a mezclar configuración, percepción y acciones. Tratar legacy como conocimiento preservado, no como arquitectura runtime objetivo.
- Preferir componentes deterministas, pequeños y testeables sin hardware. No introducir dependencias sin justificación.

## Validación por invalidación

- Usar la validación más barata que pueda falsar razonablemente el cambio, en este orden:
  1. diff, formato, referencias, análisis estático y sintaxis;
  2. tests directamente afectados;
  3. regresiones del subsystem y consumidores inmediatos;
  4. suite hardware-free completa para integración amplia o checkpoint de código;
  5. evaluator incremental de detectores/lectores afectados, reutilizando cache válida;
  6. corpus completo/global sólo ante invalidación amplia concreta;
  7. hardware/HIL para propiedades físicas o ground truth no demostrables offline.
- Repetir una validación cara sólo si un cambio posterior puede alterar su resultado. Una suite o corpus recién verde sigue vigente mientras nada relevante lo invalide.
- Mapeo mínimo: docs → formato/links; telemetry → tests de telemetry; routing → flow/runtime; OCR reader → OCR y consumidores; ROI/template/detector → evaluator incremental; `ContextResolver` → evaluación semántica/resolver; infraestructura del evaluator, preprocessing compartido o sospecha de cache inválida → posible auditoría amplia.
- Antes de ejecutar full corpus/global, responder concretamente: “¿Qué cambió que puede modificar estos resultados?”. Sin respuesta, no ejecutarlo. Tres full corpus para un fix acotado son un error de proceso salvo tres invalidaciones genuinas distintas.
- En calibración usar positivos, negativos relevantes, contextos visualmente próximos y regresiones conocidas. Acelerar no permite retirar negativos ni relajar aceptación.
- Para trabajo docs/process-only o tooling que no importa runtime, no ejecutar la suite completa. Si HEAD coincide con un checkpoint validado y no cambió código, no retestar ese baseline.

## Hardware y HIL

- Hitboxes, taps tragados, geometría de swipe, latencia/interactividad real, loading, animaciones, overlays físicos y comportamiento temporal del dispositivo requieren HIL cuando sean relevantes. Offline valida seguridad e invariantes; no sustituye un smoke físico corto con centenares de tests sintéticos.
- Los tests normales funcionan sin teléfono. Toda prueba física es separada, explícita y opt-in; no iniciar el juego ni enviar input sin autorización de esa tarea.
- El usuario opera teléfono y GUI productiva. Chat + `steer` es el canal HIL principal; workbench y teclado son instrumentación.
- Detenerse en un punto seguro cuando haga falta navegación, confirmación de pantalla, ground truth o decisión humana. Nunca inferirlos desde un tap, una predicción o una transición visual.
- Los smokes rutinarios son breves y se hacen sólo cuando aportan evidencia que offline no puede dar. Toda prueba autorizada detiene efectos no requeridos y asegura cleanup al finalizar o fallar.

## Entorno local

- Consultar `AGENT_LOCAL.md` antes de redescubrir Python, ADB o scrcpy-server; no asumir que están en `PATH`.
- `AGENT_LOCAL.md` es machine-local, no contiene secretos ni seriales y nunca se versiona; `AGENT_LOCAL.example.md` documenta su formato.
- Ejecutar tools Python con imports internos desde la raíz y como módulos, preferentemente con `./tools/agent_run.ps1 tools.nombre <args>`.
- No hardcodear resoluciones, device IDs ni paths absolutos portables. Derivar geometría de `frame.shape` y mantener cleanup explícito de sources, procesos, sockets y forwards.

## Datos, Git y documentación

- Verificar referencias antes de borrar datos, capturas o assets. No descartar evidencia rara o costosa de reproducir sin revisar sus consumidores.
- No versionar datasets grandes, `screencaps/`, `artifacts/`, logs, caches, `.env` ni `AGENT_LOCAL.md`. Sí pueden versionarse manifests curados y assets runtime bajo `assets/`.
- Separar adquisición/evidencia de implementación salvo razón concreta. Raw vive temporalmente bajo `artifacts/`; la evidencia promovida son manifests, curados y assets revisados.
- Preservar cambios ajenos. Antes de commit revisar `git status --short`, diff acotado y archivos staged; después confirmar el estado final.
- Hacer commits pequeños y conceptualmente coherentes. Una feature riesgosa o por fases necesita checkpoints intermedios claros y un baseline estable preservado.
- No hacer push, reescribir historia ni borrar branches/datos sin instrucción explícita.
- Actualizar `CONTEXT.md` cuando cambie el estado real, `ARCHITECTURE.md` cuando cambien contratos y `ROADMAP.md` al completar o repriorizar trabajo. Reservar `CHANGELOG.md` para milestones, migraciones, releases o capacidades importantes.
- Preferir output conciso (`pytest -q`, `git status --short`, `git diff --stat`, `git log --oneline`, `rg` acotado) y ampliar sólo el error relevante.

## Routing y trabajo costoso

- Usar un agente principal generalista para implementación normal, bugs no triviales, diseño, integración y checkpoints.
- Usar un agente ligero y operativo para HIL, adquisición, curación, calibración ROI/OCR, análisis de logs, auditorías mecánicas, tests dirigidos y fixes locales con causa clara.
- Reservar revisión arquitectónica excepcional para problemas transversales demostrados y decididos explícitamente. No seleccionar el recurso más caro sólo porque está disponible.
- Antes de full suite repetida, full corpus, evaluator grande, reprocesamiento/adquisición masivos o migración amplia, indicar brevemente qué se ejecutará, qué cambio lo invalidó y por qué no alcanza una validación más barata.

## Stop conditions

- Detener implementación y reportar cuando un fix acumule excepciones; sostenga una abstracción reciente con varias abstracciones nuevas; toque sistemas no relacionados; requiera demasiado estado implícito para una acción simple; o sea más complejo que el comportamiento del juego.
- También detenerse si cuesta explicar el próximo input, si offline permanece verde pero hardware rompe repetidamente, o si el diseño se conserva principalmente por sunk cost.
- Considerar explícitamente simplificación, partial revert, reimplementación local o reconstrucción desde el último checkpoint estable. El costo ya invertido no justifica portar o preservar complejidad.
