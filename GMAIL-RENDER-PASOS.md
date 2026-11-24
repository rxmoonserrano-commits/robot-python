# Gmail en Render — 2 variables, 5 minutos (Sereno)

_Fecha: 2026-11-24. Una sola cosa: que el robot pueda mandar correo. Sin esto, los correos de handoff y el reporte semanal NO salen (Diagnóstico lo marca AVISO en `gmail`), aunque el robot conteste igual. `OWNER_EMAIL` ya está OK (`jserranosopena@gmail.com`); solo faltan estas dos._

## Paso 1 — Tu contraseña de aplicación (2 min, en tu cuenta Google)

1. Entra a tu cuenta Google → **Seguridad** → **Verificación en 2 pasos** → **Contraseñas de aplicaciones**.
2. Nombre de la app: `Sereno Render` → **Crear**.
3. Google te muestra 16 letras (con espacios). Copia las 16 letras **sin espacios**: esas son tu `GMAIL_APP_PASSWORD`. Es un secreto: no lo compartas; si lo pierdes, revócalo en la misma pantalla y crea otro.

## Paso 2 — Pégalas en Render (2 min)

Render → servicio `robot-whatsapp-python` → pestaña **Environment** → agregar estas dos variables exactas:

```
GMAIL_USER=jserranosopena@gmail.com
GMAIL_APP_PASSWORD=<las 16 letras sin espacios>
```

Guarda → **Manual Deploy > Deploy latest commit**.

## Paso 3 — Verifica (1 min)

1. Abre la hoja "Robot WhatsApp — Documento oficial" → pestaña **Diagnóstico**: el renglón `gmail` debe decir **OK** ("Gmail configurado: handoffs y reporte llegan").
2. Prueba de humo: en WhatsApp pide una cita y confirma con los botones. Debe llegarte el correo **"¡Nueva cita!"** a `jserranosopena@gmail.com`.

## Lo que esto NO arregla (para que no te sorprenda)

- `ADMIN_TOKEN` y `META_APP_SECRET` siguen en AVISO hasta que los pongas (son otros dos pasos, aparte): sin `ADMIN_TOKEN` no abren `/pausa` ni `/reporte-semanal` manual; sin `META_APP_SECRET` el webhook no verifica la firma de Meta.
- Los recordatorios por plantilla siguen esperando la aprobación de `recordatorio_cita` en Meta. Eso es otro paso.

Verificado contra el código: `robot/salud.py` marca `gmail` OK solo si `GMAIL_USER` y `GMAIL_APP_PASSWORD` están puestas; `robot/mail.py` manda por `smtp.gmail.com:587` con esas dos. Esta hoja reemplaza la parte de Gmail de `ALERTAS-DUENO-PASOS.md` (18 nov, ya desactualizada).
