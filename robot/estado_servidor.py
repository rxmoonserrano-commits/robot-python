"""Estado del servidor en memoria (v3.4): la ventana para ver si el
robot está vivo por dentro, sin entrar a Render.

El 13 de noviembre de 2026 el robot dejó de contestar y no había
nada que mirar: /health decía ok (solo dice que el servidor web
responde), la hoja no tenía filas nuevas y los hilos de segundo plano
no dejaban rastro. Con esto, GET /estado dice: versión, cuánto lleva
prendido, si el chequeo de salud terminó, cuántos webhooks llegaron,
cuántos lotes se procesaron y cuántos fallaron, y cuál fue el último
error. Sin teléfonos ni datos de clientes: solo números.

Puro (sin internet): se prueba solo.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

_ARRANQUE = time.monotonic()
_ARRANQUE_ISO = datetime.now(timezone.utc).isoformat()

_CANDADO = threading.Lock()
_ESTADO: dict = {
    "webhooks_recibidos": 0,
    "lotes_iniciados": 0,
    "lotes_terminados": 0,
    "lotes_fallidos": 0,
    "ultimo_webhook_iso": "",
    "ultimo_lote_iso": "",
    "ultimo_error": "",
    "salud_lista": False,
    "salud_iso": "",
}


def contar_webhook() -> None:
    """Llegó un mensaje al webhook (antes de procesarlo)."""
    with _CANDADO:
        _ESTADO["webhooks_recibidos"] += 1
        _ESTADO["ultimo_webhook_iso"] = datetime.now(timezone.utc).isoformat()


def contar_lote_inicio() -> None:
    """Empezó a procesarse un lote."""
    with _CANDADO:
        _ESTADO["lotes_iniciados"] += 1
        _ESTADO["ultimo_lote_iso"] = datetime.now(timezone.utc).isoformat()


def contar_lote_fin(ok: bool, error: str = "") -> None:
    """Terminó un lote: bien (ok=True) o con error."""
    with _CANDADO:
        if ok:
            _ESTADO["lotes_terminados"] += 1
        else:
            _ESTADO["lotes_fallidos"] += 1
            _ESTADO["ultimo_error"] = error[:300]


def marcar_salud_lista() -> None:
    """El chequeo de salud del arranque terminó (bien o mal)."""
    with _CANDADO:
        _ESTADO["salud_lista"] = True
        _ESTADO["salud_iso"] = datetime.now(timezone.utc).isoformat()


def foto() -> dict:
    """Foto del estado, sin teléfonos ni datos de clientes."""
    with _CANDADO:
        copia = dict(_ESTADO)
    copia["arranque_iso"] = _ARRANQUE_ISO
    copia["prendido_segundos"] = round(time.monotonic() - _ARRANQUE, 1)
    return copia
