"""Pruebas aisladas del almacenamiento del nuevo buzón en Sheets."""
from __future__ import annotations

import re
import threading
import unittest

from robot.cola_durable import ColaDurable
from robot.trabajador_cola import TrabajadorCola


class SheetsFalso:
    def __init__(self):
        self.filas = [list(ColaDurable.ENCABEZADOS)]
        self.fallar_append_antes = False
        self.fallar_append_despues = False
        self.llamadas_append = 0

    def values(self):
        return self

    def get(self, **kw):
        rango = kw["range"]
        class Resultado:
            def execute(otro):
                if rango.endswith("A1:D1"):
                    filas = self.filas[:1]
                elif re.search(r"!A\d+:B\d+$", rango):
                    n = int(re.search(r"!A(\d+)", rango).group(1))
                    filas = [self.filas[n - 1][:2]] if n <= len(self.filas) else []
                else:
                    m = re.search(r"!A(\d+):D(\d+)$", rango)
                    filas = self.filas[int(m.group(1)) - 1:int(m.group(2))]
                return {"values": [list(f) for f in filas]}
        return Resultado()

    def append(self, **kw):
        class Resultado:
            def execute(otro):
                self.llamadas_append += 1
                if self.fallar_append_antes:
                    raise OSError("sin red")
                self.filas.extend([list(f) for f in kw["body"]["values"]])
                if self.fallar_append_despues:
                    self.fallar_append_despues = False
                    raise TimeoutError("resultado incierto")
                return {}
        return Resultado()

    def batchUpdate(self, **kw):
        class Resultado:
            def execute(otro):
                for entrada in kw["body"]["data"]:
                    n = int(re.search(r"!B(\d+)$", entrada["range"]).group(1))
                    self.filas[n - 1][1] = entrada["values"][0][0]
                return {}
        return Resultado()


def mensaje(wamid):
    return ({"id": wamid, "from": "521111", "type": "text", "text": {"body": "hola"}},
            {"contacts": [{"wa_id": "521111", "profile": {"name": "Ana"}}]})


class TestColaDurable(unittest.TestCase):
    def setUp(self):
        self.servicio = SheetsFalso()
        self.cola = ColaDurable(lambda: self.servicio, "hoja-ficticia")

    def test_guardar_recuperar_y_deduplicar_tras_reinicio(self):
        self.assertEqual(self.cola.guardar([mensaje("a"), mensaje("a"), mensaje("b")]), 2)
        reiniciada = ColaDurable(lambda: self.servicio, "hoja-ficticia")
        self.assertEqual(reiniciada.guardar([mensaje("a")]), 0)
        fila, wamid, contenido = reiniciada.siguiente()
        self.assertEqual((fila, wamid, contenido["mensaje"]["id"]), (2, "a", "a"))
        reiniciada.terminar(fila, wamid)
        self.assertEqual(reiniciada.siguiente()[1], "b")
        self.assertEqual(reiniciada.guardar([mensaje("a")]), 0)

    def test_error_de_sheets_se_propaga(self):
        self.servicio.fallar_append_antes = True
        with self.assertRaises(OSError):
            self.cola.guardar([mensaje("a")])
        self.assertEqual(len(self.servicio.filas), 1)

    def test_resultado_incierto_se_concilia_por_id(self):
        self.servicio.fallar_append_despues = True
        with self.assertRaises(TimeoutError):
            self.cola.guardar([mensaje("a")])
        self.assertEqual(self.cola.guardar([mensaje("a")]), 0)
        self.assertEqual(len(self.servicio.filas), 2)

    def test_peticiones_simultaneas_no_agregan_dos_veces(self):
        barrera = threading.Barrier(4)
        resultados = []
        def escribir():
            barrera.wait()
            resultados.append(self.cola.guardar([mensaje("a")]))
        hilos = [threading.Thread(target=escribir) for _ in range(4)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        self.assertEqual(sorted(resultados), [0, 0, 0, 1])
        self.assertEqual(len(self.servicio.filas), 2)

    def test_trabajador_agrupa_y_termina_solo_tras_procesar(self):
        self.cola.guardar([mensaje("a"), mensaje("b"), mensaje("c")])
        vistos = []
        trabajador = TrabajadorCola(self.cola, lambda filas: vistos.append([f[1] for f in filas]), espera_segundos=0)
        self.assertTrue(trabajador.paso())
        self.assertEqual(vistos, [["a", "b", "c"]])
        self.assertIsNone(self.cola.siguiente())

    def test_un_fallo_no_impide_atender_a_otro_telefono(self):
        a = mensaje("a")
        b = mensaje("b")
        b[0]["from"] = "522222"
        self.cola.guardar([a, b])
        vistos = []
        def procesar(filas):
            telefono = filas[0][2]["mensaje"]["from"]
            if telefono == "521111":
                raise RuntimeError("fallo simulado")
            vistos.append(telefono)
        trabajador = TrabajadorCola(self.cola, procesar, espera_segundos=0)
        self.assertTrue(trabajador.paso())
        self.assertTrue(trabajador.paso())
        self.assertEqual(vistos, ["522222"])
        self.assertEqual(self.cola.siguiente()[1], "a")

    def test_no_termina_una_fila_reordenada(self):
        self.cola.guardar([mensaje("a")])
        with self.assertRaises(RuntimeError):
            self.cola.terminar(2, "otro")
        self.assertEqual(self.cola.siguiente()[1], "a")

    def test_rechaza_entrada_sin_id_y_hoja_sin_encabezados(self):
        with self.assertRaises(ValueError):
            self.cola.guardar([({}, {})])
        self.servicio.filas[0] = ["id"]
        with self.assertRaises(RuntimeError):
            self.cola.guardar([mensaje("a")])


if __name__ == "__main__":
    unittest.main()
