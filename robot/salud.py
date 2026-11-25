"""Salud del robot al arrancar (v3.0): la revisión de activación.

Antes, al arrancar solo se probaba Gemini. Todo lo demás (la hoja,
el calendario, el token de WhatsApp, Gmail, las claves de seguridad)
se descubría cuando ya había fallado de noche, con un cliente
esperando. Ahora, al arrancar, el robot revisa cada pieza y escribe
el resultado en la pestaña Diagnóstico de la hoja: OK, AVISO (falta
algo, pero el robot sigue) o FALLO (esto no funciona y hay que
arreglarlo). El dueño lo ve en la hoja sin entrar a Render.

Qué se revisa:
- gemini: la clave contesta (la autoprueba de siempre).
- sheets: la hoja oficial se lee.
- calendar: el calendario responde (prueba de disponibilidad).
- whatsapp: el token es válido (401 = muerto o inválido).
- gmail: usuario y contraseña de aplicación configurados.
- owner_email: no sigue siendo el ejemplo dueno@empresa.com.
- admin_token: /pausa y /reporte-semanal protegidos.
- meta_firma: el webhook verifica la firma de Meta.

Cada revisión es best-effort: si una falla, las demás se hacen igual
y el robot arranca. Nada de esto bloquea el arranque.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from . import booking, gemini, sheets
from .config import settings
from .registro import aviso, error, info

_API_WHATSAPP = "https://graph.facebook.com/v21.0"


def revisar_salud(deps, ahora: datetime | None = None) -> list[dict]:
    """Revisa cada pieza y devuelve [{'componente', 'estado', 'detalle'}].

    `deps` es el objeto de dependencias (solo se usa para escribir en
    Diagnóstico). Cada resultado queda también en el registro del
    servidor, con su nivel (info / aviso / error).
    """
    ahora = ahora or datetime.now(timezone.utc)
    resultados: list[dict] = []

    def anotar(componente: str, estado: str, detalle: str) -> None:
        resultados.append({"componente": componente, "estado": estado, "detalle": detalle})
        try:
            deps.registrar_diagnostico(ahora, componente, estado, detalle)
        except Exception:
            pass
        mensaje = f"[salud] {componente}: {estado} — {detalle}"
        if estado == "OK":
            info(mensaje)
        elif estado == "AVISO":
            aviso(mensaje)
        else:
            error(mensaje)

    # Gemini: la clave contesta (prosa, no JSON).
    try:
        gemini.generar_texto("Responde solo con la palabra OK.", json_mode=False)
        anotar("gemini", "OK", "Autoprueba al arrancar: Gemini contestó.")
    except Exception as exc:  # noqa: BLE001
        anotar("gemini", "FALLO", str(exc)[:300])

    # Sheets: la hoja oficial se lee.
    try:
        sheets.leer_control()
        anotar("sheets", "OK", "La hoja oficial se lee bien.")
    except Exception as exc:  # noqa: BLE001
        anotar("sheets", "FALLO", str(exc)[:300])

    # Calendar: el calendario responde a una consulta de disponibilidad.
    try:
        booking.hora_libre((ahora + timedelta(days=7)).isoformat())
        anotar("calendar", "OK", "El calendario se lee bien.")
    except Exception as exc:  # noqa: BLE001
        anotar("calendar", "FALLO", str(exc)[:300])

    # WhatsApp: el token es válido (200) o está muerto (401).
    try:
        respuesta = requests.get(
            f"{_API_WHATSAPP}/{settings.whatsapp_phone_number_id}",
            headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
            timeout=15,
        )
        if respuesta.status_code == 200:
            anotar("whatsapp", "OK", "El token de WhatsApp es válido.")
        elif respuesta.status_code == 401:
            anotar("whatsapp", "FALLO",
                   "Token de WhatsApp inválido o vencido (401). Pon uno nuevo en Render.")
        else:
            anotar("whatsapp", "FALLO",
                   f"WhatsApp devolvió {respuesta.status_code}: {respuesta.text[:200]}")
    except Exception as exc:  # noqa: BLE001
        anotar("whatsapp", "FALLO", str(exc)[:300])

    # Registro del número en la Cloud API (v3.20.12): un número agregado en
    # WhatsApp Manager queda 'Pendiente' y Meta no entrega mensajes al
    # webhook hasta registrarlo por API. Se consulta el estado y, si no
    # está conectado, se intenta registrar. Best-effort: nunca rompe el
    # arranque y todo queda en Diagnóstico.
    try:
        from . import whatsapp as _wa

        estado = _wa.consultar_estado_numero()
        status = estado.get("status", "")
        verif = estado.get("code_verification_status", "")
        nombre = estado.get("verified_name", "")
        if status == "Connected":
            anotar("registro_numero", "OK",
                   f"Número conectado en Meta (verificación: {verif or '?'}, nombre: {nombre or '?'}).")
        else:
            try:
                _wa.registrar_numero(pin=settings.whatsapp_register_pin)
                anotar("registro_numero", "OK",
                       f"Número registrado en Meta (antes: {status or 'sin estado'}).")
            except Exception as exc:
                anotar("registro_numero", "AVISO",
                       f"Número en estado {status or '?'} (verificación: {verif or '?'}); "
                       f"registro automático falló: {str(exc)[:200]}")
    except Exception as exc:  # noqa: BLE001
        anotar("registro_numero", "AVISO",
               f"No se pudo consultar el estado del número: {str(exc)[:200]}")

    # Gmail: sin él, los handoffs y el reporte no llegan (en silencio).
    if settings.gmail_user and settings.gmail_app_password:
        anotar("gmail", "OK", "Gmail configurado: handoffs y reporte llegan.")
    else:
        anotar("gmail", "AVISO",
               "Gmail sin configurar: los handoffs y el reporte semanal NO llegan. Ver README, paso 4.")

    # Correo del dueño: que no siga siendo el ejemplo.
    if settings.owner_email and settings.owner_email != "dueno@empresa.com":
        anotar("owner_email", "OK", f"Alertas para {settings.owner_email}.")
    else:
        anotar("owner_email", "AVISO",
               "OWNER_EMAIL sigue siendo dueno@empresa.com: las alertas no llegan a nadie.")

    # Clave de dueño: sin ella, /pausa y /reporte-semanal están cerrados.
    if settings.admin_token:
        anotar("admin_token", "OK", "/pausa y /reporte-semanal protegidos con clave.")
    else:
        anotar("admin_token", "AVISO",
               "Sin ADMIN_TOKEN: /pausa y /reporte-semanal están cerrados hasta configurarlo.")

    # Firma de Meta: sin secreto, el webhook no verifica quién llama.
    if settings.meta_app_secret:
        anotar("meta_firma", "OK", "El webhook verifica la firma de Meta.")
    else:
        anotar("meta_firma", "AVISO",
               "Sin META_APP_SECRET: el webhook acepta mensajes sin verificar la firma.")

    return resultados
