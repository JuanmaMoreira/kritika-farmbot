---
name: kritika-dev-workflow
description: Desarrollar o depurar Kritika FarmBot con cambio mínimo, causa demostrada y validación proporcional. Usar para implementación normal y bugs; no para campañas puras de adquisición HIL.
---

# Kritika development workflow

Aplicar las políticas permanentes del `AGENTS.md` raíz mediante un ciclo corto y causal.

## Ciclo

1. **Observe:** reunir el fallo, log, test, frame o contrato que demuestre el problema. Separar hechos de hipótesis.
2. **First causal divergence:** localizar el primer punto donde la ejecución observada se aparta de la esperada. No empezar por síntomas posteriores.
3. **Classify:** decidir si la causa es local, transversal o física.
4. **Minimal change:** corregir el owner más estrecho que pueda resolver la divergencia sin cambiar policy vecina.
5. **Minimal validation:** recorrer la escalera de `AGENTS.md` sólo hasta el nivel capaz de falsar el cambio. Registrar qué resultado previo quedó invalidado.
6. **HIL if physical:** pedir un smoke corto cuando la incógnita sea hitbox, gesto, timing, loading, animación, overlay o respuesta real del dispositivo.
7. **Stop:** cerrar cuando la causa quedó corregida y la evidencia afectada pasa. No continuar con mejoras oportunistas.

## Local o transversal

- Tratar como local una divergencia con un owner y contrato claros, aunque exista una generalización posible.
- Proponer cambio transversal sólo cuando varios casos reales exhiban la misma causa y el contrato compartido reduzca complejidad total.
- Si una solución necesita nuevas policies, coordinadores, lifecycles o varias capas de fallback, detener el patch y presentar evidencia, costo y alternativa simple antes de seguir.

## Validation decision

- Nombrar qué cambió y qué resultados puede alterar.
- Reutilizar toda validación previa no invalidada.
- Antes de trabajo inusualmente caro, comunicar comando/alcance, invalidación concreta y por qué el nivel anterior no alcanza.
- No usar tests sintéticos para declarar probada una propiedad física.

## Terminado

La tarea termina cuando la primera divergencia causal está resuelta, pasan las validaciones afectadas, se obtuvo HIL cuando la propiedad era física, el diff no contiene trabajo vecino y `git status` preserva cambios ajenos. Actualizar documentación sólo cuando el estado o contrato real haya cambiado.
