"""Google Gemini, capa gratuita. La única IA del robot.

Modelo (v2.9): gemini-4-hydrogen (respaldo: gemini-3.8-flash, y
siempre Flash-Lite al final), todos gratis a noviembre de 2026. Los
viejos gemini-2.0-flash y gemini-2.5-flash Google los retiró para
usuarios nuevos: el 12 de noviembre de 2026 el robot se quedó sin
cerebro por eso (404 "This model ... is no longer available to new
users. Please update your code to use models/gemini-3.8-flash"). El
3.8-flash sí funcionó, pero a las 22:19 devolvió 503 "high demand":
estaba saturado, por eso el cambio a 4 Hydrogen.
Clave: se saca en Google AI Studio (aistudio.google.com), sin tarjeta.
Se habla con Gemini por su API REST con `requests`, sin SDK pesado:
un POST con el texto (y el audio en base64, si lo hay) y listo.

Autocuración (v2.7): si Google retira un modelo, su error dice qué
modelo usar en su lugar ("use models/gemini-X"). El robot lee esa
sugerencia y la prueba SOLO, sin que nadie toque el código ni las
variables de entorno. Y recuerda el último modelo que funcionó, para
empezar por él la próxima vez (solo en memoria, se olvida al reiniciar).

Límites honestos de la capa gratuita: hay tope de peticiones por minuto
y por día. Para un negocio chico que empieza, alcanza. Si se acaba,
Gemini devuelve error y el robot no responde ese mensaje: el mensaje
queda registrado en Sheets, no se pierde.
Nada de pago aquí: ni Whisper, ni GPT.
"""

from __future__ import annotations

import base64
import re
import time

import requests

from .config import settings

_API = "https://generativelanguage.googleapis.com/v1beta/models"

# Modelos que Google ya retiró para usuarios nuevos. Si el .env o Render
# todavía traen uno de estos, el robot lo detecta y usa el vigente.
_MODELOS_RETIRADOS = ("gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro")

# Último modelo que SÍ contestó (solo en memoria). La próxima llamada
# empieza por él, para no tropezar dos veces con el mismo modelo muerto.
_ULTIMO_MODELO_OK: str | None = None


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


def _llamar(modelo: str, partes: list[dict]) -> str:
    """Un POST a Gemini. Devuelve el texto de la respuesta.

    (v2.5) Si Gemini responde 429 (cuota por minuto) o 500/502/503
    (Google saturado), se reintenta UNA vez tras 2 segundos antes de
    rendirse. De noche, sin nadie despierto para reintentarlo a mano,
    ese segundo intento es lo que evita un silencio.
    (v2.8) Lo mismo si la llamada se tarda demasiado o se corta la red:
    antes, un timeout (ReadTimeout) salía volando sin reintentar y sin
    probar el siguiente modelo, y el cliente se quedaba con un "dame
    un momento". Ahora el timeout se convierte en GeminiError y se
    reintenta igual. El tiempo de espera es 120 s: el robot contesta
    en segundo plano (el webhook ya respondió 200) y la burbuja de
    "escribiendo..." se refresca cada 20 s, así que al cliente no le
    afecta esperar un poco más; lo que no puede pasar es rendirse a
    los 60 s cuando el modelo está frío y contesta a los 70.
    """
    url = f"{_API}/{modelo}:generateContent?key={settings.gemini_api_key}"
    ultimo_error: GeminiError | None = None
    for intento in range(3):
        try:
            respuesta = requests.post(
                url, json={"contents": [{"parts": partes}]}, timeout=120
            )
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            ultimo_error = GeminiError(f"Gemini tardó demasiado o se cortó la red: {exc}")
            if intento == 0:
                time.sleep(2)
                continue
            raise ultimo_error
        if respuesta.status_code == 200:
            break
        ultimo_error = GeminiError(
            f"Gemini devolvió {respuesta.status_code}: {respuesta.text[:300]}"
        )
        # (v2.9) 503 "high demand" (modelo saturado): Google mismo dice
        # que es temporal ("spikes are usually temporary"). Se espera
        # más cada vez (2 s, 8 s) antes de rendirse y probar otro modelo.
        # El 12 de noviembre a las 22:19 el 3.8-flash estaba saturado y
        # con un solo reintento de 2 s no alcanzó.
        if respuesta.status_code == 503 and intento < 2:
            time.sleep(2 if intento == 0 else 8)
            continue
        if respuesta.status_code in (429, 500, 502) and intento == 0:
            time.sleep(2)
            continue
        raise ultimo_error
    datos = respuesta.json()
    try:
        return datos["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GeminiError(f"Gemini respondió algo que no entiendo: {datos}") from exc


def _candidatos() -> list[str]:
    """Modelos a probar, en orden, sin repetidos y sin retirados.

    Empieza por el último que funcionó (si lo hay), luego el principal
    y el respaldo. Los retirados se quitan: no tiene caso llamar a un
    modelo que Google ya dio de baja.
    (v2.9) Al final siempre va Flash-Lite, el modelo gratis más chico
    y el menos saturado: si los Flash grandes están a tope (503), el
    chico suele contestar.
    """
    orden = []
    for modelo in (_ULTIMO_MODELO_OK, settings.gemini_model, settings.gemini_model_fallback,
                   "gemini-3.5-flash-lite"):
        if modelo and modelo not in orden and modelo not in _MODELOS_RETIRADOS:
            orden.append(modelo)
    return orden or ["gemini-4-hydrogen"]


def _probar_candidatos(partes: list[dict]) -> str:
    """Prueba los modelos en orden. Si Google dice 'usa este otro',
    lo agrega a la lista y lo prueba solo (autocuración).

    Guarda el modelo que contestó, para empezar por él la próxima vez.
    Si ninguno contesta, lanza el último error.
    """
    global _ULTIMO_MODELO_OK
    candidatos = _candidatos()
    ultimo_error: GeminiError | None = None
    i = 0
    while i < len(candidatos):
        modelo = candidatos[i]
        i += 1
        try:
            texto = _llamar(modelo, partes)
        except GeminiError as exc:
            ultimo_error = exc
            sugerido = _modelo_sugerido(str(exc))
            if sugerido and sugerido not in candidatos:
                print(f"[gemini] Google retiró {modelo}; pruebo {sugerido} como sugiere el error.")
                candidatos.append(sugerido)
            continue
        _ULTIMO_MODELO_OK = modelo
        return texto
    raise ultimo_error or GeminiError("Gemini no contestó con ningún modelo.")


def generar_texto(prompt: str) -> str:
    """Pide texto a Gemini. Prueba los modelos en orden; si Google
    retira uno, usa el que Google sugiere, solo."""
    if not settings.gemini_api_key:
        raise GeminiError("Falta GEMINI_API_KEY en el .env. Ver README, paso 2.")
    return _probar_candidatos([{"text": prompt}])


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
