# Prueba del número nuevo — v3.20.12 (esta noche, 10 min)

**Robot:** +52 669 100 1402 · **Tu personal:** +52 669 460 8263
**Phone Number ID:** 1407658669107360 · **WABA:** 1662274398730005
**Versión esperada:** 3.20.12 (commit b8601dc6, subida 2026-11-25 ~13:19 MST)

## Paso 1 — Confirmar que quedó en vivo (1 min)

Abre `/estado` del robot en Render. Debe decir:
- Versión **3.20.12**
- Salud **true**, sin errores

Si dice 3.20.11 todavía, espera 2 minutos y recarga.

## Paso 2 — Leer el registro automático (1 min)

En la hoja oficial, pestaña **Diagnóstico**, busca la fila `registro_numero`.
- Si dice que ya está Connected / registrado → sigue al paso 3.
- Si dice AVISO o error → copia esa fila y pégala en el chat; ahí se ve qué falló.

## Paso 3 — Mensaje de prueba (3 min)

Desde tu WhatsApp **personal** (+52 669 460 8263), manda al **+52 669 100 1402**:

```
Hola, ¿cuánto cuesta la limpieza?
```

Qué debe pasar:
1. El mensaje llega con **doble palomita** (antes se quedaba en una).
2. El robot responde con el precio desde Conocimiento, sin inventar.
3. En la hoja, pestaña **Conversaciones**, aparece tu mensaje.
4. El contador de **webhooks** en `/estado` sube de 0.

## Paso 4 — Probar una cita completa (5 min, opcional esta noche)

Sigue en el mismo chat:

```
Quiero agendar una limpieza para el sábado a las 10
```

Qué debe pasar: botones Confirmar / Cambiar hora / Hablar con una persona → toca **Confirmar** → llega la confirmación y la cita aparece en **Citas** y en el calendario.

## Si algo falla

| Síntoma | Qué hacer |
|---|---|
| Sigue una sola palomita | El número sigue "Pendiente" en Meta: revisa la fila `registro_numero` del Paso 2 y pásala en el chat. |
| Llega pero el robot no responde | Revisa `bot_activo = SI` en Control y que no haya pausa humana activa. |
| Responde pero no cae en la hoja | Revisa credenciales de Google en Render (Diagnóstico). |

## Pendientes que NO bloquean esta prueba

- Contraseña de Gmail en Render (correos de handoff y reportes).
- Plantilla `recordatorio_cita` en Meta.
- Corrida real de las 34 conversaciones doradas en tu Mac.
