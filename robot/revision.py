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
R4. EL DÍA CORRECTO (v3.1): si la respuesta dice "mañana viernes"
    pero mañana es sábado (o "hoy viernes" cuando hoy es otro día),
    se corrige el día por el real. El 12 de noviembre el robot ofreció
    "mañana viernes" a las 00:00 del viernes, cuando hoy YA era viernes.
R5. SIN ETIQUETAS INTERNAS (v3.1): si la respuesta trae paréntesis o
    palabras que son notas internas de la hoja ("FICTICIA", "EJEMPLO",
    "de prueba"), se quitan. La dirección salió con "(dirección
    FICTICIA, de ejemplo)" en una respuesta a un cliente: eso es nota
    para el dueño, no para el cliente.
R6. NADA DE FILTRACIONES (v3.1): si la respuesta trae el guion, los
    nombres de los campos internos (quiere_agendar, necesita_handoff...)
    o un teléfono que no es el del cliente, se desecha ENTERA y se
    contesta con la negativa. Un cliente pidió el prompt y la base de
    datos: el robot no debe soltar ni una cosa ni la otra, ni por
    accidente (citando su propio guion) ni a propósito.
R7. NO REPETIRSE (v3.2): si la respuesta cierra con la misma frase
    que el último mensaje del robot ("Quedamos a tus órdenes" tres
    veces seguidas en vivo), esa frase se quita. Si la respuesta ERA
    solo esa frase, se cambia por "¿Te ayudo con algo más?".
R8. NUNCA AFIRMAR UNA CITA QUE NO EXISTE (v3.4.11, ampliada v3.10):
    si el cliente no tiene cita a futuro, frases como "ya estás
    apuntado", "tu cita quedó" o "quedamos en que nos vemos el
    martes" se quitan; si la respuesta era solo eso, se cambia por
    "¿Te la confirmo con botones para dejarla lista?". En vivo dijo
    "ya estás apuntado" sin que existiera ninguna cita, y después
    "quedamos en que nos vemos el martes" con una cita ya pasada.
R9. NINGÚN PRECIO INVENTADO (v3.17): si la respuesta trae un monto
    ("$650" o "650 pesos") que NO está en el Conocimiento del
    negocio, se desecha ENTERA y se contesta con la frase segura
    ("Déjame confirmarlo con el encargado y te aviso"). La IA no
    puede inventar precios: es la confianza del negocio. Solo se
    revisan montos escritos con $ o con "pesos" (un "600" suelto no
    se toca, para no confundir horas o direcciones). Sin la lista
    de precios conocidos, R9 no se aplica (compatibilidad con
    llamadas viejas).
R10. NO REPETIR LA RESPUESTA ENTERA (v3.20): si la respuesta es
    exactamente el mismo texto que el último mensaje del robot
    (el cliente repite la pregunta y la IA parrotea la respuesta
    anterior), se reemplaza por \"¿Te ayudo con algo más?\". R7 solo
    quitaba el cierre repetido; R10 cubre la repetición completa.
    Se compara sin acentos, en minúsculas y sin espacios de más.
