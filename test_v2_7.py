"""Pruebas de la versión 2.7, SIN internet.

Cubre solo lo nuevo de la v2.7:
(a) el robot lee el modelo que Google sugiere en su error 404.
(b) si el modelo configurado está retirado, el robot cambia SOLO al
    que Google sugiere (autocuración) y recuerda el que funcionó.
(c) un "sí gracias" después de un "dame un momento" (Gemini falló)
    NO confirma ninguna cita: es cortesía, va al agente.
(d) un "sí" justo después de que el robot ofreció la fecha SÍ confirma.
(e) cuando Gemini falla, queda escrito en Diagnóstico (pestaña nueva).

Uso:  python test_v2_7.py
"""

from datetime import datetime, timezone

import robot.gemini as gemini_mod
import robot.logic as logic_mod
from robot.agent import RespuestaAgente
from robot.config import settings
from robot.gemini import GeminiError, _modelo_sugerido, generar_texto
from robot.logic import atender_mensaje

ERROR_GOOGLE = (
    "Gemini devolvió 404: {\"error\": {\"message\": \"This model "
    "models/gemini-2.5-flash is no longer available to new users. "
    "Please update your code to use models/gemini-3.8-flash for the "
    "latest features and improvements.\"}}"
)

CONOCIMIENTO = [
    {"tipo": "servicio", "pregunta_o_servicio": "Limpieza dental",
     "respuesta_o_precio": "$600", "detalle": "Dura 60 minutos"},
    {"tipo": "horario", "pregunta_o_servicio": "Lunes a viernes",
     "respuesta_o_precio": "09:00 a 18:00", "detalle": ""},
    {"tipo": "horario", "pregunta_o_servicio": "Sábado",
     "respuesta_o_precio": "09:00 a 14:00", "detalle": ""},
]
FOTOS = [{"descripcion": "Foto del local", "url": "https://ejemplo.com/foto-local.jpg"}]


class DepsV27:
    """Servicios de mentira."""

    def __init__(self, agente=None):
        self.agente = agente or RespuestaAgente(
            respuesta_texto="Hola, Jose Ramon. Claro que sí, dime qué necesitas.")
        self.conversaciones = []
        self.clientes = []
        self.textos_enviados = []
        self.citas = []
        self.alertas = []
        self.alertas_error = []
        self.llamadas_agente = []
        self.diagnosticos = []

    def leer_control(self):
        return {"bot_activo": "SI", "ultima_respuesta_humana": ""}

    def leer_robot_activo(self, telefono):
        return "SI"

    def leer_cliente(self, telefono):
        return None

    def cancelar_cita(self, telefono, fecha_cita):
        return False

    def cancelar_cita_cliente(self, telefono):
        pass

    def guardar_propuesta(self, telefono, propuesta):
        pass

    def borrar_propuesta(self, telefono):
        pass

    def leer_propuestas(self):
        return []

    def leer_conocimiento(self):
        return CONOCIMIENTO

    def leer_fotos(self):
        return FOTOS

    def leer_historial(self, telefono):
        return [c for c in self.conversaciones if c["telefono"] == telefono]

    def registrar_conversacion(self, fecha, telefono, quien, mensaje, respondio, motivo=""):
        self.conversaciones.append({"fecha": fecha, "telefono": telefono, "quien_hablo": quien,
                                    "mensaje": mensaje, "robot_respondio": respondio, "motivo": motivo})

    def registrar_cliente(self, fecha, nombre, telefono, motivo, fecha_cita="", origen="whatsapp",
                          estatus="en conversacion", handoff="no"):
        self.clientes.append({"fecha": fecha, "nombre": nombre, "telefono": telefono,
                              "motivo": motivo, "fecha_cita": fecha_cita, "origen": origen,
                              "estatus": estatus, "handoff": handoff})

    def registrar_diagnostico(self, fecha, componente, estado, detalle, telefono="", contexto=""):
        self.diagnosticos.append({"fecha": fecha, "componente": componente,
                                  "estado": estado, "detalle": detalle,
                                  "telefono": telefono, "contexto": contexto})

    def preguntar_agente(self, mensaje, conocimiento, fotos, historial):
        self.llamadas_agente.append(mensaje)
        return self.agente

    def enviar_texto(self, telefono, texto):
        self.textos_enviados.append((telefono, texto))

    def enviar_foto(self, telefono, url):
        pass

    def crear_cita(self, nombre, telefono, motivo, fecha_cita):
        cita = {"inicio": fecha_cita}
        self.citas.append(cita)
        return cita

    def alerta_handoff(self, nombre, telefono, motivo, ultimo_mensaje, fecha):
        self.alertas.append((nombre, telefono, motivo))

    def marcar_leido_y_escribiendo(self, message_id):
        pass

    def enviar_botones(self, telefono, texto, botones):
        pass

    def alerta_error(self, motivo, telefono, ultimo_mensaje, fecha):
        self.alertas_error.append((motivo, telefono))


RESULTADOS = []


def caso(nombre, condicion, detalle=""):
    RESULTADOS.append((nombre, bool(condicion)))
    marca = "PASS" if condicion else "FAIL"
    print(f"[{marca}] {nombre}" + (f" — {detalle}" if detalle and not condicion else ""))


JUEVES_NOCHE = datetime(2026, 11, 13, 4, 19, tzinfo=timezone.utc)  # jueves 21:19 Mazatlán
JUEVES_2130 = datetime(2026, 11, 13, 4, 30, tzinfo=timezone.utc)


