# Robot genérico de WhatsApp con IA gratis — en Python

Un robot que atiende el WhatsApp de un negocio 24/7: entiende texto y
audio, contesta como una recepcionista tranquila, califica al cliente,
agenda en Google Calendar, y si hace falta una persona, avisa por correo
y se calla. Todo lo que sabe del negocio vive en una hoja de Google
Sheets. Nada de audio de respuesta, nada de mensajes automáticos por
WhatsApp: solo responde cuando le escriben.

> **Honestidad, como siempre:** la lógica pasa 225 pruebas simuladas
> sin internet (23 de la v1 en `test_simulado.py` + 28 de la v2 en
> `test_v2.py` + 15 de la v2.2 en `test_v2_2.py` + 10 de la v2.3 en
> `test_v2_3.py` + 13 de la v2.4 en `test_v2_4.py` + 9 de la v2.5 en
> `test_v2_5.py` + 7 de la v2.6 en `test_v2_6.py` + 9 de la v2.7 en
> `test_v2_7.py` + 6 de la v2.8 en `test_v2_8.py` + 7 de la v2.9 en
> `test_v2_9.py` + 8 de la v2.10 en `test_v2_10.py` + 9 de la v2.11 en
> `test_v2_11.py` + 7 de la v2.12 en `test_v2_12.py` + 18 de la v2.13
> en `test_v2_13.py` + 29 de la v3.0 en `test_v3.py` + 27 de la v3.1
> en `test_v3_1.py`). Y hay 10 **conversaciones doradas** aparte
> (`test_conversaciones_doradas.py`): conversaciones completas contra
> la IA real, que se corren con la clave de Gemini antes de cada
> despliegue. El **12 de noviembre de 2026 el robot contestó su
> primer mensaje real** por WhatsApp (y agenda citas de verdad). La
> historia de cada versión vive en `CHANGELOG.md`.

## Qué hace el robot (en una frase)

Entra un mensaje de WhatsApp, el robot lo entiende (texto o audio),
revisa si puede responder, lee la información del negocio, contesta con
calma como una persona, califica al cliente, agenda en el calendario si
ya se puede, y registra todo. Si el cliente necesita una persona, avisa
por correo y se calla.

## Cómo se ve el flujo (en 5 pasos)

```
1. WhatsApp entra (texto o audio)
   → si es audio, Gemini lo entiende; el robot responde SOLO en texto
2. Se lee Control: ¿botón en NO? ¿humano hace < 2 h?
   → NO puede responder: solo se registra el mensaje y se calla
3. Se carga Conocimiento + Fotos oficiales + Historial de ese teléfono
   → el agente (Gemini) responde con el estado de la conversación y
   un revisor corrige la respuesta antes de mandarla
4. Foto validada contra la lista blanca · Handoff → correo al dueño
   Agendar → se revisa que la hora esté libre → cita de 60 minutos
5. Se manda la foto oficial (si la hay) + el texto por WhatsApp
   → se registra todo en Conversaciones Y en Clientes
```

El código de este flujo está en `robot/logic.py`, función
`atender_mensaje`. Léelo de arriba a abajo: eso es todo el robot.

## Archivos de este producto

