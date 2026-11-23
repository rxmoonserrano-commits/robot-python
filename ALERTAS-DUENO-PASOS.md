# Alertas del dueño — 5 variables para que el robot te avise (una página)

Por qué importa: el robot ya contesta 24/7 (v3.4.2, 18 nov 2026), pero sin
estas 5 variables el dueño NO se entera: los correos de handoff, de cita
confirmada y de lead caliente no llegan, el reporte del lunes no sale,
`/pausa` y `/reporte-semanal` quedan cerrados y el webhook acepta sin
verificar la firma de Meta. El robot contesta igual; lo que se pierde es
el aviso para ti. Todo se pega en Render → servicio `robot-whatsapp-python`
→ pestaña **Environment**. Nombres exactos para copiar y pegar:

```
OWNER_EMAIL
GMAIL_USER
GMAIL_APP_PASSWORD
ADMIN_TOKEN
META_APP_SECRET
```

## 1. OWNER_EMAIL — a qué correo llegan las alertas
Pon tu correo real (el de tu app en el Explorador: `jserranosopenas@icloud.com`).
Sin esto, las alertas van a `dueno@empresa.com` y no llegan a nadie.

## 2. GMAIL_USER + GMAIL_APP_PASSWORD — que el robot pueda mandar correo
- `GMAIL_USER`: tu Gmail completo (ej. `tucorreo@gmail.com`).
- Contraseña de aplicación (NO tu clave de Google): en tu cuenta Google →
  Seguridad → Verificación en 2 pasos → Contraseñas de aplicaciones →
  Correo. Google te da 16 letras: esas van en `GMAIL_APP_PASSWORD`.

## 3. ADMIN_TOKEN — tu llave de dueño
Inventa una clave larga y guárdala (solo se muestra una vez). Con ella
abres `/pausa` y `/reporte-semanal`:
`https://robot-whatsapp-python.onrender.com/pausa?token=TU_CLAVE`

## 4. META_APP_SECRET — que el webhook verifique a Meta
En Meta for Developers → tu app **Prueba Oficial** (3233605353503540) →
Configuración básica → **Secreto de la app** → Mostrar → copiar. Ese
valor va en `META_APP_SECRET`.

## Cierre (2 minutos)
1. Guarda las 5 variables en Render → **Manual Deploy > Deploy latest commit**.
2. Abre la hoja "Robot WhatsApp — Documento oficial" → pestaña **Diagnóstico**:
   deben salir OK `gmail`, `owner_email`, `admin_token` y `meta_firma`.
3. Prueba de humo: en WhatsApp pide una cita y confirma con los botones.
   Debe llegarte el correo "¡Nueva cita!".

Si algo sale AVISO o FALLO en Diagnóstico, ese renglón dice exactamente qué
falta. Nota: las citas siguen cayendo en el calendario del robot (no en tu
Calendar personal) hasta compartir tu calendario y poner su ID en
`CALENDAR_ID`; eso es un paso aparte, no bloquea las alertas.

Hecho para Jose, 18 de noviembre de 2026 (día de descanso, con laptop).
