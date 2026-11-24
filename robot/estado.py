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
- ya_ofrecio_cita: True si hay una propuesta pendiente, o si el
  ÚLTIMO mensaje del robot ofreció una cita (v3.1). El agente a
  veces ofrece en el texto sin marcar quiere_agendar: en ese caso
  no hay propuesta guardada, pero la oferta sí existe, y el revisor
  tiene que saberlo para no repetirla.
- oferta_fecha_bonita: la fecha ofrecida, en bonito ("viernes 13 de
  noviembre a las 09:00"), o "".
- ultimo_mensaje_robot: el último texto que el robot le mandó, o "".
- ultimo_mensaje_cliente: el último texto del cliente, o "".
- tiene_cita: True si en Clientes tiene fecha_cita y estatus agendado,
  y (si se pasa "ahora") la cita es de hoy en adelante: una cita ya
  pasada no cuenta como vigente (v3.11).
- nombre: el nombre que se conoce del cliente, o "".
- mensajes: cuántos mensajes hay en el historial.
- ciclo_vida (v3.20.7): el estado explícito de la conversación, para
  que la IA no tenga que deducirlo: "nueva" (nunca ha escrito),
  "activa" (conversación viva), "esperando" (hay una oferta pendiente
  y se espera su respuesta), "agendado" (ya tiene cita), "en_handoff"
  (el último mensaje del robot fue un pase a persona) o "cerrada"
  (la conversación quedó resuelta y marcada como cerrada).

Reglas puras, sin internet: se prueban solas en test_v2_13.py.
"""

from __future__ import annotations

import re
import unicodedata

from .revision import _es_oferta

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
    # (v3.4.9) Un saludo con intención no es solo un saludo: "hola
    # quiero agendar" pide algo, no solo saluda. Sin esto, la etapa
    # salía "saludo" y el revisor quitaba la oferta que el cliente sí
    # pidió.
    _INTENCION = (
        "agendar", "cita", "precio", "cuesta", "quiero", "necesito",
        "horario", "donde", "informacion", "info", "reserva", "reservar",
        "servicio", "costo",
    )
    if any(p in normal for p in _INTENCION):
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
    ahora=None,
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
    # (v3.11) Una cita ya pasada no es vigente: si se conoce "ahora",
    # la cita solo cuenta si es de hoy en adelante. Sin esto, una cita
    # vieja hacía que el agente ofreciera "cambiar tus horas" por una
    # cita que ya pasó (visto en vivo 2026-11-22). Fecha rota: se
    # mantiene el criterio anterior (mejor no bloquear).
    if tiene_cita and ahora is not None:
        try:
            from datetime import datetime as _dt
            _f = _dt.fromisoformat(
                str(cliente.get("fecha_cita", "")).strip().replace("Z", "+00:00")
            )
            _hoy = ahora.date() if hasattr(ahora, "date") else ahora
            tiene_cita = _f.date() >= _hoy
        except Exception:
            pass
    # (v3.20.9) El nombre confirmado en Clientes (columna B) manda
    # sobre el de perfil de WhatsApp: si el cliente confirmó su
    # nombre, es con ese con el que se le trata.
    nombre_final = str(cliente.get("nombre", "") or "").strip() or (nombre or "")

    # (v3.1) La oferta verbal: el último mensaje del robot ofreció
    # una cita en el texto ("¿Te la agendo para mañana a las 9:00?"),
    # aunque el agente no haya marcado quiere_agendar y no haya
    # propuesta guardada. Sin esto, el robot ofrecía la cita tres
    # veces seguidas y el revisor no tenía nada que quitar: el estado
    # decía que no había oferta, porque solo miraba la propuesta.
    # La confirmación ("Tu cita quedó...") y el "dame un momento" no
    # son ofertas: _es_oferta los deja pasar.
    oferta_verbal = bool(ultimo_robot) and _es_oferta(ultimo_robot)
    ya_ofrecio = bool(propuesta) or oferta_verbal

    if tiene_cita:
        etapa = "agendado"
    elif ya_ofrecio:
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

    # (v3.20.7) Ciclo de vida explícito: la IA ya no tiene que
    # deducir en qué va la conversación. Se calcula aquí, con los
    # mismos datos de siempre. Orden de prioridad: cerrada manda
    # (quedó resuelta), luego en_handoff (una persona lo atiende),
    # luego esperando (hay una oferta y se espera respuesta),
    # luego agendado, y al final nueva/activa según el historial.
    _prox = str(cliente.get("proxima_accion", "") or "").strip().lower()
    _ultimo_motivo_robot = ""
    for fila in reversed(filas):
        if str(fila.get("quien_hablo", "")) == "robot":
            _ultimo_motivo_robot = str(fila.get("motivo", "") or "").strip().lower()
            break
    if _prox == "cerrada":
        ciclo_vida = "cerrada"
    elif _ultimo_motivo_robot == "handoff":
        ciclo_vida = "en_handoff"
    elif ya_ofrecio:
        ciclo_vida = "esperando"
    elif tiene_cita:
        ciclo_vida = "agendado"
    elif not filas:
        ciclo_vida = "nueva"
    else:
        ciclo_vida = "activa"

    return {
        "etapa": etapa,
        "ciclo_vida": ciclo_vida,
        "ya_ofrecio_cita": ya_ofrecio,
        "oferta_fecha_bonita": str((propuesta or {}).get("fecha_bonita", "") or ""),
        "ultimo_mensaje_robot": ultimo_robot,
        "ultimo_mensaje_cliente": ultimo_cliente,
        "tiene_cita": tiene_cita,
        "nombre": nombre_final,
        "mensajes": len(filas),
    }