R11. NINGÚN DESCUENTO INVENTADO (v3.20.2, valor exacto v3.20.3):
    si la respuesta promete un descuento o promoción ("te hago un
    20% de descuento") y el Conocimiento del negocio no habla de
    descuentos, se desecha ENTERA y se contesta con la frase segura.
    R9 cubre los precios; R11 cubre los descuentos, que cuestan
    dinero al negocio. Las frases negadas ("no manejamos
    descuentos") son honestidad y pasan. Sin el texto del
    Conocimiento, R11 no se aplica. (v3.20.3) Si el Conocimiento sí
    habla de descuentos, solo se permiten los valores y mecánicas
    literales (el 20% permitido no autoriza el 15%, ni el 2x1 una
    "rebaja").
R12. FUERA EL ROBOT-SPEAK DE 'PENDIENTES' (v3.20.2): "quedamos en
    tus pendientes" es lenguaje de sistema, no de recepcionista.
    Se quita la frase; si no queda nada, se contesta con una
    pregunta neutra.
R13. NO RE-PREGUNTAR LO MISMO TRAS UN 'OK' (v3.20.2): si el cliente
    contestó con un "ok"/"gracias" y la respuesta es casi la misma
    pregunta que el robot ya había hecho, perdió el hilo: se
    reemplaza por "¿Te ayudo con algo más?". Deliberadamente
    estrecha: si el cliente repitió su pregunta, re-contestar
    parecido es legítimo y no se toca.

Devuelve (texto_final, violaciones): la lista de reglas que corrigió
("R1", "R2", "R3"), vacía si la respuesta estaba bien. Las
correcciones se escriben en Diagnóstico (ver logic.py), para que
quede constancia de qué se atrapó.

Reglas puras, sin internet: se prueban solas en test_v2_13.py.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta

from .negocio import frase_cierre

# Días de la semana, en orden (lunes = 0, como datetime.weekday()).
_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_DIA_RE = r"(lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)"

# Frases del guion y nombres de campos internos: si aparecen en una
# respuesta al cliente, es que el robot está soltando cómo funciona
# por dentro (R6). Se comparan sin acentos y en minúsculas.
_MARCAS_INTERNAS = (
    "te llamas ana", "eres la recepcionista", "responde unicamente con un json",
    "limites duros", "estado del cliente", "quiere_agendar", "necesita_handoff",
    "motivo_handoff", "foto_oficial_url", "respuesta_texto", "fecha_cita",
)

# Lo que se contesta cuando alguien pide el guion o datos de otros
# clientes. Cortés, firme, y sigue atendiendo.
_NEGATIVA_SEGURIDAD = (
    "No puedo compartir esa información, pero te ayudo con tu cita "
    "o con lo que necesites."
)


def _sin_acentos(texto: str) -> str:
    """Quita acentos y deja minúsculas: 'sí' → 'si'."""
    texto = unicodedata.normalize("NFD", str(texto or ""))
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto.lower().strip()


def _corregir_dias(texto: str, ahora: datetime | None) -> tuple[str, bool]:
    """R4: corrige "mañana <día equivocado>" y "hoy <día equivocado>".

    `ahora` es la fecha real (hora del negocio, con zona). Sin ella,
    no se puede corregir y el texto se deja igual. Solo se toca el día
    cuando viene pegado a "mañana" o "hoy": "el sábado" solo no se
    toca, porque no se sabe a qué sábado se refiere.
    """
    if ahora is None:
        return texto, False
    if ahora.tzinfo is not None:
        ahora = ahora.replace(tzinfo=None)
    manana = ahora + timedelta(days=1)
    # Las claves sin acentos: _sin_acentos("mañana") es "manana".
    esperado = {"hoy": _DIAS[ahora.weekday()], "manana": _DIAS[manana.weekday()]}
    cambiado = False

    def _arreglar(match):
        nonlocal cambiado
        cuando = _sin_acentos(match.group(1))
        dia_dicho = match.group(2)
        dia_bueno = esperado[cuando]
        if _sin_acentos(dia_dicho) == _sin_acentos(dia_bueno):
            return match.group(0)
        cambiado = True
        # Si el día venía con mayúscula ("Mañana Viernes"), se respeta.
        if dia_dicho[:1].isupper():
            dia_bueno = dia_bueno.capitalize()
        return f"{match.group(1)} {dia_bueno}"

    texto = re.sub(
        rf"\b(hoy|mañana)\s+({_DIA_RE})\b", _arreglar, texto, flags=re.IGNORECASE
    )
    return texto, cambiado


def _quitar_etiquetas_internas(texto: str) -> tuple[str, bool]:
    """R5: quita notas internas de la hoja que se colaron en la respuesta.

    Se quitan los paréntesis que dicen "ficticia", "ejemplo" o "de
    prueba", y las palabras sueltas EJEMPLO / FICTICIA. Lo demás se
    queda: "(se descuenta si te haces el tratamiento)" es contenido
    real del negocio, no una nota interna.
    """
    original = texto
    texto = re.sub(
        r"\s*\([^)]*\b(ejemplo|fictici\w*|de prueba|no real|demo)\b[^)]*\)",
        "", texto, flags=re.IGNORECASE,
    )
    texto = re.sub(r"\s*\b(EJEMPLO|FICTICIA|FICTICIO)\b\.?", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\s+([.,])", r"\1", texto)
    texto = re.sub(r"\s{2,}", " ", texto).strip()
    return texto, texto != original


def _ultima_frase(texto: str) -> str:
    """La última frase de un texto (la que cierra el mensaje)."""
    frases = [p.strip() for p in re.split(r"(?<=[.!?])\s+", str(texto or "").strip())
              if p.strip()]
    return frases[-1] if frases else ""


def _quitar_cierre_repetido(texto: str, ultimo_robot: str) -> tuple[str, bool]:
    """R7: quita el cierre si es el mismo que el del último mensaje
    del robot. Solo se compara la última frase: si el robot cerró con
    "Quedamos a tus órdenes." y vuelve a cerrar igual, la segunda se
    quita. Si no queda nada, se pone una pregunta neutra."""
    if not ultimo_robot:
        return texto, False
    frases = [p.strip() for p in re.split(r"(?<=[.!?])\s+", texto.strip()) if p.strip()]
    if not frases:
        return texto, False
    if _sin_acentos(frases[-1]) != _sin_acentos(_ultima_frase(ultimo_robot)):
        return texto, False
    if len(frases) == 1:
        return "¿Te ayudo con algo más?", True
    return " ".join(frases[:-1]), True


def _contiene_filtracion(texto: str, telefono: str) -> bool:
    """R6: ¿La respuesta suelta el guion o datos de otros clientes?

    - Frases del guion o nombres de campos internos.
    - Un número de teléfono (10 dígitos o más) que no es el del
      cliente con el que se habla. El número del propio cliente sí
      puede aparecer (por ejemplo, en su confirmación de cita).
    """
    normal = _sin_acentos(texto)
    for marca in _MARCAS_INTERNAS:
        if marca in normal:
            return True
    propio = re.sub(r"\D", "", str(telefono or ""))
    for numero in re.findall(r"\d[\d\s\-()]{8,}\d", texto):
        digitos = re.sub(r"\D", "", numero)
        if len(digitos) >= 10 and digitos != propio and not propio.endswith(digitos) and not digitos.endswith(propio):
            return True
    return False

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
    if re.search(r"te (la )?(agendo|reservo)|agendarte|reservarte", bajo):
        return True
    if "agend" in bajo and "?" in texto:
        return True
    # (v3.20.2) "Te propongo tu cita para el martes a las 9:00" es una
    # oferta verbal tan clara como "¿Te la agendo?": sin esto, el
    # estado no veía la oferta y el robot la repetía. Solo cuenta
    # cuando la frase trae contexto de cita (día, hora o "cita"):
    # "te propongo que lo pienses" no es una oferta.
    if "te propongo" in bajo and any(
        p in bajo for p in (
            "cita", "lunes", "martes", "miercoles", "miércoles", "jueves",
            "viernes", "sabado", "sábado", "domingo", " a las ",
        )
    ):
        return True
    return False


# (v3.4.11) Frases que afirman una cita confirmada. Si el cliente NO
# tiene cita creada, el robot no puede decirlas: sería mentirle. En
# vivo dijo "ya estás apuntado" sin que existiera ninguna cita.
# (v3.10) Se suman las formas de "quedamos en que nos vemos...":
# en vivo (2026-11-22) el robot dijo "Quedamos en que nos vemos el
# martes a las 09:00" sin crear ninguna cita, y R8 no la atrapó.
_AFIRMACION_CITA_RE = re.compile(
    r"ya estás apuntado|ya quedó apuntado|quedaste apuntado|tu cita quedó"
    r"|cita confirmada|ya te agendé|ya quedó agendada|ya está agendada"
    r"|ya está apartado|ya quedó apartado"
    r"|quedamos en que|quedamos para|ya quedó para|quedó para el"
    r"|ya tienes tu cita|tu cita está|ya está tu cita|te espero el"
    r"|nos vemos el (lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)"
    r"|te veo el (lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)",
    re.IGNORECASE,
)


def _partir_oraciones(texto: str) -> list[str]:
    """Parte un texto en oraciones, sin perder los signos.

    "Hola. ¿Te agendo mañana a las 9:00 o el sábado? Avísame" →
    ["Hola.", "¿Te agendo mañana a las 9:00 o el sábado?", "Avísame"]
    """
    partes = re.split(r"(?<=[.!?])\s+", (texto or "").strip())
    return [p.strip() for p in partes if p.strip()]


# (v3.17) Montos escritos como "$600" / "$1,800" o "600 pesos".
_MONTO_RE = re.compile(r"\$\s*(\d[\d,]*)|(\d[\d,]*)\s*(?:pesos|mxn)\b", re.IGNORECASE)

# (v3.17) Respuesta segura cuando la IA inventa un precio: misma
# frase del guion para lo que no está en Conocimiento.
_RESPUESTA_PRECIO_INVENTADO = (
    "Déjame confirmarlo con el encargado y te aviso en un momento."
)


def _montos_en_texto(texto: str) -> list[int]:
    """Montos escritos con $ o con 'pesos' en un texto (v3.17)."""
    montos = []
    for m in _MONTO_RE.finditer(texto or ""):
        crudo = (m.group(1) or m.group(2) or "").replace(",", "").strip()
        if crudo.isdigit():
            montos.append(int(crudo))
    return montos


def precios_de_conocimiento(conocimiento: list[dict]) -> set[int]:
    """Precios conocidos del negocio, desde el Conocimiento (v3.17).

    Saca todos los montos escritos con $ o con 'pesos' de las filas
    de Conocimiento. Es la fuente de verdad contra la que R9 revisa
    que la IA no invente precios.
    """
    precios: set[int] = set()
    for fila in conocimiento or []:
        if not isinstance(fila, dict):
            continue
        for valor in fila.values():
            if isinstance(valor, str):
                precios.update(_montos_en_texto(valor))
    return precios


# (v3.20.2) R11: ningún descuento ni promoción inventada. R9 cubre
# los precios ($N); esto cubre las promesas de descuento ("te hago
# un 20% de descuento", "te aplico una promoción") que el guion
# prohíbe pero R9 no veía. Si el Conocimiento del negocio habla de
# descuentos/promociones, la IA puede mencionarlos; si no, cualquier
# promesa afirmativa se desecha entera, como R9.
_DESCUENTO_PALABRAS = (
    "descuento", "promocion", "rebaja", "precio especial",
    "oferta especial", "2x1",
)


def texto_conocimiento(conocimiento: list[dict]) -> str:
    """El Conocimiento como un solo texto, sin acentos (v3.20.2).

    Para que el revisor sepa qué temas conoce el negocio (por
    ejemplo, si habla de descuentos) sin pasar la lista entera.
    """
    partes = []
    for fila in conocimiento or []:
        if isinstance(fila, dict):
            for valor in fila.values():
                if isinstance(valor, str):
                    partes.append(valor)
    return _sin_acentos(" ".join(partes))


def _es_negacion_descuento(normal: str) -> bool:
    """¿La frase niega el descuento (en vez de ofrecerlo)?

    "No manejamos descuentos" / "sin promociones" / "nunca damos
    descuentos" son honestidad, no invento: se dejan pasar. Un
    "descuento" ofrecido ("te hago un descuento") no trae negación
    antes de la palabra y sí se atrapa.
    """
    if re.search(
        r"\b(no|sin|nunca)\b[^.]{0,30}(descuento|promocion|rebaja|"
        r"precio especial|oferta especial|2x1)",
        normal,
    ):
        return True
    # "Los descuentos no aplican" / "no se aplican descuentos".
    if "no aplic" in normal:
        return True
    return False


def _tiene_descuento_inventado(texto: str, texto_conoc: str) -> bool:
    """¿La respuesta promete un descuento/promoción que el negocio
    no conoce? (v3.20.2, R11; valor exacto v3.20.3).

    Solo se aplica cuando se pasa el texto del Conocimiento: sin él
    no hay con qué comparar y la regla no se aplica (compatibilidad
    con llamadas viejas, igual que R9). Una frase negada ("no
    manejamos descuentos") nunca es invento: es honestidad, y se
    deja pasar.

    Si el Conocimiento NO habla de descuentos, cualquier promesa
    afirmativa se desecha entera. Si SÍ habla, solo se permiten los
    valores y mecánicas que aparecen LITERALES en el Conocimiento
    (v3.20.3): "20% de descuento los martes" permite el 20%, no el
    15%; "2x1" permite el 2x1, no una "rebaja". La palabra genérica
    "descuento" sí se permite cuando el Conocimiento habla de
    descuentos (sin prometer un valor).
    """
    if not texto_conoc:
        return False
    _conoc_habla = (
        any(p in texto_conoc for p in _DESCUENTO_PALABRAS) or "%" in texto_conoc
    )
    if not _conoc_habla:
        # Sin descuentos conocidos: cualquier promesa es invento.
        for oracion in _partir_oraciones(texto):
            normal = _sin_acentos(oracion)
            if any(p in normal for p in _DESCUENTO_PALABRAS):
                if not _es_negacion_descuento(normal):
                    return True
            # Porcentaje suelto ("te hago un 20%"): sin % en el
            # Conocimiento, es un descuento inventado. Se excluye el
            # "100%" de énfasis ("100% segura"), que no es un descuento.
            for m in re.finditer(r"(\d[\d,]*)\s*%", normal):
                if m.group(1).replace(",", "") == "100":
                    continue
                if not _es_negacion_descuento(normal):
                    return True
        return False
    # El negocio sí maneja descuentos: solo valen los porcentajes
    # literales del Conocimiento.
    _permitidos_pct = {
        m.group(1).replace(",", "")
        for m in re.finditer(r"(\d[\d,]*)\s*%", texto_conoc)
    }
    for oracion in _partir_oraciones(texto):
        normal = _sin_acentos(oracion)
        if _es_negacion_descuento(normal):
            continue
        for m in re.finditer(r"(\d[\d,]*)\s*%", normal):
            if m.group(1).replace(",", "") == "100":
                continue
            if m.group(1).replace(",", "") not in _permitidos_pct:
                return True
        # Mecánicas de promoción (2x1, rebaja, oferta especial...):
        # solo si la frase está literal en el Conocimiento. La
        # palabra genérica "descuento" se permite cuando el
        # Conocimiento habla de descuentos (no promete un valor).
        for p in _DESCUENTO_PALABRAS:
            if p in normal and p not in texto_conoc and p != "descuento":
                return True
    return False


def _quitar_pendientes(texto: str) -> tuple[str, bool]:
    """R12: fuera el robot-speak de 'pendientes' (v3.20.2).

    El guion prohíbe "con tus pendientes" / "quedamos en tus
    pendientes": es lenguaje de sistema, no de recepcionista. Se
    quita la frase y se limpia el texto; si no queda nada, se
    contesta con una pregunta neutra. "Pendiente" en singular
    ("quedó pendiente tu cita") no se toca.
    """
    nuevo = re.sub(
        r"\b(en|con|de)?\s*(tus\s+)?pendientes\b", "", texto,
        flags=re.IGNORECASE,
    )
    nuevo = re.sub(r"\s+([.,;:])", r"\1", nuevo)
    nuevo = re.sub(r"\s{2,}", " ", nuevo).strip()
    if nuevo != texto.strip():
        # Si solo quedó puntuación ("Tus pendientes." → "."), no
        # hay respuesta: se contesta con una pregunta neutra.
        if not nuevo.strip(" .,:;"):
            return "¿Te ayudo con algo más?", True
        return nuevo, True
    return texto, False


# Respuestas cortas de cortesía del cliente: si tras una de estas el
# robot vuelve a soltar casi la misma pregunta de su último mensaje,
# perdió el hilo (R13).
_ACKS_CORTO = {
    "ok", "va", "sale", "gracias", "perfecto", "claro", "si", "dale",
    "bueno", "buenisimo", "excelente", "listo", "vale", "de acuerdo",
    "aja", "orale", "venga", "sip", "simon", "super", "buena", "buenas",
}


def _tokens(texto: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _sin_acentos(texto)))


def _es_casi_repetida(texto: str, ultimo_robot: str, ultimo_cliente: str) -> bool:
    """R13 (v3.20.2): el cliente acaba de contestar con un "ok" /
    "gracias" y la respuesta es casi la misma pregunta que el robot
    ya había hecho. Eso es perder el hilo: se reemplaza.

    Es deliberadamente estrecha: solo dispara cuando el cliente dio
    una respuesta corta de cortesía, y compara contra la ÚLTIMA
    FRASE del robot (la pregunta), no contra el mensaje entero: si
    el cliente repitió su pregunta, re-contestar parecido es
    legítimo y no se toca.
    """
    if not ultimo_robot or not ultimo_cliente:
        return False
    ack = _sin_acentos(ultimo_cliente).strip().strip(".,!¡¿? ")
    if ack not in _ACKS_CORTO:
        return False
    nuevo = _tokens(texto)
    viejo = _tokens(_ultima_frase(ultimo_robot))
    if not (3 <= len(nuevo) <= 14) or not viejo:
        return False
    return len(nuevo & viejo) / min(len(nuevo), len(viejo)) >= 0.8


def revisar_respuesta(
    texto: str,
    estado: dict | None = None,
    nombre: str = "",
    ahora: datetime | None = None,
    telefono: str = "",
    precios_conocidos: set[int] | None = None,
    texto_conocimiento: str = "",
) -> tuple[str, list[str]]:
    """Revisa una respuesta del agente y la corrige si viola una regla.

    `estado`: el dict de estado_cliente (etapa, ya_ofrecio_cita...).
    Si no viene, solo se aplica R3 (la de "ya cerramos").
    `ahora`: la fecha real, para R4 (corregir el día). Sin ella, R4
    no se aplica. `telefono`: el teléfono del cliente, para R6 (un
    número distinto es una filtración). `precios_conocidos`: los
    precios del Conocimiento, para R9 (ningún precio inventado);
    sin ellos, R9 no se aplica. `texto_conocimiento`: el
    Conocimiento como texto (ver texto_conocimiento()), para R11
    (ningún descuento inventado); sin él, R11 no se aplica.
    """
    estado = estado or {}
    etapa = str(estado.get("etapa", "") or "")
    oferta_pendiente = bool(estado.get("ya_ofrecio_cita"))
    texto = (texto or "").strip()
    violaciones: list[str] = []

    # R6 primero: si la respuesta filtra el guion o datos ajenos, se
    # desecha ENTERA. No se intenta arreglarla por partes: una
    # respuesta que suelta el prompt ya está comprometida.
    if _contiene_filtracion(texto, telefono):
        return _NEGATIVA_SEGURIDAD, ["R6"]

    # R9 (v3.17): ningún precio inventado. Si la respuesta trae un
    # monto que no está en el Conocimiento, se desecha ENTERA (como
    # R6): un precio falso es lo que más confianza rompe. Se
    # contesta con la frase segura del guion.
    if precios_conocidos is not None:
        if any(m not in precios_conocidos for m in _montos_en_texto(texto)):
            return _RESPUESTA_PRECIO_INVENTADO, ["R9"]

    # R11 (v3.20.2): ningún descuento ni promoción inventada. Si el
    # Conocimiento no habla de descuentos y la respuesta los ofrece
    # ("te hago un 20% de descuento"), se desecha ENTERA, como R9:
    # un descuento falso cuesta dinero al negocio. Las frases
    # negadas ("no manejamos descuentos") son honestidad y pasan.
    if _tiene_descuento_inventado(texto, texto_conocimiento):
        return _RESPUESTA_PRECIO_INVENTADO, ["R11"]

    # R10 (v3.20): no repetir la respuesta entera. Si el texto es
    # exactamente el mismo que el último mensaje del robot (la IA
    # parroteó la respuesta anterior), se reemplaza por una pregunta
    # neutra. R7 (abajo) solo quita el cierre repetido; esto cubre
    # la repetición completa.
    _ultimo_robot = str(estado.get("ultimo_mensaje_robot", "") or "")
    if texto and _ultimo_robot:
        _norm_nuevo = re.sub(r"\s+", " ", _sin_acentos(texto)).strip().lower()
        _norm_viejo = re.sub(r"\s+", " ", _sin_acentos(_ultimo_robot)).strip().lower()
        if _norm_nuevo and _norm_nuevo == _norm_viejo:
            texto = "¿Te ayudo con algo más?"
            violaciones.append("R10")

    # R13 (v3.20.2): el cliente contestó con un "ok"/"gracias" y la
    # respuesta es casi la misma pregunta que el robot ya había
    # hecho: perdió el hilo. Se reemplaza por una pregunta neutra.
    # Deliberadamente estrecha (ver _es_casi_repetida): si el
    # cliente repitió su pregunta, re-contestar parecido es legítimo.
    if _es_casi_repetida(
        texto,
        _ultimo_robot,
        str(estado.get("ultimo_mensaje_cliente", "") or ""),
    ):
        texto = "¿Te ayudo con algo más?"
        violaciones.append("R13")

    # R3: la frase de cierre, se cambie lo que se cambie después.
    if _CERRAMOS_RE.search(texto):
        texto = _CERRAMOS_RE.sub(frase_cierre(), texto)
        violaciones.append("R3")

    # R4: el día correcto (mañana/hoy con el día real).
    texto, cambio_dia = _corregir_dias(texto, ahora)
    if cambio_dia:
        violaciones.append("R4")

    # R5: fuera las etiquetas internas de la hoja.
    texto, cambio_etiqueta = _quitar_etiquetas_internas(texto)
    if cambio_etiqueta:
        violaciones.append("R5")

    # R12 (v3.20.2): fuera el robot-speak de "pendientes" ("quedamos
    # en tus pendientes"): es lenguaje de sistema, no de
    # recepcionista. El guion ya lo prohíbe; esto lo atrapa cuando
    # la IA lo suelta igual.
    texto, cambio_pendientes = _quitar_pendientes(texto)
    if cambio_pendientes:
        violaciones.append("R12")

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

    # R7 al final: no cerrar con la misma frase del último mensaje.
    texto, cierre_repetido = _quitar_cierre_repetido(
        texto, str(estado.get("ultimo_mensaje_robot", "") or ""))
    if cierre_repetido:
        violaciones.append("R7")

    # R8 (v3.4.11): nunca afirmar una cita confirmada si el cliente
    # NO tiene cita creada. Si la respuesta solo afirma eso, se
    # reemplaza por la oferta real (confirmar con botones).
    # (v3.10) Mira la cita a FUTURO: una cita ya pasada no justifica
    # afirmar una cita nueva (en vivo, una cita de hace 3 días dejaba
    # pasar "quedamos en que nos vemos..."). Si el estado no trae
    # tiene_cita_futura (tests viejos), cae al comportamiento previo.
    _tiene_futura = estado.get("tiene_cita_futura", estado.get("tiene_cita"))
    if not _tiene_futura and _AFIRMACION_CITA_RE.search(texto):
        quedan = [o for o in _partir_oraciones(texto)
                  if not _AFIRMACION_CITA_RE.search(o)]
        if quedan:
            texto = " ".join(quedan).strip()
        else:
            texto = "¿Te la confirmo con botones para dejarla lista?"
        violaciones.append("R8")

    return texto, violaciones
