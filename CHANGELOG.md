# CHANGELOG — La historia del robot, en orden

La historia de cada versión, para no cargarla en el código ni en el
README. El README describe lo que el robot hace HOY; aquí queda lo
que hacía antes y por qué cambió. Si algo se rompió en vivo, aquí
queda la fecha y la causa.

## v3.20.3 — Pulida agrupamiento/handoff/botones: doble toque, correos que sí salen y miedos con columna propia (2026-11-24)

Jose pidió una pulida profunda de los tres motores (agrupamiento,
handoff y botones) y aplicar las 5 propuestas de la pulida pasada
donde fuera seguro. Nueva `test_pulida_agrupamiento.py` (35
casos) + mejoras aplicadas:

- **Bug crítico: los correos de handoff nunca salían.** `logic.py`
  pasa `hilo` a `alerta_handoff` desde v3.20, pero
  `DependenciasReales` en `app.py` no aceptaba ese parámetro: el
  TypeError se tragaba en silencio y recepción nunca recibía el
  correo. Ahora `app.py` lo acepta y lo pasa a `mail`.
- **Doble toque en Confirmar creaba DOS citas.** El webhook corre
  en un hilo por mensaje y `_CITAS_PENDIENTES` no tenía candado:
  dos toques casi a la vez leían la misma propuesta antes de
  borrarla. Ahora `atender_mensaje` y `atender_boton` se serializan
  por teléfono (RLock): el segundo toque espera y ya no encuentra
  propuesta. Teléfonos distintos corren en paralelo.
- **El interruptor general no frenaba los botones.** Con
  `bot_activo=NO` en Control, un Confirmar seguía creando citas.
  Ahora los botones de cita revisan el interruptor global (salvo
  "hablar con persona", que es el camino al humano).
- **El botón se saltaba la fila.** Un toque de botón se atendía al
  instante aunque el cliente tuviera textos en el buzón de
  agrupamiento, y el lote se procesaba después sobre una propuesta
  ya consumida. Ahora `app.py` vacía el buzón (`procesar_ahora`)
  antes de atender el botón.
- **Handoff siempre con contexto completo.** El correo de
  "hablar con persona", el handoff en silencio (IA apagada) y los
  correos de adelanto/mover ahora traen el hilo de la conversación
  y el resumen, como el handoff por texto.
- **"Dejarla igual" viejo prometía una persona que nunca llegaba**
  (sin propuesta, sin correo). Ahora responde "Esa opción ya no
  está disponible" y, con propuesta real, el correo de handoff sí
  sale con el hilo.
- **Wamids con desalojo FIFO.** Al pasar el tope de 5000, antes se
  borraban TODOS los wamids vistos y un reenvío de Meta se
  reprocesaba (respuesta duplicada). Ahora se desalojan los más
  viejos; el Agrupador acepta `max_vistos`.
- **R11 con valor exacto (propuesta 2, aplicada).** Si el negocio
  sí maneja descuentos, solo se permiten los porcentajes literales
  del Conocimiento ("10% los martes" permite el 10%, no el 15%) y
  las mecánicas literales (2x1, rebaja, oferta especial).
- **Miedos con columna propia (propuesta 1, aplicada).** Nueva
  columna W "Miedos / sensibilidades" en Clientes (documento
  oficial y plantilla). El agente devuelve `miedos` en su JSON, se
  guarda en W (se acumula sin duplicar) y el contexto lo incluye
  como "Le dan miedo o le molestan: ...". Compatibilidad hacia
  atrás: si la hoja no tiene el encabezado, no se escribe nada y
  el miedo sigue en el resumen.
- **Typos inequívocos nuevos (propuesta 3, aplicada).**
  "desagendar"/"desagenda" cancelan y "pospon" cambia, con sus
  negaciones ("no quiero desagendar" no cancela). Conservador:
  nada de fuzzy amplio ("cansado" ≠ "cancelar").

Propuestas que quedaron para Jose (sin heurística segura o sin
entorno): R13 amplio (no se puede distinguir determinísticamente
una re-pregunta dañina de una re-respuesta legítima) y la
calibración de tono con IA real (necesita GEMINI_API_KEY en su
Mac; la rúbrica está lista).

Suite completa en verde (41 archivos, incluida la nueva
`test_pulida_agrupamiento.py` con 35 casos).

## v3.20.2 — Pulida conversacional: clientes emocionales, descuentos inventados y errores de dedo (2026-11-24)

Jose pidió una pulida profunda del motor conversacional con AI
(el guion, el prompt, la memoria y el revisor) antes de subir la
siguiente versión. Nueva `test_pulida_conversacional.py` (45
casos) + mejoras aplicadas:

