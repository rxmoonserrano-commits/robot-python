# CHANGELOG — La historia del robot, en orden

La historia de cada versión, para no cargarla en el código ni en el
README. El README describe lo que el robot hace HOY; aquí queda lo
que hacía antes y por qué cambió. Si algo se rompió en vivo, aquí
queda la fecha y la causa.

## v3.10.0 — Reservas para ti y para alguien más: tope 2 por número, confirmar ambas, sin afirmaciones falsas (2026-11-22)

Jose probó en vivo (03:17–03:23 MST) y reportó cuatro cosas, todas
corregidas aquí:

1. **No aparecía el botón de confirmar.** El robot propuso horas en
   texto ("¿Te parece bien?") sin botones. Causas: el agente no marcó
   quiere_agendar, la red de seguridad no reconocía "¿qué días tienes
   disponibles el martes para mí y el miércoles para mi hermana?", y
   los huecos ni se calculaban para un cliente nuevo. Ahora:
   `_PALABRAS_QUIERE_AGENDAR` incluye pedir disponibilidad y agendar
   para otra persona; los huecos también se calculan cuando el
   mensaje pide agendar con palabras claras; el guion dice que nunca
   se propongan horas en texto sin botones.
2. **Afirmaba citas que no existían.** Dijo "Quedamos en que nos
   vemos el martes a las 09:00" sin crear ninguna cita (la propuesta
   ni se guardó). R8 no la atrapó: el regex no cubría "quedamos en
   que nos vemos" y `tiene_cita` era True por una cita ya pasada.
   Ahora R8 cubre esas frases y mira la cita a FUTURO
   (`tiene_cita_futura`): una cita vieja ya no justifica afirmar una
   nueva.
3. **Reserva para otra persona.** Cuando la cita es para alguien más
   ("para mi hermana"), el robot ahora pide el nombre completo de esa
   persona y el número para registrarla (antes ni lo pedía). El
   agente trae `nombre_paciente`, `relacion_paciente` y
   `numero_paciente`; la cita se crea con el nombre de la otra
   persona, y su respuesta se guarda en las Notas del espejo.
4. **Dos citas en una propuesta.** Si pide la suya y la de otra
   persona (o dos servicios), el agente manda la segunda en
   `citas_extra` y el robot las propone juntas con un solo botón:
   **"Confirmar ambas"**. Al confirmar se crean las dos y el mensaje
   lista cada una. "Cambiar hora" con dos citas pregunta cuál
   cambiar primero (la otra se retoma después).
5. **Tope de 2 citas por número (regla de Jose).** Máximo 2 citas
   activas por teléfono (la suya y la de otra persona), para que
   nadie inunde el calendario. Se revisa antes de proponer y al
   confirmar; con 2 activas, el robot explica el límite y ofrece
   cambiar alguna. Cuenta desde la pestaña Citas (Confirmada/
   Pendiente a futuro), con respaldo en Clientes.

Detalles técnicos: la pestaña Propuestas ganó la columna I
`extra_json` (JSON con los datos de la otra persona y la segunda
cita; vacío en propuestas simples — compatible con filas viejas).
`_confirmar_cita_propuesta` crea cada cita por separado (si una hora
se ocupó, la otra todavía puede quedar; la pendiente sigue sin
afirmarse como creada). Los textos históricos de la pregunta de
datos (v3.4.11) se conservan para una sola cita del dueño. Tests:
nuevo `test_v3_10.py` 41/41; suite completa verde (26 archivos,
508 pruebas). La batería dorada con Gemini real sigue pendiente
en la Mac de Jose.

## v3.9.2 — Ritmo natural: la burbuja sale al instante y ya no dura lo que tarda la IA (2026-11-22)

Jose probó en vivo y reportó: "las burbujas de chat cuando mando
mensaje no se sienten naturales y el tiempo de escritura es
demasiado largo". Tres cambios:

1. **La burbuja sale al instante.** Antes: visto al llegar, 15 s de
   buffer, y recién ahí "escribiendo...". Ahora el webhook prende la
   burbuja junto con el visto (best-effort): el cliente ve actividad
   desde el primer segundo, como cuando una persona ve el mensaje y
   empieza a escribir. Cuando el lote arranca, `atender_mensaje`
   (paso 3) la vuelve a prender, así que se ve continua.
2. **Sin refresco infinito.** Se quitó el hilo que volvía a prender
   la burbuja cada 20 s mientras Gemini pensaba: la burbuja duraba
   lo que tardara la IA (a veces más de un minuto) y eso se siente
   robótico. Una persona escribe un rato y se calla; si la respuesta
   tarda más, la burbuja se apaga sola (~25 s) y la respuesta llega
   cuando está lista. El vigilante de 90 s sigue como red de seguridad.
3. **Menos burbujas partidas.** El guion ahora pide máximo 2 partes
   y solo por temas realmente distintos; si duda, una sola respuesta.
   El tope de código (4) queda como red de seguridad.

Pruebas nuevas en test_v3_9 (k): 38/38; suite completa verde (24 archivos).

## v3.9.1 — El doble "dame un momento" ya no se repite (2026-11-22)

