# Prueba del número nuevo — v3.20.13 (esta noche, 10 min)

**Robot:** +52 669 100 1402 · **Tu personal:** +52 669 460 8263
**Phone Number ID:** 1407658669107360 · **WABA real:** 1795248078443059
**Versión esperada:** 3.20.13 (construida, sin subir — pendiente tu aprobación)

> Estado actual: el número ya está **registrado** en Meta (`registro_numero` OK tras el PIN), pero Meta no reenvía los mensajes al robot (0 webhooks) porque la app solo está suscrita a la cuenta de prueba. La v3.20.13 suscribe la app a tu cuenta real al arrancar.

## Paso 0 — Antes de subir (2 min, en Render)

En Render → servicio `robot-whatsapp-python` → **Environment**, agrega:

- Key: `WHATSAPP_WABA_ID`
- Value: `1795248078443059`

Guarda (Render redeploya solo). **No compartas capturas con tokens.**

## Paso 1 — Aprobar la subida (1 min)

En el chat, aprueba la tarjeta de subida de la v3.20.13. Render redeploya solo.

## Paso 2 — Confirmar que quedó en vivo (1 min)

Abre `/estado` del robot en Render. Debe decir:
- Versión **3.20.13**
- Salud **true**, sin errores

Si dice 3.20.12 todavía, espera 2 minutos y recarga.

## Paso 3 — Leer la suscripción (1 min)

En la hoja oficial, pestaña **Diagnóstico**, busca la fila `suscripcion_waba`.
- Si dice **OK** → sigue al paso 4.
- Si dice **AVISO** → copia esa fila y pégala en el chat; ahí se ve qué falló.

## Paso 4 — Mensaje de prueba (3 min)

Desde tu WhatsApp **personal** (+52 669 460 8263), manda al **+52 669 100 1402**:

```
Hola, ¿cuánto cuesta la limpieza?
```

Qué debe pasar:
1. El mensaje llega con **doble palomita**.
2. El robot responde con el precio desde Conocimiento, sin inventar.
3. En la hoja, pestaña **Conversaciones**, aparece tu mensaje.
4. El contador de **webhooks** en `/estado` sube de 0.

## Paso 5 — Probar una cita completa (5 min, opcional esta noche)

Sigue en el mismo chat:

```
Quiero agendar una limpieza para el sábado a las 10
```

Qué debe pasar: botones Confirmar / Cambiar hora / Hablar con una persona → toca **Confirmar** → llega la confirmación y la cita aparece en **Citas** y en el calendario.

## Si algo falla

| Síntoma | Qué hacer |
|---|---|
| `suscripcion_waba` AVISO | Copia la fila y pégala en el chat. Revisa que `WHATSAPP_WABA_ID = 1795248078443059` esté guardado en Render. |
| Sigue 0 webhooks con doble palomita | La suscripción no pasó: revisa la fila del paso 3. |
| Llega pero el robot no responde | Revisa `bot_activo = SI` en Control y que no haya pausa humana activa. |
| Responde pero no cae en la hoja | Revisa credenciales de Google en Render (Diagnóstico). |

## Pendientes que NO bloquean esta prueba

- Contraseña de Gmail en Render (correos de handoff y reportes).
- Plantilla `recordatorio_cita` en Meta.
- Corrida real de las 34 conversaciones doradas en tu Mac.
