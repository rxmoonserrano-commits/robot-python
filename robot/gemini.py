"""Cliente REST de Gemini para texto y transcripción.

Configura modelos explícitos disponibles para la cuenta y verifica costos y
cuotas antes de usarlos. Ningún modelo está validado durante esta revisión.
"""

from __future__ import annotations

import base64
import re
import time

import requests

from .config import settings

_API = "https://generativelanguage.googleapis.com/v1beta/models"

# Último modelo que SÍ contestó (solo en memoria). La próxima llamada
# empieza por él, para no tropezar dos veces con el mismo modelo muerto.
_ULTIMO_MODELO_OK: str | None = None


def ultimo_modelo() -> str:
    """El modelo que contestó por última vez, o "" si ninguno lo ha hecho.

    (v2.13) Para saber en Diagnóstico si las respuestas malas vienen
    del modelo chico de respaldo y no del principal.
    """
    return _ULTIMO_MODELO_OK or ""


class GeminiError(RuntimeError):
    """Algo falló hablando con Gemini (clave, cuota, red, modelo retirado)."""


def _modelo_sugerido(texto_error: str) -> str:
    """Saca el modelo que Google sugiere en su error, si lo dice.

    El error es algo como: "This model models/gemini-2.5-flash is no
    longer available to new users. Please update your code to use
    models/gemini-3.8-flash ...". Devuelve "gemini-3.8-flash", o ""
    si el error no sugiere nada.
    """
    encontrado = re.search(r"use\s+models/([a-z0-9][a-z0-9._-]*)", texto_error or "")
    return encontrado.group(1) if encontrado else ""


