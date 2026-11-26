# Aloara v3.21.0 — Ponerla en vivo (10 min, una sola pasada)

_Fecha: 2026-11-26. La v3.21.0 "Identidad Aloara" ya está construida y probada (suite 56/56 verde, incluyendo 11 pruebas nuevas de identidad Aloara). En vivo sigue la v3.20.15 hasta que apruebes la subida. Esta hoja es solo lo que falta para que Aloara salga al aire y sus correos empiecen a llegar._

## Paso 1 — Aprobar la subida (1 min)

Toca la tarjeta de aprobación del push de la v3.21.0. Si ya caducó, dime "sube la v3.21.0" y la relanzo. Render despliega solo.

## Paso 2 — Verificar que quedó en vivo (2 min)

1. Abre `/estado` del robot: debe decir `version: "3.21.0"` y salud ok.
2. Hoja "Robot WhatsApp — Documento oficial" → pestaña **Diagnóstico**: busca el renglón `gmail`. Hoy dice AVISO ("Gmail sin configurar"); el paso 3 lo pone en OK.

## Paso 3 — Gmail: que los correos Aloara salgan (5 min, solo tú)

Sin esto, **ningún** correo Aloara sale nunca (handoff, urgencia, oportunidad, cita, reporte semanal y mensual), aunque el robot conteste igual. `OWNER_EMAIL` ya está OK (`jserranosopena@gmail.com`); solo faltan estas dos variables en Render:

1. Tu cuenta Google → **Seguridad** → **Verificación en 2 pasos** → **Contraseñas de aplicaciones** → nombre `Aloara Render` → **Crear**. Copia las 16 letras **sin espacios**: esa es tu `GMAIL_APP_PASSWORD`. Es un secreto: no lo compartas.
2. Render → servicio `robot-whatsapp-python` → **Environment** → agrega:

```
GMAIL_USER=jserranosopena@gmail.com
GMAIL_APP_PASSWORD=<las 16 letras sin espacios>
```

Guarda → **Manual Deploy > Deploy latest commit**. Luego el renglón `gmail` en Diagnóstico debe decir **OK**.

## Paso 4 — Prueba real de la identidad Aloara (2 min)

Desde tu WhatsApp personal manda al robot **+52 669 100 1402**:

> Hola, ¿cuánto cuesta la limpieza?

Debe responder como asistente virtual del negocio (no como persona), con el precio desde Conocimiento. Si quieres probar el botón de handoff, escribe después: "Quiero hablar con una persona" — debe llegarte el correo **"Una conversación necesita tu atención · …"** con botón **"Continuar conversación"** (abre el chat en wa.me). La cita confirmada llega como **"Tienes una nueva cita · …"**; la urgencia como **"Atención prioritaria requerida · …"** con botón **"Atender ahora"**; el lead caliente como **"Una nueva oportunidad llegó a tu negocio · …"** con botón **"Ver oportunidad"**.

## Lo que sale solo después (no hay que hacer nada)

- **Aloara Weekly**: cada lunes 08:00, asunto "Tu semana en [negocio] — citas, humanos y resumen", con interpretación, no solo números.
- **Resumen de la mañana**: todos los días 08:00, asunto "Tu día, en perspectiva — [fecha]", abre con "Tu día comienza en orden."
- **Reporte mensual nuevo**: día 1 a las 08:00, "Un mes de nuevas posibilidades" (cubre el mes anterior).
- La firma "— Aloara" en el agente solo sale si el negocio la autoriza (`firma_aloara = SI` en Configuración); por defecto el agente se presenta como "asistente virtual de [negocio]".

## Pendientes que esto NO arregla

- Plantilla `recordatorio_cita` en Meta (recordatorios ~24 h antes): sigue esperando aprobación.
- `ADMIN_TOKEN` y `META_APP_SECRET`: siguen en AVISO; son otros pasos aparte.
- Corrida dorada de 34 conversaciones en tu Mac: queda para otra ventana.

Verificado contra el código (2026-11-26): `VERSION = "3.21.0"` en app.py; asuntos y botones exactos de robot/mail.py; reportes en robot/report.py (semanal lunes 08:00, mensual día 1 08:00, resumen diario 08:00); pruebas nuevas en test_aloara.py (11 casos, suite 56/56 verde). El estado en vivo de Render tras la aprobación queda por verificar en el Paso 2.
