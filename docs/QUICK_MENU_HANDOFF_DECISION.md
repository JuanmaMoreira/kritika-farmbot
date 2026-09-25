# Quick Menu — contrato de handoff

`IMPLEMENTATION_CONTRACT`; la [arquitectura](../ARCHITECTURE.md) posee el límite estable y [GAMEPLAY_GT](GAMEPLAY_GT.md) la clase OVERLAY/caller. Comparaciones y checkpoints anteriores: [snapshot histórico](legacy/DOC_RESET_20260925.md).

El normal path usa origen verificado: source limpio RESOLVED que autorizó el OpenQuickMenu efectivo → menú fresco posterior compatible → selección de tile permitido. Visibilidad del tile no autoriza por sí sola. UNKNOWN bajo el menú puede ser compatible con el handoff causal; UNKNOWN aislado no autoriza nada.

`action_source_snapshot` procede del último input efectivo, incluyendo retry legítimo; no del snapshot inicial por costumbre. `recovery_after_action` bloquea nuevo handoff desde cleanup. Recovery, AMBIGUOUS, base foreign o pérdida observada invalidan retry. Layout deriva del source; geometría del frame fresco. El resolver no conserva origen ni inventa una BASE.

Discovery/recovery observan estado actual sin fabricar lineage. Scopes deben conservar contradicciones relevantes; no reducir a tile+destino si desaparece esa evidencia. Este contrato no exige adquirir landmarks ocultos ni reconfirmar cada transición determinista cerrada por GT. Wiring/capacidades concretas, incluido Craft, se verifican en código y CONTEXT.
