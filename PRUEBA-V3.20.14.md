# Prueba v3.20.14 — Rescate de JSON y recuperación de mensajes (10 min)

**Versión esperada:** 3.20.14 (construida y probada: suite 54/54 verde).
**En vivo: v3.20.14 CONFIRMADA** — /estado reportó `version: "3.20.14"` con
`arranque_iso: "2026-11-25T22:22:34.096227+00:00"` (verificado 2026-11-25
15:22 MST / 22:22 UTC). Al momento de la verificación `salud_lista: false`
y `webhooks_recibidos: 0` — normal, el chequeo de salud tarda ~2 min en
arrancar. Espera ~2 min y refresca /estado antes de la prueba.

## Qué arregla

1. **La respuesta de la IA ya no se rompe:** el tope de Gemini subió de
   600 a 1500 tokens y, si el JSON viene roto o truncado, el robot
   rescata `respuesta_texto` y manda la respuesta real (AVISO en
   Diagnóstico, no FALLO).
2. **Un reinicio ya no pierde mensajes:** al arrancar, el robot busca en
   Conversaciones los mensajes de cliente sin respuesta (últimas 12 h)
   y los atiende. Queda constancia en Diagnóstico como `recuperacion`.

## La prueba en vivo

1. **Subida: HECHA** ✅ — la v3.20.14 ya está en vivo en Render
   (versión 3.20.14 confirmada en /estado a las 22:22 UTC).
2. **Espera ~2 min** y refresca `/estado`: debe decir `version: "3.20.14"`,
   `salud_lista: true` y `salud_iso` con hora reciente. Si sigue en
   `salud_lista: false` pasados 5 min, revisa Diagnóstico.
3. **Recuperación automática:** al arrancar, el robot debe contestar
   solo los dos mensajes pendientes del 2026-11-25:
   - "Hola buenas tardes" del número 5216678551299
   - tu "okay gracias"
   Si llegan esas respuestas, la recuperación funciona. En Diagnóstico
   debe aparecer `recuperacion` AVISO: "Recuperé 2 mensaje(s) sin
   respuesta de 2 teléfono(s)".
4. **Respuesta real:** manda desde tu personal un mensaje nuevo, ej.
   "hola, cuánto cuesta la limpieza?". Debe llegar una respuesta real
   (no el genérico "Dame un momento..."). Si el JSON vino roto y se
   rescató, en Diagnóstico aparece `gemini` AVISO "JSON de Gemini roto
   o truncado; se rescató respuesta_texto...".
5. **Segundo número:** manda un mensaje desde el otro número y verifica
   lo mismo: respuesta real + fila nueva en Clientes.

## Si algo falla

- Sin respuesta tras 2 min: revisa `/estado` (webhooks_recibidos debe
  subir) y Diagnóstico (componentes `recuperacion`, `gemini`).
- Si la recuperación no contestó los pendientes: revisa que en
  Diagnóstico aparezca la fila `recuperacion`; si dice AVISO con el
  error, mándame captura.
