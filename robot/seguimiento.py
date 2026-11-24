"""Seguimiento proactivo (v3.20.7): clientes que preguntaron y no agendaron.

Hoy el robot solo deja borradores de correo semanales para esos
clientes. Este módulo implementa el mecanismo de seguimiento por
WhatsApp, detrás de un interruptor APAGADO por defecto
(Configuración: `seguimiento_proactivo` = SI/NO, vacío = NO).

Reglas duras:
- Sin interruptor en SI, no se manda NADA (ni se leen clientes).
- Los mensajes proactivos de WhatsApp requieren una PLANTILLA de
  Meta aprobada (la aprobación es paso de Jose; ver
  PLANTILLA-SEGUIMIENTO-META.md) y el opt-in del cliente
  (Consentimiento_mensajes = SI en Clientes).
- Solo se sigue a clientes que preguntaron y quedaron a medias:
  estatus en conversación/calificado, sin cita, sin cerrar, sin
  handoff, con robot activo, inactivos desde hace días, y que no
  hayan recibido ya un seguimiento.
- Mejor esfuerzo: si una plantilla falla, se cuenta y se sigue con
  el siguiente; nunca tira el job.

El job corre cada hora desde app.py (id="seguimiento"), igual que
los recordatorios.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from . import negocio
from .logic import _a_hora_local, _parse_fecha_iso


def seguimiento_activo() -> bool:
    """¿El negocio tiene encendido el seguimiento proactivo?

    Apagado por defecto (v3.20.7): solo un SI explícito en
    Configuración (`seguimiento_proactivo`) lo enciende.
    """
    return negocio.interruptor("seguimiento_proactivo", "NO") == "SI"


def _consentimiento_si(cliente: dict) -> bool:
    """¿El cliente aceptó mensajes? (Consentimiento_mensajes = SI)."""
    valor = str(cliente.get("Consentimiento_mensajes", "") or "").strip().upper()
    return valor in {"SI", "SÍ", "TRUE", "1", "YES", "SE"}


def clientes_para_seguimiento(deps, ahora: datetime, dias_min: int = 3,
                              maximo: int = 20) -> list[dict]:
    """Clientes que preguntaron, no agendaron y llevan días sin escribir.

    Filtros (todos deben cumplirse):
    - estatus en conversación o calificado (no agendado/cancelado);
    - sin fecha_cita;
    - proxima_accion distinta de "cerrada";
    - handoff distinto de "si";
    - robot_activo distinto de "NO";
    - Consentimiento_mensajes = SI;
    - su último mensaje (Conversaciones) es anterior a `dias_min`
      días respecto a `ahora`;
    - no tiene ya un mensaje con motivo "seguimiento" en su historial
      (para no perseguirlo dos veces).

    Si no se puede leer la hoja de Clientes o el historial de un
    cliente, ese cliente se salta (mejor esfuerzo).
    """
    try:
        clientes = deps.leer_clientes() or []
    except Exception:
        return []
    elegibles: list[dict] = []
    # Límite en hora local naive, igual que las fechas del historial.
    try:
        ahora_local = _a_hora_local(ahora).replace(tzinfo=None)
    except Exception:
        ahora_local = ahora.replace(tzinfo=None) if getattr(ahora, "tzinfo", None) else ahora
    limite = ahora_local - timedelta(days=dias_min)
    for cliente in clientes:
        try:
            telefono = str(cliente.get("telefono", "") or "").strip()
            if not telefono:
                continue
            estatus = str(cliente.get("estatus", "") or "").strip().lower()
            if estatus not in {"en conversacion", "calificado"}:
                continue
            if str(cliente.get("fecha_cita", "") or "").strip():
                continue
            if str(cliente.get("proxima_accion", "") or "").strip().lower() == "cerrada":
                continue
            if str(cliente.get("handoff", "") or "").strip().lower() == "si":
                continue
            if str(cliente.get("robot_activo", "") or "").strip().upper() == "NO":
                continue
            if not _consentimiento_si(cliente):
                continue
            historial = deps.leer_historial(telefono) or []
            if not historial:
                continue
            if any(str(f.get("motivo", "") or "").strip().lower() == "seguimiento"
                   for f in historial):
                continue
            ultima = _parse_fecha_iso(str(historial[-1].get("fecha", "") or ""))
            if ultima is None:
                continue
            # Se compara en hora local naive (la misma que usa
            # atender_mensaje): _a_hora_local devuelve con zona, así
            # que se le quita la zona después de convertir.
            try:
                ultima_local = _a_hora_local(ultima).replace(tzinfo=None)
            except Exception:
                ultima_local = ultima.replace(tzinfo=None) if ultima.tzinfo else ultima
            if ultima_local > limite:
                continue
            elegibles.append(cliente)
            if len(elegibles) >= maximo:
                break
        except Exception:
            continue
    return elegibles


def enviar_seguimientos_pendientes(deps, ahora: datetime | None = None,
                                   dias_min: int = 3, maximo: int = 20) -> dict:
    """Manda el seguimiento a los clientes elegibles. Devuelve conteos.

    Sin el interruptor en SI devuelve {"enviados": 0, "fallidos": 0}
    sin tocar nada. Con el interruptor en SI pero sin plantilla
    aprobada en Meta, los envíos fallan (Meta rechaza) y se cuentan
    como fallidos: por eso la plantilla es paso de Jose.
    """
    if not seguimiento_activo():
        return {"enviados": 0, "fallidos": 0}
    if ahora is None:
        ahora = datetime.now()
    cfg = negocio.configuracion()
    plantilla = str(cfg.get("plantilla_seguimiento", "") or "").strip() \
        or "seguimiento_no_agendo"
    idioma = str(cfg.get("idioma_plantilla", "") or "").strip() or "es_MX"
    enviados = 0
    fallidos = 0
    for cliente in clientes_para_seguimiento(deps, ahora, dias_min, maximo):
        telefono = str(cliente.get("telefono", "") or "").strip()
        nombre = str(cliente.get("nombre", "") or "").strip() or "hola"
        motivo = str(cliente.get("motivo", "") or "").strip() \
            or str(cliente.get("intereses", "") or "").strip() or "tu consulta"
        try:
            deps.enviar_plantilla(telefono, plantilla, idioma, [nombre, motivo])
            enviados += 1
            try:
                deps.registrar_conversacion(
                    ahora.isoformat(), telefono, "robot",
                    f"(seguimiento proactivo: {plantilla})", "si", "seguimiento")
            except Exception:
                pass
        except Exception:
            fallidos += 1
    return {"enviados": enviados, "fallidos": fallidos}
