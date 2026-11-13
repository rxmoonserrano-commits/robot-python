"""El revisor: la segunda mirada antes de mandar (v2.13).

El problema que corrige: antes, lo que Gemini contestaba se le mandaba
al cliente tal cual, sin que nadie lo revisara. Por eso los errores que
Jose veía en vivo (ofrecer la cita dos veces, ofrecerla a un simple
saludo, decir "ya cerramos") llegaban al cliente: ningún código y
ningún segundo modelo los vio antes.

El revisor es determinista (reglas por código, sin otra llamada a la
IA: rápido, gratis, siempre igual) y corre sobre TODOS los mensajes en
vivo, no solo en pruebas. Revisa tres cosas:

R1. NO REPETIR LA OFERTA: si ya hay una cita ofrecida y pendiente
    (estado "oferta_pendiente"), la respuesta nueva NO puede volver a
    ofrecer una cita. Se quita la frase de la oferta; el resto de la
    respuesta queda. Si la respuesta ERA solo la oferta, queda un
    texto corto que recuerda que los horarios ya están arriba.
R2. NO OFRECER EN UN SALUDO: si la etapa es "saludo" (el cliente solo
    saludó), la respuesta NO puede ofrecer una cita. Se quita la frase
    de la oferta; si no queda nada, se saluda y se pregunta qué necesita.
R3. DE NOCHE, EL ROBOT NO CIERRA: si la respuesta dice "ya cerramos"
    o "ahora estamos cerrados" como si el robot cerrara, se cambia por
    la frase de cierre del perfil del negocio (robot/negocio.py):
    "El negocio ya cerró por hoy, pero yo te atiendo igual", o "En
    <nombre> ya cerraron por hoy..." si el negocio tiene nombre.

Devuelve (texto_final, violaciones): la lista de reglas que corrigió
("R1", "R2", "R3"), vacía si la respuesta estaba bien. Las
correcciones se escriben en Diagnóstico (ver logic.py), para que
quede constancia de qué se atrapó.

Reglas puras, sin internet: se prueban solas en test_v2_13.py.
"""

from __future__ import annotations

import re

from .negocio import frase_cierre

# Frases que son una oferta de cita (nueva). Ojo: "Te aparto el lugar
# hasta mañana sin compromiso" NO es una oferta nueva: es aguantar la
# oferta que ya está hecha, y nunca se quita.
_OFERTA_RE = re.compile(
    r"agend|confirmo tu cita|te va el|te viene el|¿te la|te la agendo",
    re.IGNORECASE,
)

# "Ya cerramos" dicho por el robot, como si él cerrara. El "pero abrimos
# mañana" que a veces viene pegado se traga también, para que no quede
# colgando después del cambio ("...te atiendo igual pero abrimos mañana").
_CERRAMOS_RE = re.compile(
    r"ahorita ya cerramos(?: pero abrimos mañana)?|ahora estamos cerrados"
    r"|ya cerramos por hoy|estamos cerrados",
    re.IGNORECASE,
)

# La frase de cierre sale del perfil del negocio (v3.0): antes estaba
# escrita a mano aquí ("la clínica...") y el robot genérico se la
# decía a cualquier negocio. Ver robot/negocio.py: frase_cierre().


def _es_oferta(oracion: str) -> bool:
    """¿Esta frase ofrece una cita nueva?

    "Te aparto el lugar hasta mañana sin compromiso" no cuenta: es
    aguantar la oferta, no hacer una nueva. Y "la agenda de mañana
    está llena" tampoco: habla de la agenda, no ofrece nada. Por eso
    "agend" solo cuenta si la frase pregunta ("¿Te la agendo...?") o
    lleva el verbo con "te" ("te la agendo para mañana").
    """
    texto = (oracion or "").strip()
    if not texto:
        return False
    bajo = texto.lower()
    if "sin compromiso" in bajo:
        return False
    if "confirmo tu cita" in bajo:
        return True
    if re.search(r"te va el|te viene el", bajo):
        return True
    if re.search(r"te (la )?agendo|agendarte", bajo):
        return True
    if "agend" in bajo and "?" in texto:
        return True
    return False


def _partir_oraciones(texto: str) -> list[str]:
    """Parte un texto en oraciones, sin perder los signos.

    "Hola. ¿Te agendo mañana a las 9:00 o el sábado? Avísame" →
    ["Hola.", "¿Te agendo mañana a las 9:00 o el sábado?", "Avísame"]
    """
    partes = re.split(r"(?<=[.!?])\s+", (texto or "").strip())
    return [p.strip() for p in partes if p.strip()]


def revisar_respuesta(
    texto: str,
    estado: dict | None = None,
    nombre: str = "",
) -> tuple[str, list[str]]:
    """Revisa una respuesta del agente y la corrige si viola una regla.

    `estado`: el dict de estado_cliente (etapa, ya_ofrecio_cita...).
    Si no viene, solo se aplica R3 (la de "ya cerramos").
    """
    estado = estado or {}
    etapa = str(estado.get("etapa", "") or "")
    oferta_pendiente = bool(estado.get("ya_ofrecio_cita"))
    texto = (texto or "").strip()
    violaciones: list[str] = []

    # R3 primero: la frase de cierre, se cambie lo que se cambie después.
    if _CERRAMOS_RE.search(texto):
        texto = _CERRAMOS_RE.sub(frase_cierre(), texto)
        violaciones.append("R3")

    # R1/R2: quitar la frase de la oferta cuando no toca.
    if (oferta_pendiente or etapa == "saludo") and _es_oferta(texto):
        oraciones = _partir_oraciones(texto)
        quedan = [o for o in oraciones if not _es_oferta(o)]
        if quedan:
            texto = " ".join(quedan).strip()
            # En un saludo, lo que queda no puede ser un callejón sin
            # salida ("¡Buenas noches!" y nada más): si no hay pregunta,
            # se agrega una, para que la conversación siga.
            if etapa == "saludo" and "?" not in texto:
                texto += " ¿En qué te puedo ayudar?"
        elif etapa == "saludo":
            saludo = f"¡Hola, {nombre}! " if nombre else "¡Hola! "
            texto = saludo + "¿En qué te puedo ayudar?"
        else:
            texto = (
                "Los horarios que te dejé arriba siguen disponibles. "
                "¿Te ayudo con algo más?"
            )
        violaciones.append("R1" if oferta_pendiente else "R2")

    return texto, violaciones
