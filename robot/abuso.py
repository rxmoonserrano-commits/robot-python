"""Anti-abuso (v3.3): que un teléfono no agote la cuota gratis de Gemini.

Un cliente (o un programa) mandando 100 mensajes seguidos agota la
capa gratuita de Gemini y deja al robot mudo para todos los demás.
El límite es por teléfono y por ráfaga, no por día: una conversación
normal nunca llega a 10 mensajes en un minuto, pero una ráfaga sí.

- "ok": se procesa normal.
- "avisar": pasó el límite y aún no se le avisó en esta ventana: se le
  manda UN mensaje de calma y no se procesa el lote.
- "silencio": ya se le avisó: no se procesa ni se le escribe nada más.

Puro (sin internet): se prueba solo. La memoria vive en el proceso:
un reinicio del servidor resetea el contador, y eso está bien — un
reinicio no es una forma de colarse, es empezar de cero.
"""

from __future__ import annotations

import threading
import time

# 10 mensajes en 60 segundos: una conversación normal no llega ahí;
# una ráfaga (copiar-pegar, un programa, alguien probando el robot)
# sí. El número es conservador a propósito: mejor avisar una vez de
# más que dejar al robot sin cuota para los demás clientes.
MAX_MENSAJES = 10
VENTANA_SEGUNDOS = 60.0


class Limitador:
    """Cuenta mensajes por teléfono y dice si se procesa o no."""

    def __init__(self, max_mensajes: int = MAX_MENSAJES,
                 ventana_segundos: float = VENTANA_SEGUNDOS):
        self.max_mensajes = max_mensajes
        self.ventana = ventana_segundos
        self._candado = threading.Lock()
        self._tiempos: dict[str, list[float]] = {}
        self._avisados: dict[str, float] = {}

    def registrar(self, telefono: str) -> str:
        """Registra un mensaje y devuelve "ok", "avisar" o "silencio"."""
        ahora = time.monotonic()
        with self._candado:
            tiempos = [t for t in self._tiempos.get(telefono, [])
                       if ahora - t < self.ventana]
            tiempos.append(ahora)
            self._tiempos[telefono] = tiempos
            if len(tiempos) <= self.max_mensajes:
                return "ok"
            ultimo_aviso = self._avisados.get(telefono, 0.0)
            if ahora - ultimo_aviso >= self.ventana:
                self._avisados[telefono] = ahora
                return "avisar"
            return "silencio"
