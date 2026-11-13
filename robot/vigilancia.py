"""Vigilancia anti-atasco (v3.1): que un lote lento no sea un silencio.

El 12 de noviembre de 2026 dos mensajes se quedaron sin respuesta
más de 45 minutos y no quedó ningún rastro: ni "dame un momento", ni
fila de fallo, ni nada en Diagnóstico. El lote se atoró dentro de una
llamada (probablemente Gemini colgado en sus reintentos, o una
llamada a Google sin tiempo límite) y nadie se enteró: el cliente
esperando, el dueño sin saberlo, y Muse sin nada que revisar.

Ahora cada lote corre con vigilancia: si en 90 segundos no termina,
se avisa UNA vez (el que llama decide qué hacer: escribir en
Diagnóstico y mandarle al cliente un "dame un momento") y se sigue
esperando a que termine, para que la respuesta real llegue igual
cuando el trabajo acabe. Si el trabajo lanza un error, ese error se
vuelve a lanzar en el hilo que llama, como si no hubiera vigilancia.

Puro (sin internet): se prueba solo, con trabajos falsos que duermen.
"""

from __future__ import annotations

import threading

# Segundos que se le da a un lote antes de avisar. 90 s: un Gemini
# frío puede tardar un minuto; más de 90 s ya es atasco, no lentitud.
LOTE_LENTO_SEGUNDOS = 90


def con_vigilancia(trabajo, al_tardar, segundos: float = LOTE_LENTO_SEGUNDOS) -> bool:
    """Corre trabajo() con vigilancia. Devuelve True si terminó a tiempo.

    `trabajo`: la función sin argumentos que hace el trabajo.
    `al_tardar`: se llama UNA vez si pasan `segundos` sin terminar.
    Si trabajo() lanza, la excepción se vuelve a lanzar aquí.
    """
    hecho = threading.Event()
    errores: list[BaseException] = []

    def _correr():
        try:
            trabajo()
        except BaseException as exc:  # noqa: BLE001 - se vuelve a lanzar abajo
            errores.append(exc)
        finally:
            hecho.set()

    hilo = threading.Thread(target=_correr, daemon=True)
    hilo.start()
    a_tiempo = hecho.wait(segundos)
    if not a_tiempo:
        try:
            al_tardar()
        except Exception:
            pass  # el aviso nunca rompe el trabajo
        hecho.wait()
    if errores:
        raise errores[0]
    return a_tiempo
