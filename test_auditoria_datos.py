"""Auditoría de datos y recuperación (v3.20.4).

Cubre las áreas 1 y 2 de la auditoría profunda:
- Capa Sheets: lecturas que no se truncan al llenarse la hoja,
  escritura atómica del espejo de citas, y rastro en Diagnóstico
  cuando una escritura falla (nada de escrituras silenciosas a medias).
- Recuperación ante caídas: reconciliación al arrancar — una
  propuesta cuya cita ya existe (espejo Confirmada o evento en el
  calendario) NO resucita; una propuesta genuina se conserva;
  un espejo Pendiente NO descarta (reintento posible).

Uso:  python3 test_auditoria_datos.py
Salida: 0 = todo ok; 1 = algún caso falló (se imprime el caso exacto).
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from unittest.mock import patch  # noqa: E402

from robot import sheets as sheets_mod  # noqa: E402
from robot.logic import (  # noqa: E402
    _BAJA_CONFIANZA,
    _CITAS_PENDIENTES,
    _RETOMAR,
    atender_boton,
    cargar_propuestas,
)
from test_bateria_dinamica import (  # noqa: E402
    AHORA_ABIERTO,
    DepsDinamica,
    H1,
    NOMBRE,
    TEL,
    _fila_espejo,
)

AHORA = AHORA_ABIERTO
RESULTADOS = []


def limpiar():
    _CITAS_PENDIENTES.clear()
    _RETOMAR.clear()
    _BAJA_CONFIANZA.clear()
    sheets_mod._CACHE.clear()


def caso(nombre, fn):
    limpiar()
    try:
        ok, detalle = fn()
    except Exception as exc:
        ok, detalle = False, f"excepción {type(exc).__name__}: {exc}"
    RESULTADOS.append((nombre, ok))
    marca = "PASS" if ok else "FAIL"
    print(f"[{marca}] {nombre}" + (f" :: {detalle}" if detalle and not ok else ""))
    limpiar()


# ---------------------------------------------------------------------------
# Fakes de la capa Sheets (fallos simulados, nunca la hoja en vivo)
# ---------------------------------------------------------------------------

class _ReqFalso:
    def __init__(self, servicio, datos=None):
        self.servicio = servicio
        self.datos = datos

    def execute(self):
        self.servicio.llamadas += 1
        if (self.servicio.falla_en is not None
                and self.servicio.llamadas == self.servicio.falla_en):
            raise RuntimeError("Google caído (simulado)")
        return self.datos or {}


class _ValoresFalso:
    def __init__(self, servicio):
        self.servicio = servicio
        self.updates = []
        self.gets = []

    def get(self, spreadsheetId=None, range=None):
        self.gets.append(range)
        return _ReqFalso(self.servicio, self.servicio.datos_get)

    def update(self, spreadsheetId=None, range=None, valueInputOption=None, body=None):
        self.updates.append({"range": range, "values": body["values"]})
        return _ReqFalso(self.servicio, {})

    def append(self, spreadsheetId=None, range=None, valueInputOption=None, body=None):
        self.servicio.appends.append({"range": range, "values": body["values"]})
        return _ReqFalso(self.servicio, {})

    def clear(self, spreadsheetId=None, range=None):
        self.servicio.clears.append(range)
        return _ReqFalso(self.servicio, {})


class _ServicioFalso:
    def __init__(self, datos_get=None, falla_en=None):
        self.datos_get = datos_get or {}
        self.falla_en = falla_en  # n-ésima llamada execute() que debe fallar
        self.llamadas = 0
        self.appends = []
        self.clears = []
        self.valores = _ValoresFalso(self)

    def values(self):
        return self.valores


_FILAS_CLIENTES_BASE = {
    "fecha": "2026-11-24", "nombre": "Ana", "telefono": TEL,
    "motivo": "Limpieza", "fecha_cita": "", "origen": "whatsapp",
    "estatus": "en conversacion", "handoff": "no",
    "ultima_actividad": "", "mensajes_totales": "3",
    "resumen_conversacion": "Preguntó por la limpieza.",
    "intereses": "Limpieza dental", "calificacion": "Tibio",
    "proxima_accion": "", "notas": "Solo en las mañanas",
    "robot_activo": "SI",
}

_ENCABEZADOS_CITAS = ["ID_Cita", "ID_Paciente", "Teléfono", "Servicio", "Profesional",
                      "Fecha", "Hora_inicio", "Hora_fin", "Estado", "Origen",
                      "Recordatorio_enviado", "Confirmado", "Notas", "Creado_por",
                      "Última_actualización", "Urgencia"]


def _fila_citas_base():
    return ["C-1", "", TEL, "Limpieza", "Equipo de la clínica",
            "2026-11-23", "10:00", "11:00", "Confirmada", "WhatsApp",
            "-", "Sí", "Paciente: Ana", "Asistente", "2026-11-23", "NO"]


# ---------------------------------------------------------------------------
# A. Capa Sheets: llenado, atomicidad y rastro en Diagnóstico
# ---------------------------------------------------------------------------

def _a1():
    # La lectura debe pedir un rango que cubra más de 1000 filas y
    # devolver todas las filas que Google entregue.
    filas = [["telefono", "nombre"]] + [[str(i), f"n{i}"] for i in range(1500)]
    servicio = _ServicioFalso(datos_get={"values": filas})
    sheets_mod._CACHE.clear()
    try:
        with patch.object(sheets_mod, "_servicio_sheets", lambda: servicio):
            resultado = sheets_mod.leer_pestana("Conversaciones")
    finally:
        sheets_mod._CACHE.clear()
    rango = servicio.valores.gets[0] if servicio.valores.gets else ""
    ok = len(resultado) == 1500 and "!A:Z" in str(rango)
    return ok, f"filas={len(resultado)} rango={rango}"


def _a2():
    # El espejo se actualiza con UNA sola escritura (atómica), no 6.
    servicio = _ServicioFalso(
        datos_get={"values": [_ENCABEZADOS_CITAS, _fila_citas_base()]})
    with patch.object(sheets_mod, "_servicio_sheets", lambda: servicio):
        sheets_mod.actualizar_cita_espejo(
            TEL, "2026-11-23", estado="Cancelada", notas="Paciente canceló")
    ups = servicio.valores.updates
    ok = (len(ups) == 1 and ups[0]["range"] == "Citas!F2:P2"
          and ups[0]["values"] == [[
              "2026-11-23", "10:00", "11:00", "Cancelada", "WhatsApp",
              "-", "Sí", "Paciente canceló", "Asistente", "2026-11-23", "NO"]])
    return ok, f"updates={ups}"


def _a3():
    # Si Google falla al actualizar el espejo, queda rastro en
    # Diagnóstico (no solo en el registro del servidor).
    servicio = _ServicioFalso(
        datos_get={"values": [_ENCABEZADOS_CITAS, _fila_citas_base()]},
        falla_en=2)  # 1 = lectura, 2 = escritura
    diag = []
    with patch.object(sheets_mod, "_servicio_sheets", lambda: servicio), \
         patch.object(sheets_mod, "registrar_diagnostico",
                      lambda *a, **k: diag.append(a)):
        sheets_mod.actualizar_cita_espejo(TEL, "2026-11-23", estado="Cancelada")
    ok = len(diag) == 1 and "espejo" in str(diag[0][1]).lower()
    return ok, f"diag={diag}"


def _a4():
    # Memoria: K:O se escribe bien pero W falla → no lanza y deja rastro.
    fila = dict(_FILAS_CLIENTES_BASE, **{"Miedos / sensibilidades": ""})
    servicio = _ServicioFalso(falla_en=2)  # 1 = K:O ok, 2 = W falla
    diag = []
    try:
        with patch.object(sheets_mod, "_servicio_sheets", lambda: servicio), \
             patch.object(sheets_mod, "leer_pestana", lambda pestana: [dict(fila)]), \
             patch.object(sheets_mod, "registrar_diagnostico",
                          lambda *a, **k: diag.append(a)):
            sheets_mod.guardar_memoria_cliente(
                TEL, resumen="Quiere limpieza", miedos="le dan miedo las agujas")
        lanzo = False
    except Exception:
        lanzo = True
    ok = not lanzo and len(diag) == 1
    return ok, f"lanzo={lanzo} diag={diag} updates={len(servicio.valores.updates)}"


def _a5():
    # Memoria: Google caído desde la primera escritura → no lanza y deja rastro.
    fila = dict(_FILAS_CLIENTES_BASE, **{"Miedos / sensibilidades": ""})
    servicio = _ServicioFalso(falla_en=1)
    diag = []
    try:
        with patch.object(sheets_mod, "_servicio_sheets", lambda: servicio), \
             patch.object(sheets_mod, "leer_pestana", lambda pestana: [dict(fila)]), \
             patch.object(sheets_mod, "registrar_diagnostico",
                          lambda *a, **k: diag.append(a)):
            sheets_mod.guardar_memoria_cliente(TEL, resumen="Quiere limpieza")
        lanzo = False
    except Exception:
        lanzo = True
    ok = not lanzo and len(diag) == 1
    return ok, f"lanzo={lanzo} diag={diag}"


def _a6():
    # Propuesta: si guardar en la hoja falla, queda rastro en Diagnóstico
    # (la memoria sigue valiendo, pero el fallo no es invisible).
    from robot.logic import _guardar_propuesta, _borrar_propuesta

    class DepsFalla(DepsDinamica):
        def __init__(self):
            super().__init__()
            self.diag = []

        def guardar_propuesta(self, telefono, propuesta):
            raise RuntimeError("hoja caída (simulado)")

        def borrar_propuesta(self, telefono):
            raise RuntimeError("hoja caída (simulado)")

        def registrar_diagnostico(self, fecha, componente, estado, detalle,
                                  telefono="", contexto=""):
            self.diag.append((componente, estado, detalle))

    d = DepsFalla()
    _guardar_propuesta(d, TEL, {"nombre": NOMBRE, "motivo": "Limpieza",
                                "fecha_cita": H1, "fecha_bonita": "lunes",
                                "creado_en": AHORA.isoformat()})
    en_memoria = TEL in _CITAS_PENDIENTES
    _borrar_propuesta(d, TEL)
    ok = en_memoria and len(d.diag) == 2
    return ok, f"en_memoria={en_memoria} diag={d.diag}"


# ---------------------------------------------------------------------------
# B. Recuperación ante caídas: reconciliación al arrancar
# ---------------------------------------------------------------------------

class DepsRecuperacion(DepsDinamica):
    """Deps con propuestas en "hoja" (dict), espejo y calendario falsos."""

    def __init__(self, espejo=None, propuestas=None, existe_cal=False):
        super().__init__(espejo=espejo)
        self.propuestas_hoja = propuestas or {}
        self.borradas = []
        self.existe_cal = existe_cal
        self.diag = []

    def leer_propuestas(self):
        return [dict(p) for p in self.propuestas_hoja.values()]

    def guardar_propuesta(self, telefono, propuesta):
        self.propuestas_hoja[telefono] = {"telefono": telefono, **propuesta}

    def borrar_propuesta(self, telefono):
        self.borradas.append(telefono)
        self.propuestas_hoja.pop(telefono, None)

    def existe_cita_en_calendario(self, telefono, fecha_iso):
        return self.existe_cal

    def registrar_diagnostico(self, fecha, componente, estado, detalle,
                              telefono="", contexto=""):
        self.diag.append((componente, estado, detalle))


def _fila_propuesta_hoja():
    return {"telefono": TEL, "nombre": NOMBRE, "motivo": "Blanqueamiento dental",
            "fecha_cita": H1, "fecha_bonita": "lunes 23 de noviembre a las 10:00",
            "creado_en": AHORA.isoformat(), "extra_json": ""}


def _espejo_confirmada():
    return [_fila_espejo("C-1", "2026-11-23", "10:00", "11:00", estado="Confirmada")]


def _b1():
    # Propuesta ya consumida (cita Confirmada en el espejo): al
    # arrancar NO resucita y la fila vieja se borra de la hoja.
    d = DepsRecuperacion(espejo=_espejo_confirmada(),
                         propuestas={TEL: _fila_propuesta_hoja()})
    n = cargar_propuestas(d)
    ok = (n == 0 and TEL not in _CITAS_PENDIENTES
          and d.borradas == [TEL] and d.propuestas_hoja == {})
    return ok, f"n={n} borradas={d.borradas} hoja={d.propuestas_hoja}"


def _b2():
    # Propuesta genuina (sin evidencia de cita creada): se conserva.
    d = DepsRecuperacion(espejo=[], propuestas={TEL: _fila_propuesta_hoja()})
    n = cargar_propuestas(d)
    ok = (n == 1 and TEL in _CITAS_PENDIENTES and d.borradas == [])
    return ok, f"n={n} borradas={d.borradas}"


def _b3():
    # Evidencia en el calendario (cita creada, espejo sin fila):
    # la propuesta tampoco resucita.
    d = DepsRecuperacion(espejo=[], propuestas={TEL: _fila_propuesta_hoja()},
                         existe_cal=True)
    n = cargar_propuestas(d)
    ok = (n == 0 and TEL not in _CITAS_PENDIENTES and d.borradas == [TEL])
    return ok, f"n={n} borradas={d.borradas}"


def _b4():
    # Espejo Pendiente (el calendario falló al confirmar): NO se
    # descarta — el cliente puede reintentar la confirmación.
    espejo = [_fila_espejo("C-1", "2026-11-23", "10:00", "11:00", estado="Pendiente")]
    d = DepsRecuperacion(espejo=espejo, propuestas={TEL: _fila_propuesta_hoja()})
    n = cargar_propuestas(d)
    ok = (n == 1 and TEL in _CITAS_PENDIENTES and d.borradas == [])
    return ok, f"n={n} borradas={d.borradas}"


def _b5():
    # Reinicio simulado a mitad de flujo: la confirmación creó la cita
    # (espejo Confirmada) pero borrar la propuesta falló y quedó la
    # fila. Al arrancar, la propuesta no resucita y un Confirmar
    # repetido no crea una cita duplicada.
    d = DepsRecuperacion(espejo=_espejo_confirmada(),
                         propuestas={TEL: _fila_propuesta_hoja()})
    n = cargar_propuestas(d)
    if n != 0 or TEL in _CITAS_PENDIENTES:
        return False, f"resucitó: n={n} en_memoria={TEL in _CITAS_PENDIENTES}"
    r = atender_boton(d, TEL, NOMBRE, "confirmar_cita",
                      con_ritmo=False, ahora=AHORA)
    ok = d.citas == [] and r.get("motivo") == "sin propuesta"
    return ok, f"citas={d.citas} motivo={r.get('motivo')}"


def main():
    caso("A1 leer_pestana no se trunca en 1000 filas", _a1)
    caso("A2 espejo: una sola escritura atómica F:P", _a2)
    caso("A3 espejo con Google caído deja rastro en Diagnóstico", _a3)
    caso("A4 memoria: W falla tras K:O, sin lanzar y con rastro", _a4)
    caso("A5 memoria con Google caído: sin lanzar y con rastro", _a5)
    caso("A6 propuesta con hoja caída deja rastro en Diagnóstico", _a6)
    caso("B1 propuesta ya consumida no resucita al arrancar", _b1)
    caso("B2 propuesta genuina se conserva al arrancar", _b2)
    caso("B3 evidencia en calendario descarta la propuesta", _b3)
    caso("B4 espejo Pendiente no descarta (reintento posible)", _b4)
    caso("B5 reinicio tras confirmación: sin duplicar la cita", _b5)
    fallos = [n for n, ok in RESULTADOS if not ok]
    print(f"\n{len(RESULTADOS) - len(fallos)}/{len(RESULTADOS)} casos ok "
          f"(auditoría de datos)")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