| Archivo | Para qué sirve |
|---|---|
| `app.py` | El servidor: webhook de WhatsApp, `/health`, pausa humana, reporte manual |
| `robot/config.py` | Todos los ajustes, desde el `.env` (nada secreto en el código) |
| `robot/negocio.py` | El perfil del negocio: nombre, giro y recepcionista |
| `robot/sheets.py` | Leer y escribir en Google Sheets (con caché de 10 s por pestaña) |
| `robot/gemini.py` | Hablar con Gemini gratis (texto y audio) |
| `robot/whatsapp.py` | Mandar textos y fotos, bajar audios (WhatsApp Cloud API) |
| `robot/agent.py` | El guion del agente y cómo leer su respuesta JSON |
| `robot/estado.py` | El estado del cliente, calculado por código (v2.13) |
| `robot/revision.py` | El revisor: segunda mirada antes de mandar (v2.13) |
| `robot/logic.py` | El cerebro: el flujo completo, paso a paso |
| `robot/booking.py` | Agendar en Google Calendar (60 min, revisa que esté libre) |
| `robot/mail.py` | Mandar correos por Gmail (handoff y reporte) |
| `robot/report.py` | El reporte semanal de los lunes |
| `robot/salud.py` | Revisión de salud al arrancar: cada pieza, en Diagnóstico |
| `robot/seguridad.py` | Clave de dueño y firma de Meta |
| `robot/registro.py` | El registro del robot (info / aviso / error) |
| `robot/agrupar.py` | Espera y junta los mensajes (15 s tras el último), con buzón en disco |
| `robot/ritmo.py` | Demora humana y partir respuestas largas |
| `reporte_semanal.py` | Manda el reporte ahora: `python reporte_semanal.py` |
| `instalar.py` | Asistente que te pregunta las claves y deja el `.env` listo |
| `render.yaml` | Despliegue gratis en Render con un archivo |
| `runtime.txt` | Versión de Python en Render (3.12) |
| `DESPLEGAR.md` | Cómo poner el robot en internet (Render y Railway) |
| `guion-robot.md` | El guion completo del agente, para leer y ajustar |
| `PROBARLO.md` | Plan de pruebas en 10 puntos |
| `PRUEBAS-CALIDAD.md` | Plan de pruebas de seguridad, calidad y conversación natural |
| `CHANGELOG.md` | La historia de cada versión, en orden |
| `requirements.txt` | Las librerías (todas gratuitas) |
| `.env.example` | La plantilla de claves: cópiala como `.env` y llénala |
| `test_simulado.py` | 23 pruebas de la v1: `python test_simulado.py` |
| `test_v2.py` | 28 pruebas de la v2: `python test_v2.py` |
| `test_v2_2.py` | 15 pruebas de la v2.2: `python test_v2_2.py` |
| `test_v2_3.py` | 10 pruebas de la v2.3: `python test_v2_3.py` |
| `test_v2_4.py` | 13 pruebas de la v2.4: `python test_v2_4.py` |
| `test_v2_5.py` | 9 pruebas de la v2.5: `python test_v2_5.py` |
| `test_v2_6.py` | 7 pruebas de la v2.6: `python test_v2_6.py` |
| `test_v2_7.py` | 9 pruebas de la v2.7: `python test_v2_7.py` |
| `test_v2_8.py` | 6 pruebas de la v2.8: `python test_v2_8.py` |
| `test_v2_9.py` | 7 pruebas de la v2.9: `python test_v2_9.py` |
| `test_v2_10.py` | 8 pruebas de la v2.10: `python test_v2_10.py` |
| `test_v2_11.py` | 9 pruebas de la v2.11: `python test_v2_11.py` |
| `test_v2_12.py` | 7 pruebas de la v2.12: `python test_v2_12.py` |
| `test_v2_13.py` | 18 pruebas de la v2.13: `python test_v2_13.py` |
| `test_v3.py` | 29 pruebas de la v3.0: `python test_v3.py` |
| `test_v3_1.py` | 27 pruebas de la v3.1: `python test_v3_1.py` |
| `robot/vigilancia.py` | Vigilancia anti-atasco: si un lote tarda más de 90 s, avisa en Diagnóstico y el cliente recibe un "dame un momento" |
| `test_conversaciones_doradas.py` | 10 conversaciones doradas contra la IA real (necesita GEMINI_API_KEY): `GEMINI_API_KEY=tu_clave python test_conversaciones_doradas.py` |

## La inteligencia artificial: gratis y funcional

**Google Gemini, capa gratuita: modelo principal `gemini-4-hydrogen`,
respaldo `gemini-3.8-flash`, y al final siempre `gemini-3.5-flash-lite`.**
La clave se saca en Google AI Studio (aistudio.google.com), sin tarjeta.
Es el mismo modelo para entender el texto, entender el audio y escribir
el resumen semanal. Si Google retira un modelo, el robot lee el modelo
que Google sugiere en el error y lo prueba solo (autocuración).

