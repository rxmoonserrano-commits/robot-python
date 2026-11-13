"""El estado del cliente, calculado por código (v2.13).

El problema que corrige: antes, la IA tenía que DEDUCIR en qué iba la
conversación leyendo 8 filas crudas de la hoja (fechas, teléfonos,
motivos internos). Cada mensaje era un arranque en frío y el modelo
adivinaba: si ya le ofreció una cita, si el cliente solo saludó, si ya
tiene cita. Adivinar es justo lo que producía los errores que Jose
veía en vivo (ofrecer la cita dos veces, ofrecerla a un simple saludo).

Ahora el código calcula el estado ANTES de llamar a la IA y se lo pasa
como datos, no como prosa. La IA deja de deducir y se pone a decidir.

El estado tiene:
- etapa: en qué va la conversación.
  - "saludo": el cliente solo saludó y aún no se sabe qué quiere.
  - "pregunto": preguntó algo (precio, servicio, horario) sin cita ofrecida.
  - "oferta_pendiente": ya se le ofreció una cita y no ha contestado.
  - "agendado": ya tiene cita creada (estatus agendado en Clientes).
  - "nuevo": no hay historial (nunca ha escrito).
- ya_ofrecio_cita: True si hay una propuesta pendiente.
- oferta_fecha_bonita: la fecha ofrecida, en bonito ("viernes 13 de
  noviembre a las 09:00"), o "".
- ultimo_mensaje_robot: el último texto que el robot le mandó, o "".
- ultimo_mensaje_cliente: el último texto del cliente, o "".
- tiene_cita: True si en Clientes tiene fecha_cita y estatus agendado.
- nombre: el nombre que se conoce del cliente, o "".
- mensajes: cuántos mensajes hay en el historial.

Reglas puras, sin internet: se prueban solas en test_v2_13.py.
"""

from __future__ import annotations

import re
import unicodedata

_SALUDOS = (
    "hola", "buenas", "buenos dias", "buenas tardes", "buenas noches",
    "que tal", "qué tal", "ola", "buen dia", "buen día", "hey",
)


def _sin_acentos(texto: str) -> str:
    """Quita acentos y deja minúsculas: 'sí' → 'si'."""
    texto = unicodedata.normalize("NFD", str(texto or ""))
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto.lower().strip()


def _es_solo_saludo(texto: str) -> bool:
    """¿El mensaje es solo un saludo, sin ninguna pregunta ni pedido?

    "hola", "buenas noches", "hola buenas tardes" → sí.
    "hola, ¿cuánto cuesta la limpieza?" → no (ya pide algo).
    "buenas noches, quiero una cita" → no.
    """
    normal = re.sub(r"[^a-z0-9 ]+", "", _sin_acentos(texto))
    normal = re.sub(r"\s+", " ", normal).strip()
    if not normal:
        return False
    palabras = normal.split()
    if len(palabras) > 4:
        return False
    if normal in _SALUDOS:
        return True
    if palabras[0] in ("hola", "buenas", "buenos", "ola", "hey") and len(palabras) <= 3:
        return True
    if normal in ("buenas tardes", "buenas noches", "buenos dias", "buen dia"):
        return True
    return False


def estado_cliente(
    historial: list[dict] | None,
    propuesta: dict | None,
    cliente: dict | None,
    nombre: str = "",
) -> dict:
    """Calcula el estado del cliente desde el historial, la propuesta y su fila.

    `historial`: filas de Conversaciones de ese teléfono, en orden
    (las viejas primero, como las devuelve leer_historial).
    `propuesta`: la propuesta pendiente de _CITAS_PENDIENTES, o None.
    `cliente`: su fila de Clientes, o None si no está registrado.
    """
    filas = list(historial or [])
    ultimo_robot = ""
    ultimo_cliente = ""
    for fila in reversed(filas):
        if not ultimo_robot and str(fila.get("quien_hablo", "")) == "robot":
            ultimo_robot = str(fila.get("mensaje", "") or "")
        if not ultimo_cliente and str(fila.get("quien_hablo", "")) == "cliente":
            ultimo_cliente = str(fila.get("mensaje", "") or "")
        if ultimo_robot and ultimo_cliente:
            break

    cliente = cliente or {}
    tiene_cita = bool(
        str(cliente.get("fecha_cita", "") or "").strip()
        and str(cliente.get("estatus", "") or "").strip().lower() == "agendado"
    )
    nombre_final = nombre or str(cliente.get("nombre", "") or "")

    if tiene_cita:
        etapa = "agendado"
    elif propuesta:
        etapa = "oferta_pendiente"
    elif not filas:
        etapa = "nuevo"
    elif _es_solo_saludo(ultimo_cliente):
        # Solo saludó y no pidió nada todavía: no se sabe qué quiere,
        # aunque ya haya hablado antes con el robot. La oferta viene
        # cuando ya se sabe qué quiere, no con el saludo.
        etapa = "saludo"
    else:
        etapa = "pregunto"

    return {
        "etapa": etapa,
        "ya_ofrecio_cita": bool(propuesta),
        "oferta_fecha_bonita": str((propuesta or {}).get("fecha_bonita", "") or ""),
        "ultimo_mensaje_robot": ultimo_robot,
        "ultimo_mensaje_cliente": ultimo_cliente,
        "tiene_cita": tiene_cita,
        "nombre": nombre_final,
        "mensajes": len(filas),
    }
