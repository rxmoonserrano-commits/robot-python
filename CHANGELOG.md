# CHANGELOG — La historia del robot, en orden

La historia de cada versión, para no cargarla en el código ni en el
README. El README describe lo que el robot hace HOY; aquí queda lo
que hacía antes y por qué cambió. Si algo se rompió en vivo, aquí
queda la fecha y la causa.

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