**Sus límites, con honestidad:**

- La capa gratuita tiene tope de peticiones por minuto y por día. Para un negocio chico que empieza, alcanza.
- Si se acaba el límite, Gemini devuelve error y el robot no responde ese mensaje. El mensaje queda registrado en Sheets, no se pierde.
- Google puede usar los datos de la capa gratuita para mejorar sus productos. No mandes datos sensibles (contraseñas, tarjetas, datos médicos).
- Los modelos viejos (`gemini-2.0-flash`, `gemini-2.5-flash`) están retirados: Google ya no los contesta. El instalador avisa si tu `.env` trae uno.

**No se usa nada de pago aquí:** ni Whisper de pago, ni GPT de pago.

## El perfil del negocio (v3.0)

El robot es genérico: para venderlo a otro negocio se cambia el perfil,
no el código. Tres datos en el `.env`:

- `NEGOCIO_NOMBRE` — el nombre real (opcional). Si está, el robot lo usa
  ("En Clínica Dental Sonrisa ya cerraron por hoy..."); si no, dice
  "el negocio".
- `NEGOCIO_TIPO` — el giro, con artículo: "una clínica", "un
  restaurante", "un taller". Es lo que la recepcionista dice que es.
- `RECEPCIONISTA_NOMBRE` — el nombre de la persona que es el robot
  ("Ana").

## La salud del robot (v3.0)

Al arrancar, el robot revisa cada pieza y escribe el resultado en la
pestaña **Diagnóstico** de la hoja: OK, AVISO o FALLO. Ahí se ve, sin
entrar a Render ni pedir capturas: si Gemini contesta, si la hoja se
lee, si el calendario responde, si el token de WhatsApp sigue vivo
(401 = muerto), si Gmail está configurado, si el correo del dueño es
real, y si las claves de seguridad están puestas. También quedan ahí
cada fallo de Gemini, cada envío rechazado por WhatsApp y cada
corrección del revisor.

## El botón de apagado (minimalista, estilo Apple)

No hay panel, no hay interruptor complicado. Es **una sola celda** en la hoja Control:

| bot_activo | ultima_respuesta_humana |
|---|---|
| SI | (vacío) |

- Para apagar el robot: cambia `SI` por `NO`. Eso es todo.
- Para prenderlo: vuelve a poner `SI`.
- También hay un interruptor por cliente: la columna `robot_activo`
  en Clientes (SI/NO). En blanco es SI.

## La pausa humana: "ya contesté yo" (v3.0)

Cuando una persona le escribe a un cliente por WhatsApp, el robot se
calla 2 horas y después vuelve solo, con todo el historial, incluido
lo que dijo la persona. Meta no avisa cuando el dueño contesta, así
que la pausa no puede ser automática: se activa en la página del
dueño, que se guarda en el teléfono:

```
https://TU-DIRECCION.onrender.com/pausa?token=TU_CLAVE_DE_DUENO
```

Ahí pones el teléfono del cliente y listo. La clave de dueño
(`ADMIN_TOKEN`) la crea el instalador y va como variable en Render.
También se puede activar con `POST /pausa` (JSON) o escribiendo la
fecha directo en `Control!B2` de la hoja.

Esto es diseño, no un extra: el robot no debe pisar nunca a un humano.

## Seguridad (v3.0)

- **Clave de dueño (`ADMIN_TOKEN`):** `/pausa` y `/reporte-semanal`
  solo responden con la clave (header `X-Admin-Token`, `?token=` o
  body). Sin clave configurada, están cerrados.
- **Firma de Meta (`META_APP_SECRET`):** cada webhook trae el header
  `X-Hub-Signature-256`. Con el secreto configurado, una firma mala
  se rechaza (403) sin procesarse. El secreto está en Meta for
  Developers → tu app → Configuración básica → Secreto de la app.