def _llamar(modelo: str, partes: list[dict], json_mode: bool = False) -> str:
    """Un POST a Gemini. Devuelve el texto de la respuesta.

    (v2.13) Frenos de calidad, que antes no existían: la llamada iba
    sin temperatura (el modelo contestaba con la creatividad por
    defecto, variable) y sin pedir JSON en la API (se pedía solo en
    el texto del prompt y luego se hacía malabares con regex).
    Ahora, en modo JSON: temperatura 0.3 (sigue reglas, no inventa),
    JSON obligatorio en la API y tope de 600 tokens. La transcripción
    de audio sigue en texto plano (json_mode=False).

    (v2.5) Si Gemini responde 429 (cuota por minuto) o 500/502/503
    (Google saturado), se reintenta UNA vez tras 2 segundos antes de
    rendirse. De noche, sin nadie despierto para reintentarlo a mano,
    ese segundo intento es lo que evita un silencio.
    (v2.8) Lo mismo si la llamada se tarda demasiado o se corta la red:
    antes, un timeout (ReadTimeout) salía volando sin reintentar y sin
    probar el siguiente modelo, y el cliente se quedaba con un "dame
    un momento". Ahora el timeout se convierte en GeminiError y se
    reintenta igual. El tiempo de espera es 45 s y solo 2 intentos por
    modelo (v3.4.1): con 120 s y 3 intentos, una llamada colgada dejaba
    al cliente esperando minutos con un "dame un momento" y el lote
    atorado. Mejor fallar rápido y probar el siguiente modelo: si el
    modelo estaba frío, el segundo intento ya lo agarra tibio y contesta
    en segundos; si Gemini está caído, el fallo se ve en Diagnóstico
    en vez de colgar al cliente.
    (v3.4.5) Si Gemini contesta 200 pero con texto VACÍO (''), antes se
    aceptaba como éxito y el agente moría con "no es JSON: ''", dejando
    al cliente solo con el "dame un momento". Ahora el texto vacío se
    reintenta una vez y, si sigue vacío, se prueba el siguiente modelo;
    el error lleva el finishReason para ver en Diagnóstico si fue un
    bloqueo o un tropiezo.
    """
    url = f"{_API}/{modelo}:generateContent?key={settings.gemini_api_key}"
    # (v3.20.14) 1500, no 600: el JSON del agente trae respuesta_texto
    # más todos los campos de memoria; con 600 se truncaba a media
    # respuesta y el cliente recibía el genérico "dame un momento"
    # (visto en vivo 2026-11-25 22:00 UTC, primer mensaje real).
    config = {"temperature": 0.3, "maxOutputTokens": 1500}
    if json_mode:
        config["response_mime_type"] = "application/json"
    cuerpo = {"contents": [{"parts": partes}], "generationConfig": config}
    ultimo_error: GeminiError | None = None
    for intento in range(2):
        try:
            respuesta = requests.post(url, json=cuerpo, timeout=45)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            ultimo_error = GeminiError(f"Gemini tardó demasiado o se cortó la red: {exc}")
            if intento == 0:
                time.sleep(2)
                continue
            raise ultimo_error
        if respuesta.status_code == 200:
            datos = respuesta.json()
            try:
                texto = datos["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError, TypeError) as exc:
                raise GeminiError(f"Gemini respondió algo que no entiendo: {datos}") from exc
            if texto and str(texto).strip():
                return texto
            # (v3.4.5) Texto vacío con 200: el modelo contestó nada.
            # Se reintenta una vez; si sigue vacío, se prueba el
            # siguiente modelo (no se acepta como éxito).
            candidato = (datos.get("candidates") or [{}])[0] or {}
            ultimo_error = GeminiError(
                "Gemini devolvió texto vacío "
                f"(finishReason={candidato.get('finishReason', '?')}, "
                f"promptFeedback={datos.get('promptFeedback', {})})"
            )
            if intento == 0:
                time.sleep(2)
                continue
            raise ultimo_error
        ultimo_error = GeminiError(
            f"Gemini devolvió {respuesta.status_code}: {respuesta.text[:300]}"
        )
        # (v2.9) 503 "high demand" (modelo saturado): Google mismo dice
        # que es temporal ("spikes are usually temporary"). Se reintenta
        # una vez tras 2 s antes de rendirse y probar otro modelo.
        # El 12 de noviembre a las 22:19 el 3.8-flash estaba saturado y
        # con un solo reintento de 2 s no alcanzó.
        if respuesta.status_code == 503 and intento == 0:
            time.sleep(2)
            continue
        if respuesta.status_code in (429, 500, 502) and intento == 0:
            time.sleep(2)
            continue
        raise ultimo_error


def _candidatos() -> list[str]:
    """Solo modelos configurados explícitamente, sin asumir vigencia ni precio."""
    configurados = [str(m or "").strip() for m in
                    (settings.gemini_model, settings.gemini_model_fallback)]
    orden = []
    if _ULTIMO_MODELO_OK in configurados:
        orden.append(_ULTIMO_MODELO_OK)
    for modelo in configurados:
        if modelo and modelo not in orden:
            orden.append(modelo)
    return orden


def _probar_candidatos(partes: list[dict], json_mode: bool = False) -> str:
    """Prueba solo los modelos configurados explícitamente.

    Guarda el último que contestó mientras siga configurado. No cambia
    de modelo por sugerencias externas que podrían tener otro costo.
    """
    global _ULTIMO_MODELO_OK
    candidatos = _candidatos()
    if not candidatos:
        raise GeminiError("Configura GEMINI_MODEL con un modelo disponible para tu cuenta.")
    ultimo_error: GeminiError | None = None
    i = 0
    while i < len(candidatos):
        modelo = candidatos[i]
        i += 1
        try:
            texto = _llamar(modelo, partes, json_mode=json_mode)
        except GeminiError as exc:
            ultimo_error = exc
            continue
        _ULTIMO_MODELO_OK = modelo
        return texto
    raise ultimo_error or GeminiError("Gemini no contestó con ningún modelo.")


def generar_texto(prompt: str, json_mode: bool = True) -> str:
    """Pide texto a Gemini usando únicamente modelos configurados.

    (v2.13) Modo JSON: la API devuelve JSON válido y el modelo va con
    temperatura 0.3, para que siga las reglas en vez de improvisar.
    Es el modo del agente (que devuelve un JSON con la respuesta).
    (v3.0) OJO: json_mode=True es SOLO para el agente. El reporte
    semanal y la autoprueba piden prosa y usan json_mode=False: con
    JSON obligatorio, Gemini les devolvía el texto envuelto en llaves
    y el correo del lunes llegaba con JSON crudo. Ese fue un error de
    la v2.13, corregido aquí.
    """
    if not settings.gemini_api_key:
        raise GeminiError("Falta GEMINI_API_KEY en el .env. Ver README, paso 2.")
    return _probar_candidatos([{"text": prompt}], json_mode=json_mode)


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
    return _probar_candidatos(partes).strip()