Cuando un lote tardaba más de 90 s, el vigilante mandaba el aviso al
cliente; si después la respuesta era una falla técnica (p. ej. Gemini
con 503), el robot mandaba el MISMO texto otra vez: dos burbujas
idénticas. Ahora `app.py` comparte una bandera (`aviso_lote_enviado`)
con `atender_mensaje`: si el vigilante ya avisó, la falla técnica no
reenvía el texto (el registro en la hoja, el Diagnóstico y el correo
de error quedan igual). Visto en vivo el 2026-11-22 ~03:06 MST.
Prueba nueva en test_v3_9 (j): 36/36; suite completa verde (24 archivos).

## v3.9.0 — Estructura Sereno: duración por servicio, espejo de citas, cita pendiente y correo HTML (2026-11-22)

Adoptada la estructura del ecosistema Sereno (excels del dueño) en
las hojas y en el código:

- **Duración por servicio**: la pestaña Conocimiento ganó columnas
  estructuradas (E a N: ID, categoría, Duración_min, profesionales,
  anticipo, nota de preparación, visible, vigente). La cita dura lo
  que diga la hoja para ese servicio; sin dato, 60. La confirmación
  dice la duración real ("Dura 45 minutos."). Las columnas A a D no
  se tocaron: el robot las lee por posición.
- **Espejo de citas (pestaña Citas)**: vista de solo lectura para el
  dueño (confirmadas, pendientes, canceladas, realizadas, no-show,
  con panel automático). El robot la actualiza al confirmar
  (Confirmada), al cancelar (Cancelada) y al quedar pendiente.
  Editar el espejo no agenda nada: la fuente de verdad es el
  calendario.
- **Cita pendiente (Sereno decisión 1)**: si el calendario falla con
  la hora libre, la solicitud ya NO se reporta como "hora ocupada":
  se le dice al cliente que quedó pendiente, se avisa al dueño por
  correo (`alerta_cita_pendiente`) y el espejo queda Pendiente.
  La hora ocupada (ValueError de booking) sigue con su mensaje de
  siempre.
- **Reporte semanal HTML**: el correo del lunes ahora manda versión
  HTML bonita (KPIs, las 3 secciones, números, resumen) además del
  texto plano. Cuenta canceladas y no-show desde el espejo.
- **Protocolo de urgencias**: la clave `protocolo_urgencias` de
  Configuración entra al guion (texto aprobado del negocio).
- **Clientes Q a V**: consentimiento de mensajes, fecha de
  consentimiento, citas totales, última cita, marca y hora de la
  alerta de handoff. La columna P (robot_activo) sigue igual.
- Pruebas: test_v3_9.py (33 casos). Suite completa verde (24
  archivos). Sin cambios de esquema que rompan: columnas nuevas a la
  derecha y pestañas nuevas; el robot ignora lo que no conoce.

## v3.8.0 — IA apagada: el handoff sigue leyendo (2026-11-22)

Decisión del dueño: "alerta solo en casos graves". Con la IA
apagada —interruptor por cliente o botón global de la clínica—, el
mensaje ahora igual se LEE:

