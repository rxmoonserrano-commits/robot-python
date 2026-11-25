# Conectar el número nuevo al robot — guía de una página

**Número del robot:** +52 669 100 1402
**Tu personal (no se toca):** +52 669 460 8263
**WABA (misma cuenta):** 1662274398730005
**Número de prueba actual (se reemplaza):** +1 (555) 641-6437

Regla Meta: al registrar el número en la Cloud API sale de la app y vive solo en la API. Por eso el robot usa el nuevo y tu personal sigue intacto.

## Antes de empezar (5 min)

- Ten a la mano el SIM del +52 669 100 1402 en un teléfono que reciba el código de verificación.
- Entra en TU navegador a Meta WhatsApp Manager (el navegador de Muse no puede entrar a Facebook).
- No borres nada de la WABA actual: mismo token y webhook, solo se agrega el número.

## Paso 1 — Agregar el número en Meta (tú, en tu navegador)

1. WhatsApp Manager → tu cuenta de WhatsApp Business (la misma de siempre).
2. Configuración / Números de teléfono → **Agregar número de teléfono**.
3. País: México. Número: 669 100 1402.
4. Elige cómo verificar (SMS o llamada) → pide el código → el código llega al SIM nuevo.
5. Escribe el código. Meta te confirma el número agregado.

## Paso 2 — Copiar el Phone Number ID (tú)

1. En la lista de números, abre el número nuevo.
2. Copia el **Phone Number ID** que muestra Meta.
3. Pégalo aquí en el chat. Con ese dato yo cambio `WHATSAPP_PHONE_NUMBER_ID` en Render y redeploya solo.

## Paso 3 — Prueba (2 min, juntos)

1. Desde tu WhatsApp personal (+52 669 460 8263) manda un mensaje al +52 669 100 1402.
2. El robot debe responder: saluda, pregunta, califica y agenda con botones.
3. Revisamos juntos que caiga en las hojas **Clientes** y **Citas**.

## Qué cambia al terminar

- **Cualquier número del mundo** puede escribirle al +52 669 100 1402 y el agente lo atiende 24/7 (responde, califica, agenda). Ya no es solo para destinatarios de prueba.
- Tu personal sigue en la app como siempre; el número nuevo deja de verse en la app porque vive en la API.
- El número de prueba +1 (555) 641-6437 queda reemplazado.

## Si algo se atora

- Código no llega: revisa que el SIM tenga señal y que el número sea el nuevo, no el personal.
- Meta pide verificar la cuenta de negocio: sigue el flujo que pida; no cambia el plan.
- Duda en cualquier paso: mándame captura y seguimos clic por clic.

## Pendientes relacionados (no bloquean este paso)

- Contraseña de Gmail en Render (para que salgan correos de handoff y reportes).
- Plantilla `recordatorio_cita` en Meta (para recordatorios automáticos).
- Corrida real de las 34 conversaciones doradas en tu Mac.
