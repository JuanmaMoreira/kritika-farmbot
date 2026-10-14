---
name: failure-triage
description: Investigar FAILED, MANUAL_RESOLUTION o interrupciones de Session en Kritika desde evidencia existente; diagnóstico sin iniciar fixes ni hardware.
---

# Diagnóstico causal

Aplicar [AGENTS](../../../AGENTS.md). Usar este procedimiento para un intento identificado, no para una auditoría general. Diagnosticar no autoriza implementar: si el encargo es sólo investigación, terminar con el informe.

1. Localizar ejecución y versión/config efectiva, run/session/character/operation y evidencia disponible. Buscar IDs y terminales primero; leer ventanas focales con contexto anterior suficiente, no logs completos. No atribuir al HEAD actual los bytes de un runtime histórico sin prueba.
2. Reconstruir esperado → observación → guard → acción → efecto → terminal hasta la primera divergencia. Separar error terminal, causa raíz y consecuencias propagadas; no contar la propagación flow→Session como fallos independientes.
3. Contrastar eventos, píxeles y su procedencia, ContextResolver, guards y código/tests del owner. Consultar sólo el rango pertinente de GT/contrato; para correlación o evidencia ausente, cargar [mapa de evidencia](references/evidence-map.md).
4. Distinguir hechos acreditados, hipótesis y evidencia ausente. Una captura posterior positiva no explica el corte previo. Reportar qué dato discriminaría hipótesis sin iniciar adquisición ni fabricar una causa.
5. Acreditar el último estado físico observado y efectos económicos; separar consumo confirmado, consumo incierto y ausencia de prueba. Revisar qué aceptaciones anteriores siguen válidas y cuáles invalida la divergencia; no convertir interrupción en permiso de retry o restauración.
6. Entregar diagnóstico con referencias focales, primera divergencia, owner, propuesta mínima de fix, validación que podría falsarla y límites residuales. Si hay fix autorizado, continuar con el procedimiento de desarrollo dentro de ese alcance; no modificar por haber completado el diagnóstico.