- Urgencia ("me duele...", "urgente"), queja ("queja", "reclamo",
  "pésimo"...) o pedido explícito de persona ("hablar con una
  persona") → se resuelve la mecánica de handoff: correo al dueño
  (`alerta_handoff`, siempre por correo) y caso marcado en Clientes
  con handoff=si. El paciente NO recibe respuesta (la IA está
  apagada).
- Dudas normales → solo quedan registradas, como antes.

El alcance: interruptor por cliente Y botón global (Control). La
pausa de 2 h y el canal apagado no cambian. Lo que ya funcionaba
sigue igual: el botón "hablar con una persona" hace handoff aunque
la IA esté apagada. Pruebas: test_v3_8.py (19 casos).

## v3.7.0 — Alertas del dueño: 3 tipos, un correo semanal (2026-11-21)

Lo que Jose pidió del chat de ChatGPT: las alertas para el dueño
son por correo, una vez a la semana, y solo tres tipos, en ese
estilo de "reporte de valor".

1. **Correo semanal reescrito (generar_reporte_semanal):** un solo
   correo los lunes 08:00 con los 3 tipos:
   - 📅 Citas confirmadas esta semana (lista con fecha bonita).
   - 🙋 Necesitaron atención humana (lista con motivo y cuándo).
   - 💬 Clientes por recuperar (preguntaron y no agendaron, con
     borrador listo para copiar; el robot no manda WhatsApp).
   Más el bloque 📊 TU SEMANA EN NÚMEROS estilo reporte de valor:
   conversaciones atendidas, resueltas sin humano (%), citas
   confirmadas, tiempo ahorrado estimado (5 min por conversación,
   marcado como estimado), mensajes sin respuesta (todos
   registrados). Confirmados vs estimados, sin inventar. El
   esquema de la pestaña Reporte no cambia.
2. **alertas_instantaneas (Configuración):** SI (default, como
   siempre) = alertas de cita y lead caliente al momento. NO =
   esas dos van solo en el correo semanal (sin avalancha de
   correos). El handoff (necesita humano) sigue saliendo al
   momento por seguridad, y también aparece en el semanal. La
   hoja viva y la plantilla quedan en NO.
3. **El resumen de la mañana diario se mantiene** como estaba
   (Jose lo aprobó antes); el semanal es el de los 3 tipos.
4. **Pruebas:** test_v3_7.py (6 casos). Suite completa en verde.

## v3.6.0 — Paquetes y switches por canal (2026-11-21)

Todos tienen el mismo código (la versión pro); el paquete autoriza
qué recibe cada negocio. Jose lo cambia con un botón en la hoja.

1. **Paquetes:** `paquete` en Configuración (basico / pro / premium).
   - básico: responde FAQs, deriva a humano, registra leads. Sin
     agenda, sin fotos, sin reportes.
   - pro: todo lo anterior + agenda con botones, fotos oficiales,
     resumen de la mañana, reporte semanal y alertas de lead.
   - premium: todo lo anterior + Messenger/Instagram (cuando se
     conecten) y seguimiento de leads por recuperar.
   `negocio.funcion_activa(nombre)`: interruptor explícito SI/NO
   manda; si está vacío, decide el paquete; sin paquete, todo SI
   (compatibilidad total con hojas viejas).
2. **Switches por canal:** `canal_whatsapp`, `canal_messenger`,
   `canal_instagram` en Configuración. Si WhatsApp está en NO, el
   robot no contesta (igual que el botón global). Vacío = SI para
   WhatsApp, NO para los demás.
3. **Documento maestro manda:** con NEGOCIOS_SHEET_ID y
   NEGOCIO_CLAVE en Render, el robot lee la fila del negocio en la
   pestaña Índice del maestro (paquete + checkboxes de canales) y
   esos valores ganan sobre la hoja operativa. Sin variables, todo
   sigue como antes. `sheets.leer_pestana` acepta spreadsheet_id
   opcional; la caché ahora distingue hoja + pestaña.
4. **Cortes deterministas:** agenda y fotos usan funcion_activa
   (paquete básico no propone ni manda fotos); reportes se omiten
   en básico; el guion refleja el paquete.
5. **Sheets:** maestro Índice con columnas Clave, Paquete (dropdown)
   y checkboxes WhatsApp/Messenger/Instagram; panel del negocio con
   controles y matriz de paquetes; plantilla y hoja viva con las
   filas paquete/canal_* (la demo queda en pro + WhatsApp SI).
6. **Pruebas:** test_v3_6.py (12 casos). Suite completa en verde.

## v3.5.0 — Multi-negocio: la hoja manda + canales diseñados (2026-11-21)

La evolución que Jose pidió: todo completo, Messenger e Instagram
pensados y con capacidad, pero sin conectar nada por ahora.

1. **Pestaña Configuración (clave | valor) por negocio.** El robot
   la lee en cada mensaje (`sheets.leer_configuracion` +
   `negocio.configuracion`). Prioridad: hoja > variables de entorno
   > defaults. Si la hoja no tiene la pestaña, todo sigue igual que
   siempre (compatibilidad total con la hoja actual).
2. **Perfil desde la hoja:** nombre_asistente, nombre_negocio y
   tipo_negocio ya no dependen solo de Render. El guion se
   reconstruye en cada mensaje (`guion()`, no la constante), así
   los cambios en la hoja aplican sin reiniciar.
3. **Personalización:** tono (amigable/formal/breve/detallado),
   saludo obligatorio y mensaje fuera de horario desde la hoja.
4. **Interruptores SI/NO desde la hoja:** agendar (si NO, no hay
   propuestas ni red de seguridad), enviar_fotos (si NO, no se
   manda ninguna foto), responder_faqs y derivar_humano (instrucción
   en el guion; urgencias y temas sensibles siempre se derivan).
5. **Correo del dueño desde la hoja:** correo_dueno manda; si está
   vacío, se usa OWNER_EMAIL de Render.
6. **Canales diseñados, apagados (robot/canales.py):** un motor,
   varias bocas. WhatsApp activo; Messenger e Instagram con rutas
   /webhook/messenger y /webhook/instagram que responden
   "activo: false" sin procesar nada. Adaptadores con el formato
   único de mensaje ya escritos; se encienden con
   CANAL_MESSENGER_ACTIVO / CANAL_INSTAGRAM_ACTIVO cuando Jose lo
   decida. Nada se conecta por ahora.
7. **Sheets multi-negocio:** documento maestro "Negocios" (Índice +
   panel por negocio con link a su hoja operativa) y hoja plantilla
   "Plantilla — Negocio" con todas las pestañas listas para clonar
   por cliente. Apagado por contacto: ya existía (Clientes!P).
8. **Pruebas:** test_v3_5.py (17 casos). Suite completa en verde.

## v3.4.12 — Bug de correos corregido + lifespan (2026-11-18)

Incorpora los arreglos de higiene de Arena (revisados y probados):

1. **Bug real corregido (mail.py):** los correos al dueño
   (`alerta_cita_confirmada`, `alerta_lead_caliente`) traían
   literales `\\n` en vez de saltos de línea: el texto llegaba con
   "\n" escrito. Ahora son saltos de línea de verdad.
2. **Lifespan de FastAPI:** `@app.on_event` (deprecado) →
   contexto `lifespan` en app.py. Mismo comportamiento de arranque
   y apagado, sin la advertencia de deprecación.
3. **Docs:** README con los conteos reales de pruebas (334;
   284 estaba desactualizado).
4. **Higiene:** `.DS_Store` agregado al .gitignore.

No se tomó `runtime.txt` 3.14 (el 3.12 de Render está probado; el
cambio no aporta funcionalidad). Suite completa + batería de
inteligencia en verde (41/41).

## v3.4.11 — Calidez con marketing, confirmación sin fricción y fechas a prueba de hoja (2026-11-18)

Calidad de comunicación aplicada con principios de marketing:
calidez que vende (la gente agenda porque se siente bien atendida),
fricción cero en el momento de la decisión, y datos pedidos después
del compromiso (primero el sí, luego los datos).

1. **Guion con calidez y marketing.** Nueva sección "Calidez: cómo
   se siente hablar contigo": persona de recepcionista buena onda,
   usar el nombre con naturalidad, validar emociones, celebrar los
   sí, tranquilizar ante miedos, vender el resultado al proponer
   ("sin dolor y en una sola cita"), explicar para qué se pide un
   dato ("para dejarte bien registrado"). Regla dura nueva:
   "Propuesta no es cita" — nunca afirmar una cita solo propuesta.
2. **Confirmación sin fricción.** La propuesta ya NO pide nombre ni
   número (antes mezclaba datos + confirmación + botones en un
   mensaje: el cliente no sabía si contestar o tocar). Se piden
   DESPUÉS de confirmar, en mensaje aparte y cálido, solo lo que
   falte. La confirmación quedó corta y limpia: "¡Perfecto, Juan!
   Tu cita quedó para el... / Dura 60 minutos. / Si necesitas
   cambiarla, escríbeme y la reacomodamos con gusto." Cancelar y
   cambiar también se calentaron ("Sin problema...").
3. **Revisor R8:** si el cliente no tiene cita creada, frases como
   "ya estás apuntado" o "tu cita quedó" se quitan; si la respuesta
   era solo eso, se ofrece confirmar con botones. (En vivo dijo
   "ya estás apuntado" sin que existiera ninguna cita.)
4. **Fechas a prueba de la hoja.** La hoja reinterpretaba las
   fechas escritas con USER_ENTERED ("2026-11-19T09:00:00-07:00" se
   leía como "2026-11-19 9:00:00"): el cliente veía la fecha cruda
   al cancelar y el borrado en Calendar fallaba en silencio. Ahora
   la hoja escribe con RAW y el parseo es tolerante (rellena la
   hora de un dígito) en logic.py y booking.py.
5. **Tests:** test_v2 (i3/i3b/i4) al flujo nuevo, test_inteligencia
   +5 escenarios (A9, B10, B11, E11, E11b), test_v2_13 +6 (R8,
   fechas), test_v3_3 +3 aserciones de guion, doradas G15/G18/G20
   al flujo nuevo.

## v3.4.10 — Corrección de fecha con sentido y batería de inteligencia (2026-11-18)

1. **La corrección de fecha respeta lo pedido.** Si el cliente pide
   un día cerrado (domingo) o una hora fuera de horario, el robot ya
   no corrige a "mañana" (que puede ser antes de lo pedido): busca
   la próxima apertura EN la fecha pedida o después. `proxima_apertura`
   acepta `desde` y nunca devuelve una fecha pasada. Pedir domingo
   ahora da lunes 09:00, no jueves.
2. **Batería de pruebas de inteligencia** (`test_inteligencia.py`):
   36 escenarios en 5 categorías (botones, agenda, handoff,
   documento de info, calidez y entendimiento), sin internet ni
   clave de API. Corre en cualquier lado: `python test_inteligencia.py`.

## v3.4.9 — Inteligencia para manejar las situaciones (2026-11-18)

Auditoría completa del código contra las ~28 situaciones del
playbook: dónde se decidía con palabras y dónde con código. Se
cerraron los huecos donde el robot decidía mal o de más:

1. **El nombre que el cliente da después de la propuesta se guarda
   en ella.** El robot pide nombre completo y número al agendar; si
   el cliente los da en el mensaje siguiente, la propuesta pendiente
   se actualiza. La confirmación ya no sale con nombre vacío
   ("Listo, ."): sin nombre dice "Listo." y el evento del calendario
   usa "Cliente" en vez de dejar el título en blanco.
2. **Número de registro.** Si el cliente dice "regístralo al
   6671234567", ese número se extrae (`_extraer_telefono`), se
   guarda en la propuesta y la cita queda registrada a ese número:
   va en la descripción del evento de Calendar y se le confirma al
   cliente en el mensaje ("Quedó registrada al ...").
3. **Cambiar con fecha nueva → propuesta nueva.** "Mejor el viernes
   a las 10" ya no recibe "¿Qué día y hora te vienen mejor?" (que
   ignora lo que el cliente ya dijo): se borra la propuesta vieja y
   el agente propone la nueva con botones. Los cambios vagos
   ("prefiero otra") siguen con la pregunta de siempre. El playbook
   ahora lo dice: "si dice el nuevo día y hora, propónlo con
   botones".
