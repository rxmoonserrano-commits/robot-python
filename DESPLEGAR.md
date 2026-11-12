# DESPLEGAR — Poner el robot en internet (gratis)

El robot tiene que estar prendido 24/7 para contestar WhatsApp. En tu
computadora solo vive mientras tú la tienes prendida. Por eso se
despliega en un servicio gratis: ahí vive solo, y Meta le manda los
mensajes a su dirección pública.

## Opción 1 — Render (recomendada para empezar)

1. Sube esta carpeta a GitHub (un repositorio privado está bien).
   No subas el `.env` ni el `credenciales-google.json`: son secretos.
2. Entra a **render.com** y crea una cuenta gratis.
3. **New → Blueprint** y conecta tu repositorio. Render lee el archivo
   `render.yaml` que ya está en esta carpeta y crea el servicio solo.
4. En el panel del servicio, pestaña **Environment**, pon las mismas
   variables que pusiste en tu `.env` (GEMINI_API_KEY, WHATSAPP_TOKEN,
   WHATSAPP_PHONE_NUMBER_ID, VERIFY_TOKEN, OWNER_EMAIL, GMAIL_USER,
   GMAIL_APP_PASSWORD). Las que dicen `sync: false` en `render.yaml`
   son justo esas: Render te las pide a ti.
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

**El plan gratis de Render duerme el servicio si nadie lo usa 15
minutos.** El primer mensaje después de dormir tarda unos 10-20
segundos en despertar el robot (el cliente ve "escribiendo..." un
poco más), los demás van normal. El reporte del lunes también lo
despierta solo. Si eso te molesta, el plan de pago más barato de
Render lo mantiene prendido siempre.

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
3. Manda 3 mensajes seguidos: el robot espera ~7 segundos y contesta
   una sola vez, con todo junto.
4. Pide una cita: te llegan los botones Confirmar / Cambiar hora /
   Hablar con una persona. Toca Confirmar y revisa Calendar.
5. El reporte semanal sigue llegando solo por correo, los lunes a las
   08:00. No hay recordatorios por WhatsApp en este robot.
