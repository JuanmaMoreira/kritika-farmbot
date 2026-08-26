# Instrucciones operativas

Estas reglas son permanentes para cualquier trabajo realizado por Codex en este repositorio.

## Lectura obligatoria

Antes de realizar cambios significativos:

1. Leer `AGENTS.md`.
2. Leer `CONTEXT.md`.
3. Leer `ROADMAP.md`.
4. Consultar `ARCHITECTURE.md` cuando el cambio afecte diseño, responsabilidades o límites entre módulos.

## Fuentes de verdad

- El código y los tests determinan qué está implementado.
- `CONTEXT.md` resume el estado técnico vigente y las decisiones cerradas.
- `ARCHITECTURE.md` describe el diseño vigente y los límites acordados.
- `ROADMAP.md` contiene únicamente trabajo futuro.

Si la documentación contradice al código, no inventar una resolución. Señalar la discrepancia y, cuando el alcance lo permita, corregir la documentación.

## Reglas para cambios

- No expandir el alcance sin necesidad.
- No implementar features fuera de la fase actual del roadmap.
- No introducir dependencias sin una justificación concreta.
- No hardcodear device IDs ni paths absolutos.
- No volver a convertir `constants.py` ni otro archivo en una fuente monolítica de configuración, percepción y acciones.
- En la arquitectura 0.2, mantener los flows separados de percepción y comandos ADB directos.
- Mantener `AdsManager` desacoplado de la percepción normal del juego.
- Preferir componentes testeables sin hardware cuando sea posible.
- Tratar la implementación legacy como conocimiento preservado, no como arquitectura objetivo.

## Git y datos

- Verificar referencias antes de borrar datos, capturas o assets potencialmente valiosos.
- No versionar datasets grandes, `screencaps/`, logs, caches ni `.env`.
- Los assets runtime curados bajo `assets/` sí pueden versionarse.
- No hacer push remoto salvo instrucción explícita.
- No reescribir historia Git salvo instrucción explícita.
- El tag `legacy-pre-hybrid` preserva el estado anterior al rediseño 0.2.

## Documentación

Actualizar:

- `CONTEXT.md` cuando cambie el estado real o se cierre una decisión importante.
- `ARCHITECTURE.md` cuando cambie el diseño o la responsabilidad de una capa.
- `ROADMAP.md` al completar o repriorizar trabajo.
- `CHANGELOG.md` solo para milestones, migraciones, releases o capacidades importantes.

No usar `CHANGELOG.md` como diario por commit, archivo o función.

## Trabajo con hardware

- Los tests normales deben poder ejecutarse sin teléfono cuando sea razonable.
- Las pruebas que requieran un dispositivo físico deben estar separadas, identificadas y ser opt-in.
- No ejecutar scripts que hagan taps, swipes o modifiquen el dispositivo sin que la tarea lo requiera expresamente.

### Protocolo human-in-the-loop

- En cualquier prueba con dispositivo físico, el chat + `steer` es el canal principal de comunicación con el usuario.
- Si Codex necesita que el usuario navegue, abra o cierre una pantalla, confirme un estado, asigne ground truth o tome una decisión humana, debe detenerse en un punto seguro, pedir esa acción explícitamente por chat en lenguaje semántico normal y continuar sólo después de recibir la respuesta mediante `steer`.
- No usar `stdin`, prompts de terminal, menús de consola, códigos numéricos ni secuencias abstractas de teclas como canal principal para obtener información del usuario.
- La UI y el teclado de Perception Workbench son instrumentación, no el protocolo de conversación con el usuario.
- Sólo exigir interacción directa con Workbench cuando esa interacción sea parte específica de lo que se está validando o sea necesaria para registrar ground truth. Antes debe explicarse por chat qué acción concreta se necesita y confirmarse que la ventana es visible.
- Incluso cuando Workbench requiera una tecla, describir primero la acción semántica por chat; no hacer que el usuario tenga que interpretar una máquina de estados o una secuencia abstracta de controles.
- Preferir que el usuario navegue normalmente desde el dispositivo físico mientras Codex observa y registra evidencia.
- Nunca inferir una confirmación humana, ground truth o destino semántico a partir de un tap, una predicción o una transición visual.