4. **"No" a la propuesta.** Un "no" pelón con propuesta pendiente
   es "esa hora no": se pregunta por otro día, sin pasar por la IA.
5. **Emoji que confirma.** "👍" (o ✅/🆗/👌) con propuesta pendiente
   confirma la cita, como la gente confirma todo el tiempo. Y un
   mensaje sin letras ni números (solo emojis) recibe respuesta
   cálida directa, sin gastar una llamada a la IA.
6. **La fecha propuesta se revisa contra el calendario.** Si la hora
   que el agente calculó ya está ocupada, se usa el primer hueco
   libre real (`hora_libre` en Dependencias). Así la confirmación no
   falla con "esa hora ya se ocupó".
7. **Saludo con intención.** "Hola, quiero agendar" ya no es etapa
   "saludo": el estado detecta palabras de intención (agendar, cita,
   precio...) y el revisor ya no quita la oferta que el cliente sí
   pidió.
8. **Sin doble pregunta de confirmación.** Si el agente escribió
   "¿Te agendo...?" en su texto, el código la quita: el sistema
   agrega la confirmación con botones. Nunca dos "¿Confirmo...?" en
   el mismo mensaje. El revisor también reconoce "¿Te reservo...?"
   como oferta.

## v3.4.8 — Visto instantáneo, propuesta sin duplicados y playbook (2026-11-18)

