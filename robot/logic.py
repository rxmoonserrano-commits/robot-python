"""El cerebro del robot: el flujo completo, paso a paso.

atender_mensaje recibe UN mensaje (o un lote ya juntado) y decide:
frenos (botón global, pausa humana, interruptor por cliente) →
registro → visto y "escribiendo..." → confirmación de cita por texto
→ cambio/cancelación → agente (con estado y revisor) → botones de
confirmación → registro en Conversaciones y Clientes.

La historia de cada versión vive en CHANGELOG.md, no aquí: este
archivo describe lo que el robot hace HOY, no lo que hacía en la v2.

Para probarlo sin internet, atender_mensaje recibe un objeto
`dependencias` con los servicios (Sheets, agente, WhatsApp, Calendar,
correo). En producción son los reales; en las pruebas son falsos.
La lógica es la misma.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .agent import RespuestaAgente, preguntar_agente
from .config import settings
from .estado import estado_cliente
from .negocio import canal_negocio_activo, configuracion, funcion_activa
from .revision import revisar_respuesta
from .registro import aviso as log_aviso
from .ritmo import enviar_con_ritmo, enviar_partes

PAUSA = timedelta(hours=2)

# Botones que se muestran al proponer una cita (id, título).
BOTONES_CITA = [
    ("confirmar_cita", "Confirmar"),
    ("cambiar_hora", "Cambiar hora"),
    ("hablar_persona", "Hablar con persona"),
]

# Citas propuestas esperando que el cliente toque un botón (o diga "sí").
# Viven en memoria Y en la pestaña Propuestas de la hoja (v2.5): si el
# servidor se reinicia, se recuperan al arrancar (ver cargar_propuestas).
_CITAS_PENDIENTES: dict[str, dict] = {}

# (v3.12) La cita "a retomar" tras un cambio de hora con dos citas:
# el cliente toca "Cambiar hora" en una propuesta de dos citas y elige
# cuál cambia; la OTRA se guarda aquí para re-proponerla junto con la
# nueva (antes se perdía y el cliente tenía que volver a explicarla).
# Solo en memoria: si Render se reinicia en medio, el cliente puede
# pedirla de nuevo. Expira con la vigencia de una propuesta (48 h)
# y solo si su fecha sigue en el futuro.
_RETOMAR: dict[str, dict] = {}

def _contiene_aparto(texto: str) -> bool:
    """¿La respuesta le aparta el lugar al cliente?

    (v3.2) La frase del guion es "Te aparto el lugar hasta mañana sin
    compromiso". Si el robot la dice y hay una propuesta activa, el
    apartado queda guardado, para que lo recuerde cuando vuelva.
    """
    normal = re.sub(r"[^a-z0-9 ]+", "", _sin_acentos(texto))
    normal = re.sub(r"\s+", " ", normal).strip()
    return ("aparto el lugar" in normal or "te lo aparto" in normal
            or "lugar apartado" in normal)


def _guardar_memoria(deps: Dependencias, telefono: str, respuesta: RespuestaAgente) -> None:
    """Guarda lo que el agente aprendió del cliente (v3.2). Best-effort.

    La respuesta ya se mandó (o se está mandando): si la hoja falla,
    la memoria se pierde en silencio, pero el cliente nunca se queda
    sin respuesta por culpa de la memoria.
    """
    if not any([respuesta.resumen_cliente, respuesta.interes_cliente,
                respuesta.proxima_accion, respuesta.preferencias]):
        return
    guardar = getattr(deps, "guardar_memoria_cliente", None)
    if guardar is None:
        return
    try:
        guardar(telefono, resumen=respuesta.resumen_cliente,
                interes=respuesta.interes_cliente,
                proxima_accion=respuesta.proxima_accion,
                preferencias=respuesta.preferencias)
    except Exception:
        pass


def _guardar_propuesta(deps: Dependencias, telefono: str, propuesta: dict) -> None:
    """Guarda una propuesta en memoria Y en la hoja (v2.5).

    La hoja es el respaldo: si Render se reinicia de noche, al
    arrancar se recuperan (ver cargar_propuestas) y el cliente puede
    confirmar igual. Si la hoja falla, la memoria sigue valiendo.
    """
    _CITAS_PENDIENTES[telefono] = propuesta
    guardar = getattr(deps, "guardar_propuesta", None)
    if guardar is not None:
        try:
            guardar(telefono, propuesta)
        except Exception:
            pass  # la memoria sigue valiendo; la hoja es respaldo


def _borrar_propuesta(deps: Dependencias, telefono: str) -> None:
    """Borra una propuesta de memoria Y de la hoja (se confirmó, cambió o canceló)."""
    _CITAS_PENDIENTES.pop(telefono, None)
    borrar = getattr(deps, "borrar_propuesta", None)
    if borrar is not None:
        try:
            borrar(telefono)
        except Exception:
            pass


def cargar_propuestas(deps: Dependencias) -> int:
    """Al arrancar el servidor: recupera las propuestas guardadas en la hoja.

    Devuelve cuántas recuperó. Sin esto, un reinicio de Render de noche
    dejaba al cliente con botones que ya no llevaban a ningún lado.
    """
    leer = getattr(deps, "leer_propuestas", None)
    if leer is None:
        return 0
    try:
        filas = leer() or []
    except Exception:
        return 0
    n = 0
    for fila in filas:
        telefono = str(fila.get("telefono", "") or "").strip()
        if not telefono or not str(fila.get("fecha_cita", "") or "").strip():
            continue
        propuesta = {
            k: str(fila.get(k, "") or "")
            for k in ("nombre", "motivo", "fecha_cita", "fecha_bonita", "creado_en")
        }
        # (v3.10) La columna extra_json trae los datos de la otra
        # persona y la segunda cita, si la hay. Vacía o ilegible =
        # propuesta de una cita, como siempre (compatibilidad).
        extra = _parse_extra_propuesta(fila.get("extra_json"))
        propuesta["nombre_paciente"] = extra.get("nombre_paciente", "")
        propuesta["relacion_paciente"] = extra.get("relacion_paciente", "")
        propuesta["numero_paciente"] = extra.get("numero_paciente", "")
        propuesta["profesional"] = extra.get("profesional", "")
        propuesta["cita2"] = extra.get("cita2")
        propuesta["urgencia"] = extra.get("urgencia", "")
        propuesta["tipo"] = extra.get("tipo", "")
        propuesta["cita_id"] = extra.get("cita_id", "")
        propuesta["fecha_vieja"] = extra.get("fecha_vieja", "")
        propuesta["fecha_bonita_vieja"] = extra.get("fecha_bonita_vieja", "")
        propuesta["servicio"] = extra.get("servicio", "")
        propuesta["hora_inicio_vieja"] = extra.get("hora_inicio_vieja", "")
        propuesta["hora_fin_vieja"] = extra.get("hora_fin_vieja", "")
        propuesta["notas_vieja"] = extra.get("notas_vieja", "")
        _CITAS_PENDIENTES[telefono] = propuesta
        n += 1
    return n


def _parse_extra_propuesta(crudo) -> dict:
    """Lee el JSON de la columna extra_json de Propuestas (v3.10).

    Devuelve {"nombre_paciente", "relacion_paciente", "numero_paciente",
    "profesional", "cita2"} con valores seguros. Vacío o ilegible =
    propuesta de una cita para quien escribe, como siempre.
    """
    vacio = {"nombre_paciente": "", "relacion_paciente": "",
             "numero_paciente": "", "profesional": "", "cita2": None,
             "urgencia": "", "tipo": "", "cita_id": "", "fecha_vieja": "",
             "fecha_bonita_vieja": "", "servicio": "", "hora_inicio_vieja": "",
             "hora_fin_vieja": "", "notas_vieja": ""}
    if not crudo:
        return vacio
    try:
        datos = json.loads(str(crudo))
    except (ValueError, TypeError):
        return vacio
    if not isinstance(datos, dict):
        return vacio
    cita2 = datos.get("cita2")
    if isinstance(cita2, dict) and str(cita2.get("fecha_cita") or "").strip():
        cita2_limpia = {
            "motivo": str(cita2.get("motivo") or "").strip(),
            "fecha_cita": str(cita2.get("fecha_cita") or "").strip(),
            "fecha_bonita": str(cita2.get("fecha_bonita") or "").strip(),
            "nombre_paciente": str(cita2.get("nombre_paciente") or "").strip(),
            "relacion_paciente": str(cita2.get("relacion_paciente") or "").strip(),
            "numero_paciente": str(cita2.get("numero_paciente") or "").strip(),
            "profesional": str(cita2.get("profesional") or "").strip(),
        }
    else:
        cita2_limpia = None
    return {
        "nombre_paciente": str(datos.get("nombre_paciente") or "").strip(),
        "relacion_paciente": str(datos.get("relacion_paciente") or "").strip(),
        "numero_paciente": str(datos.get("numero_paciente") or "").strip(),
        "profesional": str(datos.get("profesional") or "").strip(),
        "cita2": cita2_limpia,
        "urgencia": str(datos.get("urgencia") or "").strip(),
        "tipo": str(datos.get("tipo") or "").strip(),
        "cita_id": str(datos.get("cita_id") or "").strip(),
        "fecha_vieja": str(datos.get("fecha_vieja") or "").strip(),
        "fecha_bonita_vieja": str(datos.get("fecha_bonita_vieja") or "").strip(),
        "servicio": str(datos.get("servicio") or "").strip(),
        "hora_inicio_vieja": str(datos.get("hora_inicio_vieja") or "").strip(),
        "hora_fin_vieja": str(datos.get("hora_fin_vieja") or "").strip(),
        "notas_vieja": str(datos.get("notas_vieja") or "").strip(),
    }


def _extra_propuesta_json(propuesta: dict) -> str:
    """Serializa los extras de la propuesta a la columna extra_json.

    Vacío si no hay nada extra (propuesta de una cita para quien
    escribe): las filas viejas y las nuevas simples quedan igual.
    """
    datos = {
        "nombre_paciente": str(propuesta.get("nombre_paciente") or "").strip(),
        "relacion_paciente": str(propuesta.get("relacion_paciente") or "").strip(),
        "numero_paciente": str(propuesta.get("numero_paciente") or "").strip(),
        "profesional": str(propuesta.get("profesional") or "").strip(),
        "cita2": propuesta.get("cita2"),
        # (v3.13) La razón de urgencia viaja en la propuesta para que
        # la cita se marque URGENTE al confirmarse, aunque Render se
        # reinicie entre la oferta y la confirmación.
        "urgencia": str(propuesta.get("urgencia") or "").strip(),
        # (v3.15) El adelanto viaja completo: qué cita se mueve, de
        # cuándo a cuándo, para que el movimiento sobreviva a un
        # reinicio de Render.
        "tipo": str(propuesta.get("tipo") or "").strip(),
        "cita_id": str(propuesta.get("cita_id") or "").strip(),
        "fecha_vieja": str(propuesta.get("fecha_vieja") or "").strip(),
        "fecha_bonita_vieja": str(propuesta.get("fecha_bonita_vieja") or "").strip(),
        "servicio": str(propuesta.get("servicio") or "").strip(),
        "hora_inicio_vieja": str(propuesta.get("hora_inicio_vieja") or "").strip(),
        "hora_fin_vieja": str(propuesta.get("hora_fin_vieja") or "").strip(),
        "notas_vieja": str(propuesta.get("notas_vieja") or "").strip(),
    }
    if not any(v for v in datos.values() if v is not None and v != ""):
        return ""
    return json.dumps(datos, ensure_ascii=False)


# Una propuesta solo se confirma con un "sí" por texto si es reciente
# (48 h). Así un "sí" de otra conversación, meses después, no agenda
# una cita vieja por error.
_VIGENCIA_PROPUESTA = timedelta(hours=48)


def _misma_fecha(a, b) -> bool:
    """¿Dos fechas ISO son el mismo momento?

    (v3.4.8) Para no mandar dos veces los botones de la misma cita:
    si el agente vuelve a proponer la misma fecha que ya está
    pendiente, se contesta solo con texto y la propuesta sigue viva.
    Si algo no se puede leer, devuelve False (mejor mandar botones
    de más que dejar al cliente sin propuesta).
    """
    try:
        fa = _parse_fecha_iso(a)
        fb = _parse_fecha_iso(b)
        if fa is None or fb is None:
            return False
        if fa.tzinfo is None:
            fa = fa.replace(tzinfo=timezone.utc)
        if fb.tzinfo is None:
            fb = fb.replace(tzinfo=timezone.utc)
        return fa == fb
    except (ValueError, TypeError):
        return False


def _propuesta_vigente(propuesta: dict, ahora: datetime) -> bool:
    """¿La propuesta sigue vigente (menos de 48 h)?"""
    creado_en = (propuesta or {}).get("creado_en")
    if not creado_en:
        return True
    try:
        creado = _parse_fecha_iso(creado_en)
        if creado is None:
            return True
        if creado.tzinfo is None:
            creado = creado.replace(tzinfo=timezone.utc)
        return ahora - creado < _VIGENCIA_PROPUESTA
    except (ValueError, TypeError):
        return True


def _cita_como_retomar(propuesta: dict) -> dict:
    """La cita principal de una propuesta, en forma de cita2 (para retomar)."""
    return {
        "motivo": str(propuesta.get("motivo") or "").strip(),
        "fecha_cita": str(propuesta.get("fecha_cita") or "").strip(),
        "fecha_bonita": str(propuesta.get("fecha_bonita") or "").strip(),
        "nombre_paciente": str(propuesta.get("nombre_paciente") or "").strip(),
        "relacion_paciente": str(propuesta.get("relacion_paciente") or "").strip(),
        "numero_paciente": str(propuesta.get("numero_paciente") or "").strip(),
        "profesional": str(propuesta.get("profesional") or "").strip(),
    }


def _tomar_retomar(telefono: str, ahora: datetime) -> dict | None:
    """Saca la cita a retomar de un teléfono, si sigue vigente.

    Vigente = guardada hace menos de 48 h y su fecha sigue en el
    futuro (o hoy). Siempre limpia la entrada: consumida o vencida,
    no se queda pegada a la siguiente conversación.
    """
    entrada = _RETOMAR.pop(telefono, None)
    if not entrada:
        return None
    cita = entrada.get("cita") or {}
    fecha_cita = _parse_fecha_iso(cita.get("fecha_cita"))
    creado = _parse_fecha_iso(entrada.get("creado_en"))
    if fecha_cita is None or creado is None:
        return None
    ahora_n = ahora.replace(tzinfo=None) if ahora.tzinfo else ahora
    creado_n = creado.replace(tzinfo=None) if creado.tzinfo else creado
    if ahora_n - creado_n > _VIGENCIA_PROPUESTA:
        return None
    if fecha_cita.date() < ahora_n.date():
        return None
    return cita


def _sin_acentos(texto: str) -> str:
    """Quita acentos y deja minúsculas: 'sí' → 'si', 'Está' → 'esta'."""
    texto = unicodedata.normalize("NFD", str(texto or ""))
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto.lower().strip()


def _mensajes_previos(
    historial: list[dict] | None, texto_actual: str
) -> list[dict]:
    """Mensajes del historial SIN el actual (si viene al final).

    En producción el mensaje actual ya se registró antes de leer el
    historial, así que viene como última fila; en pruebas la última
    fila ya es previa. Si la última fila coincide con el texto actual,
    se excluye: es el mensaje que se está atendiendo.
    """
    filas = list(historial or [])
    if filas and str(filas[-1].get("mensaje", "")) == texto_actual:
        filas = filas[:-1]
    return filas


def _dias_desde_ultimo_mensaje(
    historial: list[dict] | None, texto_actual: str, ahora: datetime
) -> int | None:
    """Días desde el último mensaje PREVIO al actual, o None si no se sabe.

    (v3.4.2) Para que un cliente que vuelve después de días sea saludado
    recordando de qué hablaban, no como nuevo. Si la fecha no se puede
    leer, devuelve None.
    """
    filas = _mensajes_previos(historial, texto_actual)
    if not filas:
        return None
    try:
        fecha_txt = str(filas[-1].get("fecha", "") or "").strip()
        if not fecha_txt:
            return None
        fecha = _parse_fecha_iso(fecha_txt)
        if fecha is None:
            return None
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        return max(0, (ahora - fecha).days)
    except (ValueError, TypeError):
        return None


def _es_afirmacion(texto: str) -> bool:
    """¿El cliente está diciendo que sí a la cita propuesta?

    Solo frases cortas y claras ("sí", "sí, me va", "claro", "perfecto",
    "confirmo"). Un "sí, mejor el sábado" NO es afirmación: tiene
    "mejor" y pide otro día, así que va al agente, no a confirmar.
    """
    # Se quitan comas y puntos: "Sí, me va" debe leerse como "si me va".
    normal = re.sub(r"[^a-z0-9 ]+", "", _sin_acentos(texto)).strip()
    normal = re.sub(r"\s+", " ", normal)
    if not normal:
        # (v3.4.9) Un emoji de aprobación solo ("👍", "✅") con una
        # propuesta pendiente ES un sí: la gente confirma así todo el
        # tiempo. Solo se llega aquí con propuesta pendiente.
        if any(e in (texto or "") for e in ("👍", "✅", "🆗", "👌")):
            return True
        return False
    if any(p in normal for p in ("mejor", "otro dia", "otra hora", "cambiar", " no ")):
        return False
    if normal.startswith("no"):
        return False
    palabras = normal.split()
    if len(palabras) > 4:
        return False
    if palabras[0] in ("si", "claro", "perfecto", "ok", "confirmo", "va", "sale", "de", "me"):
        return True
    return normal in ("si me va", "si me va esa fecha", "si esta bien", "estoy de acuerdo",
                       "de acuerdo", "me va", "me parece bien", "esta bien")


# (v3.12, Sereno función 03) Confirmación de asistencia: el paciente
# confirma que SÍ vendrá a una cita ya creada ("confirmo", "ahí nos
# vemos"). Frases explícitas, sin acentos; la confirmación de una
# propuesta pendiente sigue siendo el paso 3b.
_FRASES_CONFIRMACION_ASISTENCIA = (
    "confirmo", "confirmado", "ahi nos vemos", "nos vemos el",
    "ahi estare", "ahi estaremos", "claro que si ahi",
)


def _es_confirmacion_asistencia(texto: str) -> bool:
    """¿El mensaje confirma asistencia a una cita ya creada? (v3.12)"""
    normal = _sin_acentos(texto or "").lower()
    return any(f in normal for f in _FRASES_CONFIRMACION_ASISTENCIA)


def _cita_futura_para_confirmar(deps: Dependencias, telefono: str, ahora: datetime):
    """La cita futura más próxima del teléfono en el espejo (v3.12).

    Busca en la pestaña Citas las filas Confirmada/Pendiente de ese
    teléfono con fecha de hoy en adelante. None si no hay: sin cita,
    "confirmo" no es confirmación de asistencia.
    """
    leer = getattr(deps, "leer_citas_espejo", None)
    if leer is None:
        return None
    try:
        filas = leer() or []
    except Exception:
        return None
    hoy = _a_hora_local(ahora).strftime("%Y-%m-%d")
    candidatas = []
    for f in filas:
        if str(f.get("Teléfono", "") or "").strip() != str(telefono).strip():
            continue
        if str(f.get("Estado", "") or "").strip() not in ("Confirmada", "Pendiente"):
            continue
        fecha_dia = str(f.get("Fecha", "") or "")[:10]
        if not fecha_dia or fecha_dia < hoy:
            continue
        candidatas.append(f)
    if not candidatas:
        return None
    candidatas.sort(key=lambda f: (str(f.get("Fecha", ""))[:10],
                                   str(f.get("Hora_inicio", "") or "")))
    return candidatas[0]


def _registrar_confirmacion_asistencia(deps: Dependencias, telefono: str, nombre: str,
                                       fecha: str, cita: dict, con_ritmo: bool = True) -> dict:
    """Registra que el paciente confirmó asistencia y le responde (v3.12).

    La confirmación queda en las Notas del espejo (cuenta en el
    reporte semanal) y el cliente recibe certeza cálida. Best-effort
    en la hoja: la respuesta sale igual.
    """
    fecha_dia = str(cita.get("Fecha", "") or "")[:10]
    hora = str(cita.get("Hora_inicio", "") or "").strip()
    try:
        fecha_bonita = formatear_cita_bonita(f"{fecha_dia}T{hora}:00")
    except (ValueError, TypeError):
        fecha_bonita = f"{fecha_dia} {hora}".strip()
    notas_actuales = str(cita.get("Notas", "") or "").strip()
    marca = f"Paciente confirmó asistencia {str(fecha or '')[:10]}"
    notas_nuevas = f"{notas_actuales} | {marca}" if notas_actuales else marca
    try:
        deps.actualizar_cita_espejo(telefono, fecha_dia, notas=notas_nuevas)
    except Exception:
        pass
    mensaje = (
        f"¡Perfecto! Quedó confirmada tu asistencia para el {fecha_bonita}. "
        "Te esperamos."
    )
    enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
    deps.registrar_conversacion(
        fecha, telefono, "robot", mensaje, "si", "confirmacion asistencia")
    return {"respondio": True, "handoff": False, "confirmacion_asistencia": True}


def _tiene_fecha_especifica(texto: str) -> bool:
    """¿El mensaje trae un día o una hora concreta?

    (v3.4.9) Para no preguntarle al cliente otra vez lo que ya dijo:
    "mejor el viernes a las 10" trae día y hora; "prefiero otra" no.
    """
    normal = _sin_acentos(texto)
    if re.search(r"\b(lunes|martes|miercoles|jueves|viernes|sabado|domingo)\b", normal):
        return True
    if re.search(r"\b(manana|hoy|pasado manana)\b", normal):
        return True
    if re.search(r"\b\d{1,2}(:\d{2})?\s*(am|pm|h|hrs)?\b", normal):
        return True
    return False


def _extraer_telefono(texto: str, telefono_propio: str = "") -> str:
    """Saca el primer número de teléfono que trae un mensaje.

    (v3.4.9) Para el número de registro: si el cliente dice "regístralo
    al 6671234567", ese número se guarda en la propuesta. Devuelve ""
    si no hay ninguno, o si es el mismo número del chat (con o sin
    código de país).
    """
    propio = re.sub(r"\D", "", str(telefono_propio or ""))
    for numero in re.findall(r"\+?\d[\d\s\-()]{8,}\d", str(texto or "")):
        digitos = re.sub(r"\D", "", numero)
        if len(digitos) >= 10 and digitos != propio and not propio.endswith(digitos) and not digitos.endswith(propio):
            return numero.strip()
    return ""


# (v3.3) Urgencia: si el cliente dice que es urgente o que le duele,
# el robot no entretiene con preguntas: pasa a una persona en ese
# momento. Se decide por palabras, sin llamar a la IA (rápido y
# seguro). La lista es de una clínica, pero las palabras de urgencia
# ("urgente", "emergencia") valen para cualquier negocio.
_MOTIVO_URGENCIA = "Urgencia del cliente"
_PALABRAS_URGENCIA = (
    "urgente", "urgencia", "emergencia", "me duele", "dolor fuerte",
    "sangrando", "sangre", "hinchado", "hinchada", "se me cayo un diente",
    "se me rompio", "no puedo esperar",
)


def _es_urgencia(texto: str) -> bool:
    """¿El cliente dice que es urgente o que le duele?

    "¿duele la limpieza?" NO es urgencia (pregunta si duele, no dice
    que le duela); "me duele la muela" SÍ lo es.
    """
    normal = re.sub(r"[^a-z0-9 ]+", "", _sin_acentos(texto)).strip()
    normal = re.sub(r"\s+", " ", normal)
    return any(p in normal for p in _PALABRAS_URGENCIA)


# (v3.8) Con el interruptor por cliente apagado ("robot apagado para
# este cliente"), el mensaje igual SE LEE: si es una urgencia, una
# queja o un pedido explícito de persona, se resuelve la mecánica de
# handoff —correo al dueño y caso marcado en Clientes— SIN contestarle
# al paciente (la IA está apagada). Las dudas normales solo quedan
# registradas, como siempre. Decisión del dueño: "alerta solo en
# casos graves".
_PALABRAS_QUEJA = (
    "queja", "reclamo", "reclamar", "reclamacion", "pesimo", "horrible",
    "mal servicio", "no me atendieron", "tardaron", "estafa",
    "devolverme el dinero", "nunca me contestaron", "me dejaron colgado",
)

_PALABRAS_HUMANO = (
    "hablar con una persona", "hablar con alguien", "quiero hablar con",
    "pasame con", "pase con una persona", "una persona real",
)


def _normalizar_para_reglas(texto: str) -> str:
    """Texto en minúsculas, sin acentos ni puntuación, con espacios
    simples — igual que usan _es_urgencia y _quiere_agendar_ya."""
    normal = re.sub(r"[^a-z0-9 ]+", "", _sin_acentos(texto)).strip()
    return re.sub(r"\s+", " ", normal)


def _es_queja(texto: str) -> bool:
    """¿El cliente se está quejando (no solo hace una pregunta)?"""
    normal = _normalizar_para_reglas(texto)
    return any(p in normal for p in _PALABRAS_QUEJA)


def _pide_hablar_con_persona(texto: str) -> bool:
    """¿Pide con sus palabras hablar con una persona?"""
    normal = _normalizar_para_reglas(texto)
    return any(p in normal for p in _PALABRAS_HUMANO)


def _motivo_handoff_en_silencio(texto: str) -> str:
    """Motivo de handoff para un chat con la IA apagada, o "" si es
    una duda normal (solo se registra, sin correo).

    Es la regla "en cualquier caso siempre lee y resuelve el
    handoff": la IA no contesta, pero el sistema revisa el mensaje
    y, si es grave (urgencia, queja o pedido de persona), avisa.
    """
    if _es_urgencia(texto):
        return f"{_MOTIVO_URGENCIA} (IA apagada): {texto[:120]}"
    if _es_queja(texto):
        return f"Queja del cliente (IA apagada): {texto[:120]}"
    if _pide_hablar_con_persona(texto):
        return f"El cliente pidió una persona (IA apagada): {texto[:120]}"
    return ""


# (v3.3) Quiere agendar YA: el cliente pidió una cita con sus propias
# palabras ("quiero una cita", "agéndame"). No es lo mismo que una
# oferta del robot: aquí el cliente ya decidió, y el dueño debe
# enterarse en el momento (alerta de lead caliente).
_PALABRAS_QUIERE_AGENDAR = (
    "quiero una cita", "quiero agendar", "agendame", "me agendo",
    "hazme una cita", "me haces una cita", "quiero reservar",
    "reservame", "reserva una cita", "reservar una cita",
    "agendar una cita", "hacer una cita", "quiero cita",
    # (v3.10) Pedir disponibilidad o agendar para otra persona
    # también es querer agendar: "¿qué días tienes disponibles el
    # martes para mí y el miércoles para mi hermana?" no trae
    # ninguna de las frases de arriba y en vivo no generó botones.
    "que dias tienes", "dias tienes disponibles",
    "cita para mi", "cita para su", "cita para ella", "cita para el",
    "reservar para", "agendar para", "apartar para",
    "puedo agendar", "puedo reservar",
    "quiero apartar", "apartame",
)


def _quiere_agendar_ya(texto: str) -> bool:
    """¿El cliente pidió agendar con sus propias palabras?"""
    normal = re.sub(r"[^a-z0-9 ]+", "", _sin_acentos(texto)).strip()
    normal = re.sub(r"\s+", " ", normal)
    return any(p in normal for p in _PALABRAS_QUIERE_AGENDAR)


# (v3.11) Días de la semana para respetar el día que el cliente pide.
# La red de seguridad antes proponía el primer hueco libre (la próxima
# apertura) ignorando el día mencionado: pedir "el martes" y recibir
# una propuesta para el lunes es justo lo que Jose vio en vivo el
# 2026-11-22. Ahora el día pedido manda.
_DIAS_SEMANA = {
    "lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3,
    "viernes": 4, "sabado": 5, "domingo": 6,
}

# Otras personas para las que se puede pedir cita ("para mi hermana").
_RELACIONES = (
    "hermana", "hermano", "mama", "papa", "esposa", "esposo",
    "hija", "hijo", "amigo", "amiga", "novia", "novio", "familiar",
    "cuñada", "cuñado", "abuelo", "abuela",
)


def _dias_pedidos(texto: str) -> list[int]:
    """Días de la semana mencionados, en orden de aparición (v3.11).

    "el martes para mí y el miércoles para mi hermana" → [1, 2].
    Se busca por palabras completas, sin acentos: "martes" no cuenta
    dentro de otra palabra.
    """
    normal = re.sub(r"[^a-z0-9 ]+", "", _sin_acentos(texto)).strip()
    normal = re.sub(r"\s+", " ", normal)
    vistos: list[int] = []
    for palabra in normal.split():
        dia = _DIAS_SEMANA.get(palabra)
        if dia is not None and dia not in vistos:
            vistos.append(dia)
    return vistos


def _relacion_pedida(texto: str) -> str:
    """La otra persona mencionada ("para mi hermana" → "hermana")."""
    normal = _normalizar_para_reglas(texto)
    for rel in _RELACIONES:
        if re.search(rf"\b{rel}\b", normal):
            return rel
    return ""


def _hueco_en_dia(huecos, weekday: int, ahora: datetime):
    """Primer hueco ISO que cae en ese día de la semana (v3.11).

    Devuelve None si ningún hueco cae en ese día (quien llama decide:
    próxima apertura en esa fecha o después, nunca otro día a ciegas).
    """
    if not huecos:
        return None
    ahora_local = _a_hora_local(ahora)
    for iso in huecos:
        try:
            dt = _parse_fecha_iso(iso)
            if dt is None:
                continue
            local = _a_hora_local(dt)
            if local.weekday() == weekday and local >= ahora_local:
                return iso
        except Exception:
            continue
    return None


def _proxima_fecha_dia(weekday: int, ahora: datetime) -> datetime:
    """Medianoche local del próximo día con ese weekday (hoy cuenta)."""
    local = _a_hora_local(ahora)
    delta = (weekday - local.weekday()) % 7
    return (local + timedelta(days=delta)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _huecos_amplios(deps, conocimiento, ahora):
    """Huecos con rango amplio, para cuando el cliente pide días concretos.

    Los fakes viejos de las pruebas solo aceptan (conocimiento, ahora):
    si el deps no acepta cantidad/dias, se cae al llamado de siempre.
    """
    try:
        return deps.proximos_huecos_libres(
            conocimiento, ahora, cantidad=12, dias=8
        )
    except TypeError:
        try:
            return deps.proximos_huecos_libres(conocimiento, ahora)
        except Exception:
            return None
    except Exception:
        return None


def _huecos_pro_amplios(deps, conocimiento, ahora):
    """Huecos con profesional en rango amplio, para días concretos (v3.12).

    Misma idea que _huecos_amplios: si el deps no acepta cantidad/dias,
    se cae al llamado de siempre. Sin agenda por profesional -> [].
    """
    try:
        return deps.proximos_huecos_profesionales(
            conocimiento, ahora, cantidad=12, dias=8
        )
    except TypeError:
        try:
            return deps.proximos_huecos_profesionales(conocimiento, ahora)
        except Exception:
            return []
    except Exception:
        return []


def _profesional_de_fecha(fecha_iso, prof_por_iso) -> str:
    """Profesional del hueco que coincide con esa fecha (v3.12).

    Compara por instante, no por texto: la fecha que trae el agente
    puede venir en otro formato que el ISO del hueco. "" si no hay
    coincidencia (la cita queda con "Equipo de la clínica").
    """
    if not prof_por_iso or not fecha_iso:
        return ""
    try:
        objetivo = _parse_fecha_iso(str(fecha_iso))
        if objetivo is None:
            return ""
        objetivo_local = _a_hora_local(objetivo)
    except Exception:
        return ""
    for iso, nombre in prof_por_iso.items():
        try:
            dt = _parse_fecha_iso(iso)
            if dt is not None and _a_hora_local(dt) == objetivo_local:
                return str(nombre or "").strip()
        except Exception:
            continue
    return ""


def _con_profesional(nombre: str) -> str:
    """' con la Dra. Ruiz' / ' con el Dr. Santos' (v3.12).

    El artículo según el prefijo: Dra. → la, Dr. → el, sin prefijo
    conocido → sin artículo. "" si no hay profesional.
    """
    nombre = str(nombre or "").strip()
    if not nombre:
        return ""
    if nombre.lower().startswith("dra."):
        return f" con la {nombre}"
    if nombre.lower().startswith("dr."):
        return f" con el {nombre}"
    return f" con {nombre}"


def _fila_espejo(propuesta: dict, telefono: str, nombre_cita: str,
                 duracion: int, estado: str, ahora: str,
                 profesional: str = "", urgencia: str = "") -> dict:
    """Fila para la pestaña Citas (espejo de solo lectura, v3.9).

    La fecha/hora salen de la fecha_cita ISO de la propuesta; si no
    se puede leer, quedan vacías y el resto de la fila se guarda igual.
    (v3.12) `profesional` viene de la agenda por profesional; sin
    dato queda "Equipo de la clínica", como siempre.
    (v3.13) `urgencia` es la razón de la urgencia (o "" si no lo es):
    la columna Urgencia queda en SI/NO y las Notas llevan el porqué.
    """
    fecha_iso = str(propuesta.get("fecha_cita", "") or "")
    try:
        inicio = _parse_fecha_iso(fecha_iso)
        if inicio is None:
            raise ValueError("fecha inválida")
        hora_inicio = inicio.strftime("%H:%M")
        hora_fin = (inicio + timedelta(minutes=duracion)).strftime("%H:%M")
        fecha_dia = inicio.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        hora_inicio = hora_fin = ""
        fecha_dia = fecha_iso[:10]
    _urg = str(urgencia or "").strip()
    _notas = f"Paciente: {nombre_cita}" if nombre_cita else ""
    if _urg:
        _notas = f"{_notas} | URGENTE: {_urg}" if _notas else f"URGENTE: {_urg}"
    return {
        "ID_Cita": f"C-{datetime.now().strftime('%Y%m%d%H%M%S')}-{str(telefono)[-4:]}",
        "ID_Paciente": "",
        "Teléfono": telefono,
        "Servicio": str(propuesta.get("motivo", "") or ""),
        "Profesional": str(profesional or "").strip() or "Equipo de la clínica",
        "Fecha": fecha_dia,
        "Hora_inicio": hora_inicio,
        "Hora_fin": hora_fin,
        "Estado": estado,
        "Origen": "WhatsApp",
        "Recordatorio_enviado": "-",
        "Confirmado": "Sí" if estado == "Confirmada" else "No",
        "Notas": _notas,
        "Creado_por": "Asistente",
        "Última_actualización": str(ahora or "")[:10],
        "Urgencia": "SI" if _urg else "NO",
    }


# (v3.10) Tope de citas por número: la suya y la de otra persona.
# Para que nadie inunde el calendario reservando sin parar.
MAX_CITAS_POR_NUMERO = 2


def _corregir_fecha_propuesta(fecha_cita, conocimiento, ahora, deps, huecos):
    """Valida y corrige una fecha propuesta (v3.10, extraída del paso 9).

    Si cae fuera de horario o en el pasado, se corrige a la próxima
    apertura (en la fecha pedida o después). Si esa hora está ocupada,
    se usa el primer hueco libre real. Devuelve la fecha final en ISO,
    o None si no hay fecha válida (no se propone nada).
    """
    fecha_dt = None
    try:
        fecha_dt = _parse_fecha_iso(fecha_cita)
        if fecha_dt is None:
            raise ValueError(f"Fecha no legible: {fecha_cita!r}")
        local_dt = _a_hora_local(fecha_dt)
        horarios = horarios_por_dia(conocimiento)
        if not horarios:
            # Sin filas de horario en la hoja, no hay contra qué
            # validar: se confía en el agente (como siempre).
            valida = local_dt > _a_hora_local(ahora)
        else:
            horas = horarios.get(local_dt.weekday())
            valida = (
                horas is not None
                and horas[0] <= local_dt.hour * 60 + local_dt.minute < horas[1]
                and local_dt > _a_hora_local(ahora)
            )
    except (ValueError, TypeError):
        valida = False
    if not valida:
        # (v3.4.10) La corrección busca la apertura en la fecha
        # pedida o después, no desde ahora: pedir domingo y recibir
        # "mañana jueves" no tiene sentido.
        proxima_valida = proxima_apertura(conocimiento, ahora, desde=fecha_dt)
        if proxima_valida is not None:
            fecha_cita = proxima_valida.isoformat()
        else:
            return None
    # (v3.4.9) La fecha propuesta también se revisa contra el
    # calendario: si esa hora ya está ocupada, se usa el primer
    # hueco libre real. Así la confirmación no falla con "esa hora
    # ya se ocupó" por una fecha que el agente calculó.
    try:
        _verificar_libre = getattr(deps, "hora_libre", lambda f: True)
        if not _verificar_libre(fecha_cita) and huecos:
            fecha_cita = huecos[0]
    except Exception:
        pass  # sin calendario no se bloquea la propuesta
    return fecha_cita


def _citas_activas_telefono(deps, telefono: str, ahora: datetime) -> int:
    """Citas activas (Confirmada/Pendiente a futuro) de un teléfono (v3.10).

    El espejo de Citas es la fuente; si no se puede leer, se cae a
    la fila de Clientes (una cita futura agendada cuenta como 1).
    Best-effort: ante cualquier duda, devuelve 0 y no bloquea.
    """
    try:
        leer = getattr(deps, "leer_citas_espejo", None)
        if leer is not None:
            filas = leer() or []
            hoy = _a_hora_local(ahora).date().isoformat()
            n = 0
            for f in filas:
                if str(f.get("Teléfono", "") or "").strip() != str(telefono).strip():
                    continue
                estado = str(f.get("Estado", "") or "").strip()
                if estado not in ("Confirmada", "Pendiente"):
                    continue
                fecha = str(f.get("Fecha", "") or "")[:10]
                if fecha and fecha >= hoy:
                    n += 1
            return n
    except Exception:
        pass
    # Respaldo: la fila de Clientes (una sola cita por teléfono).
    try:
        leer_cliente_fn = getattr(deps, "leer_cliente", lambda t: None)
        fila = leer_cliente_fn(telefono) or {}
        if _cita_es_futura(fila, ahora):
            return 1
    except Exception:
        pass
    return 0


def _pregunta_datos_citas(info: list[dict]) -> str:
    """Pregunta de datos post-confirmación (v3.10). Una sola, cálida.

    `info`: lista de dicts con es_tercero, relacion, falta_nombre,
    falta_numero (una por cita creada). Para una sola cita del dueño
    se conservan los textos históricos de la v3.4.11.
    """
    dueno_nombre = any(c["falta_nombre"] for c in info if not c["es_tercero"])
    dueno_numero = any(c["falta_numero"] for c in info if not c["es_tercero"])
    terceros = [c for c in info if c["es_tercero"]]
    if len(info) == 1 and not terceros:
        # Textos históricos (v3.4.11): no cambiarlos.
        if dueno_nombre and dueno_numero:
            return ("Para dejarte bien registrado, ¿me das tu nombre "
                    "completo y a qué número lo registro?")
        if dueno_nombre:
            return "Para dejarte bien registrado, ¿me das tu nombre completo?"
        if dueno_numero:
            return "¿A qué número lo registro?"
        return ""
    if len(info) == 1:
        c = terceros[0]
        rel = c["relacion"]
        if c["falta_nombre"] and c["falta_numero"]:
            return (f"Para dejarla bien registrada, ¿me das el nombre "
                    f"completo de {rel} y a qué número la registro?")
        if c["falta_nombre"]:
            return f"¿Me das el nombre completo de {rel}?"
        if c["falta_numero"]:
            return f"¿A qué número registro la cita de {rel}?"
        return ""
    partes = []
    if dueno_nombre and dueno_numero:
        partes.append("tu nombre completo y a qué número registro la tuya")
    elif dueno_nombre:
        partes.append("tu nombre completo")
    elif dueno_numero:
        partes.append("a qué número registro la tuya")
    for c in terceros:
        rel = c["relacion"]
        if c["falta_nombre"] and c["falta_numero"]:
            partes.append(f"el nombre completo de {rel} y a qué número la registro")
        elif c["falta_nombre"]:
            partes.append(f"el nombre completo de {rel}")
        elif c["falta_numero"]:
            partes.append(f"a qué número registro la cita de {rel}")
    if not partes:
        return ""
    return "Para dejarlas bien registradas, ¿me das " + "? ¿Y ".join(partes) + "?"


def _guardar_datos_paciente(deps, telefono: str, nombre_paciente: str,
                            numero_paciente: str) -> None:
    """Guarda los datos de la otra persona en la cita espejo (v3.10).

    Busca la cita Confirmada más reciente del teléfono y le pone las
    Notas ("Paciente: X, registro: Y"), para que el dueño los vea.
    Best-effort: nunca rompe la respuesta al cliente.
    """
    try:
        leer = getattr(deps, "leer_citas_espejo", None)
        actualizar = getattr(deps, "actualizar_notas_cita", None)
        if leer is None or actualizar is None:
            return
        filas = [f for f in (leer() or [])
                 if str(f.get("Teléfono", "") or "").strip() == str(telefono).strip()
                 and str(f.get("Estado", "") or "").strip() == "Confirmada"]
        if not filas:
            return
        ultima = max(filas, key=lambda f: str(f.get("Fecha", "") or ""))
        notas = str(ultima.get("Notas", "") or "").strip()
        partes = [p for p in (nombre_paciente, numero_paciente) if p]
        nuevo = ", ".join(partes)
        if nuevo and nuevo not in notas:
            notas = f"{notas} | {nuevo}" if notas else nuevo
        actualizar(telefono, str(ultima.get("Fecha", "") or ""), notas)
    except Exception:
        pass


def _texto_urgencia_fijo(abierto: bool) -> str:
    """Texto de urgencia de respaldo (v3.14): solo si la IA falla.

    La respuesta normal la compone la IA (pensada para ese cliente);
    este texto existe para que una urgencia nunca se quede sin
    respuesta por una falla de Gemini. Personalizable con
    `mensaje_urgencia` y `mensaje_urgencia_fuera_horario` en
    Configuración.
    """
    try:
        _mensaje = (configuracion().get("mensaje_urgencia") or "").strip()
    except Exception:
        _mensaje = ""
    if not _mensaje:
        _mensaje = (
            "Si sientes que es una urgencia médica, busca atención "
            "inmediata. Claro, es urgente. Te paso con una persona "
            "del negocio de inmediato, te atienden lo antes posible."
        )
    if not abierto:
        try:
            _aviso = (configuracion().get("mensaje_urgencia_fuera_horario") or "").strip()
        except Exception:
            _aviso = ""
        if not _aviso:
            _aviso = (
                "Estamos fuera de horario, así que puede que tarden "
                "un poco en responderte; en cuanto abran, te atenderán."
            )
        _mensaje = _mensaje.rstrip() + " " + _aviso
    return _mensaje


def _normalizar_nombre(texto: str) -> str:
    """Minúsculas, sin acentos, espacios simples (para comparar nombres)."""
    normal = _sin_acentos(str(texto or ""))
    normal = re.sub(r"[^a-z0-9 ]+", " ", normal)
    return re.sub(r"\s+", " ", normal).strip()


def _paciente_de_notas(notas: str) -> str:
    """El paciente nombrado en las Notas del espejo ("Paciente: X"), o ""."""
    m = re.search(r"paciente\s*:\s*([^|]+)", str(notas or ""), re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _mismo_paciente(paciente: str, nombre: str) -> bool:
    """¿La cita nombrada es de quien escribe? Compara por nombre.

    Sin nombre conocido no se puede afirmar: False (conservador).
    """
    p = _normalizar_nombre(paciente)
    n = _normalizar_nombre(nombre)
    if not p or not n:
        return False
    if p == n or p in n or n in p:
        return True
    return p.split()[0] == n.split()[0]


def _cita_propia_mas_cercana(deps: Dependencias, telefono: str, nombre: str,
                             ahora: datetime) -> dict | None:
    """La cita futura más cercana de quien escribe (v3.15).

    Lee el espejo de Citas: citas Confirmada/Pendiente a futuro con
    este teléfono. Si las Notas nombran a OTRO paciente ("Paciente:
    su hermana"), esa cita no es suya y se salta. Sin nombre conocido
    solo cuentan las citas sin paciente nombrado. Devuelve la fila
    del espejo (dict) o None.
    """
    try:
        leer = getattr(deps, "leer_citas_espejo", None)
        filas = leer() if leer is not None else []
    except Exception:
        return None
    if not filas:
        return None
    hoy = _a_hora_local(ahora).date().isoformat()
    candidatas = []
    for f in filas:
        if str(f.get("Teléfono", "") or "").strip() != str(telefono).strip():
            continue
        if str(f.get("Estado", "") or "").strip() not in ("Confirmada", "Pendiente"):
            continue
        fecha = str(f.get("Fecha", "") or "")[:10]
        if not fecha or fecha < hoy:
            continue
        paciente = _paciente_de_notas(str(f.get("Notas", "") or ""))
        if paciente and not _mismo_paciente(paciente, nombre):
            continue
        candidatas.append(f)
    if not candidatas:
        return None
    candidatas.sort(key=lambda f: (str(f.get("Fecha", "") or "")[:10],
                                   str(f.get("Hora_inicio", "") or "")))
    return candidatas[0]


def _plan_urgencia(deps: Dependencias, telefono: str, nombre: str,
                   conocimiento: list[dict], ahora: datetime) -> dict:
    """Decide qué propone la urgencia (v3.15): adelantar, nueva o nada.

    - "adelanto": el cliente tiene una cita propia futura y la primera
      hora libre es ANTES de esa cita → se le propone moverla.
    - "nueva": no tiene cita propia → cita nueva urgente (la urgencia
      salta el tope de 2 citas, v3.14.1).
    - "ninguna": agenda apagada, ya hay propuesta, sin huecos, o la
      cita propia ya está en la primera hora disponible (adelantar
      no gana nada: el handoff sale igual y la IA lo explica).
    """
    if not funcion_activa("agendar"):
        return {"tipo": "ninguna", "motivo": "agenda apagada"}
    if _CITAS_PENDIENTES.get(telefono):
        return {"tipo": "ninguna", "motivo": "ya hay propuesta pendiente"}
    try:
        huecos = deps.proximos_huecos_libres(conocimiento, ahora)
    except Exception:
        huecos = None
    huecos_pro = []
    try:
        huecos_pro = deps.proximos_huecos_profesionales(conocimiento, ahora) or []
    except Exception:
        huecos_pro = []
    prof_por_iso = {
        h["inicio"]: str(h.get("profesional") or "")
        for h in huecos_pro if h.get("inicio")
    }
    if huecos_pro:
        huecos = [h["inicio"] for h in huecos_pro]
    if not huecos:
        return {"tipo": "ninguna", "motivo": "sin huecos"}
    fecha_cita = huecos[0]
    try:
        fecha_bonita = formatear_cita_bonita(fecha_cita)
        inicio_nuevo = _parse_fecha_iso(fecha_cita)
        if inicio_nuevo is None:
            raise ValueError("fecha inválida")
        clave_nueva = (inicio_nuevo.strftime("%Y-%m-%d"), inicio_nuevo.strftime("%H:%M"))
    except (ValueError, TypeError):
        return {"tipo": "ninguna", "motivo": "fecha no legible"}
    profesional = _profesional_de_fecha(fecha_cita, prof_por_iso)
    propia = _cita_propia_mas_cercana(deps, telefono, nombre, ahora)
    if propia:
        clave_vieja = (str(propia.get("Fecha", "") or "")[:10],
                       str(propia.get("Hora_inicio", "") or "")[:5])
        fecha_vieja_iso = f"{clave_vieja[0]}T{clave_vieja[1]}:00"
        try:
            fecha_bonita_vieja = formatear_cita_bonita(fecha_vieja_iso)
        except (ValueError, TypeError):
            fecha_bonita_vieja = clave_vieja[0]
        if clave_nueva < clave_vieja:
            return {
                "tipo": "adelanto",
                "cita": propia,
                "fecha_cita": fecha_cita,
                "fecha_bonita": fecha_bonita,
                "profesional": profesional,
                "fecha_vieja": fecha_vieja_iso,
                "fecha_bonita_vieja": fecha_bonita_vieja,
            }
        return {
            "tipo": "ninguna",
            "motivo": "su cita ya está en la primera hora disponible",
            "cita": propia,
            "fecha_bonita_vieja": fecha_bonita_vieja,
        }
    return {
        "tipo": "nueva",
        "fecha_cita": fecha_cita,
        "fecha_bonita": fecha_bonita,
        "profesional": profesional,
    }


def _hecho_del_plan(plan: dict, deps: Dependencias, telefono: str,
                    ahora: datetime) -> str:
    """El hecho del plan de urgencia para el marco de la IA (v3.15).

    La IA no decide el plan: lo dice con naturalidad. El código
    ejecuta (botones, movimiento, CRM, correo).
    """
    if plan.get("tipo") == "adelanto":
        return (
            f"El cliente ya tiene una cita el {plan.get('fecha_bonita_vieja', '')}. "
            f"El sistema le va a proponer adelantarla a {plan.get('fecha_bonita', '')}"
            f"{_con_profesional(str(plan.get('profesional') or '').strip())} "
            "por la urgencia. Dilo con naturalidad, en una frase."
        )
    if plan.get("tipo") == "nueva":
        n = _citas_activas_telefono(deps, telefono, ahora)
        extra = f" El cliente ya tiene {n} citas registradas con este número." if n else ""
        return (
            f"El sistema le va a proponer una cita nueva para el "
            f"{plan.get('fecha_bonita', '')}"
            f"{_con_profesional(str(plan.get('profesional') or '').strip())}."
            f"{extra} Dilo con naturalidad, en una frase."
        )
    motivo = str(plan.get("motivo") or "sin huecos")
    fecha_vieja = str(plan.get("fecha_bonita_vieja") or "").strip()
    extra = f" Su cita más cercana es el {fecha_vieja}." if fecha_vieja else ""
    return (
        f"No hay cita nueva que proponer ({motivo}).{extra} "
        "Dilo con naturalidad, en una frase."
    )


def _propuesta_cita_urgente(deps: Dependencias, telefono: str, nombre: str,
                            texto: str, conocimiento: list[dict],
                            ahora: datetime, razon: str,
                            plan: dict | None = None) -> dict | None:
    """(v3.13) Guarda la propuesta de cita urgente con botones.

    Al detectar una urgencia, el robot además del handoff ofrece
    agendar la primera hora disponible. La propuesta viaja marcada
    con `urgencia` (la razón): al confirmarse, la cita queda
    catalogada como URGENTE en el CRM y el dueño recibe el correo
    con el porqué. Devuelve la propuesta guardada, o None si no se
    pudo ofrecer (agenda apagada, ya hay propuesta o sin huecos): en
    esos casos el handoff sale igual, sin botones.

    (v3.14.1) La urgencia SIEMPRE propone fecha si hay hueco: salta
    el tope de citas por número. Un cliente con dolor no se queda
    sin oferta; el dueño ve el correo de urgencia y puede reagendar.

    (v3.15) Si el cliente ya tiene una cita propia futura y la
    primera hora libre es antes, la propuesta es ADELANTO: mover
    esa cita, no crear otra. El plan lo decide `_plan_urgencia`
    antes de llamar a la IA; aquí solo se guarda.
    """
    if plan is None:
        plan = _plan_urgencia(deps, telefono, nombre, conocimiento, ahora)
    if plan.get("tipo") == "ninguna":
        return None
    if plan["tipo"] == "adelanto":
        cita = plan["cita"]
        propuesta_dict = {
            "nombre": nombre,
            "motivo": texto[:120],
            "fecha_cita": plan["fecha_cita"],
            "fecha_bonita": plan["fecha_bonita"],
            "creado_en": ahora.isoformat(),
            "profesional": plan.get("profesional", ""),
            "nombre_paciente": "",
            "relacion_paciente": "",
            "numero_paciente": "",
            "cita2": None,
            "urgencia": razon,
            "tipo": "adelanto",
            "cita_id": str(cita.get("ID_Cita") or ""),
            "fecha_vieja": plan["fecha_vieja"],
            "fecha_bonita_vieja": plan["fecha_bonita_vieja"],
            "servicio": str(cita.get("Servicio") or ""),
            "hora_inicio_vieja": str(cita.get("Hora_inicio") or ""),
            "hora_fin_vieja": str(cita.get("Hora_fin") or ""),
            "notas_vieja": str(cita.get("Notas") or ""),
        }
    else:
        propuesta_dict = {
            "nombre": nombre,
            "motivo": texto[:120],
            "fecha_cita": plan["fecha_cita"],
            "fecha_bonita": plan["fecha_bonita"],
            "creado_en": ahora.isoformat(),
            "profesional": plan.get("profesional", ""),
            "nombre_paciente": "",
            "relacion_paciente": "",
            "numero_paciente": "",
            "cita2": None,
            "urgencia": razon,
        }
    propuesta_dict["extra_json"] = _extra_propuesta_json(propuesta_dict)
    _guardar_propuesta(deps, telefono, propuesta_dict)
    return propuesta_dict


def _duracion_entre(hora_inicio, hora_fin) -> int:
    """Minutos entre dos horas "HH:MM" del espejo. Default 60."""
    try:
        hi = str(hora_inicio or "")[:5]
        hf = str(hora_fin or "")[:5]
        h1, m1 = int(hi[:2]), int(hi[3:5])
        h2, m2 = int(hf[:2]), int(hf[3:5])
        minutos = (h2 * 60 + m2) - (h1 * 60 + m1)
        return minutos if 0 < minutos <= 480 else 60
    except (ValueError, TypeError):
        return 60


def _confirmar_adelanto(deps: Dependencias, telefono: str, nombre: str,
                        fecha: str, con_ritmo: bool = True,
                        ahora: datetime | None = None) -> dict:
    """Mueve la cita existente a la hora nueva (v3.15).

    La usan el botón "Adelantar cita" y el "sí" por texto. Primero
    crea la cita nueva (si falla, la vieja queda intacta), luego
    cancela la vieja y mueve la fila del espejo. La cita queda
    marcada URGENTE y el dueño recibe el correo con el porqué.
    """
    propuesta = _CITAS_PENDIENTES.get(telefono)
    if not propuesta or propuesta.get("tipo") != "adelanto":
        return {"respondio": True, "motivo": "sin adelanto", "handoff": False}
    ahora = ahora or datetime.now(timezone.utc)
    nueva_fecha = propuesta["fecha_cita"]
    razon = str(propuesta.get("urgencia") or "")
    servicio = str(propuesta.get("servicio") or propuesta.get("motivo") or "")
    try:
        libre = deps.hora_libre(nueva_fecha)
    except Exception:
        libre = True
    if not libre:
        _borrar_propuesta(deps, telefono)
        mensaje = ("Esa hora ya se ocupó. Te paso con una persona para "
                   "acomodarte lo antes posible.")
        enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
        deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", "adelanto ocupado")
        _avisar_por_correo(deps.alerta_handoff, nombre, telefono, razon,
                           "(adelanto ocupado)", fecha)
        return {"respondio": True, "motivo": "hora ocupada", "handoff": True}
    nota = (f"URGENTE: {razon} | Adelantada desde "
            f"{propuesta.get('fecha_bonita_vieja', '')}").strip(" |")
    try:
        resultado = deps.crear_cita(nombre, telefono, servicio, nueva_fecha, nota=nota)
    except Exception as exc:
        resultado = {"error": str(exc)}
    if not resultado or resultado.get("error"):
        _borrar_propuesta(deps, telefono)
        mensaje = ("No pude adelantar tu cita por un problema técnico; tu cita "
                   "queda como está. Te paso con una persona de inmediato.")
        enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
        deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", "adelanto fallido")
        _avisar_por_correo(deps.alerta_handoff, nombre, telefono, razon,
                           "(adelanto fallido)", fecha)
        return {"respondio": True, "motivo": "adelanto fallido", "handoff": True}
    try:
        deps.cancelar_cita(telefono, propuesta["fecha_vieja"])
    except Exception:
        pass
    try:
        inicio_nuevo = _parse_fecha_iso(nueva_fecha)
        duracion = _duracion_entre(propuesta.get("hora_inicio_vieja"),
                                   propuesta.get("hora_fin_vieja"))
        hora_inicio_nueva = inicio_nuevo.strftime("%H:%M")
        hora_fin_nueva = (inicio_nuevo + timedelta(minutes=duracion)).strftime("%H:%M")
        fecha_dia_nueva = inicio_nuevo.strftime("%Y-%m-%d")
    except (ValueError, TypeError, AttributeError):
        hora_inicio_nueva = hora_fin_nueva = ""
        fecha_dia_nueva = str(nueva_fecha)[:10]
    notas_vieja = str(propuesta.get("notas_vieja") or "")
    if notas_vieja:
        notas_nueva = f"{notas_vieja} | Adelantada por urgencia: {razon}"
    else:
        notas_nueva = f"Adelantada por urgencia: {razon}"
    try:
        deps.actualizar_cita_espejo(
            telefono, propuesta["fecha_vieja"], estado="Confirmada",
            notas=notas_nueva, urgencia="SI",
            nueva_fecha=fecha_dia_nueva, nueva_hora_inicio=hora_inicio_nueva,
            nueva_hora_fin=hora_fin_nueva)
    except Exception:
        pass
    try:
        leer_cliente = getattr(deps, "leer_cliente", lambda t: None)
        cliente = leer_cliente(telefono) or {}
        if str(cliente.get("fecha_cita", "") or "")[:10] == str(propuesta["fecha_vieja"])[:10]:
            deps.registrar_cliente(
                fecha, nombre, telefono,
                str(cliente.get("motivo", "") or servicio),
                nueva_fecha, "whatsapp", "agendado", "no")
    except Exception:
        pass
    _borrar_propuesta(deps, telefono)
    _con_pro = _con_profesional(str(propuesta.get("profesional") or "").strip())
    mensaje = f"¡Listo! Tu cita quedó para el {propuesta['fecha_bonita']}{_con_pro}."
    enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
    deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", "cita adelantada")
    _avisar_por_correo(
        deps.alerta_cita_urgente, nombre, telefono, servicio,
        propuesta["fecha_bonita"], fecha,
        razon=f"Adelantada desde {propuesta.get('fecha_bonita_vieja', '')}. {razon}")
    return {"respondio": True, "handoff": False, "cita_adelantada": True,
            "fecha_cita": nueva_fecha}


def _dejar_cita_igual(deps: Dependencias, telefono: str, nombre: str,
                      fecha: str, con_ritmo: bool = True,
                      ahora: datetime | None = None) -> dict:
    """El cliente prefirió dejar su cita como está (v3.15)."""
    _borrar_propuesta(deps, telefono)
    mensaje = ("Perfecto, tu cita queda como está. Te paso con una persona de "
               "inmediato para que te atiendan lo antes posible.")
    enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
    deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", "adelanto rechazado")
    return {"respondio": True, "handoff": False, "cita_sin_cambio": True}


def _enviar_propuesta_urgente(deps: Dependencias, telefono: str, fecha: str,
                              con_ritmo: bool = True) -> None:
    """(v3.13) Manda la oferta de cita urgente con botones.

    Sale después del mensaje de handoff (paso 8): primero la
    empatía y la promesa de persona, luego la cita lista para
    confirmar con un toque. Si los botones fallan, va el texto y
    la propuesta guardada sigue valiendo para un "sí" escrito.
    """
    propuesta = _CITAS_PENDIENTES.get(telefono)
    if not propuesta or not str(propuesta.get("urgencia") or "").strip():
        return
    _con_pro = _con_profesional(str(propuesta.get("profesional") or "").strip())
    if propuesta.get("tipo") == "adelanto":
        # (v3.15) Adelanto: mover la cita que ya tiene, no crear otra.
        mensaje = (
            f"Vi que ya tienes una cita el {propuesta.get('fecha_bonita_vieja', '')}. "
            f"Te la adelanto a {propuesta['fecha_bonita']}{_con_pro} por la urgencia. "
            "¿La adelantamos?"
        )
        botones = [
            ("adelantar_cita", "Adelantar cita"),
            ("dejar_cita_igual", "Dejarla como está"),
            ("hablar_persona", "Hablar con persona"),
        ]
    else:
        mensaje = (
            f"Te dejo lista tu cita para el {propuesta['fecha_bonita']}{_con_pro}. "
            "¿La confirmamos?"
        )
        botones = BOTONES_CITA
    try:
        deps.enviar_botones(telefono, mensaje, botones)
    except Exception as exc:
        try:
            deps.registrar_diagnostico(
                fecha, "whatsapp", "FALLO",
                f"Botones no enviados: {str(exc)[:250]}",
                telefono, "propuesta urgente con botones",
            )
        except Exception:
            pass
        enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
    deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", "cita urgente")


def _confirmar_cita_propuesta(deps: Dependencias, telefono: str, nombre: str,
                              fecha: str, con_ritmo: bool = True) -> dict:
    """Crea la cita de una propuesta guardada y manda la confirmación bonita.

    La usan el botón Confirmar y el "sí" por texto: el mismo resultado
    por los dos caminos. Si la hora ya se ocupó, avisa y no crea nada.
    Si el calendario falla con la hora libre, la solicitud queda
    PENDIENTE y se avisa al dueño (v3.9, Sereno decisión 1: nunca
    inventar una cita).
    (v3.10) Una propuesta puede traer DOS citas (la suya y la de otra
    persona, o dos servicios): se crean las dos y se confirma en un
    solo mensaje. El tope de 2 citas por número se revisa aquí también
    (por si se confirmó otra cita entre la propuesta y la confirmación).
    """
    propuesta = _CITAS_PENDIENTES.get(telefono)
    if not propuesta:
        mensaje = "Claro. ¿Qué necesitas? Cuéntame y te ayudo."
        enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
        return {"respondio": True, "motivo": "sin propuesta", "handoff": False}
    # (v3.15) Un "sí" por texto a un adelanto mueve la cita, no crea otra.
    if propuesta.get("tipo") == "adelanto":
        return _confirmar_adelanto(deps, telefono, nombre, fecha, con_ritmo)
    nombre_cita = str(propuesta.get("nombre") or "").strip()
    telefono_registro = str(propuesta.get("telefono_registro") or "").strip()
    # (v3.13) Urgencia: si la propuesta viene de una urgencia, todas
    # sus citas se marcan URGENTE (CRM, calendario y correo con el
    # porqué). Vacío = cita normal, como siempre.
    urgencia_razon = str(propuesta.get("urgencia") or "").strip()
    # (v3.10) Citas a crear: la primera + la segunda si la hay.
    citas = [{
        "motivo": propuesta["motivo"],
        "fecha_cita": propuesta["fecha_cita"],
        "fecha_bonita": propuesta["fecha_bonita"],
        "profesional": str(propuesta.get("profesional") or "").strip(),
        "nombre_paciente": str(propuesta.get("nombre_paciente") or "").strip(),
        "relacion_paciente": str(propuesta.get("relacion_paciente") or "").strip(),
        "numero_paciente": str(propuesta.get("numero_paciente") or "").strip(),
        "urgencia": urgencia_razon,
    }]
    if propuesta.get("cita2"):
        _c2 = propuesta["cita2"]
        citas.append({
            "motivo": _c2.get("motivo") or propuesta["motivo"],
            "fecha_cita": _c2["fecha_cita"],
            "fecha_bonita": _c2.get("fecha_bonita") or _c2["fecha_cita"],
            "profesional": str(_c2.get("profesional") or "").strip(),
            "nombre_paciente": str(_c2.get("nombre_paciente") or "").strip(),
            "relacion_paciente": str(_c2.get("relacion_paciente") or "").strip(),
            "numero_paciente": str(_c2.get("numero_paciente") or "").strip(),
            "urgencia": urgencia_razon,
        })
    # (v3.10) Es cita para OTRA persona si trae nombre o relación
    # (aunque el nombre aún no se sepa: la relación ya lo dice).
    # El nombre de la cita nunca es el del dueño para una cita ajena.
    for _cita in citas:
        _cita["es_tercero"] = bool(_cita["nombre_paciente"] or _cita["relacion_paciente"])
        _cita["nombre_cita"] = (
            _cita["nombre_paciente"]
            or (_cita["relacion_paciente"] if _cita["es_tercero"] else nombre_cita)
            or "Cliente"
        )
    # (v3.10) Tope de 2 citas por número, revisado al confirmar.
    _ahora_real = datetime.now(timezone.utc)
    if _citas_activas_telefono(deps, telefono, _ahora_real) + len(citas) > MAX_CITAS_POR_NUMERO:
        _borrar_propuesta(deps, telefono)
        mensaje = (
            "Ya tienes 2 citas registradas con este número, para no "
            "llenar la agenda. Si quieres cambiar alguna, dime cuál y "
            "te ayudo con gusto."
        )
        enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
        deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", "tope de citas por numero")
        return {"respondio": True, "motivo": "tope de citas", "handoff": False}
    _borrar_propuesta(deps, telefono)
    # Crea cada cita por separado: si una hora se ocupó, la otra
    # todavía puede quedar (se reporta honesto lo que pasó).
    resultados = []  # (cita, "creada" | "ocupada" | "pendiente", duracion)
    for _cita in citas:
        _nombre_pac = _cita["nombre_cita"]
        # (v3.9) Duración por servicio desde la hoja; si no hay dato, el default.
        _dur = getattr(deps, "duracion_servicio", lambda m: None)(_cita["motivo"])
        try:
            _duracion = int(_dur) if _dur else settings.duracion_cita_minutos
        except (TypeError, ValueError):
            _duracion = settings.duracion_cita_minutos
        _nota_partes = []
        if _cita.get("urgencia"):
            _nota_partes.append(f"URGENTE: {_cita['urgencia']}")
        if _cita["nombre_paciente"]:
            _nota_partes.append(f"Paciente: {_cita['nombre_paciente']}")
        if _cita.get("profesional"):
            _nota_partes.append(f"Profesional: {_cita['profesional']}")
        _num_reg = _cita["numero_paciente"] or telefono_registro
        if _num_reg:
            _nota_partes.append(f"Teléfono de registro: {_num_reg}")
        try:
            deps.crear_cita(
                _nombre_pac or "Cliente", telefono, _cita["motivo"],
                _cita["fecha_cita"], nota=". ".join(_nota_partes),
            )
            resultados.append((_cita, "creada", _duracion))
        except ValueError:
            # booking: la hora está ocupada (su contrato). No se crea nada.
            resultados.append((_cita, "ocupada", _duracion))
        except Exception:
            # (v3.9) Falló el calendario (u otra cosa) al crear. ¿La hora
            # está libre? Si sí, la solicitud queda PENDIENTE: se le dice
            # al cliente con honestidad y se avisa al dueño. Si no está
            # libre, es una hora ocupada normal.
            _libre = True
            try:
                _libre = bool(deps.hora_libre(_cita["fecha_cita"]))
            except Exception:
                _libre = True
            if _libre:
                resultados.append((_cita, "pendiente", _duracion))
                _reg = getattr(deps, "registrar_cita_espejo", lambda f: None)
                try:
                    _reg(_fila_espejo(
                        {"motivo": _cita["motivo"], "fecha_cita": _cita["fecha_cita"],
                         "fecha_bonita": _cita["fecha_bonita"]},
                        telefono, _nombre_pac, _duracion, "Pendiente", fecha,
                        profesional=_cita.get("profesional", ""),
                        urgencia=_cita.get("urgencia", "")))
                except Exception:
                    pass
                _avisa = getattr(deps, "alerta_cita_pendiente", lambda *a: None)
                try:
                    _avisa(_nombre_pac or "Cliente", telefono, _cita["motivo"],
                           _cita["fecha_bonita"], fecha)
                except Exception:
                    pass
            else:
                resultados.append((_cita, "ocupada", _duracion))
    creadas = [r for r in resultados if r[1] in ("creada", "pendiente")]
    ocupadas = [r for r in resultados if r[1] == "ocupada"]
    if not creadas:
        # Ninguna quedó: el mensaje histórico de hora ocupada.
        mensaje = (
            "Uy, esa hora ya se ocupó, perdón. ¿Qué otro día y hora "
            "te vienen mejor? Te la agendo enseguida."
        )
        enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
        deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", "hora ocupada")
        return {"respondio": True, "motivo": "hora ocupada", "handoff": False}
    if len(resultados) == 1 and resultados[0][1] == "pendiente":
        # Una sola cita y quedó pendiente: el mensaje histórico, sin
        # saludo ni confirmación (la cita NO se creó: nunca inventar).
        _cita_p = resultados[0][0]
        mensaje = (
            f"Me pasó algo al registrar tu cita del {_cita_p['fecha_bonita']} "
            f"y quedó pendiente, perdón. Ya avisé al equipo para que te la "
            f"dejen lista en breve."
        )
        enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
        deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", "cita pendiente")
        return {"respondio": True, "motivo": "cita pendiente", "handoff": False}
    # (v3.4.11) Confirmación cálida, limpia y sin fricción: corta,
    # con la fecha en claro y una sola idea por línea. Es el momento
    # que el cliente recuerda (el final de la experiencia): debe
    # sentirse bien y dar certeza total. (v3.10) Con dos citas, cada
    # una lleva su bloque; si una se ocupó, se dice con honestidad.
    # La pendiente NO se afirma como creada: se dice que quedó
    # pendiente (nunca inventar una cita, v3.9).
    saludo = f"¡Perfecto, {nombre_cita}!" if nombre_cita else "¡Perfecto!"
    bloques = []
    for _cita, _estado, _duracion in resultados:
        if _estado == "ocupada":
            continue
        _es_tercero = _cita["es_tercero"]
        _rel = _cita["relacion_paciente"] or "la persona"
        if _estado == "pendiente":
            if _es_tercero:
                bloques.append(
                    f"Me pasó algo al registrar la cita de {_rel} del "
                    f"{_cita['fecha_bonita']} y quedó pendiente, perdón. "
                    f"Ya avisé al equipo para que la dejen lista en breve.")
            else:
                bloques.append(
                    f"Me pasó algo al registrar tu cita del "
                    f"{_cita['fecha_bonita']} y quedó pendiente, perdón. "
                    f"Ya avisé al equipo para que te la dejen lista en breve.")
            continue
        # (v3.12) Con agenda por profesional: "con la Dra. Ruiz".
        _con_pro = _con_profesional(_cita.get("profesional", ""))
        if _es_tercero:
            encabezado = f"La cita de {_rel} quedó para el {_cita['fecha_bonita']}{_con_pro}."
        else:
            encabezado = f"Tu cita quedó para el {_cita['fecha_bonita']}{_con_pro}."
        bloque = f"{encabezado}\n\nDura {_duracion} minutos."
        _num_reg = _cita["numero_paciente"] or telefono_registro
        if _num_reg:
            bloque += f"\n\nQuedó registrada al {_num_reg}."
        bloques.append(bloque)
    if len(resultados) == 1 and resultados[0][1] == "creada":
        mensaje = f"{saludo} {bloques[0]}"
        mensaje += "\n\nSi necesitas cambiarla, escríbeme y la reacomodamos con gusto."
    else:
        mensaje = f"{saludo} " + "\n\n".join(bloques)
        if ocupadas:
            mensaje += ("\n\nLa otra hora ya se ocupó, perdón. ¿Qué otro día y "
                        "hora te vienen mejor para esa? Te la agendo enseguida.")
        mensaje += "\n\nSi necesitas cambiar alguna, escríbeme y la reacomodamos con gusto."
    enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
    deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", propuesta["motivo"])
    # Solo se marca "agendado" si alguna cita se creó de verdad: una
    # pendiente no es una cita (nunca inventar, v3.9).
    if any(r[1] == "creada" for r in resultados):
        deps.registrar_cliente(
            fecha, propuesta["nombre"], telefono, propuesta["motivo"],
            propuesta["fecha_cita"], "whatsapp", "agendado", "no",
        )
    # (v3.9) Espejo de citas: la pestaña Citas queda como vista de
    # solo lectura para el dueño. Best-effort: nunca rompe la confirmación.
    _reg = getattr(deps, "registrar_cita_espejo", lambda f: None)
    for _cita, _estado, _duracion in creadas:
        if _estado != "creada":
            continue  # la pendiente ya escribió su fila
        try:
            _reg(_fila_espejo(
                {"motivo": _cita["motivo"], "fecha_cita": _cita["fecha_cita"],
                 "fecha_bonita": _cita["fecha_bonita"]},
                telefono, _cita["nombre_cita"],
                _duracion, "Confirmada", fecha,
                profesional=_cita.get("profesional", ""),
                urgencia=_cita.get("urgencia", "")))
        except Exception:
            pass
    # (v3.4.11) Después de confirmar (la cita YA quedó: pedir los
    # datos no bloquea nada), si falta el nombre completo o el número
    # de registro, se piden en un mensaje aparte y cálido. Primero el
    # compromiso, luego los datos: cero fricción al agendar. Se dice
    # para qué ("para dejarte bien registrado"): la gente da sus
    # datos cuando entiende por qué. (v3.10) La pregunta cubre también
    # a la otra persona (su nombre completo y su número).
    info_datos = []
    for _cita, _estado, _duracion in resultados:
        if _estado != "creada":
            continue  # la pendiente no lleva pregunta de datos
        _es_tercero = _cita["es_tercero"]
        _num = _cita["numero_paciente"] or telefono_registro
        if _es_tercero:
            falta_nombre = not _cita["nombre_paciente"]
        else:
            falta_nombre = not nombre_cita or nombre_cita == str(nombre or "").strip()
        info_datos.append({
            "es_tercero": _es_tercero,
            "relacion": _cita["relacion_paciente"] or "la persona",
            "falta_nombre": falta_nombre,
            "falta_numero": not _num,
        })
    pregunta = _pregunta_datos_citas(info_datos)
    if pregunta:
        enviar_con_ritmo(deps.enviar_texto, telefono, pregunta, dormir=con_ritmo)
        deps.registrar_conversacion(
            fecha, telefono, "robot", pregunta, "si", "pedir datos de registro")
    # (v3.3) Alerta de cita confirmada: el dueño no ve las citas en su
    # calendario (el robot agenda en el suyo propio). Sin este correo,
    # se entera hasta el lunes. Best-effort: si el correo falla, la
    # cita ya quedó creada igual. (v3.7) Con alertas_instantaneas=NO
    # la cita va en el correo semanal de 3 tipos y aquí no se manda
    # nada (sin avalancha de correos). (v3.13) Excepción: la cita
    # urgente SIEMPRE avisa en el momento, con el porqué — una
    # urgencia no espera al lunes.
    for _cita, _estado, _duracion in creadas:
        if _estado != "creada":
            continue
        if _cita.get("urgencia"):
            _avisar_por_correo(
                getattr(deps, "alerta_cita_urgente", None),
                _cita["nombre_paciente"] or propuesta["nombre"], telefono,
                _cita["motivo"], _cita["fecha_bonita"], fecha,
                razon=_cita["urgencia"],
            )
        elif funcion_activa("alertas_instantaneas"):
            _avisar_por_correo(
                getattr(deps, "alerta_cita_confirmada", None),
                _cita["nombre_paciente"] or propuesta["nombre"], telefono,
                _cita["motivo"], _cita["fecha_bonita"], fecha,
            )
    return {"respondio": True, "handoff": False,
            "cita": resultados[0][0] if resultados else None}


# --- Cambiar / cancelar cita (v2.4) ---

_PALABRAS_CANCELAR = ("cancelar", "cancela", "anular", "ya no quiero la cita")
_PALABRAS_CAMBIAR = (
    "cambiar", "reprogramar", "reagendar", "mover la cita", "mejor no",
    "prefiero otra", "otra hora", "otro dia", "otro día", "no quiero",
    "no me va", "no me sirve",
)


def _intencion_cambio(texto: str, hay_propuesta: bool = False) -> str | None:
    """¿El cliente quiere cambiar o cancelar su cita? Devuelve "cambiar",
    "cancelar" o None.

    Se lee el mensaje completo, no una sola palabra: "disculpe, mejor
    no, ¿si deseo cambiar la cita puedo?" es cambiar, aunque empiece
    con "disculpe". Un "otra" solo, con una propuesta pendiente, es
    "prefiero otra fecha" (cambiar). Sin propuesta ni cita, "otra" no
    es nada: va al agente, que pregunta qué otra cosa necesita.
    """
    normal = re.sub(r"[^a-z0-9 ]+", "", _sin_acentos(texto))
    normal = re.sub(r"\s+", " ", normal).strip()
    if any(p in normal for p in _PALABRAS_CANCELAR):
        return "cancelar"
    if any(p in normal for p in _PALABRAS_CAMBIAR):
        return "cambiar"
    if hay_propuesta and normal in ("otra", "otro", "prefiero otra"):
        return "cambiar"
    # (v3.4.9) Un "no" pelón a la propuesta es "esa hora no": se
    # pregunta por otro día, sin pasar por la IA.
    if hay_propuesta and normal in ("no", "nop", "nel", "nope"):
        return "cambiar"
    return None


def _atender_cambio_cancelacion(deps: Dependencias, telefono: str, nombre: str,
                                fecha: str, intencion: str, con_ritmo: bool = True,
                                ahora: datetime | None = None) -> dict:
    """Atiende un cambio o cancelación de cita, de día o de noche.

    - Si solo había una propuesta (todavía no se creó la cita), se
      borra la propuesta y se pregunta por el nuevo día.
    - Si la cita ya está creada (estatus agendado en Clientes) y es
      a futuro (o de hoy), se borra el evento de Calendar y se limpia
      la hoja, y se confirma. Una cita ya pasada no se "cancela": ya
      terminó; se trata como si no hubiera nada que cambiar.
    - Si no hay nada que cambiar, se pregunta qué día le viene bien.
    Nunca se repite la frase de fuera de horario: el cliente ya dijo
    lo que quiere, y eso se respeta.
    """
    propuesta = _CITAS_PENDIENTES.get(telefono)
    _borrar_propuesta(deps, telefono)
    leer_cliente = getattr(deps, "leer_cliente", lambda t: None)
    cliente = leer_cliente(telefono) or {}
    fecha_cita = str(cliente.get("fecha_cita", "") or "").strip()
    _ahora = ahora or _parse_fecha_iso(fecha) or datetime.now(timezone.utc)
    agendada = _cita_es_futura(cliente, _ahora)
    if agendada:
        try:
            fecha_bonita = formatear_cita_bonita(fecha_cita)
        except (ValueError, TypeError):
            fecha_bonita = fecha_cita
        cancelar_cita = getattr(deps, "cancelar_cita", lambda t, f: False)
        cancelar_cliente = getattr(deps, "cancelar_cita_cliente", lambda t: None)
        try:
            cancelar_cita(telefono, fecha_cita)
        except Exception:
            pass
        try:
            cancelar_cliente(telefono)
        except Exception:
            pass
        # (v3.9) El espejo marca la cita como Cancelada. Best-effort.
        _act = getattr(deps, "actualizar_cita_espejo", lambda t, f, e: None)
        try:
            _act(telefono, fecha_cita, "Cancelada")
        except Exception:
            pass
        if intencion == "cancelar":
            mensaje = (
                f"Sin problema, tu cita del {fecha_bonita} quedó cancelada. "
                f"Cuando quieras agendar otra, dime qué día te viene bien "
                f"y te la dejo lista."
            )
        else:
            mensaje = (
                f"Sin problema, cancelé tu cita del {fecha_bonita}. "
                f"¿Qué día y hora te vienen mejor para la nueva?"
            )
        enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
        deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si",
                                    "cancelar cita" if intencion == "cancelar" else "cambiar cita")
        deps.registrar_cliente(fecha, nombre, telefono,
                               "Canceló su cita" if intencion == "cancelar" else "Quiere cambiar su cita",
                               "", "whatsapp", "en conversacion", "no")
        return {"respondio": True, "handoff": False, "cita_cancelada": True}
    if propuesta is not None or intencion == "cambiar":
        mensaje = "Claro, sin problema. ¿Qué día y hora te vienen mejor?"
        enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
        deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", "cambiar cita")
        return {"respondio": True, "handoff": False, "cita_cancelada": False}
    mensaje = "Claro. No tienes ninguna cita agendada con nosotros. ¿Te ayudo con algo más?"
    enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
    deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", "cancelar cita")
    return {"respondio": True, "handoff": False, "cita_cancelada": False}


# --- Reglas puras (sin internet, se prueban solas) ---


def puede_responder(
    bot_activo: str,
    ultima_respuesta_humana: str,
    ahora: datetime | None = None,
) -> tuple[bool, str]:
    """¿Puede hablar el robot? Devuelve (sí/no, motivo del silencio).

    - bot_activo en NO → no, "boton apagado".
    - Un humano escribió hace menos de 2 horas → no, "humano activo hace menos de 2 horas".
    - Si no, sí.
    """
    ahora = ahora or datetime.now(timezone.utc)
    if str(bot_activo).strip().upper() != "SI":
        return False, "boton apagado"
    if ultima_respuesta_humana:
        try:
            ultima = _parse_fecha_iso(ultima_respuesta_humana)
            if ultima is None:
                return True, ""
            if ultima.tzinfo is None:
                ultima = ultima.replace(tzinfo=timezone.utc)
            if ahora - ultima < PAUSA:
                return False, "humano activo hace menos de 2 horas"
        except ValueError:
            pass  # Fecha mal escrita en Control: no se bloquea por eso.
    return True, ""


def robot_activo_para_cliente(valor: str) -> bool:
    """¿El robot le contesta a este cliente? Solo un NO explícito lo apaga.

    La columna robot_activo de Clientes: "NO" → apagado. En blanco,
    "SI" o cualquier otra cosa → encendido (el robot contesta por
    defecto; nadie se queda sin respuesta por una celda vacía).
    """
    return str(valor or "").strip().upper() not in {"NO", "N", "FALSE", "FALSO"}


def foto_es_oficial(url: str, fotos: list[dict]) -> bool:
    """¿Está esta URL en la lista blanca de Fotos oficiales?"""
    url = (url or "").strip()
    if not url:
        return False
    oficiales = {(f.get("url") or "").strip() for f in fotos}
    return url in oficiales


# --- Horarios del negocio (de la hoja Conocimiento) ---

_DIAS = {
    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2, "jueves": 3,
    "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6,
}
_DIAS_NOMBRE = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
          "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _dias_de_texto(texto: str) -> list[int]:
    """Días que cubre un texto como 'Lunes a viernes' o 'Sábado'."""
    texto = texto.lower()
    encontrados = [(m.start(), _DIAS[m.group(0)]) for m in re.finditer(
        r"lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo", texto)]
    if not encontrados:
        return []
    if len(encontrados) == 1:
        return [encontrados[0][1]]
    inicio, fin = encontrados[0][1], encontrados[-1][1]
    if fin < inicio:  # p. ej. "viernes a lunes": no se complica, se toman los dos
        return [inicio, fin]
    return list(range(inicio, fin + 1))


def _horas_de_texto(texto: str) -> tuple[int, int] | None:
    """Horas de un texto como '09:00 a 18:00'. Devuelve (apertura, cierre) en minutos."""
    match = re.search(r"(\d{1,2}):(\d{2})\s*(?:a|-)\s*(\d{1,2}):(\d{2})", texto or "")
    if not match:
        return None
    h1, m1, h2, m2 = (int(x) for x in match.groups())
    return h1 * 60 + m1, h2 * 60 + m2


def horarios_por_dia(conocimiento: list[dict]) -> dict[int, tuple[int, int]]:
    """De Conocimiento (filas tipo=horario) a {día_semana: (apertura, cierre)}."""
    horarios: dict[int, tuple[int, int]] = {}
    for fila in conocimiento:
        if str(fila.get("tipo", "")).strip().lower() != "horario":
            continue
        horas = _horas_de_texto(str(fila.get("respuesta_o_precio", "")))
        if not horas:
            continue
        for dia in _dias_de_texto(str(fila.get("pregunta_o_servicio", ""))):
            horarios[dia] = horas
    return horarios


def _a_hora_local(ahora: datetime) -> datetime:
    """Pasa una fecha a la zona horaria del negocio.

    Ojo: una fecha SIN zona (como "2026-11-14T10:00:00", que es como
    Gemini y el negocio escriben las citas) ya está en hora del
    negocio, no en UTC. Solo las fechas que sí traen zona se convierten.
    """
    zona = ZoneInfo(settings.timezone)
    if ahora.tzinfo is None:
        return ahora.replace(tzinfo=zona)
    return ahora.astimezone(zona)


def _cita_es_futura(cliente: dict | None, ahora: datetime) -> bool:
    """¿La cita registrada del cliente es a futuro (o de hoy)? (v3.10)

    R8 la usa para no afirmar citas que no existen: una cita ya
    pasada (estatus agendado pero fecha vieja) no justifica decir
    "quedamos en que nos vemos...". Si la fecha no se puede leer,
    se devuelve True: mejor no bloquear con una fecha rota.
    """
    if not cliente:
        return False
    fecha_cita = str(cliente.get("fecha_cita", "") or "").strip()
    estatus = str(cliente.get("estatus", "") or "").strip().lower()
    if not fecha_cita or estatus != "agendado":
        return False
    try:
        dt = _parse_fecha_iso(fecha_cita)
        if dt is None:
            return True
        zona = ZoneInfo(settings.timezone)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=zona)
        else:
            dt = dt.astimezone(zona)
        ahora_local = _a_hora_local(ahora)
        return dt >= ahora_local or dt.date() == ahora_local.date()
    except Exception:
        return True


def horario_abierto(conocimiento: list[dict], ahora: datetime | None = None) -> tuple[bool, str]:
    """¿Está abierto el negocio ahora? Devuelve (sí/no, resumen de horarios).

    Si la hoja no tiene filas de horario, se asume abierto (no se
    bloquea al cliente por falta de datos).
    """
    horarios = horarios_por_dia(conocimiento)
    if not horarios:
        return True, ""
    local = _a_hora_local(ahora or datetime.now(timezone.utc))
    horas = horarios.get(local.weekday())
    if horas is None:
        return False, _resumen_horarios(conocimiento)
    minutos = local.hour * 60 + local.minute
    return horas[0] <= minutos < horas[1], _resumen_horarios(conocimiento)


def _resumen_horarios(conocimiento: list[dict]) -> str:
    """Texto corto con los horarios, p. ej. 'lunes a viernes de 09:00 a 18:00'."""
    partes = []
    for fila in conocimiento:
        if str(fila.get("tipo", "")).strip().lower() != "horario":
            continue
        dia = str(fila.get("pregunta_o_servicio", "")).strip()
        hora = str(fila.get("respuesta_o_precio", "")).strip()
        if dia and hora:
            partes.append(f"{dia.lower()} de {hora}")
    return ", ".join(partes) or "en su horario habitual"


def proxima_apertura(
    conocimiento: list[dict],
    ahora: datetime | None = None,
    desde: datetime | None = None,
) -> datetime | None:
    """La próxima fecha en que el negocio abre (fecha con hora de apertura).

    `desde` (v3.4.10): si el cliente pidió una fecha concreta que cayó
    cerrada, la corrección busca la apertura en esa fecha o después,
    no desde ahora. Pedir domingo y recibir "mañana jueves" no tiene
    sentido; recibir el lunes sí. El resultado siempre es futuro
    respecto a `ahora` (nunca se agenda en el pasado).
    """
    horarios = horarios_por_dia(conocimiento)
    if not horarios:
        return None
    ahora_local = _a_hora_local(ahora or datetime.now(timezone.utc))
    base = _a_hora_local(desde) if desde is not None else ahora_local
    for adelanto in range(0, 9):
        dia = base + timedelta(days=adelanto)
        horas = horarios.get(dia.weekday())
        if horas is None:
            continue
        apertura = dia.replace(hour=horas[0] // 60, minute=horas[0] % 60, second=0, microsecond=0)
        if apertura <= ahora_local:
            continue  # ya pasó: buscar el siguiente día
        if apertura < base:
            continue  # antes de la fecha pedida: no sirve
        return apertura
    return None


def _parse_fecha_iso(texto: str) -> datetime | None:
    """Parsea una fecha ISO con tolerancia (v3.4.11).

    Acepta lo normal ('2026-11-19T09:00:00-07:00') y también lo que
    la hoja devolvía tras reinterpretar fechas guardadas con
    USER_ENTERED ('2026-11-19 9:00:00', hora de un dígito, sin zona):
    rellena la hora a dos dígitos. Devuelve None si no se puede leer.
    """
    t = str(texto or "").strip().replace("Z", "+00:00")
    if not t:
        return None
    m = re.match(r"^(\d{4}-\d{2}-\d{2})[T ](\d{1,2}):(\d{2})(?::(\d{2}))?(.*)$", t)
    if m:
        fecha, hora, minuto, segundo, resto = m.groups()
        t = f"{fecha}T{int(hora):02d}:{minuto}:{segundo or '00'}{resto}"
    try:
        return datetime.fromisoformat(t)
    except ValueError:
        return None


def formatear_cita_bonita(fecha_iso: str) -> str:
    """'2026-11-14T10:00:00' → 'sábado 14 de noviembre a las 10:00'.

    Sin depender del idioma del servidor: los nombres están escritos
    a mano, en español.
    """
    fecha = _parse_fecha_iso(fecha_iso)
    if fecha is None:
        raise ValueError(f"Fecha no legible: {fecha_iso!r}")
    local = _a_hora_local(fecha)
    return (
        f"{_DIAS_NOMBRE[local.weekday()]} {local.day} de "
        f"{_MESES[local.month - 1]} a las {local:%H:%M}"
    )


def contar_semana(
    conversaciones: list[dict], clientes: list[dict], desde: datetime, hasta: datetime
) -> dict:
    """Cuenta la última semana. Los números salen de las hojas, no se inventan.

    Devuelve: mensajes_atendidos, clientes_calificados, citas_agendadas,
    handoffs, sin_respuesta_por_humano, motivos_top (lista de (motivo, veces)).
    """
    def en_semana(fila: dict) -> bool:
        try:
            fecha = _parse_fecha_iso(fila.get("fecha", ""))
            if fecha is None:
                return False
            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=timezone.utc)
            return desde <= fecha < hasta
        except ValueError:
            return False

    conv = [f for f in conversaciones if en_semana(f)]
    cli = [f for f in clientes if en_semana(f)]
    motivos: dict[str, int] = {}
    for fila in conv:
        motivo = str(fila.get("motivo") or "").strip()
        if motivo:
            motivos[motivo] = motivos.get(motivo, 0) + 1
    return {
        "mensajes_atendidos": sum(
            1 for f in conv if f.get("quien_hablo") == "robot" and f.get("robot_respondio") == "si"
        ),
        # Clientes distintos (por teléfono), no filas: antes, un cliente
        # con 5 mensajes contaba como 5 clientes calificados.
        "clientes_calificados": len({str(f.get("telefono", "")).strip() for f in cli if str(f.get("telefono", "")).strip()}),
        "citas_agendadas": sum(
            1 for f in cli if str(f.get("estatus", "")).strip() == "agendado"
        ),
        "handoffs": sum(
            1 for f in cli if str(f.get("handoff", "")).strip().lower() == "si"
        ),
        "sin_respuesta_por_humano": sum(
            1
            for f in conv
            if f.get("robot_respondio") == "no"
            and "humano activo" in str(f.get("motivo") or "")
        ),
        "motivos_top": sorted(motivos.items(), key=lambda x: -x[1])[:5],
    }


# --- El flujo completo ---


class Dependencias:
    """Los servicios que el robot necesita. Cada método es una sola acción.

    En producción se usan las funciones reales de sheets/whatsapp/etc.
    En las pruebas se reemplazan por falsas. Si un día cambias de
    proveedor (otro Sheets, otro WhatsApp), solo cambia este archivo.
    Los métodos nuevos de la v2 tienen una versión vacía aquí: si una
    dependencia vieja no los tiene, el robot sigue funcionando.
    """

    # Sheets
    def leer_control(self) -> dict: ...
    def leer_robot_activo(self, telefono: str) -> str:
        """Interruptor por cliente (columna robot_activo de Clientes). Por defecto: SI."""
        return "SI"
    def leer_cliente(self, telefono: str) -> dict | None:
        """La fila de Clientes de un teléfono, o None si no está registrado."""
        return None
    def cancelar_cita_cliente(self, telefono: str) -> None:
        """Limpia la cita de un cliente en Clientes (fecha vacía, estatus en conversacion)."""
        ...
    def guardar_propuesta(self, telefono: str, propuesta: dict) -> None:
        """Guarda una propuesta de cita en la hoja (respaldo ante reinicios)."""
        ...
    def borrar_propuesta(self, telefono: str) -> None:
        """Borra una propuesta de cita de la hoja."""
        ...
    def leer_propuestas(self) -> list[dict]:
        """Todas las propuestas guardadas en la hoja (para recuperarlas al arrancar)."""
        return []
    def guardar_memoria_cliente(self, telefono: str, resumen: str = "", interes: str = "",
                                proxima_accion: str = "", preferencias: str = "") -> None:
        """Guarda lo que se aprendió del cliente en Clientes (v3.2). Por defecto: nada."""
        ...
    def leer_conocimiento(self) -> list[dict]: ...
    def leer_fotos(self) -> list[dict]: ...
    def leer_historial(self, telefono: str) -> list[dict]: ...
    def registrar_conversacion(self, fecha, telefono, quien, mensaje, respondio, motivo=""): ...
    def registrar_cliente(self, fecha, nombre, telefono, motivo, fecha_cita="", origen="whatsapp", estatus="en conversacion", handoff="no"): ...

    # Agente
    def preguntar_agente(self, mensaje, conocimiento, fotos, historial) -> RespuestaAgente:
        return preguntar_agente(mensaje, conocimiento, fotos, historial)

    # WhatsApp / Calendar / correo
    def enviar_texto(self, telefono, texto): ...
    def enviar_foto(self, telefono, url): ...
    def enviar_plantilla(self, telefono, plantilla, idioma, parametros): ...
    def crear_cita(self, nombre, telefono, motivo, fecha_cita, nota="") -> dict:
        """Crea la cita. `nota` (v3.4.9) es un dato extra para la
        descripción del evento (p. ej. el teléfono de registro)."""
        ...
    def cancelar_cita(self, telefono, fecha_cita) -> bool:
        """Borra del Calendar la cita de ese teléfono en esa fecha. True si la borró."""
        return False
    def alerta_handoff(self, nombre, telefono, motivo, ultimo_mensaje, fecha, resumen=""): ...

    # --- Nuevos en la v3.3 (vacío = no hacer nada, el robot sigue) ---
    def proximos_huecos_libres(self, conocimiento: list[dict], ahora: datetime,
                               cantidad: int = 2, dias: int = 3) -> list[str]:
        """Los próximos huecos libres (fechas ISO) para ofrecer. Por defecto: ninguno.

        (v3.11) cantidad/dias permiten pedir un rango amplio cuando el
        cliente pide días concretos; el default mantiene el comportamiento
        de siempre.
        """
        return []
    def proximos_huecos_profesionales(self, conocimiento: list[dict], ahora: datetime,
                                      cantidad: int = 2, dias: int = 3) -> list[dict]:
        """Huecos con profesional (v3.12): [{"inicio": iso, "profesional": nombre}].

        Por defecto vacío: sin agenda por profesional, el robot usa la
        agenda por clínica de siempre (compatibilidad total).
        """
        return []
    def hora_libre(self, fecha_iso: str) -> bool:
        """¿Está libre esa hora en el calendario? (v3.4.9) Por defecto
        True: sin verificar, la propuesta sale igual y la confirmación
        vuelve a revisar la hora."""
        return True
    def alerta_cita_confirmada(self, nombre, telefono, motivo, fecha_bonita, fecha): ...
    def alerta_lead_caliente(self, nombre, telefono, motivo, ultimo_mensaje, fecha): ...
    def alerta_cita_urgente(self, nombre, telefono, motivo, fecha_bonita, fecha, razon=""):
        """Avisa al dueño de una cita confirmada marcada como URGENTE (v3.13). Por defecto: nada."""
        ...

    # --- Nuevos en la v3.9 (vacío = no hacer nada, el robot sigue) ---
    def duracion_servicio(self, motivo: str):
        """Duración en minutos del servicio (hoja Conocimiento). None = usar el default."""
        return None

    def registrar_cita_espejo(self, fila: dict) -> None:
        """Agrega la cita a la pestaña Citas (espejo de solo lectura). Por defecto: nada."""
        ...

    def actualizar_cita_espejo(self, telefono: str, fecha_cita: str, estado: str | None = None,
                               notas: str | None = None,
                               recordatorio_enviado: str | None = None,
                               urgencia: str | None = None,
                               nueva_fecha: str | None = None,
                               nueva_hora_inicio: str | None = None,
                               nueva_hora_fin: str | None = None) -> None:
        """Actualiza el estado, las notas, el recordatorio, la urgencia y/o
        la fecha/hora de la cita espejo. Por defecto: nada."""
        ...

    def leer_citas_espejo(self) -> list[dict]:
        """Todas las filas de la pestaña Citas. Por defecto: []."""
        return []

    def actualizar_notas_cita(self, telefono: str, fecha_cita: str, notas: str) -> None:
        """Pone las Notas de una cita espejo (datos de la otra persona). Por defecto: nada."""
        ...

    def alerta_cita_pendiente(self, nombre, telefono, motivo, fecha_bonita, fecha) -> None:
        """Avisa al dueño que una cita no quedó creada (falló el calendario). Por defecto: nada."""
        ...

    # --- Nuevos en la v2 (vacío = no hacer nada, el robot sigue) ---
    def marcar_leido_y_escribiendo(self, message_id): ...
    def enviar_botones(self, telefono, texto, botones): ...
    def alerta_error(self, motivo, telefono, ultimo_mensaje, fecha): ...
    def registrar_diagnostico(self, fecha, componente, estado, detalle,
                              telefono="", contexto=""):
        """Escribe en la pestaña Diagnóstico (v2.7). Por defecto: nada."""
        ...


def _avisar_por_correo(avisar, *args, **kwargs) -> None:
    """Avisa por correo sin romper nada: best-effort.

    El correo es un aviso al dueño, no parte de la respuesta al
    cliente. Si Gmail no está configurado (o falla la red, o la
    contraseña de aplicación), enviar_correo lanza CorreoError; aquí
    se atrapa, se deja en el registro del servidor y el robot sigue
    con lo suyo: contestar por WhatsApp y registrar en Sheets.
    Si `avisar` es None (una dependencia vieja sin ese método), no se
    hace nada: el robot sigue igual.
    """
    if avisar is None:
        return
    try:
        avisar(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - el correo nunca rompe WhatsApp
        log_aviso(f"[correo] No se pudo avisar por correo (el robot sigue): {exc}")


def _diagnostico(deps: Dependencias, fecha, componente: str, estado: str,
                 detalle: str, telefono: str = "", contexto: str = "") -> None:
    """Escribe en la pestaña Diagnóstico, sin romper nada (v2.7).

    Es lo que permite revisar la salud del robot desde la hoja, sin
    entrar a Render: si Gemini falla, si el token muere, si la
    autoprueba sale mal, queda escrito aquí con fecha y detalle.
    """
    try:
        registrar = getattr(deps, "registrar_diagnostico", None)
        if registrar is not None:
            registrar(fecha, componente, estado, detalle, telefono, contexto)
    except Exception as exc:  # noqa: BLE001 - el diagnóstico nunca rompe nada
        log_aviso(f"[diagnostico] No pude escribir en la hoja: {exc}")


def atender_mensaje(
    deps: Dependencias,
    telefono: str,
    nombre: str,
    texto: str,
    fecha_iso: str | None = None,
    message_id: str = "",
    con_ritmo: bool = True,
    ahora: datetime | None = None,
    aviso_lote_enviado: dict | None = None,
) -> dict:
    """Atiende UN mensaje (o un lote ya juntado) de un cliente.

    `texto` puede ser varios mensajes juntos, unidos con saltos de
    línea: el Agrupador ya los juntó. `message_id` es el wamid del
    primer mensaje, para el visto y la burbuja. `con_ritmo=False`
    apaga las pausas (solo para las pruebas, que si no tardarían).
    `ahora` es la hora actual (solo para las pruebas de horario).
    `aviso_lote_enviado` es un dict compartido `{"si": bool}` que el
    vigilante de app.py pone en True cuando ya mandó el "dame un
    momento" (lote > 90 s): así la falla técnica no manda el mismo
    texto dos veces. Devuelve un resumen de lo que pasó.
    """
    ahora = ahora or datetime.now(timezone.utc)
    fecha = fecha_iso or ahora.isoformat()
    # 1. ¿Puede responder el robot? Tres frenos, en orden:
    #    (a) botón global (Control), (b) pausa de 2 h si habló un humano,
    #    (c) interruptor por cliente (robot_activo en Clientes, v2.3).
    control = deps.leer_control()
    puede, motivo_silencio = puede_responder(
        control.get("bot_activo", "SI"),
        control.get("ultima_respuesta_humana", ""),
        ahora,
    )
    if puede:
        leer_activo = getattr(deps, "leer_robot_activo", lambda t: "SI")
        if not robot_activo_para_cliente(leer_activo(telefono)):
            puede, motivo_silencio = False, "robot apagado para este cliente"
    # (v3.6) Switch por canal del negocio (Configuración o documento
    # maestro): si WhatsApp está apagado para este negocio, el robot
    # no contesta, igual que con el botón global. Vacío = SI.
    if puede and not canal_negocio_activo("whatsapp"):
        puede, motivo_silencio = False, "canal WhatsApp apagado para este negocio"
    # 2. Registrar que llegó el mensaje del cliente (una sola vez, siempre).
    deps.registrar_conversacion(
        fecha, telefono, "cliente", texto,
        "si" if puede else "no", motivo_silencio,
    )
    if not puede:
        # En silencio: sin visto, sin burbuja, sin respuesta. Solo registro.
        # (v3.8) Excepción con la IA apagada —interruptor por cliente
        # o botón global de la clínica—: el mensaje igual se LEE. Si
        # es una urgencia, una queja o un pedido de persona, se
        # resuelve el handoff —correo al dueño (siempre por correo) y
        # caso marcado en Clientes— sin contestarle al paciente. Las
        # dudas normales solo quedan registradas. Los demás silencios
        # (pausa humana de 2 h, canal apagado) no cambian.
        if motivo_silencio in ("robot apagado para este cliente", "boton apagado"):
            motivo_handoff = _motivo_handoff_en_silencio(texto)
            if motivo_handoff:
                _avisar_por_correo(
                    deps.alerta_handoff,
                    nombre, telefono, motivo_handoff, texto, fecha,
                )
                deps.registrar_cliente(
                    fecha, nombre, telefono, texto[:120], "", "whatsapp",
                    "en conversacion", "si",
                )
                return {
                    "respondio": False,
                    "motivo": "robot apagado para este cliente; handoff alertado",
                    "handoff": True,
                }
        return {"respondio": False, "motivo": motivo_silencio, "handoff": False}

    # 3. Visto + "escribiendo...": el cliente ve que lo leyeron.
    # Best-effort: si Meta falla, se sigue igual, sin avisarle al cliente.
    try:
        deps.marcar_leido_y_escribiendo(message_id)
    except Exception:
        pass

    # 3b. "Sí" a una cita propuesta: se confirma por texto, sin botones
    # y sin llamar al agente. Vale de noche (fuera de horario) y de día:
    # si el cliente ya aceptó la fecha, no hay nada que preguntarle.
    # Si la propuesta es vieja (más de 48 h), se descarta y se sigue normal.
    # (v2.7) PERO: un "sí" solo confirma si el último mensaje del robot
    # fue la propuesta. Si lo último que el robot dijo fue "dame un
    # momento" (Gemini falló), un "sí gracias" es cortesía, no una
    # confirmación: el 12 de noviembre de 2026 un "sí gracias" confirmó
    # una cita que ya estaba ocupada y el robot contestó "esa hora ya
    # se ocupó". En ese caso el "sí" va al agente, que atiende normal.
    historial = deps.leer_historial(telefono)
    ultimo_robot = None
    for fila in reversed(historial or []):
        if fila.get("quien_hablo") == "robot":
            ultimo_robot = fila
            break
    ultimo_fue_fallo = bool(
        ultimo_robot
        and (
            ultimo_robot.get("motivo") == "falla tecnica"
            or str(ultimo_robot.get("mensaje", "")).startswith("Dame un momento")
        )
    )
    propuesta = _CITAS_PENDIENTES.get(telefono)
    if propuesta and _es_afirmacion(texto) and not ultimo_fue_fallo:
        creado_en = propuesta.get("creado_en")
        vigente = True
        if creado_en:
            try:
                creado = _parse_fecha_iso(creado_en)
                if creado is None:
                    vigente = True
                else:
                    if creado.tzinfo is None:
                        creado = creado.replace(tzinfo=timezone.utc)
                    vigente = ahora - creado < _VIGENCIA_PROPUESTA
            except ValueError:
                vigente = True
        if vigente:
            return _confirmar_cita_propuesta(deps, telefono, nombre, fecha, con_ritmo)
        _borrar_propuesta(deps, telefono)

    # 3b2. Confirmación de asistencia (v3.12, Sereno función 03): el
    # paciente confirma que SÍ vendrá a una cita ya creada ("confirmo",
    # "ahí nos vemos"). Solo sin propuesta vigente (eso es 3b) y solo
    # si tiene una cita futura registrada: sin cita, "confirmo" va al
    # agente como cualquier otro mensaje.
    if _es_confirmacion_asistencia(texto) and not _CITAS_PENDIENTES.get(telefono):
        _cita_futura = _cita_futura_para_confirmar(deps, telefono, ahora)
        if _cita_futura:
            return _registrar_confirmacion_asistencia(
                deps, telefono, nombre, fecha, _cita_futura, con_ritmo)

    # 3c. Cambiar / cancelar cita: se atiende ANTES que el agente, de
    # día y de noche. Un "mejor no" o un "prefiero otra" no es una
    # pregunta nueva: es una decisión sobre la cita que ya tiene.
    intencion = _intencion_cambio(texto, hay_propuesta=telefono in _CITAS_PENDIENTES)
    # (v3.4.9) Con propuesta pendiente, un mensaje que trae otro día u
    # otra hora ("mejor el viernes a las 10") es cambiar la cita: el
    # cliente ya dijo a qué hora la quiere. No se le pregunta otra vez.
    # (Si es una pregunta, "¿tienen lugar el viernes?", va al agente
    # con la propuesta intacta.)
    if (intencion is None and telefono in _CITAS_PENDIENTES
            and _tiene_fecha_especifica(texto)
            and not texto.strip().endswith("?")):
        intencion = "cambiar"
    if intencion == "cambiar" and telefono in _CITAS_PENDIENTES and _tiene_fecha_especifica(texto):
        # (v3.4.9) "Mejor el viernes a las 10": el cliente ya dijo el
        # nuevo día y hora. No se le pregunta otra vez lo que ya dijo:
        # se borra la propuesta vieja y el agente propone la nueva con
        # botones. Si ya hay una cita creada (no solo una propuesta),
        # se sigue por el camino seguro de abajo.
        _cliente_tmp = (getattr(deps, "leer_cliente", lambda t: None)(telefono) or {})
        _agendada = (str(_cliente_tmp.get("estatus", "")).strip().lower() == "agendado"
                     and str(_cliente_tmp.get("fecha_cita", "") or "").strip())
        if not _agendada:
            _borrar_propuesta(deps, telefono)
            intencion = None  # sigue al agente, que propone la nueva hora
    if intencion is not None:
        return _atender_cambio_cancelacion(deps, telefono, nombre, fecha, intencion, con_ritmo, ahora=ahora)

    # 3d. Mensaje sin letras ni números (solo emojis o símbolos): no
    # hay nada que preguntarle a la IA. Respuesta cálida directa.
    # (Con propuesta pendiente, un "👍" ya confirmó arriba, en 3b.)
    if not re.search(r"[a-z0-9]", _sin_acentos(texto)):
        _pend = _CITAS_PENDIENTES.get(telefono)
        if _pend:
            mensaje = (
                f"¡Gracias! Tu cita para el {_pend.get('fecha_bonita', '')} "
                "sigue en pie. ¿Te la confirmo?"
            )
        else:
            mensaje = "¡Gracias! ¿En qué te ayudo hoy?"
        enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
        deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", "mensaje sin texto")
        return {"respondio": True, "handoff": False}

    # 4. Cargar lo que el robot necesita saber.
    # (El historial ya se cargó arriba, en el paso 3b, para saber si
    # el último mensaje del robot fue un fallo.)
    conocimiento = deps.leer_conocimiento()
    fotos = deps.leer_fotos()

    # 5. Contexto para el agente (v2.6): la IA contesta SIEMPRE, de día
    # y de noche, y siempre sabe qué hora es, si el negocio está
    # abierto, a qué hora abre, cuál es la próxima apertura y cómo se
    # llama el cliente. Ya NO hay atajo con frase grabada: ni para un
    # primer "hola" de noche, ni como respaldo si Gemini falla.
    # La frase grabada escondía los fallos de Gemini: el cliente veía
    # siempre la misma respuesta y parecía que no había IA, cuando lo
    # que pasaba es que la IA no estaba contestando. Ahora, si Gemini
    # falla, el cliente recibe un "dame un momento" honesto (paso 8)
    # y el dueño un correo: el fallo se ve, no se disfraza.
    abierto, resumen_horarios = horario_abierto(conocimiento, ahora)
    proxima = proxima_apertura(conocimiento, ahora) if not abierto else None
    local_ahora = _a_hora_local(ahora)
    # (v3.1) Mañana, escrito tal cual: el 12 de noviembre el robot
    # ofreció "mañana viernes" a las 00:00 del viernes, cuando hoy YA
    # era viernes. Con el día de mañana explícito en el contexto, el
    # modelo no tiene que calcularlo (y el revisor R4 lo corrige si
    # aun así se equivoca).
    manana = local_ahora + timedelta(days=1)
    contexto = [
        f"Hoy es {_DIAS_NOMBRE[local_ahora.weekday()]} {local_ahora.day} de "
        f"{_MESES[local_ahora.month - 1]}, son las {local_ahora:%H:%M} (hora del negocio).",
        f"Mañana es {_DIAS_NOMBRE[manana.weekday()]} {manana.day} de {_MESES[manana.month - 1]}.",
        f"El negocio está {'ABIERTO' if abierto else 'CERRADO'}: abre {resumen_horarios}.",
    ]
    if nombre:
        contexto.append(f"El cliente se llama {nombre}: salúdalo por su nombre la primera vez.")
    if not abierto:
        proxima_txt = formatear_cita_bonita(proxima.isoformat()) if proxima is not None else ""
        contexto.append(
            "No agendes para hoy ni para una hora en que esté cerrado. "
            f"Si el cliente quiere una cita, ofrécele la próxima apertura: {proxima_txt}."
        )
    propuesta_activa = _CITAS_PENDIENTES.get(telefono)
    if propuesta_activa:
        contexto.append(
            "Ya le propusiste una cita para el "
            f"{propuesta_activa.get('fecha_bonita', '')} (AÚN NO está confirmada: "
            "falta que él confirme con los botones). Si te pregunta por ella, "
            "recuérdale la fecha SIN decir que ya está agendada ni apuntada; "
            "si dice que le va, confirma; si prefiere otra, pregunta cuál."
        )
        # (v3.2) Memoria de apartados: si le apartaron el lugar, el
        # robot tiene que recordarlo cuando el cliente vuelva, no
        # ofrecerle otra cosa como si nada hubiera pasado.
        if str(propuesta_activa.get("apartado", "") or "").strip().lower() == "si":
            contexto.append(
                "Le apartaste el lugar hasta "
                f"{propuesta_activa.get('aparta_hasta', 'mañana')}: si escribe, "
                "recuérdale que su lugar sigue apartado."
            )
    contexto.append("Responde su mensaje con calma, como una persona, usando tu criterio.")
    # (v2.13) Estado del cliente, calculado por código: la IA ya no
    # tiene que deducir en qué va la conversación leyendo las filas
    # crudas de la hoja. Se lo pasamos como datos, no como prosa.
    leer_cliente_fn = getattr(deps, "leer_cliente", lambda t: None)
    try:
        fila_cliente = leer_cliente_fn(telefono) or {}
    except Exception:
        fila_cliente = {}
    estado = estado_cliente(
        historial, _CITAS_PENDIENTES.get(telefono), fila_cliente, nombre,
        ahora=ahora,
    )
    # (v3.10) ¿La cita del cliente es a futuro? R8 la usa: una cita ya
    # pasada no justifica afirmar una cita nueva. La fecha de Clientes
    # viene en hora del negocio (naive); se compara en hora local.
    estado["tiene_cita_futura"] = _cita_es_futura(fila_cliente, ahora)
    # (v3.11) Memoria: una cita ya pasada no es vigente. Se le dice
    # al agente para que no ofrezca cambiarla ni la trate como viva
    # (en vivo el 2026-11-22 el robot ofreció cambiar "tus horas" por
    # una cita del 19 de noviembre que ya había pasado).
    _fc_pasada = str(fila_cliente.get("fecha_cita", "") or "").strip()
    if (
        _fc_pasada
        and str(fila_cliente.get("estatus", "") or "").strip().lower() == "agendado"
        and not estado.get("tiene_cita")
    ):
        try:
            _bonita_pasada = formatear_cita_bonita(_fc_pasada)
        except Exception:
            _bonita_pasada = _fc_pasada
        contexto.append(
            f"Su última cita fue el {_bonita_pasada} y ya pasó: no la "
            "trates como vigente ni le ofrezcas cambiarla."
        )
    # (v3.2) Memoria del cliente: lo que el robot aprendió en
    # conversaciones pasadas (resumen, intereses, pendientes,
    # preferencias). Va ANTES de los últimos mensajes: así el robot
    # recuerda de ayer y de la semana pasada, no solo de hace 5
    # minutos. Solo se pone lo que hay: un campo vacío no se menciona.
    memoria = []
    if str(fila_cliente.get("resumen_conversacion", "") or "").strip():
        memoria.append(f"Resumen: {fila_cliente['resumen_conversacion']}")
    if str(fila_cliente.get("intereses", "") or "").strip():
        memoria.append(f"Le interesa {fila_cliente['intereses']}")
    if str(fila_cliente.get("proxima_accion", "") or "").strip():
        memoria.append(f"Quedaron en: {fila_cliente['proxima_accion']}")
    if str(fila_cliente.get("notas", "") or "").strip():
        memoria.append(f"Prefiere {fila_cliente['notas']}")
    if memoria:
        contexto.append(
            "Lo que sabes de este cliente: " + " ".join(memoria)
            + " Úsalo con naturalidad: si vuelve, salúdalo recordando de qué "
            "hablaban, como si lo conocieras de antes. No vuelvas a preguntar "
            "lo que ya sabes y nunca menciones 'pendientes' ni listas: dilo "
            "en una frase corta y cálida."
        )
    # (v3.4.2) Cliente que vuelve: si ya hay historial o memoria, el
    # saludo recuerda de qué hablaban en vez de tratarlo como nuevo.
    # Si pasaron días desde el último mensaje, se dice explícitamente
    # para que el saludo suene a regreso, no a arranque en frío.
    if _mensajes_previos(historial, texto) or memoria:
        if estado["etapa"] == "saludo":
            dias = _dias_desde_ultimo_mensaje(historial, texto, ahora)
            if dias is not None and dias >= 1:
                contexto.append(
                    f"Hace {dias} día(s) que este cliente no escribía. "
                    "Salúdalo con gusto recordando de qué hablaban la última "
                    "vez; no lo trates como nuevo ni le preguntes el nombre "
                    "otra vez."
                )
            else:
                contexto.append(
                    "Este cliente ya ha hablado contigo antes: salúdalo "
                    "recordando de qué hablaban, no como a un desconocido."
                )
        elif estado["etapa"] == "pregunto":
            # (v3.4.6) Si preguntó algo concreto, se responde eso primero.
            # Antes el saludo de regreso tapaba la pregunta (en vivo:
            # "¿qué recibiste?" recibió un saludo en vez de respuesta).
            contexto.append(
                "Este cliente ya ha hablado contigo antes. Responde su "
                "pregunta actual primero; si encaja con naturalidad, "
                "recuerda de qué hablaban. No lo trates como nuevo, pero "
                "tampoco ignores lo que pregunta."
            )
    # (v3.4.2) El nombre ya no se fuerza desde el contexto (antes pedía
    # preguntarlo "antes de seguir con lo demás", y sonaba a robot).
    # Lo pide el guion cuando encaje con naturalidad: al agendar o al
    # saludar a un cliente nuevo.
    # (v3.3) Huecos libres de verdad: el agente solo ofrece horas que
    # existen en el calendario. Antes inventaba "mañana a las 9:00" y
    # al confirmar salía "esa hora ya se ocupó". Solo se calculan
    # cuando el agente podría ofrecer (pregunto / oferta_pendiente):
    # un saludo no necesita huecos. Si la llamada falla (huecos=None),
    # no se dice nada: el agente actúa como antes, sin inventar.
    # (v3.10) También se calculan cuando el mensaje pide agendar con
    # palabras claras, aunque sea el primer mensaje del cliente
    # (etapa "nuevo"): sin huecos, la red de seguridad no puede
    # proponer con botones.
    _dias_msg = _dias_pedidos(texto)
    huecos_pro: list[dict] = []
    prof_por_iso: dict[str, str] = {}
    if estado["etapa"] in ("pregunto", "oferta_pendiente") or _quiere_agendar_ya(texto):
        try:
            if _dias_msg:
                # (v3.11) Pidió días concretos: se buscan huecos en un
                # rango amplio para poder ofrecerle ESE día, no el
                # primer hueco de la semana.
                huecos = _huecos_amplios(deps, conocimiento, ahora)
            else:
                huecos = deps.proximos_huecos_libres(conocimiento, ahora)
        except Exception:
            huecos = None
        # (v3.12) Agenda por profesional: si hay profesionales con
        # horario, los huecos salen de ellos (con nombre) y el resto
        # del flujo sigue igual con los ISO derivados. Sin datos se
        # queda la agenda por clínica de siempre.
        try:
            if _dias_msg:
                huecos_pro = _huecos_pro_amplios(deps, conocimiento, ahora) or []
            else:
                huecos_pro = deps.proximos_huecos_profesionales(conocimiento, ahora) or []
        except Exception:
            huecos_pro = []
        if huecos_pro:
            prof_por_iso = {
                h["inicio"]: str(h.get("profesional") or "")
                for h in huecos_pro if h.get("inicio")
            }
            huecos = [h["inicio"] for h in huecos_pro]
        if huecos and _dias_msg:
            # (v3.11) Hueco por día pedido: el agente ofrece el día
            # que el cliente mencionó, nunca inventa ni cambia el día.
            lineas = []
            for _d in _dias_msg:
                _iso_d = _hueco_en_dia(huecos, _d, ahora)
                if _iso_d:
                    try:
                        _dt_d = _a_hora_local(_parse_fecha_iso(_iso_d))
                        # (v3.12) Con agenda por profesional, el hueco
                        # trae nombre: "el martes a las 09:00 con la Dra. Ruiz".
                        _prof_d = _profesional_de_fecha(_iso_d, prof_por_iso)
                        _con_d = _con_profesional(_prof_d)
                        lineas.append(
                            f"el {_DIAS_NOMBRE[_d]} a las {_dt_d:%H:%M}{_con_d}"
                        )
                    except Exception:
                        pass
            if lineas:
                contexto.append(
                    "Huecos en los días que pidió: " + "; ".join(lineas)
                    + ". Ofrécele SOLO estos: nunca inventes una hora "
                    "ni cambies el día que pidió."
                )
            else:
                contexto.append(
                    "En los días que pidió no hay huecos libres por "
                    "ahora: no ofrezcas cita para esos días; di que la "
                    "agenda está llena por ahora y pregúntale si quiere "
                    "que le avises cuando se libere algo."
                )
        elif huecos:
            bonitos = []
            for iso in huecos[:2]:
                try:
                    _bonita = formatear_cita_bonita(iso)
                    # (v3.12) Con agenda por profesional: "... con la Dra. Ruiz".
                    _prof_h = _profesional_de_fecha(iso, prof_por_iso)
                    bonitos.append(f"{_bonita}{_con_profesional(_prof_h)}")
                except (ValueError, TypeError):
                    pass
            if bonitos:
                contexto.append(
                    "Los próximos huecos libres para agendar son: "
                    + " y ".join(bonitos)
                    + ". Ofrécele SOLO estos: nunca inventes una hora."
                )
        elif huecos is not None:
            contexto.append(
                "No hay huecos libres en los próximos 3 días: no ofrezcas "
                "cita, di que la agenda está llena por ahora y pregúntale "
                "si quiere que le avises cuando se libere algo."
            )
    mensaje_agente = (
        "[Contexto: " + " ".join(contexto) + "]\n"
        "[Estado del cliente: " + json.dumps(estado, ensure_ascii=False) + "]\n"
        f"{texto}"
    )

    # 6. El agente decide qué responder y qué hacer. La burbuja ya
    # salió en el webhook y se volvió a prender en el paso 3; aquí
    # ya no se refresca (v3.9.2): refrescarla sin fin hacía que el
    # "escribiendo..." durara lo que tardara Gemini, y eso se siente
    # robótico. Una persona escribe un rato y se calla.
    # (v3.3) Urgencia: si el cliente dice que es urgente o que le
    # duele, no se llama al agente: se pasa a una persona en ese
    # momento, con el correo al dueño (paso 8, handoff).
    # (v3.12, Sereno demanda 3) Antes del handoff, el cliente recibe
    # la orientación del protocolo aprobado: si es una urgencia
    # médica, buscar atención inmediata. Nunca indicaciones ni
    # diagnósticos: solo orientar y pasar a una persona. La clínica
    # puede personalizar el texto con `mensaje_urgencia`.
    if _es_urgencia(texto):
        # (v3.14) La respuesta de urgencia la COMPOSE LA IA, no una
        # plantilla: el cliente merece una respuesta pensada, no un
        # copy-paste. El código fuerza el handoff (la detección es
        # por palabras, sin depender de que la IA lo marque) y la
        # oferta de cita con botones. Si la IA falla, texto fijo de
        # respaldo: una urgencia nunca se queda sin respuesta.
        _razon = f"{_MOTIVO_URGENCIA}: {texto[:120]}"
        # (v3.15) El plan se decide ANTES de llamar a la IA: si el
        # cliente ya tiene una cita propia, la urgencia propone
        # adelantarla; si no, una cita nueva. La IA solo lo dice con
        # naturalidad; el código ejecuta (botones, movimiento, CRM,
        # correo).
        _plan = _plan_urgencia(deps, telefono, nombre, conocimiento, ahora)
        _hecho_plan = _hecho_del_plan(_plan, deps, telefono, ahora)
        _marco_urgencia = (
            "[URGENTE] El cliente expresa urgencia o dolor. Responde como una buena "
            "recepcionista: reconoce lo que siente con empatía, dile que lo pasas con "
            "una persona de inmediato y que lo atenderán lo antes posible. "
            "Responde corto: máximo 2 frases, un solo mensaje. "
            "El protocolo de urgencias es tu guía: dilo con tus propias palabras, "
            "integrado a tu respuesta, nunca copiado literal. "
            "No digas 'como te comenté' ni 'como te dije': di las cosas directamente. "
            + ("El negocio está CERRADO ahora: dilo con empatía, puede que tarden en "
               "responder hasta que abran. " if not abierto else "")
            + "Si parece una urgencia médica grave, oriéntalo a buscar atención inmediata. "
            "Nunca des diagnósticos ni indicaciones médicas, nunca hagas preguntas "
            "innecesarias. No ofrezcas la cita tú: el sistema la propone con botones "
            "justo después de tu mensaje. "
            + _hecho_plan
        )
        try:
            respuesta = deps.preguntar_agente(
                f"{_marco_urgencia}\n{mensaje_agente}", conocimiento, fotos, historial)
        except Exception:
            respuesta = None
        if (respuesta is None or respuesta.falla_tecnica
                or not (respuesta.respuesta_texto or "").strip()):
            respuesta = RespuestaAgente(
                respuesta_texto=_texto_urgencia_fijo(abierto),
                nombre=nombre, motivo=texto[:120])
        respuesta.necesita_handoff = "si"
        respuesta.motivo_handoff = _razon
        respuesta.nombre = nombre
        respuesta.motivo = texto[:120]
        _propuesta_cita_urgente(
            deps, telefono, nombre, texto, conocimiento, ahora, _razon, plan=_plan)
    else:
        respuesta = deps.preguntar_agente(mensaje_agente, conocimiento, fotos, historial)

    # (v2.13) Revisor: segunda mirada antes de mandar. Si la respuesta
    # repite una oferta pendiente, ofrece cita en un saludo o dice
    # "ya cerramos", se corrige aquí, no en el teléfono del cliente.
    # La falla técnica ("dame un momento") no se toca: es honesta.
    # (v3.14) La respuesta de urgencia TAMBIÉN pasa por el revisor:
    # ahora la compone la IA, así que merece la misma segunda mirada
    # que cualquier otra respuesta.
    # Lo corregido queda en Diagnóstico, para ver qué se atrapó.
    if not respuesta.falla_tecnica:
        texto_revisado, violaciones = revisar_respuesta(
            respuesta.respuesta_texto, estado, nombre,
            ahora=local_ahora, telefono=telefono,
        )
        if violaciones:
            _diagnostico(
                deps, fecha, "revision", "CORREGIDO",
                "Reglas corregidas antes de mandar: " + ", ".join(violaciones)
                + f" (modelo: {getattr(respuesta, 'modelo', '') or 'sin dato'})",
                telefono, texto,
            )
            respuesta.respuesta_texto = texto_revisado

    # (v3.4.8) Las partes también pasan por el revisor, una por una:
    # cada mensaje que el cliente va a ver merece la segunda mirada.
    if respuesta.partes and not respuesta.falla_tecnica:
        partes_revisadas: list[str] = []
        violaciones_partes: list[str] = []
        for parte in respuesta.partes:
            texto_p, viol_p = revisar_respuesta(
                parte, estado, nombre, ahora=local_ahora, telefono=telefono,
            )
            partes_revisadas.append(texto_p)
            violaciones_partes.extend(viol_p)
        respuesta.partes = partes_revisadas
        if violaciones_partes:
            _diagnostico(
                deps, fecha, "revision", "CORREGIDO",
                "Reglas corregidas en las partes: "
                + ", ".join(sorted(set(violaciones_partes)))
                + f" (modelo: {getattr(respuesta, 'modelo', '') or 'sin dato'})",
                telefono, texto,
            )

    # (v3.4.9) El nombre que el cliente dio DESPUÉS de la propuesta
    # (el robot se lo pidió al agendar) se guarda en la propuesta
    # pendiente: la confirmación sale con su nombre, no vacía. Y si
    # dio otro número para el registro ("regístralo al 667..."), se
    # guarda también: la cita queda registrada al número que él dio.
    _pendiente = _CITAS_PENDIENTES.get(telefono)
    if _pendiente:
        # Solo se reemplaza si la propuesta trae el nombre de perfil
        # (el que el robot puso por defecto) o ninguno: el nombre
        # completo que dio el cliente vale más que el de WhatsApp.
        _nombre_previo = str(_pendiente.get("nombre") or "").strip()
        if respuesta.nombre and (
            not _nombre_previo or _nombre_previo == str(nombre or "").strip()
        ):
            _pendiente["nombre"] = respuesta.nombre
            _guardar_propuesta(deps, telefono, _pendiente)
        _num_registro = _extraer_telefono(texto, telefono)
        if _num_registro and _num_registro != str(_pendiente.get("telefono_registro") or "").strip():
            _pendiente["telefono_registro"] = _num_registro
            _guardar_propuesta(deps, telefono, _pendiente)

    # (v3.10) Datos de la otra persona: si el agente extrajo el nombre
    # o el número de la persona de la cita (porque el robot lo pidió
    # tras confirmar), se guardan en las Notas de la cita espejo, para
    # que el dueño los vea. Best-effort: nunca rompe la respuesta.
    _nombre_pac = str(getattr(respuesta, "nombre_paciente", "") or "").strip()
    _numero_pac = str(getattr(respuesta, "numero_paciente", "") or "").strip()
    if _nombre_pac or _numero_pac:
        _guardar_datos_paciente(deps, telefono, _nombre_pac, _numero_pac)

    # (v3.2) Memoria de apartados: si la respuesta le aparta el lugar
    # y hay una propuesta activa, el apartado queda guardado en la
    # propuesta (memoria Y hoja), hasta mañana. Si el cliente vuelve,
    # el contexto se lo recuerda al agente.
    propuesta_activa = _CITAS_PENDIENTES.get(telefono)
    if propuesta_activa and _contiene_aparto(respuesta.respuesta_texto):
        manana = local_ahora + timedelta(days=1)
        propuesta_activa["apartado"] = "si"
        propuesta_activa["aparta_hasta"] = (
            f"mañana {_DIAS_NOMBRE[manana.weekday()]} {manana.day}"
        )
        _guardar_propuesta(deps, telefono, propuesta_activa)

    # 7. Foto: solo si está en la lista blanca. Si no, se borra sin avisar al cliente.
    foto = respuesta.foto_oficial_url_or_null
    if not foto_es_oficial(foto, fotos):
        foto = ""

    # 8. Handoff: el robot deja de contestar este hilo.
    if respuesta.necesita_handoff == "si":
        if respuesta.falla_tecnica:
            # Gemini falló: al cliente un "dame un momento" (no silencio),
            # al dueño un correo de error, y queda escrito en Diagnóstico
            # para revisarlo desde la hoja sin entrar a Render (v2.7).
            # (v3.9.1) Si el vigilante ya mandó el "dame un momento"
            # (el lote tardó más de 90 s), NO mandar el mismo texto
            # otra vez: el cliente recibía dos burbujas idénticas.
            # El registro en la hoja y los avisos quedan igual.
            _aviso_ya = (
                isinstance(aviso_lote_enviado, dict)
                and bool(aviso_lote_enviado.get("si"))
            )
            if not _aviso_ya:
                enviar_con_ritmo(deps.enviar_texto, telefono, respuesta.respuesta_texto, dormir=con_ritmo)
            deps.registrar_conversacion(fecha, telefono, "robot", respuesta.respuesta_texto, "si", "falla tecnica")
            _diagnostico(deps, fecha, "gemini", "FALLO", respuesta.motivo_handoff or "Gemini no contestó",
                         telefono, texto)
            _avisar_por_correo(deps.alerta_error, respuesta.motivo_handoff, telefono, texto, fecha)
        else:
            # (v3.3.1) El cliente TAMBIÉN recibe el texto del handoff
            # ("te paso con una persona..."). Antes solo llegaba el
            # correo al dueño y el cliente quedaba en silencio esperando
            # a que un humano se diera cuenta. Jose lo pidió 2026-11-13.
            # (v3.14) En una urgencia el texto lo compone la IA; en un
            # handoff normal, el del agente. (v3.14.2) La urgencia sale
            # en UNA sola burbuja: es un mensaje que se lee completo.
            _es_urgencia_handoff = str(respuesta.motivo_handoff or "").startswith(_MOTIVO_URGENCIA)
            enviar_con_ritmo(deps.enviar_texto, telefono, respuesta.respuesta_texto,
                             dormir=con_ritmo, sin_dividir=_es_urgencia_handoff)
            deps.registrar_conversacion(fecha, telefono, "robot", respuesta.respuesta_texto, "si", "handoff")
            _avisar_por_correo(
                deps.alerta_handoff,
                respuesta.nombre or nombre, telefono, respuesta.motivo_handoff, texto, fecha,
                resumen=str(fila_cliente.get("resumen_conversacion", "") or ""),
            )
            # (v3.13) Urgencia con cita: después del mensaje de
            # handoff, la oferta de cita urgente con botones (la
            # propuesta se guardó al detectar la urgencia).
            if str(respuesta.motivo_handoff or "").startswith(_MOTIVO_URGENCIA):
                _enviar_propuesta_urgente(deps, telefono, fecha, con_ritmo)
        deps.registrar_cliente(
            fecha, respuesta.nombre or nombre, telefono,
            respuesta.motivo or texto, "", "whatsapp", "en conversacion", "si",
        )
        _guardar_memoria(deps, telefono, respuesta)
        # El cliente siempre recibe algo en un handoff (el texto o el
        # "dame un momento"): respondio es True en los dos casos.
        return {"respondio": True, "motivo": "handoff",
                "handoff": True, "falla_tecnica": respuesta.falla_tecnica}

    # (v3.5) Interruptor de agenda desde Configuración: si el negocio
    # apagó "agendar", el robot responde preguntas pero no propone
    # citas (ni por red de seguridad). Vacío en la hoja = SI, como
    # siempre. (v3.6) Ahora también manda el paquete: básico no agenda.
    _agendar_activo = funcion_activa("agendar")
    if not _agendar_activo:
        respuesta.quiere_agendar = "no"

    # (v3.4.7) Red de seguridad determinista: si el cliente pidió
    # agendar con sus propias palabras ("quiero agendar", "agéndame")
    # pero el agente no disparó la propuesta (listó los huecos en
    # texto en vez de marcar quiere_agendar), el programa propone
    # con el primer hueco libre. El paso que vende no se deja al azar
    # del modelo. (v3.4.11) La propuesta NO pide nombre ni número:
    # se piden después de confirmar, para no frenar la reserva.
    # (v3.11) La red respeta el DÍA que el cliente pidió: si mencionó
    # "el martes", la propuesta es para el martes (su primer hueco de
    # ese día), no para la próxima apertura. Si mencionó dos días y
    # otra persona ("el martes para mí y el miércoles para mi
    # hermana"), arma las dos citas en determinista. Y marca la
    # propuesta como de red de seguridad: el texto del agente (que
    # lista horas en texto) se reemplaza por una propuesta limpia,
    # sin fricción.
    _red_seguridad = False
    # (v3.11.1) La red también entra si el agente dijo "sí agendo"
    # pero sin fecha o con una fecha ilegible: sin esto, el cliente
    # que pidió cita en claro se quedaba sin propuesta (visto en la
    # simulación de 100 escenarios, caso X2: el modelo a veces marca
    # quiere_agendar sin mandar fecha). Con fecha válida del agente,
    # la red no toca nada.
    _fecha_rota = (
        respuesta.quiere_agendar == "si"
        and (
            not str(respuesta.fecha_cita or "").strip()
            or _parse_fecha_iso(respuesta.fecha_cita) is None
        )
    )
    if _agendar_activo and _quiere_agendar_ya(texto) and (
        respuesta.quiere_agendar != "si" or _fecha_rota
    ):
        _huecos = locals().get("huecos")
        if _huecos:
            _dias_msg = _dias_pedidos(texto)
            respuesta.quiere_agendar = "si"
            _red_seguridad = True
            if _dias_msg:
                _fecha_dia = _hueco_en_dia(_huecos, _dias_msg[0], ahora)
                if _fecha_dia:
                    respuesta.fecha_cita = _fecha_dia
                else:
                    _pa = proxima_apertura(
                        conocimiento, ahora,
                        desde=_proxima_fecha_dia(_dias_msg[0], ahora),
                    )
                    respuesta.fecha_cita = (
                        _pa.isoformat() if _pa else _huecos[0]
                    )
            else:
                respuesta.fecha_cita = _huecos[0]
            # Segunda cita en determinista: dos días + otra persona.
            if (
                len(_dias_msg) >= 2
                and not (getattr(respuesta, "citas_extra", None))
            ):
                _rel = _relacion_pedida(texto)
                if _rel:
                    _fecha2 = _hueco_en_dia(_huecos, _dias_msg[1], ahora)
                    if not _fecha2:
                        _pa2 = proxima_apertura(
                            conocimiento, ahora,
                            desde=_proxima_fecha_dia(_dias_msg[1], ahora),
                        )
                        _fecha2 = _pa2.isoformat() if _pa2 else None
                    if _fecha2:
                        respuesta.citas_extra = [{
                            "motivo": respuesta.motivo or texto,
                            "fecha_cita": _fecha2,
                            "nombre_paciente": "",
                            "relacion_paciente": _rel,
                        }]

    # 9. Agendar: NO se crea la cita todavía. Se propone con botones y
    # el cliente confirma. Así no se agenda nada por un malentendido.
    # (v2.4) La fecha que propone el agente se valida: si cae fuera de
    # horario o en el pasado (p. ej. de noche propuso para hoy), se
    # corrige sola a la próxima apertura. Si no hay próxima apertura,
    # no se propone nada: se contesta el texto del agente, sin botones.
    # (v3.10) La validación vive en _corregir_fecha_propuesta para
    # poder usarla también con la segunda cita.
    if respuesta.quiere_agendar == "si" and respuesta.fecha_cita:
        _huecos = locals().get("huecos")
        _fecha_ok = _corregir_fecha_propuesta(
            respuesta.fecha_cita, conocimiento, ahora, deps, _huecos)
        if _fecha_ok is None:
            respuesta.quiere_agendar = "no"
        else:
            respuesta.fecha_cita = _fecha_ok
    # (v3.10) Segunda cita (si el cliente pidió dos: la suya y la de
    # otra persona, o dos servicios). Cada extra se valida igual; si
    # no se puede corregir, se descarta y queda la primera sola.
    citas_extra_validas = []
    if respuesta.quiere_agendar == "si":
        for _extra in (getattr(respuesta, "citas_extra", None) or []):
            _fecha2 = _corregir_fecha_propuesta(
                _extra.get("fecha_cita"), conocimiento, ahora, deps,
                locals().get("huecos"))
            if _fecha2:
                try:
                    _bonita2 = formatear_cita_bonita(_fecha2)
                except (ValueError, TypeError):
                    _bonita2 = _fecha2
                citas_extra_validas.append({
                    "motivo": _extra.get("motivo") or respuesta.motivo or texto,
                    "fecha_cita": _fecha2,
                    "fecha_bonita": _bonita2,
                    "nombre_paciente": str(_extra.get("nombre_paciente") or "").strip(),
                    "relacion_paciente": str(_extra.get("relacion_paciente") or "").strip(),
                    "numero_paciente": str(_extra.get("numero_paciente") or "").strip(),
                    # (v3.12) Profesional del hueco de esta segunda cita.
                    "profesional": _profesional_de_fecha(_fecha2, prof_por_iso),
                })
    if respuesta.quiere_agendar == "si" and respuesta.fecha_cita:
        # (v3.10) Tope de 2 citas por número (la suya y la de otra
        # persona): para que nadie inunde el calendario. Se revisa
        # antes de proponer, no solo al confirmar.
        _n_citas = 1 + len(citas_extra_validas)
        if _citas_activas_telefono(deps, telefono, ahora) + _n_citas > MAX_CITAS_POR_NUMERO:
            mensaje_tope = (
                "Ya tienes 2 citas registradas con este número, para no "
                "llenar la agenda. Si quieres cambiar alguna, dime cuál y "
                "te ayudo con gusto."
            )
            enviar_con_ritmo(deps.enviar_texto, telefono, mensaje_tope, dormir=con_ritmo)
            deps.registrar_conversacion(
                fecha, telefono, "robot", mensaje_tope, "si", "tope de citas por numero")
            return {"respondio": True, "handoff": False, "cita_propuesta": False}
        # (v3.4.11) La propuesta NO pide nombre ni número: pedirlos
        # en el mismo mensaje que la confirmación crea fricción
        # (el cliente no sabe si contestar en texto o tocar el botón).
        # Se piden DESPUÉS de confirmar, en _confirmar_cita_propuesta:
        # primero el compromiso, luego los datos. La cita ya quedó.
        # (v3.4.8) Si ya hay una propuesta con botones pendiente para
        # ESA MISMA cita, no se mandan botones otra vez: el cliente
        # recibe el texto (su pregunta contestada) y la propuesta
        # sigue viva. En vivo, dos mensajes seguidos generaron dos
        # "¿Confirmo tu cita...?" para la misma cita.
        previa = _CITAS_PENDIENTES.get(telefono)
        _misma_cita2 = False
        if previa and previa.get("cita2") and citas_extra_validas:
            _misma_cita2 = _misma_fecha(
                previa["cita2"].get("fecha_cita"), citas_extra_validas[0]["fecha_cita"])
        if (
            previa
            and _misma_fecha(previa.get("fecha_cita"), respuesta.fecha_cita)
            and (not citas_extra_validas or _misma_cita2)
            and _propuesta_vigente(previa, ahora)
        ):
            enviar_con_ritmo(
                deps.enviar_texto, telefono, respuesta.respuesta_texto,
                dormir=con_ritmo,
            )
            deps.registrar_conversacion(
                fecha, telefono, "robot", respuesta.respuesta_texto,
                "si", respuesta.motivo,
            )
            deps.registrar_cliente(
                fecha, respuesta.nombre or nombre, telefono,
                respuesta.motivo or texto, respuesta.fecha_cita,
                "whatsapp", "en conversacion", "no",
            )
            _guardar_memoria(deps, telefono, respuesta)
            return {"respondio": True, "handoff": False,
                    "cita_propuesta": True, "fecha_cita": respuesta.fecha_cita}
        try:
            fecha_bonita = formatear_cita_bonita(respuesta.fecha_cita)
        except (ValueError, TypeError):
            fecha_bonita = respuesta.fecha_cita
        cita2 = citas_extra_validas[0] if citas_extra_validas else None
        # (v3.12) Si el cliente venía de cambiar una de dos citas, la
        # otra se retoma aquí: viaja junto con la nueva en vez de
        # perderse. Solo si la propuesta nueva no trae ya segunda
        # cita y el tope de 2 por número lo permite.
        if cita2 is None:
            _retomar = _tomar_retomar(telefono, ahora)
            if _retomar and (
                _citas_activas_telefono(deps, telefono, ahora) + 2 <= MAX_CITAS_POR_NUMERO
            ):
                cita2 = _retomar
        # (v3.12) Profesional del hueco elegido (agenda por profesional):
        # "" si no hay agenda por profesional o la fecha no viene de un hueco.
        _profesional = _profesional_de_fecha(respuesta.fecha_cita, prof_por_iso)
        _con_pro = _con_profesional(_profesional)
        if cita2:
            # (v3.10) Dos citas en una propuesta: se listan las dos y
            # un solo botón las confirma ("Confirmar ambas").
            # (v3.12) Si la primera cita es de otra persona (el cliente
            # cambió la de ella y se retoma la suya), las etiquetas se
            # invierten para no confundir.
            _rel1 = str(
                getattr(respuesta, "relacion_paciente", "") or ""
            ).strip() or str(
                getattr(respuesta, "nombre_paciente", "") or ""
            ).strip()
            _prof2 = str(cita2.get("profesional") or "").strip()
            _con_pro2 = _con_profesional(_prof2)
            if _rel1:
                propuesta = (
                    "¡Con gusto! Te propongo:\n"
                    f"• La cita de {_rel1} para el {fecha_bonita}{_con_pro}.\n"
                    f"• Tu cita para el {cita2['fecha_bonita']}{_con_pro2}.\n"
                    "¿Confirmamos ambas?"
                )
            else:
                _rel2 = str(cita2.get("relacion_paciente") or "").strip()
                _etiqueta2 = f"la cita de {_rel2}" if _rel2 else "tu segunda cita"
                propuesta = (
                    "¡Con gusto! Te propongo:\n"
                    f"• Tu cita para el {fecha_bonita}{_con_pro}.\n"
                    f"• {_etiqueta2.capitalize()} para el {cita2['fecha_bonita']}{_con_pro2}.\n"
                    "¿Confirmamos ambas?"
                )
            botones = [
                ("confirmar_cita", "Confirmar ambas"),
                ("cambiar_hora", "Cambiar hora"),
                ("hablar_persona", "Hablar con persona"),
            ]
        else:
            if _red_seguridad:
                # (v3.11) Propuesta de la red de seguridad: texto
                # limpio, sin la lista de horas del agente. Una sola
                # pregunta + botones: el cliente toca, no teclea.
                propuesta = (
                    f"¡Con gusto! Te propongo tu cita para el {fecha_bonita}{_con_pro}. "
                    "¿La confirmamos?"
                )
            else:
                # (v3.4.9) Si el agente preguntó "¿Te agendo...?" o
                # "¿Confirmo...?" en su texto, esa pregunta se quita: el
                # sistema agrega la confirmación con botones. Nunca dos
                # preguntas de confirmación en el mismo mensaje.
                # (v3.12) La fecha lleva al profesional cuando el hueco
                # lo trae: "¿Confirmo tu cita para el martes... con la
                # Dra. Ruiz?" — el cliente sabe con quién va.
                _fecha_con = f"{fecha_bonita}{_con_pro}"
                texto_propuesta = re.sub(
                    r"¿(te (la )?agendo|confirmo|te reservo)[^?]*\?\s*",
                    "", respuesta.respuesta_texto, flags=re.IGNORECASE,
                ).strip()
                if texto_propuesta:
                    propuesta = f"{texto_propuesta}\n\n¿Confirmo tu cita para el {_fecha_con}?"
                else:
                    propuesta = f"¿Confirmo tu cita para el {_fecha_con}?"
            botones = BOTONES_CITA
        propuesta_dict = {
            "nombre": respuesta.nombre or nombre,
            "motivo": respuesta.motivo or texto,
            "fecha_cita": respuesta.fecha_cita,
            "fecha_bonita": fecha_bonita,
            "creado_en": ahora.isoformat(),
            "profesional": _profesional,
            "nombre_paciente": str(getattr(respuesta, "nombre_paciente", "") or "").strip(),
            "relacion_paciente": str(getattr(respuesta, "relacion_paciente", "") or "").strip(),
            "numero_paciente": str(getattr(respuesta, "numero_paciente", "") or "").strip(),
            "cita2": cita2,
        }
        propuesta_dict["extra_json"] = _extra_propuesta_json(propuesta_dict)
        _guardar_propuesta(deps, telefono, propuesta_dict)
        # (v3.3) Lead caliente: si el cliente PIDIÓ agendar con sus
        # propias palabras ("quiero una cita"), el dueño se entera en
        # el momento, no el lunes. Si solo preguntó un precio y el
        # robot le ofreció, no hay correo: eso no es un lead caliente.
        # (v3.7) Con alertas_instantaneas=NO, el lead va en el correo
        # semanal de 3 tipos (sección clientes por recuperar).
        if _quiere_agendar_ya(texto) and funcion_activa("alertas_instantaneas"):
            _avisar_por_correo(
                getattr(deps, "alerta_lead_caliente", None),
                respuesta.nombre or nombre, telefono,
                respuesta.motivo or texto, texto, fecha,
            )
        try:
            deps.enviar_botones(telefono, propuesta, botones)
        except Exception as exc:
            # Si los botones fallan, se manda el texto normal: el cliente
            # puede contestar "sí" escribiendo. Nunca se queda sin respuesta.
            # (v3.11) El fallo se registra en Diagnóstico: antes caía a
            # texto en silencio y el error real de Meta era invisible.
            # Sin este registro, "no aparece el botón" no se puede
            # diagnosticar (Jose lo reportó el 2026-11-22).
            try:
                deps.registrar_diagnostico(
                    fecha, "whatsapp", "FALLO",
                    f"Botones no enviados: {str(exc)[:250]}",
                    telefono, "propuesta con botones",
                )
            except Exception:
                pass
            enviar_con_ritmo(deps.enviar_texto, telefono, propuesta, dormir=con_ritmo)
        deps.registrar_conversacion(fecha, telefono, "robot", propuesta, "si", respuesta.motivo)
        deps.registrar_cliente(
            fecha, respuesta.nombre or nombre, telefono,
            respuesta.motivo or texto, respuesta.fecha_cita,
            "whatsapp", "en conversacion", "no",
        )
        _guardar_memoria(deps, telefono, respuesta)
        return {"respondio": True, "handoff": False, "cita_propuesta": True,
                "fecha_cita": respuesta.fecha_cita}

    # 10. Responder por WhatsApp, con ritmo humano: foto oficial primero
    # (si la hay), luego el texto. Si el agente decidió partes, cada
    # parte va como su propio mensaje, en orden (v3.4.8).
    # (v3.5) Interruptor de fotos desde Configuración: si está en NO,
    # no se manda ninguna foto (el texto sale igual). (v3.6) El
    # paquete básico tampoco manda fotos.
    if foto and funcion_activa("enviar_fotos"):
        deps.enviar_foto(telefono, foto)
    if respuesta.partes:
        enviar_partes(deps.enviar_texto, telefono, respuesta.partes, dormir=con_ritmo)
        texto_registro = "\n\n".join(respuesta.partes)
    else:
        enviar_con_ritmo(deps.enviar_texto, telefono, respuesta.respuesta_texto, dormir=con_ritmo)
        texto_registro = respuesta.respuesta_texto

    # 11. Registrar la respuesta del robot y al cliente (las DOS hojas).
    deps.registrar_conversacion(
        fecha, telefono, "robot", texto_registro, "si",
        respuesta.motivo,
    )
    # (v2.5) De noche, TODO el que escribe es un lead: si el agente no
    # sacó nombre ni motivo (p. ej. solo saludó o preguntó algo corto),
    # se registra igual con su mensaje como motivo. De día se mantiene
    # la regla de siempre (solo si hay nombre o motivo), para no llenar
    # Clientes de saludos. registrar_cliente fusiona por teléfono:
    # nunca duplica la fila.
    if respuesta.nombre or respuesta.motivo or not abierto:
        deps.registrar_cliente(
            fecha, respuesta.nombre or nombre, telefono,
            respuesta.motivo or texto, respuesta.fecha_cita or "",
            "whatsapp",
            "calificado" if (respuesta.nombre or respuesta.motivo) else "en conversacion",
            "no",
        )
    _guardar_memoria(deps, telefono, respuesta)
    return {"respondio": True, "handoff": False, "cita": None, "foto": bool(foto)}


def atender_boton(
    deps: Dependencias,
    telefono: str,
    nombre: str,
    boton_id: str,
    fecha_iso: str | None = None,
    con_ritmo: bool = True,
    ahora: datetime | None = None,
) -> dict:
    """Atiende lo que el cliente tocó en los botones de la cita.

    - confirmar_cita: crea la cita y manda la confirmación bonita.
    - cambiar_hora: borra la propuesta y pregunta por otro día y hora.
    - hablar_persona: handoff (texto corto al cliente + correo al dueño).
    """
    ahora = ahora or datetime.now(timezone.utc)
    fecha = fecha_iso or ahora.isoformat()

    # Interruptor por cliente (v2.3): si el robot está apagado para este
    # cliente, no crea citas ni contesta. La propuesta pendiente se
    # borra para que un "sí" viejo no la confirme después. Excepción:
    # "hablar con una persona" sigue funcionando: es el camino al
    # humano, no una respuesta del robot.
    if boton_id in ("confirmar_cita", "cambiar_hora", "cambiar_mia", "cambiar_de_otra",
                     "adelantar_cita", "dejar_cita_igual"):
        leer_activo = getattr(deps, "leer_robot_activo", lambda t: "SI")
        if not robot_activo_para_cliente(leer_activo(telefono)):
            _borrar_propuesta(deps, telefono)
            deps.registrar_conversacion(
                fecha, telefono, "cliente", f"(botón {boton_id})", "no",
                "robot apagado para este cliente",
            )
            return {"respondio": False, "motivo": "robot apagado para este cliente", "handoff": False}

    if boton_id == "confirmar_cita":
        # El mismo camino que el "sí" por texto (ver _confirmar_cita_propuesta).
        return _confirmar_cita_propuesta(deps, telefono, nombre, fecha, con_ritmo)

    if boton_id == "adelantar_cita":
        # (v3.15) Mover la cita existente a la hora propuesta.
        return _confirmar_adelanto(deps, telefono, nombre, fecha, con_ritmo, ahora)

    if boton_id == "dejar_cita_igual":
        # (v3.15) El cliente prefirió dejar su cita como está.
        return _dejar_cita_igual(deps, telefono, nombre, fecha, con_ritmo, ahora)

    if boton_id == "cambiar_hora":
        # (v3.10) Con dos citas en la propuesta, se pregunta cuál
        # cambiar primero (la otra se retoma después).
        # (v3.11) Esa pregunta va con BOTONES: un toque en vez de
        # teclear. Regla de Jose: los botones están para reducir
        # fricción, en todos los casos.
        _propuesta_cambio = _CITAS_PENDIENTES.get(telefono)
        # (v3.12) Se guarda la propuesta completa para retomar la cita
        # que NO se cambie (antes se perdía al borrar la propuesta).
        if _propuesta_cambio and _propuesta_cambio.get("cita2"):
            _RETOMAR[telefono] = {
                "propuesta": _propuesta_cambio,
                "creado_en": ahora.isoformat(),
            }
        _borrar_propuesta(deps, telefono)
        if _propuesta_cambio and _propuesta_cambio.get("cita2"):
            _rel_cambio = str(
                (_propuesta_cambio.get("cita2") or {}).get("relacion_paciente") or ""
            ).strip()
            if _rel_cambio:
                mensaje = (
                    f"Claro, sin problema. ¿Cuál cambiamos primero: la tuya o la de "
                    f"{_rel_cambio}? Dime el nuevo día y hora para esa, y la otra "
                    f"la retomamos después."
                )
                botones = [
                    ("cambiar_mia", "La mía"),
                    ("cambiar_de_otra", f"La de {_rel_cambio}"[:20]),
                    ("hablar_persona", "Hablar con persona"),
                ]
                try:
                    deps.enviar_botones(telefono, mensaje, botones)
                except Exception as exc:
                    try:
                        deps.registrar_diagnostico(
                            fecha, "whatsapp", "FALLO",
                            f"Botones no enviados: {str(exc)[:250]}",
                            telefono, "cambiar hora",
                        )
                    except Exception:
                        pass
                    enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
                deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", "cambiar hora")
                return {"respondio": True, "handoff": False}
            else:
                mensaje = (
                    "Claro, sin problema. ¿Cuál cambiamos primero? Dime el nuevo "
                    "día y hora para esa, y la otra la retomamos después."
                )
        else:
            mensaje = "Claro, sin problema. ¿Qué día y hora te vienen mejor?"
        enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
        deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", "cambiar hora")
        return {"respondio": True, "handoff": False}

    if boton_id in ("cambiar_mia", "cambiar_de_otra"):
        # (v3.12) La cita que NO se cambia se guarda para retomar: al
        # proponer la nueva, viaja junto (ver _tomar_retomar). Si no
        # hay propuesta guardada (p. ej. reinicio), se pregunta igual,
        # como antes.
        _entrada = _RETOMAR.pop(telefono, None) or {}
        _prop_guardada = _entrada.get("propuesta") or {}
        if boton_id == "cambiar_mia":
            _otra = _prop_guardada.get("cita2")
            if _otra:
                _RETOMAR[telefono] = {"cita": _otra, "creado_en": ahora.isoformat()}
                mensaje = "Claro, sin problema. ¿Qué día y hora te vienen mejor para la tuya? La otra la dejamos pendiente para retomarla."
            else:
                mensaje = "Claro, sin problema. ¿Qué día y hora te vienen mejor para la tuya?"
        else:
            if _prop_guardada.get("fecha_cita"):
                _RETOMAR[telefono] = {
                    "cita": _cita_como_retomar(_prop_guardada),
                    "creado_en": ahora.isoformat(),
                }
                mensaje = "Claro, sin problema. ¿Qué día y hora te vienen mejor para esa cita? La otra la dejamos pendiente para retomarla."
            else:
                mensaje = "Claro, sin problema. ¿Qué día y hora te vienen mejor para esa cita?"
        enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
        deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", "cambiar hora")
        return {"respondio": True, "handoff": False}

    if boton_id == "hablar_persona":
        propuesta = _CITAS_PENDIENTES.get(telefono)
        _borrar_propuesta(deps, telefono)
        _RETOMAR.pop(telefono, None)
        motivo = (propuesta or {}).get("motivo", "El cliente pidió hablar con una persona")
        mensaje = "Claro, te paso con una persona del negocio. Te atienden en un momento."
        enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
        _avisar_por_correo(deps.alerta_handoff, nombre, telefono, motivo, mensaje, fecha)
        deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", motivo)
        deps.registrar_cliente(
            fecha, nombre, telefono, motivo, "", "whatsapp", "en conversacion", "si",
        )
        return {"respondio": True, "motivo": "handoff", "handoff": True}

    # Botón desconocido: se trata como mensaje normal, con calma.
    mensaje = "Claro. ¿Me cuentas qué necesitas?"
    enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
    return {"respondio": True, "motivo": "boton desconocido", "handoff": False}
