# Correo en Render — Gmail o iCloud, 5 minutos (Aloara)

_Fecha: 2026-11-24, actualizado 2026-11-26 (v3.22.0: correo saliente
configurable). Una sola cosa: que el robot pueda mandar correo. Sin
esto, los correos de handoff y el reporte semanal NO salen
(Diagnóstico lo marca AVISO en `gmail`), aunque el robot conteste
igual. `OWNER_EMAIL` debe ser el correo donde quieres RECIBIR las
alertas (tu iCloud si solo tienes ese)._

El robot manda correos por SMTP. Elige el camino que te toque:

## Camino A — iCloud (Apple) — si solo tienes correo de Apple

### Paso 1 — Tu contraseña de aplicación (2 min, en tu cuenta Apple)

1. Entra a [appleid.apple.com](https://appleid.apple.com) → **Inicio de
   sesión y seguridad** → **Contraseñas específicas de aplicaciones**
   → genera una para el robot.
2. Copia la contraseña que te da Apple: esa es tu `SMTP_PASSWORD`.
   Es un secreto: no la compartas; si la pierdes, revócala en la
   misma pantalla y crea otra.

### Paso 2 — Pégalas en Render (2 min)

Render → servicio `robot-whatsapp-python` → pestaña **Environment** →
agrega estas variables exactas (copia y pega):

```
SMTP_HOST=smtp.mail.me.com
```

```
SMTP_PORT=587
```

```
SMTP_USER=jserranosopenas@icloud.com
```

```
SMTP_PASSWORD=<la contraseña de aplicación de Apple>
```

```
OWNER_EMAIL=jserranosopenas@icloud.com
```

Guarda → **Manual Deploy > Deploy latest commit**.

## Camino B — Gmail (si algún día lo usas)

### Paso 1 — Tu contraseña de aplicación (2 min, en tu cuenta Google)

1. Entra a tu cuenta Google → **Seguridad** → **Verificación en 2 pasos** → **Contraseñas de aplicaciones**.
2. Nombre de la app: `Aloara Render` → **Crear**.
3. Google te muestra 16 letras (con espacios). Copia las 16 letras **sin espacios**: esas son tu `GMAIL_APP_PASSWORD`.

### Paso 2 — Pégalas en Render (2 min)

Render → servicio `robot-whatsapp-python` → pestaña **Environment** → agrega:

```
GMAIL_USER=jserranosopena@gmail.com
```

```
GMAIL_APP_PASSWORD=<las 16 letras sin espacios>
```

Guarda → **Manual Deploy > Deploy latest commit**.

## Paso 3 — Verifica (1 min, igual para los dos caminos)

1. Abre la hoja "Robot WhatsApp — Documento oficial" → pestaña **Diagnóstico**: el renglón `gmail` debe decir **OK** ("Correo configurado: handoffs y reporte llegan").
2. Prueba de humo: en WhatsApp pide una cita y confirma con los botones. Debe llegarte el correo **"Tienes una nueva cita"** a tu `OWNER_EMAIL`.

## Lo que esto NO arregla (para que no te sorprenda)

- `ADMIN_TOKEN` y `META_APP_SECRET` siguen en AVISO hasta que los pongas (son otros dos pasos, aparte): sin `ADMIN_TOKEN` no abren `/pausa` ni `/reporte-semanal` manual; sin `META_APP_SECRET` el webhook no verifica la firma de Meta.
- Los recordatorios por plantilla siguen esperando la aprobación de `recordatorio_cita` en Meta. Eso es otro paso.

Verificado contra el código: `robot/salud.py` marca `gmail` OK solo si hay usuario y contraseña de correo saliente (`correo_configurado()`); `robot/mail.py` manda por el SMTP configurado (`correo_saliente()`).