- **R11 — ningún descuento inventado (revisor):** R9 cazaba los
  precios ($N) pero no las promesas de descuento ("te hago un 20%
  de descuento", "te aplico una promoción"). Ahora, si el
  Conocimiento no habla de descuentos, la respuesta se desecha
  entera y sale la frase segura. Las negaciones ("no manejamos
  descuentos") pasan intactas; si el negocio sí maneja descuentos,
  la IA puede mencionarlos.
- **R12 — fuera el robot-speak de "pendientes":** "quedamos en tus
  pendientes" es lenguaje de sistema; el guion lo prohíbe pero
  nada lo atrapaba. Ahora se quita la frase (el "pendiente" en
  singular, "quedó pendiente tu cita", no se toca).
- **R13 — no re-preguntar lo mismo tras un "ok":** si el cliente
  contestó con un "ok"/"gracias" y la respuesta es casi la misma
  pregunta que el robot ya había hecho, se reemplaza por "¿Te
  ayudo con algo más?". Deliberadamente estrecha: si el cliente
  repitió su pregunta, re-contestar parecido es legítimo.
- **"Te propongo" es una oferta verbal:** "Te propongo tu cita
  para el martes a las 9:00" no era detectada como oferta, así que
  el estado no veía la oferta y el robot la repetía. Ahora cuenta
  (con contexto de cita; "te propongo que lo pienses" no).
- **Errores de dedo en cancelar/cambiar:** "canselo mi cita",
  "cancelo", "anulo" y "canbiar la cita" no coincidían con nada e
  iban al agente: el cliente creía que canceló y la cita seguía
  viva. Ahora cancelan y cambian de verdad (con sus negaciones:
  "no canselo" no cancela).
- **Quejas delicadas en la red de seguridad:** "no me gustó la
  cita pasada", "quedé inconforme", "me atendieron mal", "me
  dolió después de la cita" ahora se detectan como queja (alerta
  al dueño cuando la IA está apagada).
- **Guion: clientes emocionales y difíciles.** Entradas nuevas en
  el playbook (sincronizadas en `agent.py` y `guion-robot.md`):
  miedo/fobia (cucarachas, agujas, el dentista), cliente triste o
  abrumado, queja delicada (escuchar, lamentar, pasar a persona,
  sin compensar con otra cita), pedidos fuera de lo normal (en su
  casa, trueque, descuento por grupo: no inventar, confirmar con
  el encargado + handoff) y contradicción entre mensajes seguidos
  (quédate con lo ÚLTIMO). Además: instrucción anti-repetición de
  frases y miedos guardados en el resumen de memoria para atender
  al cliente con cuidado la próxima vez.
- **Rúbrica de tono para la batería dorada** (`RUBRICA-TONO-GOLDEN.md`):
  lista para que Jose califique el tono de la IA real en su Mac.

Suite completa: 40/40 archivos en verde (incluyendo la nueva
`test_pulida_conversacional.py` 45/45). Pendiente: subir a Render
(en vivo sigue v3.20.1) y correr la batería dorada con IA real en
la Mac de Jose.

## v3.20.1 — Corrida adversarial profunda: 6 bugs reales (2026-11-24)

Jose pidió una corrida profunda antes de subir la última versión.
Nueva `test_corrida_adversarial.py` (25 casos) + barrida propia
sobre los clasificadores y el flujo real. Bugs reales corregidos:

- **Confirmación de asistencia falsa (03):** "confirmo que no
  podré ir" registraba "Paciente confirmó asistencia" y respondía
  "¡Perfecto! Quedó confirmada tu asistencia" a quien decía que
  NO podía ir; "confirmo pero quiero cambiar" se tragaba la
  petición de cambio. Ahora solo las confirmaciones puras cuentan:
  negación o cambio/cancelación van al flujo correcto.
- **Falsa urgencia por "no tengo dolor" (05):** "no tengo dolor,
  solo quiero una limpieza" disparaba el protocolo de urgencia
  (handoff + propuesta urgente). Ahora es negación, no urgencia.
- **Señales médicas que faltaban (05):** "sangro mucho" y "se me
  hinchó la cara" no disparaban la urgencia (la lista solo tenía
  "sangrando"/"sangre" e "hinchado/a"). Raíces "sangr" e "hinch".
- **Citas ajenas intocables (02):** "cancela la de mi vecino" o
  "cambia la cita de mi hermana" cancelaban la cita del propio
  cliente. Ahora van al agente, que lo atiende conversando.
- **"no quiero la cita" es cancelar (02):** antes caía en el
  "no quiero" de cambiar y el robot preguntaba "qué día te viene
  mejor para la nueva". "no quiero esa hora" sigue siendo cambiar.
- **"cancelar" con solo propuesta (02):** confirmaba la
  cancelación en vez de preguntar por un día nuevo.
- **Tests:** nueva `test_corrida_adversarial.py` (25 casos);
  2 casos de la simulación profunda (x8/v9) actualizados: con la
  guarda, la respuesta sale por botones (agente) en vez del texto
  mecánico — la invariante (nada cancelado) se mantiene. Suite
  completa verde + baterías (dinámica 4 semillas sin violaciones,
  profunda 99/99, conversacional 27/27).

