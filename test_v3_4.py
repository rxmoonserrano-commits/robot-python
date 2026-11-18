"""Pruebas de la versión 3.4 (que el robot nunca se calle), SIN internet.

El 13 de noviembre de 2026 el robot dejó de contestar: el webhook
devolvía 200, pero ningún lote se procesaba, no había filas nuevas en
la hoja ni aviso del vigilante, y no había nada que mirar para saber
por qué. Esta versión pone dos cosas:
(a) El Agrupador libera solo un teléfono atascado: un lote muerto ya
    no deja mudo a ese cliente para siempre.
(b) GET /estado con contadores: si el robot se calla, se ve en
    segundos si el webhook recibió algo y si los lotes arrancaron.

Uso:  python test_v3_4.py
"""

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from robot import estado_servidor
from robot.agrupar import Agrupador

RESULTADOS: list[tuple[str, bool]] = []


def caso(nombre: str, ok: bool, detalle: str = "") -> None:
    RESULTADOS.append((nombre, ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {nombre}" + (f" {detalle}" if not ok else ""))


def _agrupador_con_bloqueo(atascado: float):
    """Agrupador cuyo primer lote se atasca (el resto pasa directo)."""
    llamadas: list[list[str]] = []
    bloqueo = threading.Event()
    primero = {"si": True}

    def lento(tel, nombre, textos, wamids):
        llamadas.append(list(textos))
        if primero["si"]:
            primero["si"] = False
            bloqueo.wait(timeout=5)  # simula el lote atascado

    ag = Agrupador(lento, espera_segundos=0.05, atascado_segundos=atascado)
    return ag, llamadas, bloqueo


def main() -> None:
    # (a) Un teléfono atascado se libera solo y el siguiente lote sí se atiende.
    ag, llamadas, bloqueo = _agrupador_con_bloqueo(atascado=0.2)
    ag.agregar("5210000000001", "hola", wamid="w1", nombre="Prueba")
    time.sleep(0.3)
    caso("(a) El primer lote atascado está en proceso",
         ag.procesando() == 1, f"procesando={ag.procesando()}")
    ag.agregar("5210000000001", "cuanto cuesta", wamid="w2", nombre="Prueba")
    time.sleep(1.2)
    caso("(a) Atascado: el segundo lote se procesa (el teléfono se liberó solo)",
         len(llamadas) == 2 and llamadas[1] == ["cuanto cuesta"],
         f"llamadas={llamadas}")
    bloqueo.set()

    # (b) Sin atasco: el segundo lote espera su turno y luego se procesa.
    ag2, llamadas2, bloqueo2 = _agrupador_con_bloqueo(atascado=5.0)
    ag2.agregar("5210000000002", "hola", wamid="w1", nombre="Prueba")
    time.sleep(0.3)
    ag2.agregar("5210000000002", "cuanto cuesta", wamid="w2", nombre="Prueba")
    time.sleep(0.6)
    caso("(b) Sin atasco: el segundo lote espera (no se adelanta)",
         len(llamadas2) == 1, f"llamadas={llamadas2}")
    bloqueo2.set()  # el primer lote termina
    time.sleep(2.5)  # el temporizador de reintento (2 s) dispara el segundo
    caso("(b) Sin atasco: el segundo lote se procesa después",
         len(llamadas2) == 2 and llamadas2[1] == ["cuanto cuesta"],
         f"llamadas={llamadas2}")

    # (c) Los contadores de /estado suben y la foto trae solo claves previstas.
    antes = estado_servidor.foto()
    estado_servidor.contar_webhook()
    estado_servidor.contar_lote_inicio()
    estado_servidor.contar_lote_fin(True)
    estado_servidor.contar_lote_fin(False, "fallo de prueba")
    estado_servidor.marcar_salud_lista()
    despues = estado_servidor.foto()
    caso("(c) Los contadores suben y la salud queda marcada",
         despues["webhooks_recibidos"] == antes["webhooks_recibidos"] + 1
         and despues["lotes_iniciados"] == antes["lotes_iniciados"] + 1
         and despues["lotes_terminados"] == antes["lotes_terminados"] + 1
         and despues["lotes_fallidos"] == antes["lotes_fallidos"] + 1
         and despues["ultimo_error"] == "fallo de prueba"
         and despues["salud_lista"] is True,
         f"antes={antes} despues={despues}")
    caso("(c) La foto trae solo las claves previstas (nada de clientes)",
         set(despues.keys()) == {
             "webhooks_recibidos", "lotes_iniciados", "lotes_terminados",
             "lotes_fallidos", "ultimo_webhook_iso", "ultimo_lote_iso",
             "ultimo_error", "salud_lista", "salud_iso",
             "arranque_iso", "prendido_segundos",
         },
         f"claves={sorted(despues.keys())}")

    # (d) El cableado en app.py: /estado existe y cuenta lo que debe.
    app_txt = Path(__file__).with_name("app.py").read_text(encoding="utf-8")
    caso("(d) Existe GET /estado y usa la foto sin datos personales",
         '@app.get("/estado")' in app_txt
         and "estado_servidor.foto()" in app_txt,
         "falta la ruta /estado")
    caso("(d) El webhook cuenta cada mensaje que llega",
         "estado_servidor.contar_webhook()" in app_txt,
         "falta contar_webhook en el webhook")
    caso("(d) El arranque marca la salud como lista",
         "estado_servidor.marcar_salud_lista()" in app_txt,
         "falta marcar_salud_lista en el arranque")

    fallos = [n for n, ok in RESULTADOS if not ok]
    print(f"\n{len(RESULTADOS) - len(fallos)}/{len(RESULTADOS)} casos PASS (test_v3_4)")
    if fallos:
        print("FALLOS:", fallos)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
