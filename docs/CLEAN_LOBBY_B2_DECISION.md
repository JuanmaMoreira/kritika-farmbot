# Clean Lobby — contrato vigente

`IMPLEMENTATION_CONTRACT`. [ARCHITECTURE](../ARCHITECTURE.md) posee ownership; [GAMEPLAY_GT](GAMEPLAY_GT.md), clasificación/oclusión. Auditoría de consumidores y cifras antiguas: [snapshot histórico](legacy/DOC_RESET_20260925.md), no instrucciones para repetir validaciones.

Clean Lobby significa `RESOLVED screen.lobby + overlays vacíos`. Discovery/recovery y postcondiciones de sesión usan observación global. Retornos conocidos pueden usar el scope resolver-complete existente: conserva dependencias del catálogo para bases/overlays, blockers y contradicciones, y omite readers que no alimentan resolución. Source, freshness, retry y recovery pertenecen al caller.

Los términos base/overlay de ese catálogo son técnicos, no clasificación física USER_GT. Este diseño implementado no obliga a declarar físicamente BASE a Friends/Mailbox/Quests/Black Market, ni autoriza usar landmarks expuestos a CHAT/Heaven & Hell.

El landmark Lobby ligado a temporada es una limitación conocida; un sustituto seguro/scoping menor requiere necesidad y evidencia pertinentes. No imponer nueva HIL si GT ya cierra la transición, ni extrapolar cifras históricas de detectores o tests como contrato de aceptación.