def main():
    # (a) El robot lee el modelo sugerido en el error de Google.
    caso("(a) Lee 'gemini-3.8-flash' del error 404 de Google",
         _modelo_sugerido(ERROR_GOOGLE) == "gemini-3.8-flash",
         f"salió: {_modelo_sugerido(ERROR_GOOGLE)!r}")
    caso("(a) Sin sugerencia en el error, devuelve vacío",
         _modelo_sugerido("Gemini devolvió 429: cuota por minuto") == "")

    # (b) Autocuración: modelos retirados en la config, Google sugiere 3.8.
    modelo_viejo, respaldo_viejo = settings.gemini_model, settings.gemini_model_fallback
    clave_vieja = settings.gemini_api_key
    llamar_viejo = gemini_mod._llamar
    try:
        settings.gemini_api_key = "clave-de-prueba"  # _llamar es falso, no sale a internet
        settings.gemini_model = "gemini-2.5-flash"
        settings.gemini_model_fallback = "gemini-2.0-flash"
        gemini_mod._ULTIMO_MODELO_OK = None

        def llamar_falso(modelo, partes):
            if modelo in ("gemini-2.5-flash", "gemini-2.0-flash"):
                raise GeminiError(ERROR_GOOGLE)
            if modelo == "gemini-3.8-flash":
                return "OK"
            raise GeminiError(f"modelo inesperado: {modelo}")

        gemini_mod._llamar = llamar_falso
        texto = generar_texto("Responde solo con la palabra OK.")
        caso("(b) Con modelos retirados, cambia solo a gemini-3.8-flash",
             texto == "OK", f"salió: {texto!r}")
        caso("(b) Recuerda el modelo que funcionó",
             gemini_mod._ULTIMO_MODELO_OK == "gemini-3.8-flash",
             f"salió: {gemini_mod._ULTIMO_MODELO_OK!r}")
    finally:
        settings.gemini_model, settings.gemini_model_fallback = modelo_viejo, respaldo_viejo
        settings.gemini_api_key = clave_vieja
        gemini_mod._llamar = llamar_viejo
        gemini_mod._ULTIMO_MODELO_OK = None

    # (c) "sí gracias" después de un fallo NO confirma la cita.
    logic_mod._CITAS_PENDIENTES.clear()
    agente_lunes = RespuestaAgente(
        respuesta_texto="Perfecto.", nombre="Jose Ramon", motivo="Quiere agendar",
        fecha_cita="2026-11-16T09:00:00", quiere_agendar="si")
    d = DepsV27(agente=agente_lunes)
    atender_mensaje(d, "5216694608263", "Jose Ramon", "Quiero una cita",
                     con_ritmo=False, ahora=JUEVES_NOCHE)
    assert "5216694608263" in logic_mod._CITAS_PENDIENTES, "la propuesta debió guardarse"
    # El robot falló después (Gemini caído) y dijo "dame un momento".
    d.registrar_conversacion(JUEVES_2130.isoformat(), "5216694608263", "robot",
                             "Dame un momento, por favor. Estoy revisando tu mensaje y te atiendo enseguida.",
                             "si", "falla tecnica")
    r = atender_mensaje(d, "5216694608263", "Jose Ramon", "si gracias",
                         con_ritmo=False, ahora=JUEVES_2130)
    caso("(c) 'sí gracias' tras un fallo NO confirma la cita",
         len(d.citas) == 0 and len(d.llamadas_agente) == 2,
         f"citas={d.citas} llamadas={len(d.llamadas_agente)}")
    caso("(c) La propuesta sigue pendiente (no se borró por el 'sí')",
         "5216694608263" in logic_mod._CITAS_PENDIENTES)

    # (d) "sí" justo después de la oferta SÍ confirma.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsV27(agente=agente_lunes)
    atender_mensaje(d, "5216694608263", "Jose Ramon", "Quiero una cita",
                     con_ritmo=False, ahora=JUEVES_NOCHE)
    r = atender_mensaje(d, "5216694608263", "Jose Ramon", "Sí, me va",
                         con_ritmo=False, ahora=JUEVES_2130)
    caso("(d) 'Sí, me va' tras la oferta SÍ crea la cita",
         len(d.citas) == 1 and d.citas[0]["inicio"].startswith("2026-11-16T09:00"),
         f"citas={d.citas}")

    # (e) Gemini falla: queda escrito en Diagnóstico.
    logic_mod._CITAS_PENDIENTES.clear()
    agente_falla = RespuestaAgente.segura("Dame un momento, por favor.", falla_tecnica=True)
    d = DepsV27(agente=agente_falla)
    r = atender_mensaje(d, "5216694608263", "Jose Ramon", "Hola, quiero una cita",
                         con_ritmo=False, ahora=JUEVES_NOCHE)
    caso("(e) Gemini falla: queda en Diagnóstico con el error",
         len(d.diagnosticos) == 1 and d.diagnosticos[0]["componente"] == "gemini"
         and d.diagnosticos[0]["estado"] == "FALLO",
         f"diagnosticos={d.diagnosticos}")

    pasaron = sum(1 for _, ok in RESULTADOS if ok)
    print(f"\n{pasaron}/{len(RESULTADOS)} casos pasaron.")
    raise SystemExit(0 if pasaron == len(RESULTADOS) else 1)


if __name__ == "__main__":
    main()
