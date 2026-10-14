---
name: kritika-dev-workflow
description: Investigar o corregir un defecto o cambio concreto de Kritika con validación afectada y alcance autorizado. No usar para auditorías generales ni adquisición pura.
---

# Desarrollo causal

Aplicar [AGENTS](../../../AGENTS.md). Elegir modalidad desde el encargo, no desde la capacidad del agente; indicar la elegida cuando aclare el alcance. Las modalidades no conceden permisos.

| Modalidad | Procedimiento y cierre |
| --- | --- |
| `diagnose-only` | Investigar con evidencia existente; usar [failure-triage](../failure-triage/SKILL.md) para FAILED/MANUAL/interrupción. Entregar causa/hipótesis, owner y propuesta; sin modificaciones ni hardware. |
| `fix-and-validate` | Investigar, corregir dentro del alcance y validar lo afectado. No iniciar live porque un test pase o falte evidencia física. |
| `full-live-ownership` | Añadir navegación y prueba física expresamente autorizadas, en el owner/harness pertinente. No amplía economía, publicación ni restauración manual. |

Para cambios autorizados:

1. Revisar estado/diff y localizar causa o contrato del cambio. Leer sólo código/tests y rangos de la fuente dueña que cambian la decisión.
2. Implementar en el owner existente y elegir validación capaz de falsar el cambio según AGENTS. Un fallo de la validación se investiga antes de ampliar el patch; conservar resultados aún válidos.
3. Continuar las acciones locales ya autorizadas sin confirmaciones redundantes. Si falta autorización necesaria, delimitar esa acción y seguir el trabajo independiente; no elevar modalidad por iniciativa propia.
4. En modalidad live, preparar evidencia y condición de aceptación antes de iniciar el recorrido. Primera divergencia → diagnóstico → fix sólo si autorizado → validación invalidada. La adquisición de una pregunta física abierta usa [kritika-hil-acquisition](../kritika-hil-acquisition/SKILL.md); no cargarla para un fix exclusivamente offline.
5. Cerrar con causa, cambio, validación y límites, actualizando sólo la fuente dueña. Cleanup de herramientas no autoriza restaurar manualmente el juego, repetir un consumo incierto ni publicar.
