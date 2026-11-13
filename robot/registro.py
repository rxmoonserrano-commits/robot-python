"""Registro del robot: un solo lugar para los mensajes de diagnóstico.

Antes cada archivo hacía print() a su manera (22 prints sueltos), sin
hora ni nivel, y en Render se mezclaban con todo. Ahora hay tres
niveles y un formato único: info (todo bien), aviso (algo falta o
algo se degradó, pero el robot sigue), error (algo falló y hay que
mirarlo). El formato es "HH:MM:SS [robot] mensaje", para que en los
registros de Render se lea de un vistazo.

Uso: from .registro import info, aviso, error
"""

from __future__ import annotations

import logging

logger = logging.getLogger("robot")


def configurar() -> None:
    """Prende el formato del registro (una sola vez, al arrancar)."""
    if not logger.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [robot] %(message)s",
            datefmt="%H:%M:%S",
        )


def info(mensaje: str) -> None:
    logger.info(mensaje)


def aviso(mensaje: str) -> None:
    logger.warning(mensaje)


def error(mensaje: str) -> None:
    logger.error(mensaje)
