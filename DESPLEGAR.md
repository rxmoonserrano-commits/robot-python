# DESPLEGAR — Poner el robot en internet

> **No desplegar todavía:** las doradas y las integraciones reales siguen
> pendientes. No apuntes el webhook de pacientes reales hasta superar las
> pruebas y confirmar. El plan Starter tiene costo.

## Versión 3.0 — qué cambió al actualizar

Para actualizar un robot ya desplegado: sube el código nuevo a GitHub
y en Render dale a **Manual Deploy > Deploy latest commit**. No hay
que tocar Meta ni el webhook. Pero hay **dos variables nuevas** que
poner en Render (Environment) antes o después del deploy:

- **`ADMIN_TOKEN`** — la clave de dueño, que el instalador genera y
  muestra una sola vez (corre `python instalar.py` en tu Mac y
  cópiala). Sin ella, `/pausa` y `/reporte-semanal` están cerrados.
  Guarda la página de pausa en tu teléfono:
  `https://TU-DIRECCION.onrender.com/pausa?token=TU_CLAVE`
- **`META_APP_SECRET`** — el secreto de la app de Meta (Meta for
  Developers → tu app → Configuración básica → Secreto de la app →
  Mostrar). Con él, el robot verifica que cada webhook venga de Meta
  de verdad. Sin él, el webhook rechaza la solicitud con 503 y la
  revisión de salud registra un fallo.

También nuevo en la v3.0: al arrancar, el robot revisa su salud y la
escribe en la pestaña **Diagnóstico** de la hoja (Gemini, Sheets,
Calendar, token de WhatsApp, Gmail, claves). Mírala después del
primer deploy: si algo dice FALLO, ahí está el error exacto.

**Sigue pendiente (solo lo puede hacer Jose):**
- **Token permanente de WhatsApp.** El temporal dura 24 horas; al
  vencerse, el robot deja de contestar (error 401 en Diagnóstico y en
  los Logs). Sácalo en Meta y ponlo en Render como `WHATSAPP_TOKEN`.
- **Contraseña de aplicación de Gmail.** Sin ella no llegan los
  correos de handoff ni el reporte semanal del lunes. El robot
  contesta igual, pero esos correos no llegan. Pon `GMAIL_USER` y
  `GMAIL_APP_PASSWORD` en Render (Environment) y redeploya.
- **Calendario del dueño.** Comparte el calendario del negocio con
  el correo de la cuenta de servicio (Editor) y pon su ID en
  `CALENDAR_ID` en Render, en vez de `primary`. Si no, las citas
  caen en el calendario del robot y no se ven en tu app.

El robot tiene que estar prendido 24/7 para contestar WhatsApp. En tu
computadora solo vive mientras tú la tienes prendida. Por eso se
despliega en un servicio de alojamiento; la disponibilidad y el costo
son los contratados con el proveedor, no están garantizados por este código.

## Opción 1 — Render (recomendada para empezar)

1. Sube esta carpeta a GitHub (un repositorio privado está bien).
   No subas el `.env` ni el `credenciales-google.json`: son secretos.
2. Entra a **render.com** y crea una cuenta gratis.
3. **New → Blueprint** y conecta tu repositorio. Render lee el archivo
   `render.yaml` que ya está en esta carpeta y crea el servicio solo.
4. En el panel del servicio, pestaña **Environment**, pon las mismas
   variables que pusiste en tu `.env` (GEMINI_API_KEY, WHATSAPP_TOKEN,
   WHATSAPP_PHONE_NUMBER_ID, VERIFY_TOKEN, OWNER_EMAIL, GMAIL_USER,
   GMAIL_APP_PASSWORD, ADMIN_TOKEN, META_APP_SECRET). Las que dicen
   `sync: false` en `render.yaml` son justo esas: Render te las pide
   a ti.
5. El archivo de la cuenta de servicio de Google (`credenciales-google.json`)
   no se sube al repositorio. Súbelo en Render como **Secret File** con
   ese mismo nombre, o pega su contenido en la variable
   `GOOGLE_CREDENTIALS_JSON` (el código lo lee como ruta; si lo pegas
   como texto, guárdalo primero como archivo secreto).
6. Dale a **Deploy**. Cuando termine, Render te da una dirección como:
   `https://robot-whatsapp-xxxx.onrender.com`
7. Abre `https://robot-whatsapp-xxxx.onrender.com/health`: debes ver
   `{"ok": true, ...}`. Si lo ves, el robot está vivo.
8. Esa dirección + `/webhook` es tu webhook para Meta:
   `https://robot-whatsapp-xxxx.onrender.com/webhook`
   Pégala en Meta for Developers → WhatsApp → Configuración del
   webhook, junto con tu VERIFY_TOKEN. Meta la verifica sola.

El blueprint solicita el plan **Starter** de pago. Confirma los precios y
condiciones actuales en Render. Configura un solo proceso y una instancia;
prepara primero `BuzonMeta` como se describe en README.md.

## Opción 2 — Railway (alternativa)

Igual de fácil: nuevo proyecto desde tu repositorio en **railway.com**,
variables de entorno en el panel (las mismas del `.env`), comando de
arranque `uvicorn app:app --host 0.0.0.0 --port $PORT`. Railway te da
una dirección pública (`https://tu-app.up.railway.app`) que usas igual
como webhook. El plan gratis tiene un crédito mensual que alcanza para
un robot chico; cuando se acaba, el servicio se pausa hasta el mes
siguiente. Render no tiene ese límite de crédito, por eso va primero.

## Mientras pruebas en tu computadora (sin desplegar)

Usa **ngrok** (gratis): con el robot prendido (`uvicorn app:app --port 8000`),
corre en otra terminal `ngrok http 8000`. Te da una dirección como
`https://tu-url.ngrok.io` — tu webhook es `https://tu-url.ngrok.io/webhook`.
Solo sirve mientras tu computadora está prendida y ngrok corriendo.

## Después de desplegar: la prueba de humo

1. Manda un WhatsApp al número de prueba de Meta.
2. Debes ver las palomitas azules y "escribiendo..." en segundos.
3. Manda 3 mensajes seguidos: el robot espera ~15 segundos y contesta
   una sola vez, con todo junto.
4. Pide una cita: te llegan los botones Confirmar / Cambiar hora /
   Hablar con una persona. Toca Confirmar y revisa Calendar.
5. El reporte semanal sigue llegando solo por correo, los lunes a las
   08:00. No hay recordatorios por WhatsApp en este robot.