Cuatro mejoras pedidas por Jose tras ver la conversación en vivo:

1. **Visto instantáneo.** En cuanto llega un mensaje se marca como
   leído (palomitas azules), antes de esperar los 15 segundos del
   buffer. El "escribiendo..." sigue saliendo solo cuando el robot
   de verdad está redactando. Nueva función `marcar_leido` en
   `robot/whatsapp.py`, llamada desde `_ingresar_mensaje` en
   `app.py` (best-effort: si falla, el mensaje sigue su curso).
2. **La propuesta siempre pide nombre y número.** Si el agente
   propone con botones pero no pidió el nombre completo y el número
   de registro, el código lo agrega. El paso que vende no se deja
   al azar del modelo.
3. **Sin botones duplicados.** Si ya hay una propuesta con botones
   pendiente para la MISMA cita (misma fecha, vigente menos de
   48 h), no se mandan botones otra vez: el cliente recibe el texto
   (su pregunta contestada) y la propuesta sigue viva. En vivo, dos
   mensajes seguidos generaron dos "¿Confirmo tu cita...?" para la
   misma cita.
4. **Playbook en el guion.** Nueva sección "Playbook: situaciones
   frecuentes y hacia dónde llevar la conversación" en
   `robot/agent.py` (y su espejo en `guion-robot.md`): ~28
   situaciones recurrentes con la frase exacta y el propósito de
   cada respuesta (que se sienta atendido, recibido, en calma, y
   que la conversación avance hacia la cita, la calificación o una
   persona). Además: el agente ya no pregunta "¿Te agendo?" ni
   "¿Confirmo?" cuando propone con botones (el sistema agrega la
   confirmación), ni "¿a qué hora te gustaría?" si ya propone un
   hueco; y con propuesta pendiente contesta la pregunta sin
   mandar botones nuevos.
5. **Partes.** El agente puede decidir si su respuesta va en 1 solo
   mensaje o en varios (campo opcional "partes" en el JSON): cada
   parte es su propio mensaje, en orden, con pausita entre cada
   una. Cada parte pasa por el revisor. Sin "partes", todo sigue
   igual que antes.

Tests: +5 casos en `test_v2.py` (35/35), +4 afirmaciones de guion
en `test_v3_3.py` (46/46). Suite falsa completa en verde. La
batería dorada queda pendiente de correr en la Mac de Jose.

## v3.4 — Que nunca se calle (2026-11-13)

El 13 de noviembre, a las 02:00, el robot dejó de contestar: el
webhook devolvía 200, pero ningún lote se procesaba, no había filas
nuevas en la hoja ni aviso del vigilante, y no había nada que mirar
para saber por qué. El código estaba bien (la misma prueba, en local,
procesó el lote y dejó constancia); el proceso en Render tenía el
trabajo de segundo plano atascado mientras el servidor web seguía
respondiendo. El reinicio del despliegue lo despeja, y esta versión
pone dos cosas para que no vuelva a pasar en silencio:
(1) el Agrupador libera solo un teléfono atascado más de 5 minutos
(un lote muerto ya no deja mudo a ese cliente para siempre);
(2) GET /estado: versión, tiempo prendido, salud lista o no,
webhooks recibidos, lotes iniciados/terminados/fallidos, último
error, lotes pendientes y en proceso. Solo números, sin teléfonos
ni datos de clientes. El webhook cuenta cada mensaje que llega y
cada lote cuenta su inicio y su fin. 9 casos nuevos en
`test_v3_4.py` (284 en total). El caso (e) de `test_v2_12.py` se
actualizó (el Agrupador tiene un parámetro más).

## v3.3.1 — El cliente también escucha el handoff (2026-11-13)

