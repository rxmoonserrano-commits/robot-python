"""Trabajador serial para el buzón persistente de WhatsApp.

La recepción se confirma después de escribir en Sheets. Este trabajador
consume de a una conversación, espera el plazo de agrupación y marca cada
lote terminado únicamente después de que el callback retorna sin error.
"""
from __future__ import annotations

import math
import threading
import time
from datetime import datetime, timezone
from typing import Callable

from .registro import aviso


class TrabajadorCola:
    def __init__(self, cola, procesar: Callable, espera_segundos: float = 15,
                 reintento_segundos: float = 10, reloj: Callable = time.monotonic):
        self.cola = cola
        self.procesar = procesar
        self.espera = max(0.0, espera_segundos)
        self.reintento = max(1.0, reintento_segundos)
        self.reloj = reloj
        self.despertar = threading.Event()
        self.detener = threading.Event()
        self._demorados: dict[str, float] = {}

    def paso(self, ahora: datetime | None = None) -> bool:
        """Procesa como máximo un lote. True indica que procesó uno."""
        ahora = ahora or datetime.now(timezone.utc)
        actual = self.reloj()
        self._demorados = {t: vencimiento for t, vencimiento in self._demorados.items()
                           if vencimiento > actual}
        filas = self.cola.pendientes(limite=100, excluir_telefonos=set(self._demorados))
        if not filas:
            return False
        # Buscamos un teléfono listo sin bloquear a los demás durante su
        # ventana de agrupación. Nunca se altera el orden dentro de un chat.
        telefonos = list(dict.fromkeys(str(f[2]["mensaje"].get("from") or "") for f in filas))
        for telefono in telefonos:
            mensajes = [f for f in filas if str(f[2]["mensaje"].get("from") or "") == telefono]
            # Solo ordenar por timestamp cuando TODOS lo tienen válido.
            # Si falta alguno, no sabemos dónde ubicarlo temporalmente:
            # preservamos el orden de recepción (filas de la hoja), sin
            # saltar un texto anterior para procesar primero un botón.
            tiempos = []
            for fila in mensajes:
                try:
                    valor = float(fila[2]["mensaje"].get("timestamp"))
                    if not math.isfinite(valor) or valor <= 0:
                        raise ValueError("timestamp inválido")
                    tiempos.append(valor)
                except (TypeError, ValueError, OverflowError):
                    tiempos = []
                    break
            if tiempos:
                mensajes = [fila for _, fila in sorted(
                    zip(tiempos, mensajes), key=lambda par: (par[0], par[1][0]))]
            lote = []
            for fila in mensajes:
                tipo = fila[2]["mensaje"].get("type", "")
                if tipo == "interactive":
                    if not lote:
                        lote.append(fila)
                    break
                lote.append(fila)
                if len(lote) >= 20:
                    break
            if not lote:
                continue
            if lote[0][2]["mensaje"].get("type") != "interactive":
                try:
                    recibidas = [datetime.fromisoformat(f[2]["_recibido_en"]) for f in lote]
                    ultima = max(d if d.tzinfo else d.replace(tzinfo=timezone.utc) for d in recibidas)
                except (KeyError, ValueError, TypeError):
                    aviso("[cola] Fecha de recepción inválida; requiere revisión")
                    self._demorados[telefono] = actual + self.reintento
                    continue
                if (ahora - ultima).total_seconds() < self.espera:
                    continue
            try:
                self.procesar(lote)
                self.cola.terminar_lote([(f[0], f[1]) for f in lote])
                self._demorados.pop(telefono, None)
            except Exception as exc:
                aviso(f"[cola] Falló un lote; se reintentará: {type(exc).__name__}")
                self._demorados[telefono] = actual + self.reintento
            return True
        return False

    def ejecutar(self) -> None:
        """Recupera en serie y continúa escuchando hasta que se detenga."""
        while not self.detener.is_set():
            try:
                trabajo = self.paso()
            except Exception as exc:
                aviso(f"[cola] No se pudo consultar Sheets: {type(exc).__name__}")
                trabajo = False
            if not trabajo:
                self.despertar.wait(timeout=15)
                self.despertar.clear()

    def avisar(self) -> None:
        self.despertar.set()

    def cerrar(self) -> None:
        self.detener.set()
        self.despertar.set()
