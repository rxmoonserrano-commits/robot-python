# Plantilla de recordatorio en Meta — aprobar `recordatorio_cita` (una página)

Por qué importa: la v3.12.0 ya trae recordatorios automáticos (~24 h antes
de cada cita confirmada), pero WhatsApp solo deja mandar plantillas
aprobadas por Meta. Sin esta aprobación, el robot intenta mandar el
recordatorio, Meta lo rechaza, queda registrado en Diagnóstico y no cuesta
nada — pero el paciente no recibe nada. Con la plantilla aprobada, los
recordatorios salen solos.

Esto se hace una sola vez, en tu navegador (no en el del robot).

## Qué vas a crear (copia y pega tal cual)

- **Nombre de la plantilla:**
```
recordatorio_cita
```

- **Categoría:** Utility (utilidad)

- **Idioma:** Spanish (Mexico) — código `es_MX`

- **Cuerpo del mensaje (copia y pega exactamente esto):**
```
Hola {{1}}, te recordamos tu cita del {{2}}. Responde CONFIRMO para confirmar tu asistencia, o CANCELAR si necesitas cambiarla.
```

- **Valores de ejemplo** (Meta los pide para aprobar; pon estos):
  - `{{1}}` → `Jose`
  - `{{2}}` → `martes 24 de noviembre a las 10:00`

No agregues botones ni encabezado: el código del robot manda solo el
cuerpo con dos valores, en este orden: `{{1}}` = nombre del paciente,
`{{2}}` = fecha y hora bonita de la cita. Si la plantilla trae otra cosa,
Meta la rechaza al enviar.

## Pasos en WhatsApp Manager

1. Entra a `business.facebook.com` → **WhatsApp Manager** → tu cuenta de
   WhatsApp → pestaña **Message templates** (Plantillas de mensajes).
2. Botón **Create template** (Crear plantilla).
3. Nombre: pega `recordatorio_cita`. Categoría: **Utility**. Idioma:
   **Spanish (Mexico)**.
4. En el cuerpo, pega el texto de arriba tal cual.
5. En los valores de ejemplo, pon `Jose` y `martes 24 de noviembre a las 10:00`.
6. **Submit** (Enviar para revisión). Meta suele aprobar en minutos u
   horas; si queda en revisión, no hay que hacer nada más.

## Cómo saber que quedó

- En la lista de plantillas debe decir **Approved** (Aprobada) con el
  idioma `es_MX`.
- Cuando el robot ya esté en v3.12.0 en vivo, agenda una cita de prueba a
  ~24 h y revisa en la hoja, pestaña **Diagnóstico**: si algo falla, el
  renglón dice exactamente qué pasó. Si sale bien, en el espejo de Citas
  la columna `Recordatorio_enviado` queda con la fecha.

## Si no quieres recordatorios por ahora

En la hoja oficial, pestaña **Configuración**, pon `recordatorios = NO`.
El robot no intenta mandar nada. Cuando apruebes la plantilla, lo regresas
a `SI`.

---

Hecho para Jose, 22 de noviembre de 2026. Verificado contra el código:
`robot/recordatorios.py` manda la plantilla `recordatorio_cita` en idioma
`es_MX` con exactamente dos parámetros de cuerpo (nombre y fecha/hora).
