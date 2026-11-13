# Pruebas de calidad: seguridad, servicio y conversación natural

Este documento es el plan que pediste: cómo probar que el robot es
seguro, que da buen servicio y que se siente como hablar con un
humano. No es teoría: cada prueba dice **qué hacer, qué esperar y
qué es pasar**. Las de código (sin internet) ya corren solas con
`python test_simulado.py`, `test_v2.py`, `test_v2_2.py` y
`test_v2_3.py`. Las de esta hoja se hacen **en vivo**, con tu teléfono,
contra el robot en Render, y se revisan en la hoja y en los logs
de Render (buscar `[lote]`).

Regla de oro: una prueba que no se puede repetir no es una prueba.
Si algo falla, anota la hora, el mensaje que mandaste, lo que
contestó el robot y la línea `[lote]` de Render. Sin eso, no se
puede arreglar.

---

## 1. Seguridad — que nunca se rompa nada ni se filtre nada

| # | Prueba | Cómo se hace | Pasa si... |
|---|--------|--------------|-----------|
| S1 | Sin secretos a la vista | Busca en el código y en la hoja: claves, tokens, contraseñas | No hay ninguna. Las claves solo viven en `.env` y en Render |
| S2 | No inventa precios | Pregunta por un servicio que NO está en Conocimiento | Dice que no lo sabe o pregunta, nunca inventa un precio |
| S3 | Solo fotos oficiales | Pide una foto de algo que no está en Fotos oficiales | No manda ninguna foto, o manda solo una de la lista blanca |
| S4 | Apagado global | Pon Control en NO y manda "Hola" | Silencio total. En Conversaciones: robot_respondio = no |
| S5 | Apagado por cliente | Pon robot_activo = NO en tu fila de Clientes y manda "Hola" | Silencio total, solo para ti. Otro cliente sí recibe respuesta |
| S6 | No agenda horas imposibles | Pide cita un domingo (si el negocio no abre) o a las 3 de la mañana | No crea la cita; ofrece el próximo día que abre |
| S7 | No agenda lo ocupado | Pide la misma hora dos veces (dos teléfonos) | La segunda recibe "esa hora ya se ocupó" y otra opción |
| S8 | El robot no se queda callado por un error | Apaga el WiFi no; simula: manda un mensaje raro, un audio vacío, un emoji solo | Siempre responde algo, o avisa "dame un momento". Nunca silencio sin registro |
| S9 | Datos que no debe guardar | Manda tu CURP, una tarjeta o una contraseña de prueba | No aparece en la hoja (el registro guarda el mensaje, pero el robot no lo repite ni lo usa) — y se borra a mano si se guardó |
| S10 | El humano manda | Escribe como humano (o usa /pausa) y luego manda un mensaje como cliente | El robot se calla ~2 horas y luego retoma con contexto |

**Cómo revisar S4/S5/S10:** en Conversaciones, la fila del mensaje
debe decir `robot_respondio = no` y el motivo correcto
("boton apagado", "robot apagado para este cliente",
"humano activo hace menos de 2 horas").

---

## 2. Calidad de servicio — que nunca pierda a un cliente

| # | Prueba | Cómo se hace | Pasa si... |
|---|--------|--------------|-----------|
| Q1 | Primera respuesta rápida | Manda "Hola" en horario | Responde en menos de ~30 s (Render dormido puede tardar hasta 50 s la primera vez) |
| Q2 | Nunca dos respuestas | Manda un mensaje y espera | Llega UNA respuesta (o una con botones), no dos |
| Q3 | Tres mensajes seguidos | Manda "Hola", "quiero una cita", "para el viernes" con 2 s entre cada uno | UNA sola respuesta que toma en cuenta los tres, no tres respuestas |
| Q4 | Audio | Manda un audio de 5 s: "Hola, quiero una cita el viernes" | Entiende el audio y responde como si fuera texto |
| Q5 | Fuera de horario | Manda "Hola" de noche | Propone la próxima apertura y guarda el lead; un "sí" crea la cita |
| Q6 | Cambiar hora | Agenda y luego escribe "mejor el sábado" | No confirma la hora vieja; pregunta o reacomoda |
| Q7 | Cancelar | Escribe "quiero cancelar mi cita" | No la borra a ciegas: confirma contigo o pasa al humano |
| Q8 | Cliente molesto | Escribe "esto es un pésimo servicio, quiero hablar con alguien" | Pasa al humano (correo al dueño) y le dice al cliente que lo atienden |
| Q9 | No duplicar clientes | Escribe 5 veces en la semana | En Clientes hay UNA fila tuya, con el último estatus y la última actividad al día |
| Q10 | La cita sí existe | Agenda una cita | Aparece en Google Calendar, con inicio y fin distintos, 60 min |
| Q11 | La cita confirmada se ve en la hoja | Revisa Clientes y Panel | Tu fila dice agendado, con fecha; el Panel cuenta 1 cita esta semana |

---

## 3. Conversación natural — que se sienta humano

Esto no se mide con un cronómetro, se mide con la sensación.
Haz cada guion completo, de principio a fin, y pregúntate al final:
¿esto lo habría escrito una persona del negocio?

**Guion A — El que solo pregunta el precio**
> Hola → ¿Cuánto cuesta [servicio]? → ¿Y cuánto dura? → Gracias

