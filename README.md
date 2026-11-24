# Robot genérico de WhatsApp con IA gratis — en Python

Un robot que atiende el WhatsApp de un negocio 24/7: entiende texto y
audio, contesta como una recepcionista tranquila, califica al cliente,
agenda en Google Calendar con botones, y si hace falta una persona,
avisa por correo y se calla. Todo lo que sabe del negocio vive en una
hoja de Google Sheets. Nada de audio de respuesta, nada de mensajes
automáticos por WhatsApp: solo responde cuando le escriben.

> **Honestidad, como siempre:** la lógica pasa **545 pruebas
> simuladas sin internet** en 27 archivos (más la batería de
> inteligencia de 41 escenarios, ya incluida en el conteo). Y hay **20 conversaciones doradas**
> aparte (`test_conversaciones_doradas.py`): conversaciones completas
> contra la IA real, que se corren con la clave de Gemini antes de
> cada despliegue — la puerta de embarque: si una falla, esa versión
> no sale. El **12 de noviembre de 2026 el robot contestó su primer
> mensaje real** por WhatsApp (y agenda citas de verdad). La historia
> de cada versión vive en `CHANGELOG.md`.

## Qué hace el robot (en una frase)

Entra un mensaje de WhatsApp, el robot lo entiende (texto o audio),
revisa si puede responder, lee la información del negocio, contesta con
calma como una persona, califica al cliente, agenda en el calendario si
ya se puede, y registra todo. Si el cliente necesita una persona, avisa
por correo y se calla. Con la IA apagada, sigue leyendo: si llega una
urgencia, una queja o alguien pide una persona, avisa al dueño igual.

## Cómo se ve el flujo (en 5 pasos)

```
1. WhatsApp entra (texto o audio)
   → si es audio, Gemini lo entiende; el robot responde SOLO en texto
2. Se lee Control y el interruptor del cliente: ¿apagado? ¿humano hace < 2 h?
   → NO puede responder: solo se registra. Pero si el mensaje es una
     urgencia, una queja o pide una persona → handoff: correo al dueño
3. Se carga Conocimiento + Fotos oficiales + Historial de ese teléfono
   → el agente (Gemini) responde con el estado de la conversación y
   un revisor corrige la respuesta antes de mandarla
4. Foto validada contra la lista blanca · Handoff → correo al dueño
   Agendar → propuesta con botones [Confirmar | Cambiar hora | Humano]
   → al confirmar: cita con la duración del servicio (hoja) + espejo
     en la pestaña Citas. Si el calendario falla: queda PENDIENTE,
     se le dice al cliente y se avisa al dueño.
5. Se manda la foto oficial (si la hay) + el texto por WhatsApp
   → se registra todo en Conversaciones, en Clientes y en el espejo Citas
```

El código de este flujo está en `robot/logic.py`, función
`atender_mensaje`. Léelo de arriba a abajo: eso es todo el robot.

## Archivos de este producto

| Archivo | Para qué sirve |
|---|---|
| `app.py` | El servidor: webhook de WhatsApp, `/health`, `/estado`, pausa humana, reporte manual |
| `robot/config.py` | Todos los ajustes, desde el `.env` (nada secreto en el código) |
| `robot/negocio.py` | El perfil del negocio y la pestaña Configuración (v3.5) |
| `robot/canales.py` | Canales: WhatsApp activo; Messenger/Instagram diseñados, apagados (v3.5) |
| `robot/sheets.py` | Leer y escribir en Google Sheets (con caché de 10 s por pestaña) |
| `robot/gemini.py` | Hablar con Gemini gratis (texto y audio) |
| `robot/whatsapp.py` | Mandar textos y fotos, bajar audios (WhatsApp Cloud API) |
| `robot/agent.py` | El guion del agente y cómo leer su respuesta JSON |
| `robot/estado.py` | El estado del cliente, calculado por código (v2.13) |
| `robot/revision.py` | El revisor: segunda mirada antes de mandar (v2.13) |
| `robot/logic.py` | El cerebro: el flujo completo, paso a paso |
| `robot/booking.py` | Agendar en Google Calendar (duración por servicio, revisa que esté libre) |
| `robot/mail.py` | Mandar correos por Gmail (alertas y reporte, texto + HTML) |
| `robot/report.py` | El reporte semanal de los lunes (3 tipos, texto + HTML) |
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
| `test_simulado.py` … `test_escenarios_100.py` | 29 archivos de pruebas sin internet (758 casos): `python test_escenarios_100.py` y sus hermanas |
| `test_inteligencia.py` | 41 escenarios de inteligencia (botones, agenda, handoff, documento, calidez) sin API key |
| `test_escenarios_100.py` | 100 escenarios conversacionales (149 casos) contra el código real: saludo, precios, agendar, dos citas, terceros, memoria, cambio/cancelación, handoff, fallas, paquetes |
| `test_conversaciones_doradas.py` | 20 conversaciones doradas contra la IA real (necesita GEMINI_API_KEY) |

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