## v3.20.0 — Calidad conversacional: funciones 01, 04 y 05 (2026-11-23)

Jose pidió rectificar el código para mejorar la calidad en la función
completa (01 Conversaciones naturales, 04 Memoria útil, 05 Atención
humana cuando importa). Auditoría contra el código real y mejoras:

- **R10 (01):** el revisor ahora atrapa la respuesta ENTERA repetida
  (antes R7 solo quitaba el cierre repetido). Si la IA parrotea el
  último mensaje del robot, se reemplaza por "¿Te ayudo con algo
  más?" y se registra en Diagnóstico.
- **Historial más ancho (01):** el prompt lleva los últimos 8
  mensajes (antes 5): más contexto para recordar de qué hablaban.
- **Cita pasada con servicio (04):** el contexto dice "Su última
  cita fue Blanqueamiento dental el ..." (antes solo la fecha):
  el robot reconoce al paciente recurrente por lo que se hizo.
- **Preferencias en el guion (04):** si el robot sabe que el cliente
  prefiere mañanas/tardes, propone en ese horario y no pregunta de
  nuevo lo que ya dijo.
- **Handoff con hilo (05):** el correo de alerta trae los últimos 8
  mensajes de la conversación: recepción ve la foto completa sin
  abrir la hoja.
- **Bug real corregido (01):** "mejor no, quiero cambiarla" (=
  "esa no, otra") era tragado por la negación v3.16 ("no quiero
  cambiar" aparece dentro tras quitar la coma): el cambio se
  perdía. Ahora es cambiar. También se cubrieron negaciones
  faltantes ("no me cambies la cita" ya no cambia nada).
- **Tests:** nueva `test_v3_20.py` (14 casos), 3 viajes nuevos en la
  simulación conversacional (27 total), regresiones en
  `_intencion_cambio`. De paso se corrigieron 3 tests viejos que
  llevaban fallando sin verse (precio $600 contra conocimiento
  $500, historial 5 vs 8, R7 vs R10) y 2 fallos reales del mismo
  bug de negación (test_v2_4 y test_v2_5).

## v3.19.0 — Simulación conversacional: 24 viajes completos (2026-11-23)

Jose pidió una corrida puramente conversacional para adelantarse a
los bugs y asegurar calidad. Nueva `test_simulacion_conversacional.py`:
24 viajes multi-turno (5 a 9 turnos cada uno) contra el código real,
verificando al final citas, correos, handoffs, propuesta viva o
consumida, y que la IA recibió el contexto (días desde el último
mensaje, memoria del cliente, cuánto falta para su cita). Viajes:
cliente nuevo completo, duda y regreso tras días, dos citas en una
charla, cambiar de idea a mitad, cancelar y volver, urgencia en
medio de la charla, enojado en el embudo, 5 preguntas antes de
agendar, pedir persona en el embudo, tope y mover, confirma
asistencia, spam y basura en medio, "lo voy a pensar", adelanto por
urgencia, pregunta con propuesta viva, cita inminente, despedida y
regreso, cambiar con dos citas (retomar), dos urgencias seguidas,
cita para otra persona, confirma→cancela→sin cita, memoria al final
del viaje, "no" pelón, dos preguntas con propuesta viva.

**Bug real encontrado y corregido:**
1. **KeyError en propuesta de dos citas**: el texto de la propuesta
   leía `cita2['fecha_bonita']` con acceso directo; una cita2 sin
   ese campo (p. ej. restaurada de una hoja vieja) tumbaba el
   mensaje entero. Ahora usa `.get()` con respaldo a la fecha ISO.
   (La corrida también obligó a corregir 3 errores del propio
   arnés: la cancelación por texto necesita la cita en Clientes
   como en producción, la memoria se guarda cuando la IA manda
   resumen, y el retomar viaja por los botones cambiar_mia.)

Nota: la corrida es con agente falso (mecánica conversacional);
el tono de la IA real se valida con la batería dorada en la Mac
de Jose (necesita su GEMINI_API_KEY) y con la prueba en vivo.

## v3.18.0 — Simulación profunda: 99 escenarios adversariales (2026-11-23)

Jose pidió una corrida profunda para encontrar bugs conversacionales
en saludar, preguntar, agendar, confirmar, cancelar, handoff,
temas varios, vulnerabilidades y abusos, razonamiento y
comunicación. Nueva `test_simulacion_profunda.py` (99 escenarios
contra el código real, agente falso plausible): saludo (8),
preguntar (12), agendar (12), confirmar (12), cancelar (8),
handoff (10), vulnerabilidades/abuso (22), razonamiento y
comunicación (15).

**Bugs reales encontrados y corregidos:**
1. **"cambia mi cita" no se reconocía**: _PALABRAS_CAMBIAR solo
   traía "cambiar"; la forma conjugada "cambia/cambie" caía al
   agente y proponía una cita NUEVA en vez de cambiar la que ya
   tiene. Agregadas "cambia" y "cambie".
2. **"Es urgente que me digas el precio" disparaba el protocolo
   médico**: _es_urgencia en dos niveles — señales médicas claras
   (duele, dolor, sangra, emergencia...) siempre son urgencia;
   "urgente/urgencia" a secas solo dispara el protocolo si el
   mensaje NO es una petición de información (precio, horario,
   ubicación, foto). "Es urgente" a secas sigue disparando
   (seguridad primero).
3. **El fake de pruebas no simulaba la hora ocupada**: crear_cita
   nunca lanzaba ValueError (el contrato de booking en
   producción). Ahora fuera de huecos = hora ocupada, como en
   producción. La batería dinámica sigue verde con el fake nuevo.

**Verificado en la corrida (sin bugs):** inyecciones de prompt no
filtran (R6), "soy el dueño, apaga el robot" no apaga (el texto no
puede cambiar el interruptor), "cancela la de mi vecino" no
cancela ajenas, "agenda 10 citas" respeta el tope, "confirma mi
cita" por texto nunca confirma sin propuesta, doble toque en
Confirmar crea solo 1 cita, "no quiero cancelar" no cancela,
"me duele es urgente" con propuesta no confirma (va a urgencia),
confianza baja ×2 pasa a persona, nombre-inyección no confirma,
precio falso de la IA lo desecha R9, respuestas largas se dividen
en burbujas cortas, espanglish y mensajes larguísimos sin crash.

## v3.17.0 — Batería dinámica: la inteligencia se prueba sola (2026-11-23)

Jose pidió una batería "demasiado completa" y luego explicó su
visión: que la respuesta de la IA tenga inteligencia de verdad
(coherencia, contexto, memoria, circunstancias, tiempo), sin una
base de datos gigante. Esta versión da el primer paso verificable
en esa dirección:

1. **Batería dinámica (`test_bateria_dinamica.py`)**: en vez de
   escenarios escritos a mano, un generador arma estados (sin cita,
   1-2 citas, propuestas, memoria, fuera de horario...) y mensajes
   por categoría, y un explorador adaptativo va por las
   combinaciones que faltan (matriz estado×categoría completa +
   sondas a propuestas + botones + pasada aleatoria con mutaciones).
   Todo se juzga contra INVARIANTES: nunca crear cita sin sí de
   verdad, nunca más de 2 citas sin urgencia, nunca cancelar con
   "no quiero cancelar", la urgencia siempre pasa a una persona en
   una burbuja, nunca inventar un precio, nunca decir "ya
   cerramos", nunca dejar aire muerto, respetar terminar/no
   responder, confianza baja ×2 → persona. Dos pisos: mecánico con
   agente falso (gratis, miles de casos) y muestra de tono con IA
   real (`--real`, solo si hay GEMINI_API_KEY). Reproducible por
   semilla. En su primera corrida encontró 2 cosas reales: un
   toque viejo en "Adelantar cita" se quedaba en silencio, y "me va
   por favor" no confirmaba.
2. **R9 en el revisor — ningún precio inventado**: si la respuesta
   trae un monto ("$650" o "650 pesos") que no está en el
   Conocimiento, se desecha entera y se contesta con la frase
   segura del guion. La IA ya no puede inventar precios.
3. **Cortesía en el sí**: "me va por favor", "sí por favor" y
   "vale" ahora confirman. "gracias" sigue fuera (el incidente del
   12 de noviembre fue un "sí gracias").
4. **Toque viejo sin silencio**: "Adelantar cita"/"Mover cita" con
   propuesta ya cambiada responde "tu cita propuesta sigue en pie"
   en vez de callar.
- Pruebas: nueva `test_v3_17.py` (11 casos: R9 ×5, cortesía ×4,
  toque viejo, humo de la batería dinámica). Batería dinámica
  verificada en 4 semillas × 847 casos sin violaciones.

## v3.16.0 — Parche robusto: comunicación y fricciones (2026-11-22)

Jose probó la urgencia en vivo y encontró dos cosas: "me duele es
urgente" chocó con el muro del tope en vez de correr la urgencia, y
"???" recibió un "¡Gracias! ¿En qué te ayudo hoy?". La simulación
contra el código real (test_simulacion_escenarios.py, 37 escenarios)
encontró las causas y esta versión las corrige, más las fricciones
que la caza proactiva destapó:

- Falso sí corregido: `_es_afirmacion` ya no toma cualquier mensaje
  corto que empieza con "me"/"sí"/"de" como confirmación. Ahora
  TODAS las palabras deben ser de afirmación (lista blanca):
  "me duele es urgente", "me urge una cita" y "me puedes ayudar"
  ya no confirman nada. El caso de Jose ahora corre la urgencia.
- Negaciones: "no me duele nada" y "no es urgente" ya no disparan
  el flujo de urgencia; "no quiero cancelar" ya no cancela la cita
  de verdad y "no quiero cambiar" no cambia. Ante la duda, la
  urgencia gana (es un tema médico).
- La cita urgente nueva SÍ se confirma con 2 citas registradas:
  el tope ya no la bloquea al confirmar (la urgencia ya pasó el
  filtro al proponerse).
- El tope de citas ya no es un muro: si el cliente tiene una cita
  propia y hay una hora libre antes, le ofrece MOVERLA con botones
  ("Mover cita" / "Dejarla como está" / "Hablar con persona").
  Confirmar mueve la cita (Urgencia=NO, correo normal). Sin cita
  propia, el mensaje del tope de siempre.
- Tiempo completo para la IA: "hace N días desde su último
  mensaje" en cualquier etapa (antes solo en saludos) y "su cita
  es hoy a las HH:MM / en N días" según cuánto falta.
- Acción y confianza para la IA (campos nuevos accion, confianza,
  info_faltante): la IA elige responder/agendar/mover/pedir_info/
  terminar/pasar_persona/no_responder. "terminar" cierra cálido y
  marca la memoria; "no_responder" calla (spam); confianza baja
  dos veces seguidas pasa a una persona en vez de adivinar.
- Pruebas: test_v3_16.py (25 casos) + simulación adversarial
  permanente (37 escenarios) que se corre en cada cambio.
  test_escenarios_100 D38 actualizado al nuevo mover; test_v3_2
  (a2) al nuevo contexto de tiempo.

## v3.15.0 — Urgencia inteligente: adelantar o nueva cita (2026-11-22)

Jose pidió que la inteligencia entienda si adelanta la cita que el
cliente ya tiene o hace una nueva ("como que evolucione el pedo").
La decisión la toma el código ANTES de llamar a la IA, con datos
reales del espejo de Citas; la IA solo lo dice con naturalidad.

- **El plan de urgencia** (`_plan_urgencia`): si el cliente tiene
  una cita propia futura (Confirmada/Pendiente, paciente coincide
  por nombre en las Notas; las citas de otros pacientes, como la
  de su hermana, se saltan) y la primera hora libre es ANTES de
  esa cita → **adelanto**: se propone moverla. Si no tiene cita
  propia → **cita nueva** urgente (salta el tope, v3.14.1). Si su
  cita ya está en la primera hora disponible → **sin propuesta**:
  el handoff sale igual y la IA lo explica.
- **Botones de adelanto:** "Adelantar cita" / "Dejarla como está" /
  "Hablar con persona", con el mensaje "Vi que ya tienes una cita
  el {vieja}. Te la adelanto a {nueva} por la urgencia. ¿La
  adelantamos?". El "sí" por texto también adelanta.
- **Al adelantar:** se crea la cita nueva PRIMERO (si falla, la
  vieja queda intacta), se cancela la vieja del calendario, la
  fila del espejo se mueve (Fecha/Hora nuevas, Urgencia=SI, Notas
  "Adelantada por urgencia: {porqué}") y el dueño recibe el correo
  de urgencia con el movimiento. `actualizar_cita_espejo` acepta
  `nueva_fecha`/`nueva_hora_inicio`/`nueva_hora_fin` (columnas F/G/H).
- **Persistencia:** el adelanto viaja completo en extra_json (tipo,
  cita_id, fecha vieja/nueva, servicio, horas, notas) y se recupera
  al arrancar. Pruebas: test_v3_15.py (17 casos).

## v3.14.2 — Urgencia en una burbuja, tono sobrio (2026-11-22)

Jose reprobó el formato de la urgencia en vivo ("¿qué clase de
formatos son esos?"): la respuesta salía partida en 2 burbujas,
abría copiando el protocolo literal y la oferta decía "¡Con
gusto!" (demasiado alegre para una urgencia).

- **Una sola burbuja.** `enviar_con_ritmo` acepta `sin_dividir`:
  la respuesta de urgencia sale completa en un mensaje aunque pase
  de 300 caracteres (la regla de partir sigue para todo lo demás).
  El marco le pide a la IA máximo 2 frases.
- **El protocolo es guía, no copia.** El marco y el guion le piden
  a la IA decir el protocolo de urgencias con sus propias
  palabras, integrado a la respuesta, nunca copiado literal; y no
  decir "como te comenté" (decir las cosas directamente).
- **Oferta sobria.** El mensaje de la propuesta urgente cambió de
  "¡Con gusto! Te propongo tu cita para el..." a "Te dejo lista tu
  cita para el... ¿La confirmamos?".

## v3.14.1 — La urgencia siempre propone fecha (2026-11-22)

Jose probó la urgencia en vivo y no vio ninguna fecha propuesta:
su número de prueba ya tenía 2 citas activas (la del martes y la
de su hermana del miércoles) y el tope de 2 citas por número
bloqueó la oferta en silencio. Decisión de Jose: "necesito que la
función esté bien estipulada de calidad" — una urgencia siempre
recibe una propuesta de cita con fecha, si hay hueco.

- **La urgencia salta el tope de 2 citas.** `_propuesta_cita_urgente`
  ya no revisa el tope: propone la primera hora disponible con
  botones aunque el cliente ya tenga 2 citas. El tope sigue
  vigente para el flujo normal. La oferta solo se omite si la
  agenda está apagada, ya hay una propuesta pendiente (nunca se
  pisa) o no hay huecos libres. El dueño ve el correo de urgencia
  al confirmar y puede reagendar.
- **La IA lo dice con naturalidad:** el marco de urgencia le pasa
  el dato ("ya tiene 2 citas registradas") y el guion le pide
  decirlo con naturalidad: el sistema propone una cita adicional
  por la urgencia.

## v3.14.0 — Urgencia pensada: la IA compone la respuesta (2026-11-22)

Jose probó la urgencia en vivo y rechazó el texto fijo: "parecen
copy and paste, necesito que la IA piense la respuesta bien, no
responda por responder". La respuesta de urgencia ya no sale de
una plantilla: la compone la IA con el guion, el protocolo del
negocio y el contexto real (horario, citas registradas).

- **La IA compone, el código manda.** La detección sigue siendo
  por palabras (rápida y segura), pero la respuesta la escribe el
  agente con un marco de urgencia (empatía, handoff inmediato,
  fuera de horario con empatía, guía a atención inmediata si es
  grave, nunca diagnósticos, nunca preguntas innecesarias, no
  ofrecer la cita: el sistema la propone con botones). El código
  FUERZA el handoff y la oferta de cita sin depender de que la IA
  lo marque. Si la IA falla o viene vacía, texto fijo de respaldo
  (`mensaje_urgencia` / `mensaje_urgencia_fuera_horario` en
  Configuración): una urgencia nunca se queda sin respuesta.
- **El revisor también revisa la urgencia** (antes se saltaba por
  ser texto fijo; ahora es texto de la IA, misma segunda mirada).
- **Guion reforzado:** la regla de urgencia del playbook pide
  responder pensando (reconocer lo que siente, decir lo del
  horario cerrado con empatía, orientar a atención inmediata si
  es grave, mencionar con naturalidad las citas ya registradas) y
  se agregó un ejemplo de urgencia en "Cómo hablas".
- **Diagnóstico de la prueba en vivo:** los botones no salieron en
  la prueba de Jose porque su número de prueba ya tenía 2 citas
  activas (el tope es 2 por número, v3.10): el código omitió la
  oferta en silencio. Ahora el marco le pasa a la IA el dato
  ("ya tiene 2 citas registradas") para que lo diga con naturalidad
  en vez de quedarse callado.

## v3.13.0 — Cita urgente: urgencia con oferta de cita, marca en el CRM y correo con el porqué (2026-11-22)

Jose simuló una emergencia y pidió el paso completo: cuando el
cliente suena urgente, el robot no solo pasa a una persona —también
ofrece agendar y la cita sale marcada como urgente.

- **Urgencia con oferta de cita.** Al detectar urgencia, además del
  handoff (correo al dueño + caso en Clientes, como siempre), el
  robot guarda una propuesta con botones para la primera hora
  disponible (con profesional si hay agenda por profesional) y la
  manda justo después del mensaje de handoff. Si la agenda está
  apagada, ya hay una propuesta viva, hay tope de citas o no hay
  huecos, no se ofrece nada: el handoff sale igual. La propuesta
  viaja con la razón de la urgencia (también en `extra_json`, para
  sobrevivir a un reinicio de Render).
- **Fuera de horario con empatía.** Si el negocio está cerrado, el
  mensaje de urgencia agrega que puede que tarden en responder
  hasta que abran (texto personalizable con
  `mensaje_urgencia_fuera_horario` en Configuración). La guía
  médica y la promesa de persona inmediata se mantienen.
- **Marca en el CRM.** Nueva columna `Urgencia` (P, SI/NO) en la
  pestaña Citas: la cita confirmada desde una urgencia queda en SI
  y las Notas llevan "URGENTE: {porqué}". El evento del calendario
  también lleva la marca en su descripción. `actualizar_cita_espejo`
  acepta el parámetro `urgencia` para marcar una fila existente.
- **Correo de cita urgente.** Nueva alerta `alerta_cita_urgente`:
  asunto "🚨 Cita con urgencia" y el porqué en el cuerpo. Sale
  siempre en el momento, aunque `alertas_instantaneas` esté en NO
  (una urgencia no espera al correo semanal), y reemplaza al correo
  normal de cita confirmada para esa cita.
- **Sin cambios para citas normales:** Urgencia queda en NO, el
  correo y el espejo se comportan idénticos a v3.12.0.

## v3.12.0 — Sereno completo: agenda por profesional, recordatorios, urgencia con guía (2026-11-22)

Jose adoptó el producto "Sereno" (recepción de clínica por
WhatsApp) como la definición del robot y pidió el producto final
pulido, no una demo. Auditoría contra las 6 funciones y las 3
demandas de Sereno, y construcción de lo que faltaba:

- **Agenda por profesional (función 02).** Nueva pestaña
  Profesionales leída por `sheets.leer_profesionales()`: los
  huecos salen del horario de cada profesional activo (ej. lunes
  09:00 solo con la Dra. Ruiz, que entra antes que el Dr. Santos)
  y la propuesta, la confirmación, la nota del calendario y el
  espejo llevan el nombre real. Una sola llamada freebusy al
  calendario (conservador: un evento ocupado bloquea a todos,
  nunca se duplican citas). Sin profesionales activos con horario,
  la agenda sigue por clínica, idéntica a antes.
- **Recordatorios automáticos (función 03).** Nuevo
  `robot/recordatorios.py`: ~24 h antes de la cita manda la
  plantilla aprobada de WhatsApp (nombre + fecha/hora) y marca
  `Recordatorio_enviado` en el espejo. Interruptor
  `recordatorios` en Configuración (SI/NO; en paquete básico va
  apagado, sin agenda no hay recordatorios). Job programado cada
  hora. Sin plantilla aprobada en Meta, el envío falla y queda en
  Diagnóstico: nunca silencioso. El paciente confirma con
  "confirmo" / "ahí nos vemos" y queda registrado en las Notas
  del espejo. Cancelar libera el hueco (ya funcionaba). La
  recuperación de interesados sin cita sigue siendo solo borrador
  por correo en el reporte semanal: sin WhatsApp de marketing.
- **Urgencia con guía al paciente (demanda 3).** El mensaje de
  urgencia ahora orienta a buscar atención médica inmediata
  antes del handoff ("Si sientes que es una urgencia médica,
  busca atención inmediata..."). Nunca indicaciones ni
  diagnósticos. La clínica puede personalizar el texto con
  `mensaje_urgencia` en Configuración.
- **Handoff con contexto (función 05).** El correo de handoff
  incluye el resumen de la conversación (memoria del cliente):
  el dueño recibe el contexto junto con la alerta, sin buscar en
  la hoja.
- **Servicios sin evasión (función 01).** El guion ya no deflecta
  "¿qué servicios tienen?" con "¿cuál te interesa?": responde con
  los servicios principales y sus precios de Conocimiento
  (máximo 5) y la puerta abierta a agendar. Actualizados el
  golden G7 y test_v2_10.
- **Reporte semanal con confirmaciones (función 06).** El correo
  del lunes suma "Confirmaciones de asistencia" (texto y HTML),
  contadas desde las Notas del espejo.
- **Decisión comercial:** se vende un solo plan (Pro, $1,499/mes
  ≈ Sereno $1,490); los paquetes básico/pro/premium quedan como
  control interno de Jose (cada negocio recibe lo que autoriza
  con el interruptor). El código de paquetes no se borró.

Tests: nueva batería `test_v3_12.py` 48/48; suite completa verde
(29 archivos, 758 casos). `test_v2.py` (g) actualizado: ya no
prohíbe recordatorios, verifica que van por plantilla aprobada.

**Depuración (mismo día, antes de subir):** eliminada la función
muerta `_dia_correcto` de `revision.py` (sin referencias; R4 no la
usaba); `guion-robot.md` sincronizado con el guion real (servicios
directos, nombre/número después de confirmar, perfil desde la hoja);
`README.md` con sección Sereno completo y corrección de la regla
de recordatorios; `instalar.py` ya no trae listas fijas de archivos
(escanea el directorio, nunca se desactualiza) y su mensaje final
habla de los recordatorios por plantilla; borradas las hojas de
prueba de versiones viejas (PRUEBA-HUMO-V3.4.12 y
PRUEBA-V3.11-DOS-CITAS) y las carpetas `__pycache__`.

**Retomar tras cambiar hora (mejora, mismo día):** si el cliente
toca "Cambiar hora" en una propuesta de dos citas y elige cuál
cambia, la OTRA ya no se pierde: se guarda en memoria y viaja junto
con la nueva propuesta ("Confirmar ambas"), con etiquetas correctas
en ambos sentidos (la suya / la de la otra persona). Expira a las
48 h o si su fecha ya pasó; "Hablar con persona" la limpia; el
mensaje solo promete retomarla cuando sí se guardó. Solo en memoria
(un reinicio en medio deja pedirla de nuevo). Pruebas nuevas (k)
11/11; suite completa verde (29 archivos, 758 casos).

**Lo que falta de Jose para encender los recordatorios en vivo:**
aprobar la plantilla `recordatorio_cita` en Meta (WhatsApp
Manager → Plantillas → crear: utilidad, cuerpo con dos variables
{{1}} nombre y {{2}} fecha/hora, idioma es_MX). Mientras tanto,
Meta rechaza los envíos y no cuestan nada; para apagarlos, poner
`recordatorios = NO` en Configuración.

## v3.11.1 — Simulación de 100 escenarios: dos huecos reales tapados (2026-11-22)

Jose pidió simular 100 escenarios conversacionales contra el código
real (sin su celular) y pulir lo que fallara. Nueva batería
`test_escenarios_100.py` (149 casos en 10 categorías + extras de los
casos que Jose vivió en vivo). La primera corrida dejó 144/149; los
dos huecos reales:

- **El agente dice "sí agendo" pero sin fecha (o con fecha ilegible)
  y el cliente se quedaba sin propuesta.** La red de seguridad solo
  entraba si el agente NO marcaba quiere_agendar. Ahora también
  entra cuando marca "sí" pero la fecha viene vacía o ilegible y el
  mensaje pide agendar en claro: la propuesta sale con el día
  pedido (o la próxima apertura) en vez de nada.
- **"Cancelar" una cita ya pasada borraba el evento.** El camino de
  cambio/cancelación cancelaba cualquier cita con estatus agendado,
  aunque fuera vieja. Ahora solo cancela citas a futuro (o de hoy);
  una cita pasada se trata como si no hubiera nada que cambiar.

Confirmado en la simulación: el caso de las 11:40 (propuesta viva +
pregunta de disponibilidad con días) ya propone las dos citas
(martes + miércoles) sin cancelar nada; los botones fallidos quedan
en Diagnóstico; el tope de 2 citas por número, la cita de terceros
con su nombre, la memoria sin citas viejas y los paquetes básicos
sin agenda/fotos pasan.

- **El espejo de citas caía corrido a la derecha.** Al confirmar
  las dos citas de la prueba en vivo, las filas del espejo (Citas)
  se escribieron a partir de la columna Q en vez de A: el append
  de Sheets, con rango A:Z, tomó el panel resumen (Q:R) como otra
  tabla. `agregar_fila` ahora ancla el rango al ancho real de la
  fila (Citas 15 → A:O, Diagnóstico 6 → A:F, Clientes 8 → A:H...).
  Las dos filas ya escritas se movieron a su sitio en la hoja.
  Tests: `test_v3_11.py` 41/41; suite completa verde (699 casos).

## v3.11.0 — Reservas robustas: el día que pides, memoria sin citas viejas, botones sin fricción (2026-11-22)

Jose probó en vivo (03:35 MST) y reportó que la propuesta salió para
el lunes 23 cuando pidió el martes para él y el miércoles para su
hermana, sin botones visibles, y que el robot le ofreció cambiar
"tus horas" por una cita del 19 de noviembre que ya había pasado.
Diagnóstico con evidencia (Conversaciones + Propuestas + código):

- **El día pedido manda.** La red de seguridad proponía el primer
  hueco libre (la próxima apertura) ignorando el día mencionado.
  Ahora `_dias_pedidos` detecta los días de la semana del mensaje
  ("el martes", "el miércoles") y la propuesta usa el primer hueco
  de ESE día; si no hay hueco ese día, la próxima apertura en esa
  fecha o después. Con dos días + otra persona ("para mi hermana"),
  la red arma las dos citas en determinista (la segunda con la
  relación), sin depender de que el modelo las extraiga.
- **Propuesta limpia.** Cuando la red de seguridad dispara, el
  texto del agente (que lista horas en texto, contra el guion) se
  reemplaza por una propuesta corta con una sola pregunta + botones.
  El cliente toca, no teclea.
- **Memoria sin citas viejas.** `estado_cliente` acepta `ahora`:
  una cita pasada ya no cuenta como vigente (etapa deja de ser
  "agendado") y el contexto le dice al agente "su última cita ya
  pasó: no la trates como vigente ni le ofrezcas cambiarla".
- **Botones visibles o registrados.** Si `enviar_botones` falla, el
  error real de Meta se registra en Diagnóstico (componente
  whatsapp, FALLO) antes de caer a texto plano. Antes caía en
  silencio y "no aparece el botón" era indiagnosticable.
- **Botones para reducir fricción en todos los casos (regla de
  Jose):** "cambiar hora" con dos citas ahora pregunta con botones
  (La mía / La de X / Hablar con persona) y esos botones se
  atienden; el guion enseña a proponer para los días concretos que
  el cliente menciona.
- Huecos: `proximos_huecos_libres` acepta cantidad/dias opcionales
  (rango amplio cuando hay días concretos); los fakes viejos de las
  pruebas caen al llamado de siempre. Tests: `test_v3_11.py`
  37/37; suite completa verde (27 archivos, 545 pruebas).

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