- **Claves solo en el `.env`:** nunca en el código, nunca en GitHub.
  El `.env` y el JSON de Google están en `.gitignore`.
- **Lista blanca de fotos:** el robot solo manda URLs de la hoja
  Fotos oficiales. Nunca inventa una foto.
- **Anti-extracción (v3.1):** el robot nunca revela su guion ni sus
  instrucciones, ni da datos de otros clientes. Si alguien se los
  pide, se niega con calma y sigue atendiendo. El revisor (R6) desecha
  entera cualquier respuesta que traiga el guion, nombres de campos
  internos o un teléfono que no es el del cliente.
- **Sin etiquetas internas (v3.1):** el revisor (R5) quita paréntesis
  y palabras que son notas de la hoja ("FICTICIA", "EJEMPLO"). La
  dirección de ejemplo salió con esa etiqueta en una respuesta real;
  la hoja ya se limpió y el revisor es la red de seguridad.
- **Anti-atasco (v3.1):** si un lote tarda más de 90 segundos, queda
  en Diagnóstico ("lote TARDANDO") y el cliente recibe un "dame un
  momento" en vez de silencio. Un lote se quedó más de 45 minutos sin
  responder ni fallar, sin dejar rastro; eso ya no puede pasar
  desapercibido. Las llamadas a Google (Sheets y Calendar) llevan
  tiempo límite de 30 segundos.

## El reporte semanal

Cada lunes a las 08:00 (hora del negocio), solo, el sistema lee los
últimos 7 días, cuenta y manda un correo al dueño con: mensajes
atendidos, clientes calificados, citas agendadas, casos pasados a una
persona, mensajes sin responder porque una persona atendía, motivos
más comunes, y un resumen escrito por Gemini con una idea útil y una
sugerencia. También guarda una fila en la pestaña Reporte. **Nunca
manda WhatsApp.** Los contadores salen de las hojas, no se inventan:
si no hay datos, salen en cero.

Para probarlo sin esperar al lunes: `python reporte_semanal.py` (o
`POST /reporte-semanal` con la clave de dueño).

## Instalación paso a paso

### Paso 0 — El instalador (lo más fácil, recomendado)

```bash
python instalar.py
```

Te pregunta tus claves una por una, en español, sin mostrarlas en
pantalla. Instala las librerías, escribe el `.env`, genera tu clave
de dueño, corre las 225 pruebas y al final te dice los 3 pasos que
siguen: desplegar, pegar el webhook en Meta y mandar el primer mensaje
de prueba. Se puede correr dos veces: si ya tienes `.env`, te pregunta
antes de tocarlo.

Para solo revisar que todo está en orden, sin preguntas:

```bash
python instalar.py --check
```

Si prefieres hacerlo a mano, sigue los pasos 1 a 7 de abajo.

### Paso 1 — Python y las librerías

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Paso 2 — Clave gratuita de Gemini

1. Entra a **aistudio.google.com** con tu cuenta de Google.
2. Crea una API key (Create API Key). No pide tarjeta.
3. Guárdala en el `.env` como `GEMINI_API_KEY`. No la escribas en ningún archivo de código ni se la pases a nadie.

### Paso 3 — Google Sheets y Calendar (cuenta de servicio)

1. En **Google Cloud Console**, crea un proyecto y una **cuenta de servicio**.
2. Descarga su archivo JSON y guárdalo en esta carpeta como `credenciales-google.json`.
3. Activa en ese proyecto las APIs de **Google Sheets** y **Google Calendar**.
4. Abre tu hoja "Robot WhatsApp — Documento oficial" y **compártela con el correo de la cuenta de servicio** (termina en `iam.gserviceaccount.com`), como editor. Sin este paso, el robot no puede leer ni escribir.
5. Haz lo mismo con el calendario del negocio: compártelo con ese correo. Si no, las citas caen en el calendario del robot y el dueño no las ve en su app.
6. El ID de la hoja ya está puesto en `.env.example` y en `config.py`: `1RfkuuvTf5f-YkhPkQnWzi0X95RpUoy3oHoDx00hFONo`. No lo cambies, es tu hoja oficial.