## Configuración por negocio (v3.5)

El robot es genérico: para venderlo a otro negocio se cambia la hoja,
no el código. La pestaña **Configuración** (clave | valor) manda:
nombre del negocio, tipo, nombre de la asistente, tono
(amigable/formal/breve/detallado), saludo obligatorio, mensaje fuera
de horario, interruptores (agendar, enviar fotos, responder FAQs,
derivar humano) y el correo del dueño. Prioridad: hoja > variables de
entorno > valores por defecto. Sin pestaña o vacía, el robot se
comporta como siempre. Los cambios aplican en el siguiente mensaje,
sin reiniciar.

El documento maestro **"Negocios"** es el panel de control del
vendedor: un índice con un renglón por negocio (paquete, canales,
estado) y un enlace a la hoja operativa de cada uno. La plantilla
**"Plantilla — Negocio"** es la hoja lista para clonar por cliente.

**Canales:** el motor es uno solo; cada canal es un adaptador.
WhatsApp está activo. Messenger e Instagram están diseñados y
apagados (rutas `/webhook/messenger` e `/webhook/instagram` responden
`activo: false`) hasta que Jose decida conectarlos.

## Paquetes y canales (v3.6)

Todos los negocios tienen el mismo código (la versión pro); el
paquete autoriza qué funciones recibe cada uno, con un interruptor
en Configuración o en el documento maestro:

| Paquete | Qué incluye |
|---|---|
| **Básico "Responde"** | Responde FAQs y precios, deriva a humano con alerta, registra leads. Sin agenda, sin fotos, sin reportes. |
| **Pro "Agenda"** | Todo lo básico + agendar con botones, fotos oficiales, reporte semanal de 3 tipos, borradores por recuperar, resumen de la mañana. |
| **Premium "Completo"** | Todo lo pro + Messenger/Instagram cuando se conecten + ajustes prioritarios. |

Interruptores por canal (`canal_whatsapp`, `canal_messenger`,
`canal_instagram`): WhatsApp en NO = el robot no contesta (igual que
el botón global). Un interruptor explícito SI/NO manda sobre el
paquete. Sin paquete definido, todo está en SI (compatibilidad).

## Alertas del dueño (v3.7)

**Un solo correo semanal** (lunes 08:00) con los 3 tipos que el dueño
quiere ver, sin entrar a ningún lado:

1. **📅 Citas confirmadas** — lista con fecha en claro.
2. **🙋 Necesitaron atención humana** — lista con motivo y cuándo.
3. **💬 Clientes por recuperar** — preguntaron y no agendaron, con un
   borrador listo para copiar (el robot nunca manda WhatsApp).

Más un bloque de valor: conversaciones atendidas, resueltas sin
humano (%), citas, canceladas y no-show (desde el espejo Citas),
tiempo ahorrado estimado (5 min por conversación, marcado como
estimado) y mensajes sin respuesta (todos registrados). Confirmado
vs estimado: nada inventado. El correo llega en texto y en HTML
bonito (v3.9).

Interruptor `alertas_instantaneas`: en SI (default) la cita
confirmada y el lead caliente avisan en el momento; en NO solo van
en el correo semanal (sin avalancha). Los handoff (urgencias, quejas,
fallas técnicas) siempre avisan en el momento: es seguridad.

## IA apagada: el handoff sigue leyendo (v3.8)

Con la IA apagada —interruptor por cliente (`robot_activo = NO`) o
botón global (Control)— el robot no contesta, pero **sí lee**. Si el
mensaje es una urgencia, una queja o un pedido explícito de persona,
se resuelve la mecánica de handoff: correo al dueño y caso marcado en
Clientes, sin responderle al paciente. Las dudas normales solo
quedan registradas. Reglas deterministas en código, sin IA.

## Estructura Sereno (v3.9)

La estructura de hojas adoptada del ecosistema Sereno:

- **Conocimiento con columnas estructuradas (E a N):** ID, categoría,
  `Duración_min`, profesionales, anticipo, nota de preparación,
  visible, vigente. La cita dura lo que diga la hoja para ese
  servicio; sin dato, 60 minutos. La confirmación lo dice en claro
  ("Dura 45 minutos."). Las columnas A a D no se tocaron.
- **Pestaña Citas (espejo):** vista de solo lectura para el dueño con
  el estado de cada cita (Confirmada, Pendiente, Cancelada, Realizada,
  No-show) y un panel automático de conteos. El robot la actualiza
  solo; editarla no agenda nada (la fuente de verdad es el calendario).
- **Cita pendiente:** si el calendario falla con la hora libre, la
  solicitud ya no se reporta como "hora ocupada": se le dice al
  cliente que quedó pendiente, se avisa al dueño por correo y el
  espejo queda Pendiente. Nunca se inventa una cita.
- **Protocolo de urgencias:** la clave `protocolo_urgencias` de
  Configuración (texto aprobado del negocio) entra al guion.
- **Clientes Q a V:** consentimiento de mensajes, fecha de
  consentimiento, citas totales, última cita, marca y hora de la
  alerta de handoff. La columna P (`robot_activo`) sigue siendo el
  interruptor por cliente.

## Sereno completo (v3.12)

El producto final: agenda por profesional, recordatorios,
urgencia con guía y respuestas directas.

- **Agenda por profesional:** los huecos salen del horario de cada
  profesional activo (pestaña Profesionales) y la propuesta, la
  confirmación y el espejo llevan su nombre real. Sin profesionales
  activos, la agenda sigue por clínica, idéntica a antes.
- **Recordatorios automáticos:** ~24 h antes de la cita manda la
  plantilla aprobada de WhatsApp (nombre + fecha/hora) y marca
  `Recordatorio_enviado` en el espejo. Interruptor `recordatorios`
  en Configuración (en paquete básico va apagado). Sin plantilla
  aprobada en Meta, el envío falla y queda en Diagnóstico: nunca
  silencioso, nunca con costo. El paciente puede confirmar su
  asistencia ("confirmo") y queda registrado en el espejo.
- **Urgencia con guía:** ante una posible urgencia, el robot orienta
  a buscar atención médica inmediata antes del handoff (texto
  personalizable con `mensaje_urgencia` en Configuración).
- **Servicios sin evasión:** servicios y precios se responden
  directo desde Conocimiento (máximo 5), sin derivar con "¿cuál te
  interesa?".
- **Handoff con contexto:** el correo al dueño incluye el resumen
  de la conversación del cliente.
- **Reporte con confirmaciones:** el correo semanal cuenta las
  confirmaciones de asistencia del paciente.

## La salud del robot (v3.0)

Al arrancar, el robot revisa cada pieza y escribe el resultado en la
pestaña **Diagnóstico** de la hoja: OK, AVISO o FALLO. Ahí se ve, sin
entrar a Render ni pedir capturas: si Gemini contesta, si la hoja se
lee, si el calendario responde, si el token de WhatsApp sigue vivo
(401 = muerto), si Gmail está configurado, si el correo del dueño es
real, y si las claves de seguridad están puestas. También quedan ahí
cada fallo de Gemini, cada envío rechazado por WhatsApp y cada
corrección del revisor. `GET /estado` dice si el chequeo terminó,
cuántos mensajes llegaron y cuántos lotes se procesaron (solo
números, sin datos de clientes).

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
  y palabras que son notas de la hoja ("FICTICIA", "EJEMPLO").
- **Anti-atasco (v3.1):** si un lote tarda más de 90 segundos, queda
  en Diagnóstico ("lote TARDANDO") y el cliente recibe un "dame un
  momento" en vez de silencio. Un lote se quedó más de 45 minutos sin
  responder ni fallar, sin dejar rastro; eso ya no puede pasar
  desapercibido. Las llamadas a Google (Sheets y Calendar) llevan
  tiempo límite de 30 segundos.
- **Anti-abuso:** más de 10 mensajes en 60 s de un mismo teléfono: el
  robot pide calma una vez y no procesa los demás hasta que pase la
  ventana. Protege la cuota gratis de Gemini, que es lo que deja mudo
  al robot para todos.

## La memoria del cliente (v3.2)

