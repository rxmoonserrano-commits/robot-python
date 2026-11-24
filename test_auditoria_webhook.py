"""Auditoría v3.20.4 — Área 3: webhook de Meta (idempotencia y orden).

Reproduce los hallazgos ANTES de corregir:
- C1/C1b: los botones no tenían dedup por wamid (un reenvío de Meta
  atendía el mismo tap dos veces). marcar_visto debe registrar y
  detectar repetidos, con el mismo desalojo FIFO.
- C2: el webhook lanza un hilo por mensaje; dos mensajes del mismo
  cliente pueden entrar al buzón desordenados. Con timestamp, el
  lote debe despacharse en orden de envío, no de llegada.
- C3: sin timestamps, se conserva el orden de llegada (compatibilidad).
- C4: la persistencia en disco guarda el orden y carga archivos del
  formato viejo (textos/wamids) sin romperse.
- C5: cableado en app.py (fuente): el botón se dedupea antes de
  atenderlo y los textos entran con su timestamp.

Corre con: python3 test_auditoria_webhook.py
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from robot.agrupar import Agrupador  # noqa: E402

TEL = "5216694608263"


def c1_marcar_visto():
    ag = Agrupador(lambda *a: None, espera_segundos=60)
    primero = ag.marcar_visto("wb1")
    segundo = ag.marcar_visto("wb1")
    otro = ag.marcar_visto("wb2")
    ok = primero is True and segundo is False and otro is True
    return ok, f"primero={primero} segundo={segundo} otro={otro}"


def c1b_marcar_visto_fifo():
    ag = Agrupador(lambda *a: None, espera_segundos=60, max_vistos=3)
    for w in ("a", "b", "c", "d"):
        ag.marcar_visto(w)
    viejo = ag.marcar_visto("a")      # ya se desalojó: se marca de nuevo
    reciente = ag.marcar_visto("d")   # sigue conocido
    ok = viejo is True and reciente is False
    return ok, f"viejo={viejo} reciente={reciente}"


def c2_orden_por_timestamp():
    lotes = []
    ag = Agrupador(lambda t, n, tx, w: lotes.append(list(tx)), espera_segundos=60)
    ag.agregar(TEL, "segundo", wamid="w2", timestamp="1700000100")
    ag.agregar(TEL, "primero", wamid="w1", timestamp="1700000000")
    ag.agregar(TEL, "tercero", wamid="w3", timestamp="1700000200")
    ag.procesar_ahora(TEL)
    esperado = [["primero", "segundo", "tercero"]]
    return lotes == esperado, str(lotes)


def c3_sin_timestamp_orden_de_llegada():
    lotes = []
    ag = Agrupador(lambda t, n, tx, w: lotes.append(list(tx)), espera_segundos=60)
    ag.agregar(TEL, "uno", wamid="a")
    ag.agregar(TEL, "dos", wamid="b")
    ag.procesar_ahora(TEL)
    return lotes == [["uno", "dos"]], str(lotes)


def c4_persistencia_y_formato_viejo():
    tmp = tempfile.mkdtemp()
    ruta = os.path.join(tmp, "buzon.json")
    # (a) ida y vuelta con timestamps: entra desordenado, sale ordenado
    ag1 = Agrupador(lambda *a: None, espera_segundos=60, archivo=ruta)
    ag1.agregar(TEL, "segundo", wamid="w2", timestamp="1700000100")
    ag1.agregar(TEL, "primero", wamid="w1", timestamp="1700000000")
    lotes = []
    ag2 = Agrupador(lambda t, n, tx, w: lotes.append(list(tx)),
                    espera_segundos=60, archivo=ruta)
    recuperados = ag2.cargar()
    ag2.procesar_ahora(TEL)
    if recuperados != 1 or lotes != [["primero", "segundo"]]:
        return False, f"recuperados={recuperados} lotes={lotes}"
    # (b) archivo del formato viejo (textos/wamids): carga y procesa
    ruta2 = os.path.join(tmp, "buzon-viejo.json")
    with open(ruta2, "w", encoding="utf-8") as f:
        json.dump({"pendientes": {TEL: {"textos": ["viejo uno", "viejo dos"],
                                        "wamids": ["ov1", "ov2"], "nombre": "Ana"}},
                   "vistos": ["ov1"]}, f)
    lotes2 = []
    ag3 = Agrupador(lambda t, n, tx, w: lotes2.append(list(tx)),
                    espera_segundos=60, archivo=ruta2)
    recuperados2 = ag3.cargar()
    ag3.procesar_ahora(TEL)
    ok = recuperados2 == 1 and lotes2 == [["viejo uno", "viejo dos"]]
    return ok, f"recuperados2={recuperados2} lotes2={lotes2}"


def c5_cableado_en_app():
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "app.py"), encoding="utf-8").read()
    i = src.find('if tipo == "interactive":')
    fragmento = src[i:i + 1500] if i >= 0 else ""
    boton_ok = ("marcar_visto" in fragmento
                and fragmento.find("marcar_visto") < fragmento.find("atender_boton"))
    plano = " ".join(src.split())
    texto_ok = "_AGRUPADOR.agregar(telefono, texto, wamid=wamid, nombre=nombre, timestamp=" in plano
    return (boton_ok and texto_ok), f"boton_ok={boton_ok} texto_ok={texto_ok}"


CASOS = [
    ("C1 marcar_visto detecta repetidos", c1_marcar_visto),
    ("C1b marcar_visto con desalojo FIFO", c1b_marcar_visto_fifo),
    ("C2 lote despachado por timestamp, no por llegada", c2_orden_por_timestamp),
    ("C3 sin timestamp se conserva orden de llegada", c3_sin_timestamp_orden_de_llegada),
    ("C4 persistencia con orden + formato viejo", c4_persistencia_y_formato_viejo),
    ("C5 cableado en app.py (dedup botón + timestamp)", c5_cableado_en_app),
]


def main():
    fallos = 0
    for nombre, fn in CASOS:
        try:
            ok, detalle = fn()
        except Exception as exc:  # noqa: BLE001
            ok, detalle = False, f"excepción: {exc!r}"
        estado = "PASS" if ok else "FAIL"
        if not ok:
            fallos += 1
        print(f"[{estado}] {nombre} — {detalle}")
    print(f"\n{len(CASOS) - fallos}/{len(CASOS)} casos ok (auditoría webhook)")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
