"""Simula dos escenarios prioritarios con Gemini real y agenda ficticia.

Uso: python simular_gemini_prioritarios.py
GEMINI_API_KEY debe estar en el entorno o en .env. No envía WhatsApp,
correos ni crea eventos reales: las dependencias de negocio son falsas.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

from test_conversaciones_doradas import DIA, DepsDoradas, correr, fila, no_tiene, tiene
from robot.config import settings


def main() -> int:
    if not os.environ.get("GEMINI_API_KEY"):
        print("NO EJECUTADO: falta GEMINI_API_KEY en .env o en el entorno.")
        return 2
    if not settings.gemini_model:
        print("NO EJECUTADO: falta GEMINI_MODEL (modelo habilitado para tu cuenta).")
        return 2
    casos = [
        ("b: fecha aislada fuera de horario", {
            "nombre": "B", "historial": [fila("cliente", "quiero una cita de limpieza"),
                                             fila("robot", "¿Qué día y hora te acomodan?")],
            "mensaje": "para pasado mañana a las 7 de la tarde", "ahora": DIA,
            "nombre_cliente": "",
        }),
        ("c: cliente que regresa", {
            "nombre": "C", "historial": [fila("cliente", "agendé una limpieza"),
                                             fila("robot", "Tu cita quedó registrada.")],
            "mensaje": "hola buenas tardes", "ahora": DIA,
            "cliente": {"nombre": "Jose Ramon", "motivo": "Limpieza dental",
                        "fecha_cita": "2026-11-06T09:00:00-07:00", "estatus": "agendado"},
        }),
    ]
    fallos = 0
    for etiqueta, argumentos in casos:
        try:
            if etiqueta.startswith("b"):
                with patch.object(DepsDoradas, "hora_libre", side_effect=lambda fecha: str(fecha)[:16] in {"2026-11-14T10:00", "2026-11-16T09:00"}):
                    deps, resultado, texto = correr(**argumentos)
            else:
                deps, resultado, texto = correr(**argumentos)
            print(f"\n{etiqueta}\nRespuesta exacta: {texto!r}")
            print(f"Botones: {[botones for _, _, botones in deps.botones_enviados]!r}")
            if etiqueta.startswith("b"):
                ok = (resultado.get("cita_propuesta") is True
                      and tiene(texto, "lunes 16", "lunes a las 9", "lunes a las 09")
                      and no_tiene(texto, "domingo a las 19", "domingo a las 7 de la tarde"))
            else:
                ok = (tiene(texto, "Jose", "José")
                      and no_tiene(texto, "tu nombre completo", "me das tu nombre", "cómo te llamas"))
            print("VERDE" if ok else "ROJO: no cumplió la comprobación")
            fallos += not ok
        except Exception as exc:
            print(f"ROJO: {type(exc).__name__}: {exc}")
            fallos += 1
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
