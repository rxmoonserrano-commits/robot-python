# Kit de venta — Sereno (robot de WhatsApp) para tu primer cliente

_Fecha: 2026-11-24. v3.20.1 "Corrida adversarial profunda" construida y probada en local (suite verde, zip fresco listo); **pendiente subirla a Render — en vivo sigue v3.19.0** (verificado en `/health` 2026-11-23 23:17 UTC). No digas "en vivo v3.20" a clientes hasta verificar el despliegue. El robot es genérico: NO se programa por cliente, se llena su hoja. Esto es el empacado para tu primera venta piloto._

## Qué vende Sereno (en una frase)

Tu WhatsApp contestado 24/7 como recepcionista: responde, califica, agenda citas con botones y, si hace falta una persona, avisa al dueño por correo y se calla.

## Lo que trae la v3.20.1 (ya probado: suite completa verde + 27 viajes conversacionales 27/27 + corrida adversarial 25/25)

- Agenda por profesional: huecos reales según el horario de cada profesional en la pestaña Profesionales.
- Recordatorios automáticos ~24 h antes de cada cita confirmada, con la plantilla aprobada de Meta (pendiente de aprobar: `recordatorio_cita`).
- Urgencia con guía: orienta a buscar atención inmediata antes de pasar a humano.
- Urgencia inteligente (v3.15): si el cliente ya tiene cita, le ofrece adelantarla a la primera hora libre en vez de crear otra; si no tiene, cita urgente nueva.
- El tope de 2 citas ya no es un muro (v3.16): si tiene cita y hay hora libre antes, le ofrece moverla con botones.
- Tiempo completo para la IA (v3.16): sabe cuántos días pasaron desde el último mensaje y cuánto falta para su cita, en cualquier etapa.
- Acción y confianza (v3.16): la IA elige responder/agendar/mover/pedir_info/terminar/pasar_persona/no_responder; con confianza baja dos veces seguidas pasa a una persona en vez de adivinar.
- R9 — ningún precio inventado (v3.17): si la respuesta trae un monto que no está en el Conocimiento, se desecha y se contesta con la frase segura. La IA ya no puede inventar precios.
- Calidad probada por simulación (v3.17–v3.19): batería dinámica (miles de combinaciones contra invariantes), simulación profunda de 99 escenarios adversariales y 24 viajes conversacionales completos (5–9 turnos) — 24/24 ok, con un bug real encontrado y corregido (KeyError en propuesta de dos citas).
- Handoff con contexto: el correo al dueño incluye el resumen de la conversación.
- Servicios y precios directos: responde con los 5 principales de la hoja, sin evadir.
- Reporte semanal con confirmaciones: cuenta quién confirmó asistencia.
- Seguridad: firma de Meta verificada, token de dueño, anti-abuso, interruptor general y por cliente. No inventa precios ni horarios: si no está en la hoja, pasa a humano.

## 1. La hoja del cliente (copia de la plantilla)

Copia la hoja **"Plantilla — Negocio"** (ID `1icPqQhHi9cA6tzpnK347PCEGVW0Om0LJ3COSt5ou78E`) y renómbrala con el nombre del negocio. El robot SOLO sabe lo que está en Conocimiento, SOLO manda fotos de Fotos oficiales, y registra todo en Conversaciones, Clientes y el espejo Citas.

| Pestaña | Qué va ahí (para el cliente) |
|---|---|
| **Panel** | Resumen vivo: citas, clientes y estado. No tocar. |
| **Guía** | Instrucciones para llenar la hoja. Léela con el cliente. |
| **Control** | `bot_activo=SI` (y `ultima_respuesta_humana` la llena el robot). |
| **Configuración** | Nombre del negocio, asistente, tono, horarios, paquetes, recordatorios (`recordatorios=SI`, `plantilla_recordatorio=recordatorio_cita`, `idioma_plantilla=es_MX`), correo del dueño. |
| **Conocimiento** | Servicios, precios, duración, profesionales autorizados, horarios, dirección, políticas y FAQs. Si algo no está aquí, el robot dice "déjame confirmarlo". |
| **Profesionales** | Nombre, horario y días de cada profesional (ej. "09:00-18:00", domingo cerrado). Sin profesionales activos, agenda a nivel clínica. |
| **Fotos oficiales** | Lista blanca: solo las URLs de fotos que el robot puede mandar. |
| **Conversaciones** | La llena el robot. No tocar. |
| **Clientes** | La llena el robot (un renglón por teléfono). `robot_activo=NO` apaga el robot para ese cliente. |
| **Citas** | Espejo de solo lectura de las citas (confirmadas, canceladas, pendientes) + panel de resumen. No tocar. |
| **Propuestas** | La llena el robot (propuestas de cita que sobreviven reinicios). No tocar. |
| **Diagnóstico** | La llena el robot (salud de cada pieza). Revisa que todo diga OK. |
| **Reporte** | La llena el robot (reporte semanal de los lunes 08:00 + resumen de la mañana). |

Después comparte la copia con el correo de la cuenta de servicio de Google (el del `credenciales-google.json`), con permiso de Editor. Sin eso, el robot no lee la hoja.

## 2. Lista de instalación por cliente (repetible, en orden)

**A. Datos del negocio (te los pasa el cliente):**
- [ ] Nombre del negocio, tipo con artículo (ej. "una clínica"), nombre de la recepcionista.
- [ ] Horarios, servicios con precios y duración, profesionales con horarios, dirección + enlace de mapa, formas de pago.
- [ ] Fotos oficiales (URLs públicas) para la lista blanca.
- [ ] Correo del dueño (a dónde llegan las alertas) y su calendario.