El robot recuerda de un día a otro, no solo los últimos 8 mensajes.
En cada respuesta, el agente devuelve lo que aprendió (resumen,
interés, próxima acción, preferencias) y eso se guarda en Clientes
(resumen, intereses, próxima acción, notas). En el siguiente mensaje,
el contexto empieza con "Lo que sabes de este cliente" y el robot no
vuelve a preguntar lo que ya sabe. Solo se guarda lo nuevo: un campo
vacío no borra lo que ya había, y las preferencias se acumulan sin
repetirse. Si le aparta el lugar a un cliente, el apartado queda
guardado en Propuestas (hasta mañana) y el robot lo recuerda cuando
vuelve. Y el revisor (R7) no lo deja cerrar dos veces con la misma
frase: si su último mensaje terminó en "Quedamos a tus órdenes", el
siguiente cierra distinto.

## Calidad para el dueño y para su cliente (v3.3 – v3.4)

- **Horas libres de verdad.** Antes de ofrecer, el código busca los
  próximos dos huecos libres en el calendario y se los pasa al agente.
  Si no hay huecos, dice que la agenda está llena. La confirmación
  vuelve a revisar la hora, por si se ocupó entre tanto.
- **Agenda con botones.** La propuesta llega con [Confirmar cita |
  Cambiar hora | Hablar con persona]. Sin botones no hay cita: la
  propuesta no es una cita hasta que el cliente confirma.
- **Dos citas en una (v3.10).** Si pide la suya y la de otra persona
  (o dos servicios), se proponen juntas con un solo botón:
  [Confirmar ambas | Cambiar hora | Hablar con persona]. Al confirmar
  se crean las dos. Si la cita es para otra persona, el robot pide su
  nombre completo y el número para registrarla.
- **Tope de 2 citas por número (v3.10).** Máximo 2 citas activas por
  teléfono (la suya y la de otra persona), para que nadie inunde el
  calendario. Con 2 activas, el robot explica el límite y ofrece
  cambiar alguna.
- **Confirmación sin fricción (v3.4.11).** Corta, con la fecha en
  claro y la duración real del servicio. Nombre y número se piden
  DESPUÉS de confirmar, solo si faltan, y diciendo para qué.
- **Calidez (v3.4.11).** El guion enseña a saludar como una
  recepcionista buena onda: usa el nombre con naturalidad, valida
  emociones, celebra los síes, una idea por mensaje. El revisor
  (R8, ampliado en v3.10) nunca deja que el robot afirme una cita
  que no existe (mira la cita a futuro, no una ya pasada).
- **Urgencias a humano.** Si el cliente dice que es urgente o que le
  duele, la IA compone la respuesta pensada (empatía, handoff
  inmediato, fuera de horario con empatía) y el código fuerza el
  handoff y avisa al dueño por correo. "¿Duele la limpieza?" no es
  urgencia: es una pregunta y va al agente normal. (v3.13) Además
  ofrece agendar la primera hora disponible con botones: la cita
  que sale de una urgencia se marca URGENTE en la pestaña Citas
  (columna Urgencia) y el dueño recibe un correo de "cita con
  urgencia" con el porqué. (v3.14) La respuesta ya no es una
  plantilla fija: la piensa la IA con el guion y el contexto; si la
  IA falla, texto fijo de respaldo. (v3.14.1) La urgencia siempre
  propone fecha: salta el tope de 2 citas por número (el tope sigue
  para el flujo normal). (v3.14.2) La respuesta sale en una sola
  burbuja, el protocolo se dice con palabras propias (no copiado) y
  la oferta va en tono sobrio. (v3.15) Si el cliente ya tiene una
  cita propia, la urgencia propone ADELANTAla (moverla a la primera
  hora libre) en vez de crear otra; si no tiene, cita nueva.
- **Resumen de la mañana.** Todos los días a las 08:00, un correo al
  dueño con lo de las últimas 24 h: mensajes atendidos, clientes
  nuevos, citas agendadas, quién necesita una persona, propuestas
  sin contestar y las citas de hoy. Sin IA: son números y listas.
- **Que nunca se calle (v3.4).** El Agrupador libera solo un teléfono
  atascado más de 5 minutos y `GET /estado` dice cuántos lotes se
  procesaron. Un lote muerto ya no deja mudo a un cliente para siempre.
- **El cliente también escucha el handoff (v3.3.1).** En un handoff
  normal, el cliente recibe el texto ("te paso con una persona...")
  además del correo al dueño.

## Instalación paso a paso

### Paso 0 — El instalador (lo más fácil, recomendado)

```bash
python instalar.py
```

