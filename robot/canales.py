"""Canales: un motor, varias bocas (v3.5).

El robot tiene UN solo cerebro (robot/logic.py + robot/agent.py):
entiende, responde, agenda, califica y pasa a humano. Cada canal
(WhatsApp, Messenger, Instagram) es solo una boca: recibe mensajes
de Meta, los normaliza al formato único de aquí, y manda la
respuesta de vuelta por la misma vía.

Estado actual, honesto:
- WhatsApp: ACTIVO y probado (es el canal vivo desde v1).
- Messenger e Instagram: DISEÑADOS pero APAGADOS. Las rutas
  /webhook/messenger y /webhook/instagram existen y responden
  "canal no activo" sin procesar nada. No se conecta nada hasta
  que Jose lo decida y se configuren los permisos en Meta.

Para activar un canal en el futuro (pasos, sin reescribir el motor):
1. En Meta: crear/suscribir el webhook del canal a la URL pública
   (/webhook/messenger o /webhook/instagram) con el VERIFY_TOKEN.
2. En Render: CANAL_MESSENGER_ACTIVO=SI (o INSTAGRAM) + el token
   de página/cuenta del negocio en variables de entorno.
3. Conectar el procesamiento: recibir_whatsapp de app.py es el
   modelo a seguir (200 inmediato, trabajo en segundo plano,
   normalizar con adaptador_*, pasar a logic.atender_mensaje con
   origen=<canal>, responder con enviar_<canal>).

Formato único de mensaje (lo que logic.py espera, sin importar el
canal): {canal, remitente, texto, adjuntos, recibido_en}.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

CANALES = ("whatsapp", "messenger", "instagram")


class CanalNoActivo(RuntimeError):
    """El canal existe en el diseño pero está apagado para este negocio."""


def canal_activo(canal: str) -> bool:
    """¿Este canal está prendido? WhatsApp siempre; los demás por variable.

    CANAL_MESSENGER_ACTIVO / CANAL_INSTAGRAM_ACTIVO en Render. Por
    defecto NO: sin variable, el canal está apagado y las rutas
    responden sin procesar nada.
    """
    if canal == "whatsapp":
        return True
    if canal == "messenger":
        return os.getenv("CANAL_MESSENGER_ACTIVO", "no").strip().lower() == "si"
    if canal == "instagram":
        return os.getenv("CANAL_INSTAGRAM_ACTIVO", "no").strip().lower() == "si"
    return False


def normalizar_mensaje(canal: str, remitente: str, texto: str,
                       adjuntos: list | None = None) -> dict:
    """El mensaje único que el motor entiende, venga del canal que venga."""
    return {
        "canal": canal,
        "remitente": str(remitente or "").strip(),
        "texto": str(texto or "").strip(),
        "adjuntos": list(adjuntos or []),
        "recibido_en": datetime.now(timezone.utc).isoformat(),
    }


def _extraer_messaging(payload: dict) -> list[dict]:
    """Saca los eventos de mensaje de un payload de Messenger/Instagram.

    Ambos canales de Meta mandan entry[].messaging[] con
    sender.id y message.text. Los eventos que no son mensajes
    (entregas, lecturas, postbacks) se ignoran aquí.
    """
    eventos = []
    for entrada in payload.get("entry", []) or []:
        for evento in entrada.get("messaging", []) or []:
            mensaje = evento.get("message") or {}
            texto = mensaje.get("text") or ""
            remitente = (evento.get("sender") or {}).get("id") or ""
            if remitente and texto:
                eventos.append({"remitente": remitente, "texto": texto,
                                "adjuntos": mensaje.get("attachments") or []})
    return eventos


def adaptador_messenger(payload: dict) -> list[dict]:
    """Payload de Messenger -> mensajes normalizados. Apagado por defecto."""
    if not canal_activo("messenger"):
        raise CanalNoActivo("Messenger está diseñado pero apagado para este negocio.")
    return [
        normalizar_mensaje("messenger", e["remitente"], e["texto"], e["adjuntos"])
        for e in _extraer_messaging(payload)
    ]


def adaptador_instagram(payload: dict) -> list[dict]:
    """Payload de Instagram -> mensajes normalizados. Apagado por defecto."""
    if not canal_activo("instagram"):
        raise CanalNoActivo("Instagram está diseñado pero apagado para este negocio.")
    return [
        normalizar_mensaje("instagram", e["remitente"], e["texto"], e["adjuntos"])
        for e in _extraer_messaging(payload)
    ]


def enviar_messenger(remitente: str, texto: str) -> None:
    """Mandar un texto por Messenger. Apagado hasta conectar el canal."""
    if not canal_activo("messenger"):
        raise CanalNoActivo("Messenger está diseñado pero apagado para este negocio.")
    raise NotImplementedError(
        "Enviar por Messenger se conecta cuando se active el canal "
        "(Graph API con el token de página del negocio).")


def enviar_instagram(remitente: str, texto: str) -> None:
    """Mandar un texto por Instagram. Apagado hasta conectar el canal."""
    if not canal_activo("instagram"):
        raise CanalNoActivo("Instagram está diseñado pero apagado para este negocio.")
    raise NotImplementedError(
        "Enviar por Instagram se conecta cuando se active el canal "
        "(Graph API con el token de la cuenta del negocio).")
