# Robot genérico de WhatsApp con IA gratis — en Python

Jose, este es tu producto genérico, ahora en código Python, sin n8n.
Un robot que atiende por WhatsApp, califica al cliente y agenda la cita,
sin estar atado a ningún nicho. Sirve para un negocio que atiende clientes
y agenda citas o servicios: lo único que cambia de un negocio a otro es
la hoja de Conocimiento. El robot, el handoff, la pausa y el reporte son
siempre los mismos.

Es el mismo producto que la versión de n8n (`workspace/n8n-robot-generico/`),
con la misma lógica, portada a Python. La ventaja de Python: no pagas por
operación, el código es tuyo, y lo puedes vender como producto, no como
flujo rentado en una plataforma.

> **Honestidad, como siempre:** la lógica pasa 65 pruebas simuladas sin
> internet (23 de la v1 en `test_simulado.py` + 27 de la v2 en
> `test_v2.py` + 15 de la v2.2 en `test_v2_2.py`). El **12 de noviembre
> de 2026 el robot contestó su primer mensaje real** por WhatsApp
> (fuera de horario, proponiendo el viernes 13 a las 09:00). Lo que
> todavía NO está probado en vivo: confirmar una cita con el botón o
> con un "sí" y que se cree en Google Calendar, un handoff con correo
> real (Gmail sigue sin contraseña de aplicación) y el reporte semanal
> del lunes. No lo vendas como probado hasta pasar `PROBARLO.md`.

## Versión 2 — Lo que se siente humano (nuevo)

La v1 funcionaba, pero se sentía robot. La v2 le suma los toques de
calidad, sin cambiar lo que ya funcionaba:

1. **Visto + "escribiendo...".** Cuando llega tu mensaje, el robot lo
   marca como leído (palomitas azules) y te muestra que está escribiendo.
   La burbuja dura 25 segundos como máximo: si Gemini tarda más, el
   robot la vuelve a prender. Solo cuando va a contestar de verdad:
   nunca apagado, nunca en pausa, nunca en handoff.
2. **Espera a que termines de escribir.** Si mandas 3 mensajes seguidos,
   el robot espera 7 segundos después del último y los lee todos juntos,
   de una vez. Ya no contesta mensaje por mensaje. (Se cambia con
   `ESPERA_AGRUPAR_SEGUNDOS` en el `.env`.)
3. **Ritmo humano.** Espera 1 a 3 segundos antes de contestar y, si la
   respuesta es larga, la parte en 2 mensajes cortos, con una pausita
   entre ellos. Nunca un muro de texto.
4. **Botones para confirmar la cita.** Cuando el robot propone una cita,
   no la crea todavía: te muestra 3 botones — Confirmar, Cambiar hora,
   Hablar con una persona. La cita se crea solo cuando tocas Confirmar.
5. **Confirmación bonita.** Al confirmar, te dice tu nombre, el día, la
   hora y cuánto dura, y cómo cambiarla. Es una respuesta inmediata en
   la misma conversación, **no un recordatorio**.
6. **Si Gemini falla, no hay silencio.** El cliente recibe un "dame un
   momento" y el dueño un correo. El robot nunca se queda callado por
   un error.
7. **No contesta dos veces lo mismo.** Si Meta reenvía un mensaje, el
   robot lo reconoce por su id y lo ignora.
8. **Fuera de horario.** Si escribes cuando el negocio está cerrado
   (según la hoja Conocimiento), te dice a qué hora abre y te ofrece
   agendar para el próximo día que abre, en vez de agendar una hora
   imposible.

**Y por decisión de Jose: NO hay recordatorios por WhatsApp.** Ni un
día antes, ni una hora antes, ni ningún trabajo que mande WhatsApp.
El único trabajo programado es el reporte semanal, por correo.

## Versión 2.1 — Gmail ya no rompe las respuestas (corrección)

**Qué se corrigió:** si Gmail no está configurado (falta la contraseña
de aplicación, `GMAIL_USER` / `GMAIL_APP_PASSWORD` vacíos), el correo
fallaba y rompía la respuesta de WhatsApp: el cliente se quedaba sin
la respuesta que el robot ya había preparado, o recibía un "dame un
momento" duplicado y confuso. Ahora las alertas por correo son
**best-effort**: se intentan, si fallan quedan en el registro del
servidor, y el cliente recibe igual su respuesta por WhatsApp.
Nada más cambió: sigue sin recordatorios por WhatsApp, sigue sin
audios del robot, sigue el kill-switch, la pausa de 2 horas, los
botones, el debounce de 7 segundos y el visto + "escribiendo...".

