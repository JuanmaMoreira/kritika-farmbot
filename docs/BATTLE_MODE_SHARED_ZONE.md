# Battle Mode — zona compartida

`IMPLEMENTATION_CONTRACT`. Ownership estable en [ARCHITECTURE](../ARCHITECTURE.md); estado MW/wiring en [CONTEXT](../CONTEXT.md) y [RESOURCE_ROUTING](RESOURCE_ROUTING.md). UI física en [GAMEPLAY_GT](GAMEPLAY_GT.md). Diseño/benchmark originales archivados en [snapshot](legacy/DOC_RESET_20260925.md).

- BattleModeZone posee entrada Lobby→hub y salida hub→Lobby; no gameplay, inventarios ni selección estratégica.
- PreparedActivity vincula actividad hub→hub, zona y precheck opcional. SessionRunner comparte la misma zona sólo entre posiciones consecutivas compatibles del orden seleccionado; un flow ajeno cierra la visita. Nunca reordena.
- Eligibility observa en el hub. NOT_ELIGIBLE descarta el precheck; sólo eligibility positiva consume el precheck de recursos. UNKNOWN/error conserva precedencia técnica. Un recurso insuficiente no se convierte en falta de elegibilidad.
- Activities poseen gameplay y reliefs caller-specific. La zona no conoce Socket, Combine, SKIP o Treasure. Retornos/caller se rigen por GT, no por el antiguo número de consumidores.
- Precondiciones y retornos fiables se verifican; failure/cancelación no navega a ciegas. El terminal de gameplay no oculta un fallo de cierre.

World Boss y MW tienen activity/wrapper; L1 productivo MW agrega preparación. El binding Daily de ProductiveMonsterWaveFlow sigue siendo un bug separado: `run_session` comprueba MonsterWaveFlow, no su wrapper productivo. Compartir zona no está garantizado para ese wrapper sólo porque exponga `prepared()`.
