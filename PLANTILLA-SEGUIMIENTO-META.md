# Plantilla de seguimiento en Meta — aprobar `seguimiento_no_agendo` (una página)

Por qué importa: la v3.20.7 ya trae el mecanismo de seguimiento
proactivo (escribirle a los clientes que preguntaron y no agendaron,
a los 3 días), pero WhatsApp solo deja mandar mensajes proactivos
con plantillas aprobadas por Meta. Sin esta aprobación, el robot
intenta mandar el seguimiento, Meta lo rechaza, queda registrado
y no cuesta nada — pero el cliente no recibe nada. Con la plantilla
aprobada y el interruptor encendido, los seguimientos salen solos.

**Viene APAGADO por defecto.** Para encenderlo hay que cumplir tres
cosas: (1) esta plantilla aprobada en Meta, (2) el interruptor
`seguimiento_proactivo = SI` en la pestaña Configuración, y
(3) el cliente con `Consentimiento_mensajes = SI` en Clientes.

Esto se hace una sola vez, en tu navegador (no en el del robot).

## Qué vas a crear (copia y pega tal cual)

- **Nombre de la plantilla:**
```
seguimiento_no_agendo
```

- **Categoría:** Utility (utilidad)

- **Idioma:** Spanish (Mexico) — código `es_MX`

- **Cuerpo del mensaje (copia y pega exactamente esto):**
```
Hola {{1}}, hace unos días preguntaste por {{2}} y queríamos saber si te podemos ayudar a agendar tu cita. Responde a este mensaje y te atendemos enseguida.
```

- **Valores de ejemplo** (Meta los pide para aprobar; pon estos):
  - `{{1}}` → `Jose`
  - `{{2}}` → `la limpieza dental`

No agregues botones ni encabezado: el código del robot manda solo el
cuerpo con dos valores, en este orden: `{{1}}` = nombre del cliente,
`{{2}}` = motivo o servicio que le interesó. Si la plantilla trae
otra cosa, Meta la rechaza al enviar.

## Pasos en WhatsApp Manager

1. Entra a `business.facebook.com` → **WhatsApp Manager** → tu cuenta de
   WhatsApp → pestaña **Message templates** (Plantillas de mensajes).
2. Botón **Create template** (Crear plantilla).
3. Nombre: pega `seguimiento_no_agendo`. Categoría: **Utility**. Idioma:
   **Spanish (Mexico)**.
4. En el cuerpo, pega el texto de arriba tal cual.
5. En los valores de ejemplo, pon `Jose` y `la limpieza dental`.
6. **Submit** (Enviar para revisión). Meta suele aprobar en minutos u
   horas; si queda en revisión, no hay que hacer nada más.

## Cómo saber que quedó

- En la lista de plantillas debe decir **Approved** (Aprobada) con el
  idioma `es_MX`.
- Para probarlo: en la hoja oficial, pestaña **Configuración**, pon
  `seguimiento_proactivo = SI`, y en **Clientes** pon
  `Consentimiento_mensajes = SI` a un cliente de prueba que preguntó
  hace más de 3 días y no agendó. A la siguiente hora el robot le
  manda el seguimiento y queda registrado en **Conversaciones** con
  motivo `seguimiento`.

## Si no quieres seguimientos por ahora

No hagas nada: el interruptor viene en NO por defecto y el robot no
manda ningún seguimiento. El borrador semanal por correo sigue igual.
