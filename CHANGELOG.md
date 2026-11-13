# CHANGELOG — La historia del robot, en orden

La historia de cada versión, para no cargarla en el código ni en el
README. El README describe lo que el robot hace HOY; aquí queda lo
que hacía antes y por qué cambió. Si algo se rompió en vivo, aquí
queda la fecha y la causa.

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