**Qué sigue pendiente (solo lo puede hacer Jose):**
- **Gmail sigue pendiente para alertas y reporte.** Sin la contraseña
  de aplicación, el dueño no recibe los correos de handoff ni el
  reporte semanal del lunes. El robot contesta igual, pero esos
  correos no llegan. Poner `GMAIL_USER` y `GMAIL_APP_PASSWORD` en
  el `.env` y en Render (ver Paso 4).
- **Token permanente de WhatsApp.** El token temporal de Meta dura
  24 horas. Con el temporal, el robot deja de contestar al día
  siguiente (error 401). Hay que sacar el token permanente en Meta
  y ponerlo en Render como `WHATSAPP_TOKEN`.

**Pruebas nuevas:** `test_v2.py` suma 6 casos (27 en total) que
simulan Gmail ausente: un handoff, una falla técnica y el botón
"Hablar con una persona" responden al cliente sin lanzar excepción.

## Versión 2.2 — Fuera de horario ya no pierde al cliente, y Clientes sin duplicados

**Qué se corrigió:**
1. **Fuera de horario guardaba nada.** El robot proponía la próxima
   apertura, pero no guardaba la propuesta ni registraba al cliente.
   Un "sí" nocturno volvía a ofrecer lo mismo en bucle y nunca se
   agendaba nada. Ahora la propuesta se guarda, el cliente queda
   registrado como lead, y si contesta "sí" por texto, la cita se crea
   de verdad, aunque siga siendo de noche. Un "sí, mejor el sábado"
   NO confirma: pide otro día y va al agente. Una propuesta de hace
   más de 48 horas tampoco se confirma con un "sí".
2. **Clientes duplicados.** Cada mensaje agregaba una fila nueva del
   mismo teléfono. Ahora `registrar_cliente` actualiza la fila que ya
   existe (`sheets.fusionar_cliente`): un cliente, una fila. La fecha
   es la más reciente, el nombre / motivo / fecha de cita nuevos solo
   reemplazan si vienen con algo, el estatus nunca baja (una cita
   agendada no se borra porque el cliente vuelva a escribir) y el
   handoff "si" se queda. Las columnas extra de Clientes (resumen,
   intereses, calificación...) no se tocan: solo se escribe A:H.
3. **Contadores.** `contar_semana` contaba filas, no clientes: un
   cliente con 5 mensajes contaba como 5. Ahora cuenta teléfonos
   distintos.

**Pruebas nuevas:** `test_v2_2.py`, 15 casos: propuesta fuera de
horario, "sí" de noche, "sí, mejor el sábado", propuesta vieja,
"sí" tras proponer de día, botón Confirmar (sigue igual), fusión
de cliente y conteo por clientes distintos.

**Lo que sigue pendiente (no es de esta versión):** las propuestas
de cita viven en la memoria del servidor; si Render se reinicia, se
pierden y el cliente tiene que volver a pedir la cita. Guardarlas en
la hoja es el siguiente pulido.

## Qué hace el robot (en una frase)

Entra un mensaje de WhatsApp, el robot lo entiende (texto o audio), revisa
si puede responder, lee la información del negocio, contesta con calma como
una persona, califica al cliente, agenda en el calendario si ya se puede,
y registra todo. Si el cliente necesita una persona, avisa por correo y se calla.

## Archivos de este producto

