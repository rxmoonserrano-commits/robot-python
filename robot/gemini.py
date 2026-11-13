"""Google Gemini, capa gratuita. La única IA del robot.

Modelo: gemini-2.0-flash (si Google lo retira, gemini-2.5-flash, también gratis).
Clave: se saca en Google AI Studio (aistudio.google.com), sin tarjeta.
Se habla con Gemini por su API REST con `requests`, sin SDK pesado:
un POST con el texto (y el audio en base64, si lo hay) y listo.

Límites honestos de la capa gratuita: hay tope de peticiones por minuto
y por día. Para un negocio chico que empieza, alcanza. Si se acaba,
Gemini devuelve error y el robot no responde ese mensaje: el mensaje
queda registrado en Sheets, no se pierde.
Nada de pago aquí: ni Whisper, ni GPT.
"""

from __future__ import annotations

import base64
import time

import requests

from .config import settings

_API = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiError(RuntimeError):
    """Algo falló hablando con Gemini (clave, cuota, red, modelo retirado)."""


def _llamar(modelo: str, partes: list[dict]) -> str:
    """Un POST a Gemini. Devuelve el texto de la respuesta.

    (v2.5) Si Gemini responde 429 (cuota por minuto) o 500/502/503
    (Google saturado), se reintenta UNA vez tras 2 segundos antes de
    rendirse. De noche, sin nadie despierto para reintentarlo a mano,
    ese segundo intento es lo que evita un silencio.
    """
    url = f"{_API}/{modelo}:generateContent?key={settings.gemini_api_key}"
    ultimo_error: GeminiError | None = None
    for intento in range(2):
        respuesta = requests.post(
            url, json={"contents": [{"parts": partes}]}, timeout=60
        )
        if respuesta.status_code == 200:
            break
        ultimo_error = GeminiError(
            f"Gemini devolvió {respuesta.status_code}: {respuesta.text[:300]}"
        )
        if respuesta.status_code in (429, 500, 502, 503) and intento == 0:
            time.sleep(2)
            continue
        raise ultimo_error
    datos = respuesta.json()
    try:
        return datos["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GeminiError(f"Gemini respondió algo que no entiendo: {datos}") from exc


def generar_texto(prompt: str) -> str:
    """Pide texto a Gemini. Si el modelo principal falla, prueba el de respaldo."""
    if not settings.gemini_api_key:
        raise GeminiError("Falta GEMINI_API_KEY en el .env. Ver README, paso 2.")
    try:
        return _llamar(settings.gemini_model, [{"text": prompt}])
    except GeminiError:
        # Segundo intento con el modelo de respaldo, también gratis.
        return _llamar(settings.gemini_model_fallback, [{"text": prompt}])


def transcribir_audio(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """Entiende un audio del cliente con Gemini multimodal.

    El robot NUNCA responde con audio, solo lo entiende y contesta en texto.
    Devuelve lo que dijo el cliente, en español, en una frase.
    """
    if not settings.gemini_api_key:
        raise GeminiError("Falta GEMINI_API_KEY en el .env. Ver README, paso 2.")
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    partes = [
        {"inline_data": {"mime_type": mime_type, "data": audio_b64}},
        {
            "text": "Transcribe este audio en español y resume qué quiere "
            "el cliente en una frase. Devuelve solo esa frase."
        },
    ]
    try:
        return _llamar(settings.gemini_model, partes).strip()
    except GeminiError:
        return _llamar(settings.gemini_model_fallback, partes).strip()