Te pregunta tus claves una por una, en español, sin mostrarlas en
pantalla. Instala las librerías, escribe el `.env`, genera tu clave
de dueño, corre las pruebas y al final te dice los 3 pasos que
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

Abre `http://localhost:8000/health`: debes ver `{"ok": true, "version": "3.20.1", ...}`.
Para que Meta pueda llamar a tu webhook, tu computadora necesita una URL
pública: usa `ngrok http 8000` mientras pruebas (gratis), y pon esa URL
en Meta como `https://tu-url.ngrok.io/webhook`.

## Probarlo (sin gastar nada)

```bash
python instalar.py --check   # todo: 462 pruebas + el servidor arranca
python test_v3_9.py          # 33 casos nuevos de la v3.9
python test_inteligencia.py  # 41 escenarios de inteligencia, sin API key
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

- **Contraseña de aplicación de Gmail.** Sin ella no llegan los
  correos de handoff, el reporte semanal del lunes (texto + HTML) ni
  las alertas de cita pendiente. El robot contesta igual, pero esos
  correos no llegan. Pon `GMAIL_USER` y `GMAIL_APP_PASSWORD` en
  Render (Environment) y redeploya.
- **Claves de seguridad en Render.** `ADMIN_TOKEN` y `META_APP_SECRET`
  sin poner: `/pausa` y `/reporte-semanal` están cerrados y el webhook
  acepta mensajes sin firma verificada.
- **Calendario del dueño.** Hoy las citas caen en el calendario de la
  cuenta de servicio y el dueño no las ve en su app. Comparte el
  calendario del negocio con el correo de la cuenta de servicio
  (Editor) y pon su ID en `CALENDAR_ID` en Render, en vez de `primary`.
- **Batería dorada con IA real (v3.4.8+).** Las 20 conversaciones
  doradas pasaron en v3.4.7; las versiones nuevas (calidez,
  confirmación, Sereno) aún no se corren con Gemini real en la Mac.
- **Prueba en vivo por WhatsApp (v3.9).** Probar la duración por
  servicio, el espejo Citas, la cita pendiente y el reporte HTML.

## Decisiones de diseño (Apple / Dieter Rams)

- **Menos, pero mejor.** Un archivo por idea, una función por acción. Nada de audio de respuesta, nada de envíos automáticos delicados.
- **Útil.** Cada módulo resuelve un problema real: que no se pierda un mensaje, que no se invente un precio, que no se pise a un humano.
- **Comprensible.** Un principiante puede leer `logic.py` de arriba a abajo y entender el robot. Los nombres dicen qué hace cada cosa.
- **Honesto.** Si no sabe algo, lo dice. Si no hay datos, el reporte dice cero. Si no está probado, esta guía lo dice.
- **Discreto.** El robot se calla cuando hay un humano. El botón de apagado es una celda, no un panel.
- **Seguro.** La lista blanca de fotos, el handoff por correo, el registro de todo, las claves solo en el `.env`, la clave de dueño y la firma de Meta. Nada se manda sin pasar por una validación.
- **Duradero.** El negocio cambia llenando una hoja o cambiando su perfil, no reprogramando el robot. Y a diferencia de n8n: no pagas por operación, el código es tuyo.

## Qué NO hace este robot

- No responde con audios. Nunca.
- No manda reseñas ni promociones por su cuenta. Sí manda recordatorios de cita por plantilla aprobada de WhatsApp (interruptor `recordatorios` en Configuración); todo lo demás llega por correo.
- No diagnostica ni da consejos médicos o legales.
- No inventa precios, horarios, servicios.
- No manda fotos que no estén en la lista blanca.
- No publica nada en ningún lado. El reporte es solo por correo.

## Qué cambió respecto a la versión de n8n (mejoras, no recortes)

- **La cita dura lo que diga la hoja.** En n8n, el nodo de Calendar ponía inicio = fin. Aquí `booking.py` calcula fin = inicio + duración, y la duración viene de la columna `Duración_min` de Conocimiento (sin dato: 60).
- **Clientes sí se registra.** En n8n, el último nodo solo escribía Conversaciones y había que duplicarlo. Aquí `logic.py` escribe en las DOS hojas siempre.
- **El audio sí se entiende de verdad.** En n8n era un nodo Code con instrucciones para conectar la llamada. Aquí `gemini.py` hace la llamada a Gemini multimodal directamente.
- **El reporte no depende de un Merge.** Los contadores se calculan en `logic.contar_semana` con las fechas reales de las hojas.
