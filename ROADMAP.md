# Roadmap — Kritika FarmBot 0.2

El orden es deliberado: estabilizar primero el baseline, luego reducir el costo perceptivo y recién después reconstruir Inventory Relief. No se portan commits experimentales en bloque.

## Fases

### 0. Baseline estable reconstruido — DONE

- Checkpoint productivo adoptado: `71340f58d3a4515facc346ad22addfc0d814a6ec`.
- Rama experimental preservada en `archive/inventory-relief-experimental` desde `024ff8e15f981930e3bab962ed116f1e9f3946fe`.
- Rama `rebuild/stable-baseline` creada sin mover `main`, borrar branches, reescribir historia ni hacer push.
- Baseline hardware-free canónica: 1925/1925.

### 1. Disciplina de agentes y skills — DONE

- `AGENTS.md` compacta el ciclo evidencia → primera divergencia causal → clasificación → cambio mínimo → validación mínima → stop.
- `kritika-dev-workflow` cubre desarrollo/diagnóstico ordinario.
- `kritika-hil-acquisition` cubre adquisición y calibración HIL.

### 2. Contexto documental reconstruido — DONE

- `CONTEXT.md` describe sólo el producto actual.
- `ARCHITECTURE.md` separa lo implementado de la dirección aceptada.
- `ROADMAP.md` vuelve a representar el orden real.
- `docs/HISTORY.md` conserva consolidación, experimento, regresiones, rollback y lecciones.
- La contradicción «Monster Wave sin commit/push» queda corregida sin alterar código.

### 3. Smoke corto del baseline — NEXT

Ejecutar desde la GUI productiva una prueba breve y representativa, no otra rotación 28/28. Confirmar startup, composición y una transición física útil; detenerse al primer desvío causal. No modificar arquitectura durante el smoke.

### 4. Percepción acotada incremental

Elegir un único hot path estable, medir baseline, limitar detectores relevantes y conservar escalación amplia sólo donde haga falta. Validar tests dirigidos, benchmark y un smoke corto antes de avanzar al siguiente consumidor.

- Rotation R1 (`select_predecessor_character`) — DONE: 95→2 detectores, policy/reader local intactos, 2144/2144 hardware-free y smoke natural 1/1 hasta Lobby confirmado.
- Rotation R2-A (wait post-swipe Character Select) — DONE: reutiliza el subset semánticamente idéntico de R1, 95→2, `stable_for=1.0` y scroll/sentinel intactos; 2151/2151 hardware-free y HIL natural 1/1 con Lobby confirmado. R2-B (Select→Lobby) — DONE en B2: 95→77 con todas las dependencias de bases/overlays, sin cambiar policy, action count, retry ni recovery.
- World Boss WB-1 (elegibilidad Daily) — DONE: scope 95→5 en snapshot inicial y wait estable; 2152/2152 hardware-free y `Run Session` natural 1/1, sin cambiar policy ni inputs. WB-2 (D locales) queda diferido por falta de carry/freshness equivalente; WB-3 Start y WB-4 inventario mantienen percepción global porque `_is_known_incompatible` aborta sobre cualquier base RESOLVED/AMBIGUOUS y un subset pequeño la degrada a UNKNOWN. WB-5 retorno queda global por blockers de overlay amplio. No acotar selector, Previous Rewards, Continue ni Raid Complete hasta resolver autorización overlay-only, terminal contradictorio y freshness del poll.
- Quick Menu verified-origin handoff — DONE en correctness: el verificador expone action source y señal local de recovery; Rotation R2-C, select_lobby, select_guild y BattleModeZone.leave exigen provenance de apertura. R2-C sigue global: el scope de dos detectores pierde bases foreign que invalidan el token y las degrada a UNKNOWN + menu.quick, estado que con lineage podría permitir retry erróneo. B2 acota sólo el wait final de select_lobby/BattleModeZone.leave con vocabulario resolver-complete 95→77; opener y select_guild conservan global por vocabulario de bases/contradicciones no probado en scopes moderados. No adquirir landmarks bajo el panel para normal path.
- Clean Lobby / B2 — DONE en código: discovery/recovery y postchecks de sesión permanecen globales; CloseFriends, Mailbox, Daily, Black Market, ClosePets, select_lobby, BattleModeZone.leave y R2-B usan scopes nombrados de 77 detectores que preservan las 17 bases y los 57 overlays del catálogo. El landmark positivo `Trading Center` sigue seasonal-risk; scopes menores y snapshot reuse quedan diferidos por evidencia/contrato. Ver [`docs/CLEAN_LOBBY_B2_DECISION.md`](docs/CLEAN_LOBBY_B2_DECISION.md).

### 5. Estabilizar percepción acotada

Extender de a un flow, asegurar observaciones frescas, recovery y diagnóstico. Detener la expansión si aparecen estados omitidos, costo impredecible o acoplamiento con policy.

### 6. Inventory Relief simple

Reimplementar desde cero una sola operación causal y verificable, separada del gameplay. Reutilizar manifests, assets y conocimiento archival sólo después de confirmar que siguen siendo válidos. No portar el chain, sus APIs ni su lifecycle completo.

### 7. Integración por presión de recursos

Conectar relief al caller únicamente cuando un blocker fresco autorice la operación. Definir thresholds con evidencia, verificar progreso y retorno, y limitar reintentos. Ventas fallan cerradas ante rareza, tipo o costo inciertos.

### 8. Expansión de flows

Agregar capacidades de negocio una por vez, con contrato de entrada/salida, eligibility y postcondiciones. Priorizar casos simples y frecuentes; connection recovery, scheduler y estrategias avanzadas requieren necesidad concreta.

### 9. Tower — hacia el final

Adquirir evidencia propia y construir un vertical slice después de estabilizar los bloques anteriores. Arena y automatización más amplia permanecen posteriores y no están comprometidas.

## Criterios permanentes

- Código y tests prevalecen sobre documentación histórica.
- Ningún input desde `UNKNOWN`; todo retry es bounded y state-guarded.
- Perception, resolver, flows, Rotation, executor y ADB conservan sus límites.
- Primero tests dirigidos; una única suite hardware-free completa cuando el cambio lo justifique.
- Hardware es explícito, breve, opt-in y con cleanup.
- No ampliar alcance después de obtener la evidencia o validación buscada.
- No versionar raws, screencaps, artifacts, logs, caches ni configuración local.