| Archivo | Para qué sirve |
|---|---|
| `app.py` | El servidor: webhook de WhatsApp, `/health`, pausa humana, reporte manual |
| `robot/config.py` | Todos los ajustes, desde el `.env` (nada secreto en el código) |
| `robot/sheets.py` | Leer y escribir en Google Sheets (las 6 pestañas) |
| `robot/gemini.py` | Hablar con Gemini gratis (texto y audio) |
| `robot/whatsapp.py` | Mandar textos y fotos, bajar audios (WhatsApp Cloud API) |
| `robot/agent.py` | El guion del agente y cómo leer su respuesta JSON |
| `robot/logic.py` | El cerebro: el flujo completo, paso a paso |
| `robot/booking.py` | Agendar en Google Calendar (60 min, revisa que esté libre) |
| `robot/mail.py` | Mandar correos por Gmail (handoff y reporte) |
| `robot/report.py` | El reporte semanal de los lunes |
| `reporte_semanal.py` | Manda el reporte ahora: `python reporte_semanal.py` |
| `test_simulado.py` | 23 pruebas sin internet: `python test_simulado.py` |
| `test_v2.py` | 27 pruebas nuevas de la v2 (21 + 6 de la v2.1): `python test_v2.py` |
| `test_v2_2.py` | 15 pruebas nuevas de la v2.2 (fuera de horario + sin duplicados): `python test_v2_2.py` |
| `robot/agrupar.py` | V2: espera y junta los mensajes (7 s tras el último) |
| `robot/ritmo.py` | V2: demora humana y partir respuestas largas |
| `instalar.py` | V2: asistente que te pregunta las claves y deja el `.env` listo |
| `render.yaml` | V2: despliegue gratis en Render con un archivo |
| `DESPLEGAR.md` | V2: cómo poner el robot en internet (Render y Railway) |
| `guion-robot.md` | El guion completo del agente, para leer y ajustar |
| `PROBARLO.md` | Plan de pruebas en 10 puntos (+ las nuevas de la v2) |
| `requirements.txt` | Las librerías (todas gratuitas) |
| `.env.example` | La plantilla de claves: cópiala como `.env` y llénala |

## La inteligencia artificial: gratis y funcional

**Google Gemini, capa gratuita, modelo `gemini-2.0-flash`.** La clave se saca
en Google AI Studio (aistudio.google.com), sin tarjeta. Es el mismo modelo
para entender el texto, entender el audio y escribir el resumen semanal.

**Sus límites, con honestidad:**

- La capa gratuita tiene tope de peticiones por minuto y por día. Para un negocio chico que empieza, alcanza.
- Si se acaba el límite, Gemini devuelve error y el robot no responde ese mensaje. El mensaje queda registrado en Sheets, no se pierde.
- Google puede usar los datos de la capa gratuita para mejorar sus productos. No mandes datos sensibles (contraseñas, tarjetas, datos médicos).
- Si Google retira `gemini-2.0-flash`, el código prueba solo con `gemini-2.5-flash`, también gratis.

**No se usa nada de pago aquí:** ni Whisper de pago, ni GPT de pago.

## Cómo se ve el flujo (en 5 pasos)

```
1. WhatsApp entra (texto o audio)
   → si es audio, Gemini lo entiende; el robot responde SOLO en texto
2. Se lee Control: ¿botón en NO? ¿humano hace < 2 h?
   → NO puede responder: solo se registra el mensaje y se calla
3. Se carga Conocimiento + Fotos oficiales + Historial de ese teléfono
   → el agente (Gemini) responde y decide: agendar, handoff, foto
4. Foto validada contra la lista blanca · Handoff → correo al dueño
   Agendar → se revisa que la hora esté libre → cita de 60 minutos
5. Se manda la foto oficial (si la hay) + el texto por WhatsApp
   → se registra todo en Conversaciones Y en Clientes
```

El código de este flujo está en `robot/logic.py`, función `atender_mensaje`,
con un paso numerado por cada punto de arriba. Léelo de arriba a abajo:
eso es todo el robot.

## El botón de apagado (minimalista, estilo Apple)

No hay panel, no hay interruptor complicado. Es **una sola celda** en la hoja Control:

| bot_activo | ultima_respuesta_humana |
|---|---|
| SI | (vacío) |

- Para apagar el robot: cambia `SI` por `NO`. Eso es todo.
- Para prenderlo: vuelve a poner `SI`.
- La pausa de 2 horas es automática: cuando una persona le escribe a un cliente, se anota la fecha en `ultima_respuesta_humana` (o se llama a `POST /pausa`). Durante 2 horas el robot se calla y solo registra. Pasadas las 2 horas, retoma con todo el historial, incluido lo que dijo la persona.

Esto es diseño, no un extra: el robot no debe pisar nunca a un humano.

## El reporte semanal

Cada lunes a las 08:00 (hora del negocio), solo, el sistema lee los últimos
7 días, cuenta y manda un correo al dueño con: mensajes atendidos, clientes
calificados, citas agendadas, casos pasados a una persona, mensajes sin
responder porque una persona atendía, motivos más comunes, y un resumen
escrito por Gemini con una idea útil y una sugerencia. También guarda una
fila en la pestaña Reporte. **Nunca manda WhatsApp.** Los contadores salen
de las hojas, no se inventan: si no hay datos, salen en cero.