Jose lo pidió al ver la v3.3: en un handoff normal, el cliente
también debe recibir el texto (\"te paso con una persona...\"). Antes
solo llegaba el correo al dueño y el cliente quedaba en silencio
esperando a que un humano se diera cuenta. Ahora el paso 8 manda el
texto del agente (o el fijo de la urgencia) y lo registra, y
`respondio` es True en todos los handoffs. La dorada G5 ahora exige
además que el cliente reciba el texto. El caso 7 de
`test_simulado.py` (que afirmaba lo viejo: \"no responde por
WhatsApp\") se actualizó a lo nuevo. 2 casos nuevos en `test_v3_3.py`
(275 en total).

## v3.3 — Calidad para el dueño y para su cliente (2026-11-13)

Jose preguntó qué funciones de calidad se podían incorporar ya, de
forma segura, pensando como sus clientes (los negocios) y como los
clientes de sus clientes (la gente que escribe). Seis, todas sin
claves nuevas ni cambios de arquitectura:

- **Horas libres de verdad.** El agente ofrecía \"mañana a las 9:00\"
  sin saber si estaba libre, y al confirmar salía \"esa hora ya se
  ocupó\" (pasó en vivo el 12 de noviembre). Ahora
  `booking.proximos_huecos_libres` busca los próximos 2 huecos libres
  con UNA llamada freebusy (caché de 60 s) y el contexto solo le pasa
  esos dos al agente. Sin huecos, el contexto dice que la agenda está
  llena. Si Calendar falla, no se dice nada y el agente actúa como
  antes (nunca se inventa una hora).
- **Preguntar el nombre.** Si el robot no sabe cómo se llama el
  cliente, el contexto le pide preguntárselo una sola vez (\"¿Con
  quién tengo el gusto?\"). Si ya lo preguntó en su último mensaje,
  no repite.
- **Urgencias a humano.** Palabras de urgencia o de dolor (\"me
  duele\", \"sangrando\", \"emergencia\") van directo a una persona,
  sin llamar a la IA: el cliente recibe el texto en ese momento y el
  dueño un correo. \"¿Duele la limpieza?\" no es urgencia. Encontrado
  al probar: en un handoff normal el texto del agente no se manda al
  cliente (solo el correo al dueño); en la urgencia sí, porque el
  silencio sería lo peor.
- **Resumen de la mañana.** Todos los días 08:00, por correo: lo de
  las últimas 24 h, quién necesita una persona, propuestas sin
  contestar (con sus apartados) y las citas de hoy. Sin IA: números
  y listas de la hoja. El semanal sigue los lunes.
- **Alertas en el momento.** Lead caliente (el cliente pidió agendar
  con sus palabras) y cita confirmada (botón o \"sí\"): correo al
  dueño en ese momento, con nombre, teléfono y fecha.
- **Anti-abuso.** `robot/abuso.py`: más de 10 mensajes en 60 s por
  teléfono → se le avisa una vez y se ignoran los demás hasta que
  pase la ventana. Protege la cuota gratis de Gemini.
- 31 pruebas nuevas en `test_v3_3.py` (273 en total). Doradas: 12 →
  15 (G13 huecos libres, G14 urgencia, G15 preguntar el nombre).
  El caso (g) de `test_v2.py` se actualizó: ahora son dos trabajos
  programados, los dos por correo (semanal + resumen de la mañana).

## v3.2 — Memoria (2026-11-13)

Jose preguntó: "¿y la memoria? ¿qué le falta de lo básico?" La
respuesta honesta: el robot tenía memoria de loro —todo quedaba en la
hoja, pero solo leía los últimos 8 mensajes y las columnas de Clientes
hechas para recordar (resumen, intereses, próxima acción, notas)
estaban vacías. Ahora recuerda de verdad.

- **Resumen vivo del cliente.** El agente devuelve en su JSON lo que
  aprendió (resumen, interés, próxima acción, preferencias) y eso se
  guarda en Clientes (K, L, N, O). En el siguiente mensaje el contexto
  empieza con "Lo que sabes de este cliente". Solo se escribe lo nuevo;
  un campo vacío no borra nada; las preferencias se acumulan.
- **Memoria de apartados.** "Te aparto el lugar hasta mañana" ya no
  es una promesa verbal: queda guardada en Propuestas (columnas nuevas
  G apartado, H aparta_hasta) y el contexto se lo recuerda al agente
  cuando el cliente vuelve.
- **R7: no repetirse.** Si la respuesta cierra con la misma frase del
  último mensaje del robot ("Quedamos a tus órdenes" tres veces
  seguidas en vivo), esa frase se quita; si era todo el mensaje, se
  cambia por "¿Te ayudo con algo más?".
- 17 pruebas nuevas en `test_v3_2.py` (242 en total). Doradas: 10 → 12
  (G11 memoria entre días, G12 apartado recordado).

## v3.1 — Calidad y seguridad (2026-11-13)

Prueba en vivo con la v3.0 en Render (00:00-00:05): el robot ya
contestaba bien —preguntaba cuál servicio, daba el precio exacto,
decía que no a lo inventado—, pero dejó 5 fallos. Todos corregidos
aquí, con pruebas.

- **La oferta se repetía 3 veces seguidas.** El agente ofrecía la
  cita en el texto sin marcar `quiere_agendar`, así que no había
  propuesta guardada y el estado decía que no había oferta: el
  revisor no tenía nada que quitar. Ahora el estado detecta la
  oferta en el último mensaje del propio robot (`estado.py`, v3.1).
- **"Mañana viernes" cuando hoy YA era viernes.** El contexto ahora
  dice "Mañana es sábado 14 de noviembre." explícito, y el revisor
  R4 corrige el día si el modelo se equivoca.
- **La dirección salió con "(dirección FICTICIA, de ejemplo)".**
  La hoja se limpió (esa nota no va en el texto que lee el robot) y
  el revisor R5 quita paréntesis y palabras internas que se cuelen.
  Dos preguntas que el robot no supo contestar (qué productos usan,
  si meten cosas en la boca) ahora son filas de Conocimiento.
- **Anti-extracción (R6).** Un cliente pidió el prompt y la base de
  datos. El guion ahora lo prohíbe y el revisor desecha entera
  cualquier respuesta que traiga el guion, campos internos o un
  teléfono ajeno. Dorada G10 lo prueba contra la IA real.
- **Un lote se quedó más de 45 minutos sin responder ni fallar, sin
  rastro.** Ahora hay vigilancia: a los 90 s queda en Diagnóstico
  ("lote TARDANDO") y el cliente recibe un "dame un momento". Las
  llamadas a Google (Sheets, Calendar) llevan timeout de 30 s.
- **Multi-pregunta.** El guion ahora dice: contesta TODAS las
  preguntas, una por una; si una no está en Conocimiento, di que lo
  confirmas y pasa a una persona. Dorada G9 lo prueba.
- 27 pruebas nuevas en `test_v3_1.py` (225 en total). Doradas: 8 → 10.

## v3.0 — El producto (2026-11-12)

Revisión completa del repositorio: lo que estaba crudo, corregido.

- **Reporte semanal en texto plano.** La v2.13 puso JSON obligatorio
  en todas las llamadas a Gemini y el resumen del lunes llegaba con
  llaves crudas en el correo. Ahora `generar_texto` tiene modo texto
  y modo JSON: el agente usa JSON, el reporte y la autoprueba, prosa.
- **Seguridad.** `/pausa` y `/reporte-semanal` protegidos con clave de
  dueño (`ADMIN_TOKEN`, la crea el instalador). El webhook verifica
  la firma de Meta (`META_APP_SECRET`).
- **Perfil del negocio.** Nombre, giro y recepcionista en la
  configuración. El robot dejó de decir "la clínica" a mano: de noche
  dice "El negocio ya cerró por hoy, pero yo te atiendo igual", o usa
  el nombre real si está configurado.
- **Salud al arrancar.** Gemini, hoja, calendario, token de WhatsApp,
  Gmail, correo del dueño y claves de seguridad: cada pieza se revisa
  y queda en Diagnóstico (OK / AVISO / FALLO).
- **Sheets con caché.** Cada pestaña se guarda 10 s en memoria: un
  mensaje pasó de ~8-12 llamadas a Google a ~4-5. Clientes ya no se
  lee tres veces.
- **Buzón persistente.** Los lotes pendientes y los wamids ya vistos
  se guardan en `buzon.json` y se recuperan al arrancar. Un reinicio
  ya no pierde mensajes.
- **Pausa humana usable.** Página del dueño en `GET /pausa` ("ya
  contesté yo"): pone el teléfono y el robot se calla 2 horas. Si la
  hoja falla, la página lo dice en vez de un error vacío.
- **Limpieza Apple.** README reescrito como documento de producto
  (la historia se vino aquí), `logic.py` sin su diario de versiones
  ni código muerto, versión 3.0.0 en un solo lugar, `.env.example` y
  `render.yaml` vigentes (modelos vivos, 15 s, claves nuevas),
  instalador al día, registro con niveles en vez de 22 prints.
- **Pruebas nuevas:** `test_v3.py`, 28 casos. Total: 197/197 offline.

## v2.13 — El motor nuevo (2026-11-12)

Análisis completo del motor de conversación (7 defectos): el guion se
contradecía, no había revisión antes de mandar, no había estado, los
atajos de palabras actuaban sin entender, el debounce era solo tiempo,
Gemini iba sin frenos y las pruebas probaban el prompt, no el robot.

- Estado por código (`robot/estado.py`): etapa, oferta pendiente,
  último mensaje del robot, como datos.
- Guion corto, sin contradicciones (55 líneas).
- Revisor determinista antes de mandar (`robot/revision.py`): R1 no
  repetir oferta, R2 no ofrecer en un saludo, R3 "ya cerramos" por la
  frase de cierre. Correcciones en Diagnóstico.
- Frenos en Gemini: temperatura 0.3, JSON obligatorio en la API, tope
  de 600 tokens. El agente guarda qué modelo contestó.
- Conversaciones doradas: 8 conversaciones completas contra la IA
  real, puerta de calidad antes de desplegar.
- Pruebas: 18 nuevas. Total: 169/169 offline.

## v2.12 — Espera, no repitas, y de noche tú no cierras (2026-11-12)

- Debounce de 7 s a 15 s.
- No repetir la oferta pendiente; no ofrecer cita en un saludo.
- De noche: "La clínica ya cerró por hoy, pero yo te atiendo igual",
  nunca "ya cerramos" como si el robot cerrara.
- Pruebas: 7 nuevas. Total: 151/151.

## v2.11 — Comercialmente voraz, sin parecer desesperada (2026-11-12)

- Cada respuesta avanza hacia la cita: beneficio primero, precio
  después, cita al final, siempre con DOS opciones concretas.
- Guion para "lo voy a pensar" (apartar el lugar sin compromiso).
- Prohibido rogar, repetir, inventar urgencia o descuentos.
- Pruebas: 9 nuevas. Total: 144/144.

## v2.10 — Prompt comercial (2026-11-12)

- Persona Ana, la recepcionista: cálida, mexicana, a la orden.
- Método Entiende-Responde-Avanza. Cero inventos: solo Conocimiento
  palabra por palabra, o handoff.
- Pruebas: 8 nuevas. Total: 135/135.

## v2.9 — Cambio de IA (2026-11-12)

- Modelo principal `gemini-4-hydrogen` (gratis, lanzado ese día),
  respaldo `gemini-3.8-flash`, `gemini-3.5-flash-lite` al final.
- 503 con reintentos de 2 s y 8 s.
- Pruebas: 7 nuevas. Total: 127/127.

## v2.8 — Ya no se rinde a los 60 segundos (2026-11-12)

- Timeout de 120 s con reintento y cambio de modelo.
- La prosa de Gemini (no-JSON) se manda tal cual al cliente.
- Historial recortado a los últimos 8 mensajes.
- Pruebas: 6 nuevas. Total: 119/119.

## v2.7 — Se corrige solo (2026-11-12)

- Modelos vigentes `gemini-3.8-flash` + `gemini-3.6-flash` (los 2.0 y
  2.5 retirados por Google dejaban al robot sin cerebro: 404).
- Autocuración: si Google sugiere otro modelo en el error, lo prueba.
- Pestaña Diagnóstico: salud del robot sin capturas.
- "Sí" tras un fallo técnico ya no confirma una cita.
- Pruebas: 9 nuevas. Total: 113/113.

## v2.6 — La IA contesta siempre (2026-11-12)

- Se eliminó la frase grabada de fuera de horario: todos los mensajes
  van al agente, de día y de noche, con contexto (hora, abierto o
  cerrado, nombre, propuesta pendiente).
- Si Gemini falla: "dame un momento" honesto + correo al dueño.
- Autoprueba de Gemini al arrancar.
- Pruebas: 7 nuevas. Total: 105/105.

## v2.5 — 24/7 de verdad (2026-11-12)

- Propuestas de cita persistentes en la hoja Propuestas (sobreviven
  a un reinicio de Render).
- De noche, todo el que escribe queda registrado como lead.
- Fotos, stickers, ubicaciones y audios no entendidos reciben
  respuesta corta en vez de silencio.
- Reintento de Gemini en 429/500/502/503.
- Pruebas: 9 nuevas. Total: 97/97.

## v2.4 — De noche sí hay IA, y cambiar/cancelar cita funciona (2026-11-12)

- El agente atiende también de noche (antes, de noche solo había
  frase grabada: tres mensajes seguidos recibieron la misma línea).
- Cambiar/cancelar cita funciona de día y de noche.
- Pruebas: 13 nuevas. Total: 88/88.

## v2.3 — El interruptor por cliente sí funciona (2026-11-12)

- Columna `robot_activo` en Clientes (SI/NO) respetada de verdad.
- "Hablar con una persona" sigue funcionando con el robot apagado.
- Pruebas: 10 nuevas. Total: 75/75.

## v2.2 — Fuera de horario ya no pierde al cliente (2026-11-12)

- La propuesta fuera de horario se guarda y se confirma por texto.
- Clientes sin duplicados: un cliente, una fila (fusión con estatus
  que nunca baja y handoff que se queda).
- Pruebas: 15 nuevas. Total: 65/65.

## v2.1 — Gmail ya no rompe las respuestas (2026-11-12)

- Las alertas por correo son best-effort: si Gmail falla, el cliente
  recibe igual su respuesta de WhatsApp.
- Pruebas: 28 en total en `test_v2.py` (v2 + v2.1).

## v2 — Lo que se siente humano (2026-11-12)

- Visto + "escribiendo..." (palomitas azules, burbuja de 25 s).
- Debounce: espera al último mensaje y contesta todo junto.
- Ritmo humano: 1-3 s de espera, respuestas largas partidas en ~300
  caracteres.
- Botones Confirmar / Cambiar hora / Hablar con una persona: la cita
  se crea solo al confirmar.
- Fracaso con gracia: "dame un momento" + correo al dueño, nunca
  silencio. Sin recordatorios por WhatsApp (decisión de Jose).
- Instalador en español + `render.yaml` + `DESPLEGAR.md`.
- Pruebas: 28 nuevas. Total: 51/51 (23 v1 + 28 v2).

## v1 — El robot base (2026-11-12)

- Webhook, agente Gemini, Sheets, Calendar, Gmail, reporte semanal.
- Kill-switch global, pausa humana de 2 h, fotos solo oficiales.
- 23 pruebas simuladas. Primer mensaje real contestado el 12 de
  noviembre de 2026; primera cita agendada de verdad ese mismo día
  (viernes 13 de noviembre, 09:00).