Pasa si: contesta corto, en el tono del negocio, no suelta un
párrafo de folleto, no repite el precio dos veces.

**Guion B — El indeciso**
> Hola → quiero una cita → no sé cuándo → ¿qué días tienes? → el viernes está bien → sí

Pasa si: no lo presiona, le da opciones, la cita se crea solo
cuando dice "sí" (o toca Confirmar), y la confirmación trae
día, hora y duración.

**Guion C — El que escribe de a poquito**
> Hola [enter] → oye [enter] → una pregunta [enter] → ¿cuánto cuesta?

Pasa si: espera, junta los mensajes y contesta UNA vez, con todo.

**Guion D — El que cambia de opinión**
> Quiero cita el viernes a las 10 → mejor el sábado → sí, el sábado

Pasa si: no agenda el viernes, agenda el sábado. El "sí, mejor
el sábado" NO confirma el viernes.

**Guion E — El que habla como en la calle**
> ola kiero una cita, cuanto sale? 😅

Pasa si: entiende, contesta normal, sin corregirle la ortografía,
sin sonar a robot ni a profesor.

**Guion F — El que se enoja**
> Llevo esperando y nadie me contesta, qué mal servicio

Pasa si: no discute, no se disculpa 5 veces, pasa al humano y le
dice que lo atienden en un momento.

### Señales de que NO se siente humano (corregir si aparecen)

- Contesta con párrafos larguísimos cuando la pregunta era corta.
- Repite "¡Claro que sí!" o "¡Perfecto!" en cada mensaje.
- Dice "como modelo de lenguaje" o "soy una IA".
- Pregunta lo mismo dos veces.
- Responde mensaje por mensaje en vez de esperar a que termines.
- Usa palabras que el negocio no usaría (demasiado formal, o demasiado
  slang que no es de Mazatlán).

---

## 4. Pruebas 24/7 — de noche, con los dueños dormidos

Estas se hacen de noche (después de las 18:00, o en domingo), con el
teléfono de Jose. Si el robot pasa estas, atiende 24/7 de verdad.

| # | Prueba | Cómo se hace | Pasa si... |
|---|--------|--------------|-----------|
| N1 | Pregunta a las 3 am | A las 3 am (o de noche), pregunta "¿cuánto cuesta la limpieza?" | Contesta el precio real de la hoja, no la frase grabada |
| N2 | Cita a las 3 am | De noche: "quiero una cita el martes a las 11" → toca Confirmar | La cita se crea para el martes 11:00, con confirmación bonita |
| N3 | Cambiar de noche | Con cita creada, de noche: "quiero cambiar mi cita" | Cancela la vieja y pregunta por el nuevo día (no repite la frase grabada) |
| N4 | Foto de noche | Manda una foto de tu muela a las 11 pm | Recibe "Gracias, lo recibí. ¿Me cuentas con tus palabras qué necesitas?" |
| N5 | Audio de noche | Manda un audio de noche | Lo entiende y contesta como si fuera texto |
| N6 | Reinicio de noche | En Render, haz Manual Deploy de noche con una propuesta pendiente, luego toca Confirmar | La cita se crea igual: la propuesta se recuperó de la hoja (pestaña Propuestas) |
| N7 | Primer mensaje tras dormir | No le escribas al robot en 20 min; luego manda "Hola" | Contesta (puede tardar hasta ~50 s la primera vez: Render gratis se duerme) |
| N8 | Lead nocturno | Un teléfono nuevo escribe de noche solo "Hola, ¿cuánto cuesta?" | En Clientes aparece ese teléfono, aunque no haya dado su nombre |

**Si N7 tarda mucho siempre:** Render gratis se duerme a los 15 min.
La solución es un ping gratis cada 10 min a /health (UptimeRobot) para
que nunca duerma, o el plan pago de Render cuando haya ingresos.

## 5. Qué hacer después de cada ronda de pruebas

1. Abre el Panel: ¿los números de esta semana se ven bien?
2. Abre Conversaciones: ¿cada mensaje tiene su respuesta y su motivo?
3. Abre Clientes: ¿una fila por teléfono, estatus correcto?
4. Si algo falló, anota hora + mensaje + respuesta + línea `[lote]`.
5. No arregles la hoja a mano para "que se vea bien": el arreglo va
   en el código, para que no vuelva a pasar.

**Versión de este plan:** 2026-11-12, con el robot v2.3.


## Puerta de calidad: conversaciones doradas (v2.13)

Las pruebas de arriba revisan piezas (que el prompt diga la regla,
que el flujo no se rompa). No revisan que la IA se comporte bien
hablando con un cliente de verdad. Para eso están las conversaciones
doradas: `test_conversaciones_doradas.py`.

Son 8 conversaciones completas contra la IA real (Gemini, con la
clave de verdad): saludo de noche, precio tras saludar, "lo voy a
pensar", oferta pendiente + pregunta nueva, cliente enojado, "sí
gracias" tras un fallo, piden servicios, cambio de cita de noche.
Cada una se juzga por lo que contesta el robot, no por lo que dice
el prompt.

Se corre así (desde la carpeta del robot, con la clave en el entorno):

    GEMINI_API_KEY=tu_clave python test_conversaciones_doradas.py

Regla: si una conversación dorada falla, esa versión NO se sube a
Render. Y cada error nuevo que aparezca en vivo se agrega como una
conversación dorada nueva, para que no vuelva a pasar.
