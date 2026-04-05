# ROADMAP - Kritika FarmBot

## Prioridad Alta (próximas 1-2 semanas)
- [ ] Terminar de capturar **todos** los assets de contextos faltantes y completar `constants.py`
- [ ] Integrar completamente la lógica de **prioridad** y clase `Boton` a toda la estructura de `constants.py`

## Prioridad Media
- [ ] Armar **procesos específicos** (o "specific_flows") que funcionen dentro de un contexto principal:
  - El proceso asume que ya estamos en ese contexto (el caller debe garantizarlo antes).
  - Ejemplos:
    - En contexto `friends` → mandar solicitud a todos los recomendados
    - En contexto `black-market` → comprar todos los objetos que se vendan por oro
  - Nota: No quiero mezclar esto con los `flows.py` grandes. Prefiero mantener `flows.py` para flujos completos de alto nivel y usar otro nombre (process / specific_process / subflow) para estos encapsulados.
- [ ] Implementar e integrar una función que permita **leer números y texto en pantalla** (OCR ligero o template matching de dígitos) para:
  - Leer stamina disponible de personaje
  - Otros valores dinámicos (oro, gemas, etc.)

## Prioridad Baja / Ideas futuras
- [ ] Hacer que el bot genere un registro (`.csv` o similar) por personaje con recursos importantes (stamina, oro, items clave, etc.) para poder consultarlos sin entrar al juego ni interrumpir el bot.