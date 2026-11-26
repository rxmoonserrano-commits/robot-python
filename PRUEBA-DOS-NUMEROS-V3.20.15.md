# Prueba de dos números — v3.20.15 (10 min, cierra la demo)

**Para:** mañana en tu ventana de la mañana (~30 min) o esta noche (~1 h).
**Versión esperada:** 3.20.15 — construida y probada; en vivo y estable
desde el 2026-11-25 (los 2 mensajes pendientes quedaron respondidos
con respuestas reales, de a uno, sin reinicios).
**Robot:** +52 669 100 1402 · **Tu personal:** +52 669 460 8263 ·
**Otro número de prueba:** 5216678551299.

## Antes de empezar (1 min)

1. Abre `/estado` del robot: debe decir `version: "3.20.15"` y
   `salud_lista: true`. Anota el número de `webhooks_recibidos`.
2. Si el plan gratis estaba dormido, el primer mensaje puede tardar
   ~1 min en despertar. Es normal.

## La prueba (5 min)

**Mensaje 1 — desde tu personal (+52 669 460 8263) al robot:**
copia y pega exactamente:

```
hola, cuánto cuesta la limpieza?
```

Debe llegar una respuesta **real** (no el genérico "Dame un
momento...") con el precio de la limpieza ($600, de Conocimiento).

**Mensaje 2 — desde el otro número (5216678551299) al robot:**
copia y pega exactamente:

```
hola buenas tardes, qué servicios tienen?
```

Debe llegar una respuesta real con los servicios y precios, y una
fila nueva en Clientes para ese número.

**Opcional — agenda completa (si tienes tiempo):** desde tu
personal responde a la propuesta con los botones de agendar y
confirma. Debe quedar la cita en la pestaña Citas y en el
calendario.

## Cómo verificar (3 min)

- [ ] `/estado`: `webhooks_recibidos` subió (al menos +2).
- [ ] Las 2 respuestas llegaron reales, con precios.
- [ ] Clientes: fila nueva para 5216694608263 y para 5216678551299.
- [ ] Conversaciones: los 2 mensajes registrados.
- [ ] Diagnóstico: sin FALLO nuevo.
- [ ] Espera 5 min y refresca `/estado`: el servicio sigue arriba
      (sin reinicios — la corrección de la v3.20.15 aguanta).

## Si algo falla

- Sin respuesta tras 2 min: refresca `/estado` (webhooks debe
  subir) y revisa Diagnóstico (`gemini`, `recuperacion`). Si
  aparece `gemini` AVISO de JSON rescatado, el cliente igual
  recibió respuesta real — eso está bien.
- Si el servicio se reinicia: mándame captura de `/estado` y de
  Diagnóstico; NO reintentes mandando muchos mensajes seguidos.

## Al terminar

Mándame captura de `/estado` y de las filas de Diagnóstico. Con
eso cierro la demo en vivo y quedas listo para el primer cliente
piloto.

## Pendientes que NO bloquean esta prueba

- Gmail en Render (contraseña de app) — para que salgan correos de
  handoff y reportes.
- Plantilla `recordatorio_cita` en Meta — para recordatorios en vivo.
- Corrida dorada de 34 conversaciones en tu Mac.