Para probarlo sin esperar al lunes: `python reporte_semanal.py`.

## Instalación paso a paso

### Paso 0 — El instalador (lo más fácil, recomendado)

```bash
python instalar.py
```

Te pregunta tus claves una por una, en español, sin mostrarlas en
pantalla. Instala las librerías, escribe el `.env`, corre las 50
pruebas y al final te dice los 3 pasos que siguen: desplegar, pegar
el webhook en Meta y mandar el primer mensaje de prueba. Se puede
correr dos veces: si ya tienes `.env`, te pregunta antes de tocarlo.

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
5. Haz lo mismo con el calendario del negocio: compártelo con ese correo.
6. El ID de la hoja ya está puesto en `.env.example` y en `config.py`: `1RfkuuvTf5f-YkhPkQnWzi0X95RpUoy3oHoDx00hFONo`. No lo cambies, es tu hoja oficial.

### Paso 4 — Gmail (contraseña de aplicación)

1. En tu cuenta de Google: Seguridad → Verificación en 2 pasos (actívala) → **Contraseñas de aplicaciones** → genera una para Correo.
2. Pon tu correo en `GMAIL_USER` y esa contraseña en `GMAIL_APP_PASSWORD` del `.env`. No es tu clave de Google.

### Paso 5 — WhatsApp Cloud API (Meta for Developers)

1. Crea una app en **Meta for Developers** y agrega el producto WhatsApp.
2. Meta te da un **número de prueba** y un **token temporal**: con eso ya puedes probar.
3. Copia el `Phone Number ID` y el token en el `.env`.
4. Inventa un `VERIFY_TOKEN` (una palabra secreta) y ponlo en el `.env` y en Meta, en la configuración del webhook.
5. **Importante:** para que el robot pueda contestar fuera de la ventana de 24 horas, el negocio necesita una plantilla aprobada por Meta. Para empezar, con la ventana de 24 horas alcanza.

### Paso 6 — El archivo .env

```bash
cp .env.example .env
```

Llena cada valor con tus datos. El `.env` nunca se sube a ningún lado
(está en `.gitignore`). Queda por llenar: `GEMINI_API_KEY`,
`WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `OWNER_EMAIL`
(ahora dice `dueno@empresa.com`), `GMAIL_USER` y `GMAIL_APP_PASSWORD`.

### Paso 7 — Arrancar en tu computadora

```bash
uvicorn app:app --port 8000
```

Abre `http://localhost:8000/health`: debes ver `{"ok": true, ...}`.
Para que Meta pueda llamar a tu webhook, tu computadora necesita una URL
pública: usa `ngrok http 8000` mientras pruebas (gratis), y pon esa URL
en Meta como `https://tu-url.ngrok.io/webhook`.

## Probarlo (sin gastar nada)

```bash
python test_simulado.py   # 23 casos de la v1 sin internet, todo en PASS
python test_v2.py         # 27 casos nuevos de la v2 sin internet, todo en PASS
python test_v2_2.py       # 15 casos nuevos de la v2.2 sin internet, todo en PASS
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
aplica. Pon las mismas variables del `.env` en el panel de Environment.
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

## Decisiones de diseño (Apple / Dieter Rams)

- **Menos, pero mejor.** Un archivo por idea, una función por acción. Nada de audio de respuesta, nada de envíos automáticos delicados.
- **Útil.** Cada módulo resuelve un problema real: que no se pierda un mensaje, que no se invente un precio, que no se pise a un humano.
- **Comprensible.** Un principiante puede leer `logic.py` de arriba a abajo y entender el robot. Los nombres dicen qué hace cada cosa.
- **Honesto.** Si no sabe algo, lo dice. Si no hay datos, el reporte dice cero. Si no está probado, esta guía lo dice.
- **Discreto.** El robot se calla cuando hay un humano. El botón de apagado es una celda, no un panel.
- **Seguro.** La lista blanca de fotos, el handoff por correo, el registro de todo, las claves solo en el `.env`. Nada se manda sin pasar por una validación.
- **Duradero.** El negocio cambia llenando una hoja, no reprogramando el robot. Y a diferencia de n8n: no pagas por operación, el código es tuyo.

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