### Paso 4 — Gmail (contraseña de aplicación)

1. En tu cuenta de Google: Seguridad → Verificación en 2 pasos (actívala) → **Contraseñas de aplicaciones** → genera una para Correo.
2. Pon tu correo en `GMAIL_USER` y esa contraseña en `GMAIL_APP_PASSWORD` del `.env`. No es tu clave de Google.

### Paso 5 — WhatsApp Cloud API (Meta for Developers)

1. Crea una app en **Meta for Developers** y agrega el producto WhatsApp.
2. Meta te da un **número de prueba** y un **token temporal**: con eso ya puedes probar.
3. Copia el `Phone Number ID` y el token en el `.env`.
4. Inventa un `VERIFY_TOKEN` (una palabra secreta) y ponlo en el `.env` y en Meta, en la configuración del webhook.
5. Opcional pero recomendado: copia el **Secreto de la app** (Configuración básica → Secreto de la app → Mostrar) como `META_APP_SECRET`. Con él, el robot verifica que cada mensaje venga de Meta de verdad.
6. **Importante:** para que el robot pueda contestar fuera de la ventana de 24 horas, el negocio necesita una plantilla aprobada por Meta. Para empezar, con la ventana de 24 horas alcanza.

### Paso 6 — El archivo .env

```bash
cp .env.example .env
```

Llena cada valor con tus datos. El `.env` nunca se sube a ningún lado
(está en `.gitignore`). Queda por llenar: `GEMINI_API_KEY`,
`WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `OWNER_EMAIL`
(ahora dice `dueno@empresa.com`), `GMAIL_USER` y `GMAIL_APP_PASSWORD`.
La clave de dueño (`ADMIN_TOKEN`) la crea el instalador; si lo haces
a mano, genera una con `python3 -c "import secrets; print(secrets.token_urlsafe(24))"`.

### Paso 7 — Arrancar en tu computadora

```bash
uvicorn app:app --port 8000
```

Abre `http://localhost:8000/health`: debes ver `{"ok": true, "version": "3.0.0", ...}`.
Para que Meta pueda llamar a tu webhook, tu computadora necesita una URL
pública: usa `ngrok http 8000` mientras pruebas (gratis), y pon esa URL
en Meta como `https://tu-url.ngrok.io/webhook`.

## Probarlo (sin gastar nada)

```bash
python instalar.py --check   # todo: 225 pruebas + el servidor arranca
python test_v3_1.py          # 27 casos nuevos de la v3.1
```

Y las conversaciones doradas (contra la IA real, con tu clave):

```bash
GEMINI_API_KEY=tu_clave python test_conversaciones_doradas.py
```

Y con un mensaje real de WhatsApp, simulando lo que manda Meta:

```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"entry": [{"changes": [{"value": {"messages": [{"from": "6671234567", "type": "text", "text": {"body": "Hola, quiero una cita"}}], "contacts": [{"wa_id": "6671234567", "profile": {"name": "Ana"}}]}}]}]}'
```

El plan completo de 10 pruebas está en `PROBARLO.md`.

## Desplegar gratis (cuando ya funcione en tu computadora)

Todo el detalle está en `DESPLEGAR.md`. El resumen:

**Render (recomendado para empezar).** El archivo `render.yaml` ya está
en esta carpeta: en Render, New → Blueprint, conecta tu repositorio y
aplica. Pon las mismas variables del `.env` en el panel de Environment
(incluidas `ADMIN_TOKEN` y `META_APP_SECRET`, que dicen `sync: false`).
El plan gratis duerme el servicio si nadie lo usa 15 minutos: el primer
mensaje tarda unos segundos en despertar, los demás van normal. El
reporte del lunes también despierta el servicio solo.

