"""WhatsApp Cloud API (Meta for Developers).

Tres cosas, nada más:
- mandar un texto (la única forma en que el robot responde),
- mandar una foto oficial (solo si pasó la lista blanca),
- descargar un audio que mandó el cliente (para que Gemini lo entienda).

El robot NUNCA manda audio. Tampoco manda mensajes por su cuenta:
solo responde cuando le escriben (y dentro de la ventana de 24 horas
de WhatsApp; fuera de ella, Meta pide una plantilla aprobada).
"""

from __future__ import annotations

import requests

from .config import settings

_API = "https://graph.facebook.com/v21.0"


class WhatsAppError(RuntimeError):
    """Algo falló hablando con WhatsApp (token, número, plantilla, red)."""


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.whatsapp_token}",
        "Content-Type": "application/json",
    }


def marcar_leido(message_id: str) -> None:
    """Marca un mensaje como leído (palomitas azules), sin "escribiendo...".

    (v3.4.8) Se llama en cuanto llega el mensaje, antes de esperar los
    15 segundos del buffer: el cliente ve al instante que su mensaje
    llegó y fue leído, como cuando una persona lo ve en su teléfono.
    (v3.9.2) Inmediatamente después se prende la burbuja con
    marcar_leido_y_escribiendo: el cliente ve "escribiendo..." desde
    el primer segundo, no después de la espera del buffer.
    No es un mensaje: no se cobra y no deja rastro en el chat.
    """
    if not message_id:
        return
    respuesta = requests.post(
        f"{_API}/{settings.whatsapp_phone_number_id}/messages",
        headers=_headers(),
        json={
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        },
        timeout=15,
    )
    if respuesta.status_code not in (200, 201):
        raise WhatsAppError(
            f"WhatsApp devolvió {respuesta.status_code}: {respuesta.text[:300]}"
        )


def marcar_leido_y_escribiendo(message_id: str) -> None:
    """Marca un mensaje como leído (palomitas azules) Y muestra "escribiendo...".

    Es UNA sola llamada de la Cloud API: status "read" + typing_indicator.
    La burbuja dura máximo 25 segundos y se apaga sola cuando el robot
    contesta (o a los 25 s). (v3.9.2) Se llama en cuanto llega el
    mensaje (webhook) y de nuevo al arrancar el lote (paso 3 de
    atender_mensaje). Ya NO se refresca mientras Gemini piensa: una
    burbuja que dura lo que tarda la IA (a veces más de un minuto) se
    siente robótica; una persona escribe un rato y se calla.
    Solo vale dentro de la ventana de 24 horas. En el webhook se
    prende sin saber si el robot va a contestar (pausa, apagado):
    en ese caso la burbuja solo se apaga a los 25 s, sin más efecto.
    No es un mensaje: no se cobra y no deja rastro en el chat.
    """
    if not message_id:
        return
    respuesta = requests.post(
        f"{_API}/{settings.whatsapp_phone_number_id}/messages",
        headers=_headers(),
        json={
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
            "typing_indicator": {"type": "text"},
        },
        timeout=15,
    )
    if respuesta.status_code not in (200, 201):
        raise WhatsAppError(
            f"WhatsApp devolvió {respuesta.status_code}: {respuesta.text[:300]}"
        )


def enviar_botones(telefono: str, texto: str, botones: list[tuple[str, str]]) -> None:
    """Manda un mensaje con botones de respuesta rápida (máximo 3).

    botones: lista de (id, título). El título se ve en el botón y tiene
    que ser corto (máximo 20 caracteres). Cuando el cliente toca uno,
    Meta manda un mensaje tipo "interactive" con ese id, y el robot lo
    atiende en app.py / logic.atender_boton.
    Solo se usan donde tienen sentido (confirmar una cita), nunca en
    cada mensaje: un botón de más es ruido.
    """
    botones = botones[:3]
    respuesta = requests.post(
        f"{_API}/{settings.whatsapp_phone_number_id}/messages",
        headers=_headers(),
        json={
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": texto},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": bid, "title": titulo[:20]}}
                        for bid, titulo in botones
                    ]
                },
            },
        },
        timeout=30,
    )
    if respuesta.status_code not in (200, 201):
        raise WhatsAppError(
            f"WhatsApp devolvió {respuesta.status_code}: {respuesta.text[:300]}"
        )


def enviar_texto(telefono: str, texto: str) -> None:
    """Manda un mensaje de texto a un teléfono. Solo texto, siempre."""
    respuesta = requests.post(
        f"{_API}/{settings.whatsapp_phone_number_id}/messages",
        headers=_headers(),
        json={
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "text",
            "text": {"body": texto, "preview_url": False},
        },
        timeout=30,
    )
    if respuesta.status_code not in (200, 201):
        raise WhatsAppError(
            f"WhatsApp devolvió {respuesta.status_code}: {respuesta.text[:300]}"
        )


def enviar_foto(telefono: str, url_foto: str, pie: str = "Te comparto una foto de nuestro negocio.") -> None:
    """Manda una foto por su URL. Llamar SOLO con URLs de la lista blanca.

    La validación vive en logic.py (foto_es_oficial). Este archivo no decide,
    solo manda lo que ya fue aprobado.
    """
    respuesta = requests.post(
        f"{_API}/{settings.whatsapp_phone_number_id}/messages",
        headers=_headers(),
        json={
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "image",
            "image": {"link": url_foto, "caption": pie},
        },
        timeout=30,
    )
    if respuesta.status_code not in (200, 201):
        raise WhatsAppError(
            f"WhatsApp devolvió {respuesta.status_code}: {respuesta.text[:300]}"
        )


def enviar_plantilla(
    telefono: str,
    nombre_plantilla: str,
    idioma: str,
    parametros: list[str],
) -> None:
    """Manda una plantilla aprobada de WhatsApp (recordatorios, v3.12).

    Las plantillas se aprueban en Meta (WhatsApp Manager); sin una
    aprobada, Meta devuelve error y quien llama lo registra en
    Diagnóstico. `parametros` son los valores para {{1}}, {{2}}...
    en orden (p. ej. nombre y fecha/hora de la cita).
    """
    respuesta = requests.post(
        f"{_API}/{settings.whatsapp_phone_number_id}/messages",
        headers=_headers(),
        json={
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "template",
            "template": {
                "name": nombre_plantilla,
                "language": {"code": idioma},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": str(p)} for p in parametros
                        ],
                    }
                ],
            },
        },
        timeout=30,
    )
    if respuesta.status_code not in (200, 201):
        raise WhatsAppError(
            f"WhatsApp devolvió {respuesta.status_code}: {respuesta.text[:300]}"
        )


def descargar_audio(media_id: str) -> tuple[bytes, str]:
    """Descarga un audio de WhatsApp y devuelve (bytes, tipo mime).

    Paso 1: pedir la URL del archivo. Paso 2: bajarlo con el token.
    """
    info = requests.get(
        f"{_API}/{media_id}", headers=_headers(), timeout=30
    )
    if info.status_code != 200:
        raise WhatsAppError(f"No pude pedir el audio {media_id}: {info.text[:200]}")
    datos = info.json()
    descarga = requests.get(
        datos["url"], headers=_headers(), timeout=60
    )
    if descarga.status_code != 200:
        raise WhatsAppError(f"No pude bajar el audio {media_id}.")
    return descarga.content, datos.get("mime_type", "audio/ogg")