**B. Hoja:**
- [ ] Copiar la plantilla, llenar Conocimiento, Profesionales, Fotos oficiales y Configuración; borrar los datos ficticios de "Clínica Dental Sonrisa" (precios EJEMPLO).
- [ ] Compartir con la cuenta de servicio (Editor). Anotar el ID nuevo de la hoja.

**C. Render (un servicio por negocio):**
- [ ] Nuevo servicio desde el repo `rxmoonserrano-commits/robot-python`. Plan de pago ~$7/mes para que no duerma.
- [ ] Variables de entorno (nombres exactos): `GEMINI_API_KEY`, `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `VERIFY_TOKEN`, `GOOGLE_SHEETS_ID` (el ID nuevo), `GOOGLE_CREDENTIALS_JSON`, `CALENDAR_ID`, `OWNER_EMAIL`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `ADMIN_TOKEN`, `META_APP_SECRET`, `NEGOCIO_NOMBRE`, `NEGOCIO_TIPO`, `RECEPCIONISTA_NOMBRE`, `TIMEZONE=America/Mazatlan`.
- [ ] Subir `credenciales-google.json` como Secret File en Render (nunca al repo).
- [ ] Deploy → abrir `/health` → debe decir `{"ok": true}`.

**D. Meta / WhatsApp del cliente (lo más tedioso, ya sabemos el camino):**
- [ ] Alta del número del negocio en Meta, registro del número y webhook: `https://TU-DIRECCION.onrender.com/webhook` con su `VERIFY_TOKEN`. Suscribir el campo `messages`.
- [ ] Token permanente del usuario del sistema de ESE negocio → `WHATSAPP_TOKEN`.
- [ ] `META_APP_SECRET` de la app de ESE negocio (verifica la firma del webhook).
- [ ] Aprobar la plantilla de recordatorios (Utility, es_MX, cuerpo con {{1}} nombre y {{2}} fecha/hora) para encender los recordatorios.

**E. Prueba de humo (antes de cobrar):**
- [ ] Un "hola": palomitas azules + "escribiendo..." en segundos.
- [ ] Pedir una cita: botones Confirmar / Cambiar hora / Hablar con una persona → Confirmar → revisar Calendar, la pestaña Citas y el Panel.
- [ ] Revisar la pestaña **Diagnóstico**: todo OK (gemini, sheets, calendar, token, gmail, claves).
- [ ] Confirmar que llega el correo "¡Nueva cita!" al dueño.

## 3. Precio: tus dos opciones (tú decides)

**Opción A — Planes aprobados (2026-11-21, "Me late"):** Básico "Responde" setup $1,500 + $599/mes · Pro "Agenda" setup $3,000 + $1,499/mes · Premium "Completo" setup $5,000 + $2,999/mes. Descuento fundador en el setup para los primeros 5 clientes a cambio de testimonio.

**Opción B — Tu idea nueva (2026-11-22):** $3,000–$4,000/mes con $10,000 de pago inicial. Se justifica con valor, no con costo: una recepcionista real cuesta $12,000+ al mes; un paciente vale $650–$5,000; rescatar 2 citas al mes que se perdían de noche o en fin de semana ya paga el servicio varias veces. El setup de $10,000 se defiende si es onboarding completo (verificación de Meta, cargar datos, conectar número, capacitar y dejar probado).

**La secuencia que importa:** el primer cliente es fundador — precio bajo a cambio de testimonio y permiso de compartir resultados. Con 2–3 casos con números reales ("le agendó 14 citas el primer mes"), vendes a $3,000–$4,000 sin que te regateen. Primero la prueba, luego el precio premium. Y ponle fecha de fin a la condición fundadora: sin fecha, se vuelve tu precio para siempre.

## 4. Lo que falta antes de vender (tu lista corta)

- [ ] Aprobar la plantilla `recordatorio_cita` en Meta (WhatsApp Manager → Plantillas, tipo utilidad, es_MX, cuerpo con {{1}} y {{2}}). Sin ella los recordatorios se rechazan y no cuestan nada, pero el paciente no recibe nada.
- [ ] Contraseña de aplicación de Gmail en Render (`GMAIL_USER` + `GMAIL_APP_PASSWORD`): sin ella no salen los correos del dueño ni el reporte semanal.
- [ ] Correr la batería dorada con IA real en tu Mac (cubre v3.4.8–v3.20.1).
- [ ] Prueba en vivo con el número de prueba (decidiste seguir con ese por ahora): ya está el guion listo en `~/workspace/prueba-conversacional-en-vivo.md` (3 conversaciones cortas, ~10 min) — dos citas, cambio de hora, handoff, urgencia.
- [ ] Elegir nicho y probar la oferta con 5 negocios: si 3 de 5 dicen que sí o lo piensan en serio, el precio está en buen lugar.

## Qué NO hace falta

- **No hay que construir nada más:** el robot ya pasó la puerta dorada; la v3.20.1 está construida y probada en local, pendiente de subir a Render (en vivo sigue v3.19.0), con simulaciones conversacionales y adversariales en verde. La IA gratuita (Gemini) ya funciona; una IA mejor cuesta por mensaje y se cobra en el precio — se mejora cuando un cliente pague.
- **El repo `robot-whatsapp` está vacío** y apagado; el único robot real es `robot-python`. No hay nada que apagar.
