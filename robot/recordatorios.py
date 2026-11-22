"""Recordatorios automáticos (v3.12, Sereno función 03).

~24 h antes de la cita, el robot manda la plantilla aprobada de
WhatsApp (nombre + fecha/hora) y marca Recordatorio_enviado en el
espejo de Citas. Si el paciente confirma por texto ("confirmo"),
queda registrado en las Notas y cuenta en el reporte semanal
(ver logic._registrar_confirmacion_asistencia).

Sin plantilla aprobada en Meta, el envío falla y queda en
Diagnóstico: nunca silencioso (Sereno: "nunca perder silenciosamente
un mensaje"). El interruptor es `recordatorios` en Configuración
(SI/NO); sin paquete, sigue la matriz de paquetes (básico no tiene
agenda, así que no manda recordatorios).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import negocio
from .logic import _a_hora_local, _parse_fecha_iso, formatear_cita_bonita


def _nombre_de_notas(notas: str) -> str:
    """El nombre del paciente desde las Notas del espejo ('Paciente: X')."""
    texto = str(notas or "")
    if "Paciente:" in texto:
        return texto.split("Paciente:", 1)[1].split("|")[0].strip() or "Paciente"
    return "Paciente"


def enviar_recordatorios_pendientes(deps, ahora: datetime | None = None) -> dict:
    """Manda los recordatorios de las citas en la ventana ~24 h.

    Best-effort total: un fallo en una cita no frena las demás ni
    rompe nada. Devuelve {"enviados": n, "fallidos": m}.
    """
    ahora = ahora or datetime.now(timezone.utc)
    if not negocio.funcion_activa("recordatorios"):
        return {"enviados": 0, "fallidos": 0, "motivo": "recordatorios apagados"}
    cfg = negocio.configuracion()
    plantilla = (cfg.get("plantilla_recordatorio") or "recordatorio_cita").strip()
    idioma = (cfg.get("idioma_plantilla") or "es_MX").strip()
    local_ahora = _a_hora_local(ahora)
    desde = local_ahora + timedelta(hours=20)
    hasta = local_ahora + timedelta(hours=28)
    try:
        espejo = deps.leer_citas_espejo() or []
    except Exception:
        espejo = []
    enviados = 0
    fallidos = 0
    for fila in espejo:
        try:
            if str(fila.get("Estado", "") or "").strip() != "Confirmada":
                continue
            enviado = str(fila.get("Recordatorio_enviado", "") or "").strip()
            if enviado and enviado != "-":
                continue
            fecha_dia = str(fila.get("Fecha", "") or "")[:10]
            hora = str(fila.get("Hora_inicio", "") or "").strip()
            telefono = str(fila.get("Teléfono", "") or "").strip()
            if not fecha_dia or not hora or not telefono:
                continue
            inicio = _parse_fecha_iso(f"{fecha_dia}T{hora}:00")
            if inicio is None:
                continue
            if not (desde <= _a_hora_local(inicio) <= hasta):
                continue
            nombre = _nombre_de_notas(fila.get("Notas", ""))
            try:
                fecha_bonita = formatear_cita_bonita(f"{fecha_dia}T{hora}:00")
            except (ValueError, TypeError):
                fecha_bonita = f"{fecha_dia} {hora}"
            try:
                deps.enviar_plantilla(telefono, plantilla, idioma, [nombre, fecha_bonita])
            except Exception as exc:
                fallidos += 1
                try:
                    deps.registrar_diagnostico(
                        ahora.isoformat(), "whatsapp", "FALLO",
                        f"Recordatorio no enviado (plantilla {plantilla}): {exc}",
                        telefono, "recordatorios",
                    )
                except Exception:
                    pass
                continue
            try:
                deps.actualizar_cita_espejo(
                    telefono, fecha_dia,
                    recordatorio_enviado=ahora.strftime("%Y-%m-%d"),
                )
            except Exception:
                pass
            enviados += 1
        except Exception:
            continue
    return {"enviados": enviados, "fallidos": fallidos}
