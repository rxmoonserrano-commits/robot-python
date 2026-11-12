# PROBARLO — Plan de pruebas en 10 puntos (para principiantes)

Hazlas en orden. Si una falla, no sigas: arregla esa y vuelve a probar.
Cuando las 10 pasen, ahí sí puedes decir que funciona. Antes no.

Primero, lo rápido y sin internet:

```bash
python test_simulado.py   # 23 casos de la v1
python test_v2.py         # 21 casos nuevos de la v2
```

Deben salir 44 casos en PASS entre los dos. Si alguno sale FAIL, el
problema está en la lógica, no en tus claves: no sigas hasta que salga
todo en verde.

## Las pruebas nuevas de la versión 2 (ya con claves reales)

| # | Prueba | Cómo hacerla | Qué debe pasar |
|---|---|---|---|
| 11 | Visto y "escribiendo..." | Manda un mensaje al número de prueba | Ves las palomitas azules y "escribiendo..." antes de que llegue la respuesta |
| 12 | Esperar y juntar | Manda 3 mensajes seguidos, rápido | El robot espera ~7 segundos y contesta UNA sola vez, con todo junto |
| 13 | Ritmo humano | Pide que te cuente todo (respuesta larga) | Llegan 2 mensajes cortos, con una pausita, no un muro de texto |
| 14 | Botones de la cita | Pide una cita con nombre, motivo y fecha | Llegan los botones Confirmar / Cambiar hora / Hablar con una persona (la cita NO se crea todavía) |
| 15 | Confirmar | Toca Confirmar | Llega la confirmación con día, hora y duración, y la cita aparece en Calendar |
| 16 | Cambiar hora | Pide una cita y toca Cambiar hora | No se crea cita y el robot pregunta por otro día y hora |
| 17 | Botón de persona | Toca Hablar con una persona | Llega el correo de alerta al dueño y el robot deja de contestar |
| 18 | Fuera de horario | Escribe cuando el negocio está cerrado (según Conocimiento) | Te dice a qué hora abre y te ofrece el próximo día, sin agendar nada imposible |
| 19 | Mensaje duplicado | (Difícil a mano: es automático) | Si Meta reenvía un mensaje, el robot no contesta dos veces |
| 20 | Gemini falla | (Se prueba con `test_v2.py`, caso f) | El cliente recibe un "dame un momento" y el dueño un correo, nunca silencio |

Y recuerda: **no hay recordatorios por WhatsApp que probar**, por
decisión de Jose. El robot no manda nada un día antes ni una hora
antes. Lo único programado es el reporte por correo del lunes.

## Las 10 pruebas (ya con claves reales)

| # | Prueba | Cómo hacerla | Qué debe pasar |
|---|---|---|---|
| 1 | El robot está vivo | `uvicorn app:app --port 8000` y abre `http://localhost:8000/health` | Ves `{"ok": true, ...}` |
| 2 | Llega un texto | Manda un WhatsApp al número de prueba | El robot responde en texto, con calma, una pregunta a la vez |
| 3 | Llega un audio | Manda un audio diciendo "quiero una cita" | El robot entiende lo que dijiste y responde en texto (nunca en audio) |
| 4 | Botón apagado | Pon `bot_activo = NO` en Control y manda un mensaje | El robot NO responde, pero el mensaje queda en Conversaciones |
| 5 | Pregunta imposible | Pregunta un precio que NO está en Conocimiento | El robot dice que no lo sabe y ofrece pasar a una persona |
| 6 | Agendar | Pide agendar con nombre, motivo y fecha | Se crea la cita en Google Calendar y dura 60 minutos (no 0) |
| 7 | Handoff | Pide "quiero hablar con una persona" | Llega el correo de alerta al dueño y el robot deja de contestar |
| 8 | Pausa humana | Tú le escribes al cliente por WhatsApp y luego manda otro mensaje | El robot se calla 2 horas; después retoma con el historial |
| 9 | Foto | Pide una foto del negocio | Solo llega una foto de la lista blanca; si el agente propone otra, no se manda |
| 10 | Reporte semanal | `python reporte_semanal.py` o `POST /reporte-semanal` | Llega el correo con los contadores reales de los últimos 7 días y queda una fila en Reporte |

## Si algo falla, lee esto primero

| Síntoma | Lo más probable |
|---|---|
| `/health` no abre | El servidor no arrancó: lee el error de la terminal, casi siempre es un `pip install` que faltó |
| El robot no responde nada | Revisa Control: `bot_activo` debe ser `SI` |
| Error 401 o 403 de WhatsApp | El token expiró o el `WHATSAPP_PHONE_NUMBER_ID` está mal |
| Error de Gemini (429) | Se acabó la cuota gratis del minuto o del día: espera y vuelve a probar |
| "No encontré las credenciales de Google" | El archivo `credenciales-google.json` no está en la carpeta, o la hoja no está compartida con su correo |
| No llega el correo | Falta `GMAIL_APP_PASSWORD` o no es una contraseña de aplicación (no es tu clave de Google) |
| La cita no se crea | La hora ya estaba ocupada, o el calendario no está compartido con la cuenta de servicio |
| No sale "escribiendo..." | El robot solo lo muestra cuando va a contestar: revisa que `bot_activo` sea SI y que no haya pausa humana |
| El robot contesta mensaje por mensaje | La espera de 7 s es por teléfono: si escribes desde otro número, es otro buzón |
| Los botones no llegan | Los botones solo salen al proponer una cita; fuera de la ventana de 24 h Meta los rechaza |

## Qué NO probar todavía

- No pruebes con el número real de un negocio hasta que las 10 pasen con el número de prueba de Meta.
- No mandes mensajes fuera de la ventana de 24 horas de WhatsApp: Meta los rechaza sin plantilla aprobada.
