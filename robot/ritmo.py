"""Ritmo humano: que el robot no conteste como ametralladora.

Tres reglas, nada más:
1. Antes de contestar, espera un poco (1 a 3 segundos, según lo largo
   de lo que va a decir). Una persona no contesta en 0.2 segundos.
2. Si la respuesta es larga, se parte en 2 mensajes cortos, con una
   pausita de 1 a 2 segundos entre ellos. Nunca un muro de texto.
3. Las pausas se pueden apagar en las pruebas (dormir=False), para
   que los tests no tarden. En producción siempre van prendidas.

Todo aquí es puro (sin internet): se prueba solo, sin WhatsApp.
"""

from __future__ import annotations

import re
import time

# Un mensaje de WhatsApp se lee bien hasta ~300 caracteres. Más que eso
# ya se siente como un correo, no como un chat.
MAX_POR_MENSAJE = 300


def demora_humana(texto: str) -> float:
    """Cuánto esperar antes de contestar, en segundos: entre 1 y 3.

    Más largo lo que vas a decir, más tardas en "escribirlo".
    """
    demora = 1.0 + min(len(texto) / 400.0, 2.0)
    return round(min(demora, 3.0), 2)


def dividir_mensaje(texto: str, max_chars: int = MAX_POR_MENSAJE) -> list[str]:
    """Parte un texto largo en mensajes cortos, sin romper frases.

    Primero intenta cortar por frases (punto, !, ?). Si una sola frase
    es más larga que el límite, la corta por palabras. Nunca devuelve
    una lista vacía y nunca devuelve un pedazo de más de max_chars
    (salvo una palabra suelta más larga que el límite, que no se parte).
    """
    texto = (texto or "").strip()
    if not texto:
        return []
    if len(texto) <= max_chars:
        return [texto]
    frases = re.split(r"(?<=[.!?])\s+", texto)
    partes: list[str] = []
    actual = ""
    for frase in frases:
        if not frase:
            continue
        if len(frase) > max_chars:
            # Frase larguísima: se guarda lo acumulado y se corta por palabras.
            if actual:
                partes.append(actual)
                actual = ""
            palabras = frase.split(" ")
            trozo = ""
            for palabra in palabras:
                if trozo and len(trozo) + 1 + len(palabra) > max_chars:
                    partes.append(trozo)
                    trozo = palabra
                else:
                    trozo = f"{trozo} {palabra}".strip()
            if trozo:
                partes.append(trozo)
            continue
        if actual and len(actual) + 1 + len(frase) > max_chars:
            partes.append(actual)
            actual = frase
        else:
            actual = f"{actual} {frase}".strip()
    if actual:
        partes.append(actual)
    return partes


def enviar_partes(enviar_texto, telefono: str, partes: list[str], dormir: bool = True) -> list[str]:
    """Manda varias partes como mensajes separados, con pausita entre cada una.

    (v3.4.8) El agente decide cuándo su respuesta va en 1 solo mensaje
    y cuándo en varios (por ejemplo, contestar dos temas distintos):
    cada parte es su propio mensaje, en orden. Si una parte es muy
    larga, se parte como siempre. Devuelve todos los pedazos mandados.
    """
    enviados: list[str] = []
    for parte in partes:
        for trozo in dividir_mensaje(parte):
            if dormir and enviados:
                time.sleep(1.5)
            elif dormir and not enviados:
                time.sleep(demora_humana(parte))
            enviar_texto(telefono, trozo)
            enviados.append(trozo)
    return enviados


def enviar_con_ritmo(enviar_texto, telefono: str, texto: str, dormir: bool = True) -> list[str]:
    """Manda un texto con ritmo humano. Devuelve los pedazos que mandó.

    Espera la demora humana, manda el primer pedazo, y si hay más,
    espera 1.5 segundos entre pedazo y pedazo. `enviar_texto` es la
    función que realmente manda (en producción: whatsapp.enviar_texto;
    en pruebas: una falsa que guarda en memoria).
    """
    partes = dividir_mensaje(texto)
    if dormir and partes:
        time.sleep(demora_humana(texto))
    for i, parte in enumerate(partes):
        if i > 0 and dormir:
            time.sleep(1.5)
        enviar_texto(telefono, parte)
    return partes