**Railway (alternativa).** Igual: nuevo proyecto desde tu repositorio,
variables de entorno en el panel, comando `uvicorn app:app --host 0.0.0.0 --port $PORT`.
El plan gratis tiene un crédito mensual que alcanza para un robot chico;
cuando se acaba, el servicio se pausa hasta el mes siguiente.

En los dos casos, la URL pública que te dan es la que pones en Meta como
webhook (`https://tu-app.onrender.com/webhook`). El archivo
`credenciales-google.json` no se sube al repositorio: súbelo como archivo
secreto del servicio o pega su contenido en una variable de entorno
(ver `GOOGLE_CREDENTIALS_JSON`).

## Qué sigue pendiente (solo lo puede hacer Jose)

- **Token permanente de WhatsApp.** El temporal dura ~24 horas; al
  vencerse, el robot deja de contestar (error 401 en Diagnóstico y en
  los Logs). Ya murió 3 veces. Sácalo en Meta y ponlo en Render como
  `WHATSAPP_TOKEN`.
- **Contraseña de aplicación de Gmail.** Sin ella no llegan los
  correos de handoff ni el reporte semanal del lunes. El robot
  contesta igual, pero esos correos no llegan. Pon `GMAIL_USER` y
  `GMAIL_APP_PASSWORD` en Render (Environment) y redeploya.
- **Calendario del dueño.** Hoy las citas caen en el calendario de la
  cuenta de servicio y el dueño no las ve en su app. Comparte el
  calendario del negocio con el correo de la cuenta de servicio
  (Editor) y pon su ID en `CALENDAR_ID` en Render, en vez de `primary`.

## Decisiones de diseño (Apple / Dieter Rams)

- **Menos, pero mejor.** Un archivo por idea, una función por acción. Nada de audio de respuesta, nada de envíos automáticos delicados.
- **Útil.** Cada módulo resuelve un problema real: que no se pierda un mensaje, que no se invente un precio, que no se pise a un humano.
- **Comprensible.** Un principiante puede leer `logic.py` de arriba a abajo y entender el robot. Los nombres dicen qué hace cada cosa.
- **Honesto.** Si no sabe algo, lo dice. Si no hay datos, el reporte dice cero. Si no está probado, esta guía lo dice.
- **Discreto.** El robot se calla cuando hay un humano. El botón de apagado es una celda, no un panel.
- **Seguro.** La lista blanca de fotos, el handoff por correo, el registro de todo, las claves solo en el `.env`, y desde la v3.0: la clave de dueño y la firma de Meta. Nada se manda sin pasar por una validación.
- **Duradero.** El negocio cambia llenando una hoja o cambiando su perfil, no reprogramando el robot. Y a diferencia de n8n: no pagas por operación, el código es tuyo.

## Qué NO hace este robot

- No responde con audios. Nunca.
- No manda mensajes de WhatsApp por su cuenta (reseñas, recordatorios). Solo responde cuando le escriben, y avisa por correo lo demás.
- No diagnostica ni da consejos médicos o legales.
- No inventa precios, horarios, servicios.
- No manda fotos que no estén en la lista blanca.
- No publica nada en ningún lado. El reporte es solo por correo.

## Qué cambió respecto a la versión de n8n (mejoras, no recortes)

- **La cita dura 60 minutos.** En n8n, el nodo de Calendar ponía inicio = fin. Aquí `booking.py` calcula fin = inicio + duración, y la duración se cambia en el `.env`.
- **Clientes sí se registra.** En n8n, el último nodo solo escribía Conversaciones y había que duplicarlo. Aquí `logic.py` escribe en las DOS hojas siempre.
- **El audio sí se entiende de verdad.** En n8n era un nodo Code con instrucciones para conectar la llamada. Aquí `gemini.py` hace la llamada a Gemini multimodal directamente.
- **El reporte no depende de un Merge.** Los contadores se calculan en `logic.contar_semana` con las fechas reales de las hojas.
