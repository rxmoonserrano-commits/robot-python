"""El perfil del negocio: quién es el robot y de qué negocio habla.

Antes, el robot genérico decía "la clínica" en el guion y en el
revisor, aunque el negocio fuera un restaurante: el giro del negocio
estaba escrito a mano en el código. Ahora el perfil vive en la
configuración (NEGOCIO_NOMBRE, NEGOCIO_TIPO, RECEPCIONISTA_NOMBRE)
y todo lo que el robot dice sale de aquí. Para venderle el robot a
otro negocio, se cambia el perfil, no el código.

- Recepcionista: el nombre que usa la IA para presentarse ("Ana").
- Negocio: el nombre real si está; si no, "el negocio".
- Frase de cierre (de noche): neutra para cualquier giro. Con nombre:
  "En Clínica Dental Sonrisa ya cerraron por hoy, pero yo te atiendo
  igual". Sin nombre: "El negocio ya cerró por hoy, pero yo te
  atiendo igual". Lo importante es el verbo: cerraron / cerró el
  negocio, nunca "ya cerramos" (el robot no cierra).
"""

from __future__ import annotations

from .config import settings


def configuracion() -> dict[str, str]:
    """La pestaña Configuración de la hoja, como dict clave -> valor.

    Es la fuente de verdad por negocio (v3.5): Jose la llena por
    cliente y el robot se personaliza sin tocar código. Prioridad:
    hoja > variables de entorno > valores por defecto. Si la hoja
    no tiene la pestaña (hojas viejas), devuelve {} y todo sigue
    como antes. Se lee perezoso y con red de seguridad: un fallo de
    red nunca tumba una respuesta.

    (v3.6) Si NEGOCIOS_SHEET_ID y NEGOCIO_CLAVE están en Render, el
    documento maestro Negocios manda paquete y canales: Jose los
    cambia con checkboxes en un solo lugar y el robot los respeta.
    """
    try:
        from . import sheets

        cfg = sheets.leer_configuracion()
    except Exception:  # noqa: BLE001 - sin configuración, defaults
        cfg = {}
    try:
        maestra = _config_maestra()
        for clave in ("paquete", "canal_whatsapp", "canal_messenger", "canal_instagram"):
            if maestra.get(clave):
                cfg[clave] = maestra[clave]
    except Exception:  # noqa: BLE001 - sin maestro, manda la hoja
        pass
    return cfg


def _si_no(valor) -> str:
    """Normaliza un checkbox de Sheets (TRUE/FALSE) o SI/NO a SI/NO."""
    texto = str(valor if valor is not None else "").strip().upper()
    if texto in ("TRUE", "SI", "SÍ", "1", "YES"):
        return "SI"
    if texto in ("FALSE", "NO", "0", ""):
        return "NO" if texto else ""
    return texto


def _config_maestra() -> dict[str, str]:
    """Paquete y canales desde el documento maestro Negocios.

    Lee la pestaña Índice del maestro y busca la fila con la clave
    de este negocio (NEGOCIO_CLAVE). Sin variables o sin fila, {}
    y el robot usa la Configuración de su propia hoja. Nunca lanza.
    """
    import os

    sid = os.getenv("NEGOCIOS_SHEET_ID", "").strip()
    clave = os.getenv("NEGOCIO_CLAVE", "").strip()
    if not sid or not clave:
        return {}
    try:
        from . import sheets

        filas = sheets.leer_pestana("Índice", spreadsheet_id=sid)
    except Exception:  # noqa: BLE001 - sin maestro, sin cambios
        return {}
    for fila in filas:
        if str(fila.get("Clave", "")).strip().lower() == clave.lower():
            cfg: dict[str, str] = {}
            paquete_valor = str(fila.get("Paquete", "") or "").strip().lower()
            if paquete_valor:
                cfg["paquete"] = paquete_valor
            for columna, clave_cfg in (("WhatsApp", "canal_whatsapp"),
                                       ("Messenger", "canal_messenger"),
                                       ("Instagram", "canal_instagram")):
                valor = _si_no(fila.get(columna, ""))
                if valor:
                    cfg[clave_cfg] = valor
            return cfg
    return {}


def _cfg(clave: str, defecto: str = "") -> str:
    return str(configuracion().get(clave, "") or defecto).strip()


def interruptor(clave: str, defecto: str = "SI") -> bool:
    """Interruptor SI/NO desde Configuración. Vacío o ausente = defecto."""
    valor = _cfg(clave, "").strip().upper()
    if not valor:
        return defecto.strip().upper() == "SI"
    return valor == "SI"


def tono() -> str:
    """Tono de voz del robot: amigable / formal / breve / detallado."""
    return _cfg("tono", "amigable").lower() or "amigable"


def saludo_config() -> str:
    """Saludo obligatorio si el negocio lo definió; "" si no."""
    return _cfg("saludo", "")


def mensaje_fuera_horario() -> str:
    """Mensaje fuera de horario si el negocio lo definió; "" si no."""
    return _cfg("mensaje_fuera_horario", "")


def correo_dueno() -> str:
    """Correo del dueño: Configuración manda; si no, OWNER_EMAIL."""
    return _cfg("correo_dueno", "") or (settings.owner_email or "").strip()


# --- Paquetes (v3.6): todos tienen el mismo código (la versión pro);
# el paquete solo autoriza qué funciones recibe cada negocio. Jose lo
# cambia con un botón en la hoja; el robot lo respeta en cada mensaje.

_FUNCIONES_POR_PAQUETE = {
    "basico": {
        "responder_faqs": True, "derivar_humano": True,
        "agendar": False, "enviar_fotos": False, "reportes": False,
    },
    "pro": {
        "responder_faqs": True, "derivar_humano": True,
        "agendar": True, "enviar_fotos": True, "reportes": True,
    },
    "premium": {
        "responder_faqs": True, "derivar_humano": True,
        "agendar": True, "enviar_fotos": True, "reportes": True,
    },
}


def paquete() -> str:
    """El paquete del negocio: basico / pro / premium, o "" si no hay."""
    return _cfg("paquete", "").strip().lower()


def funcion_activa(nombre: str) -> bool:
    """¿La función está autorizada para este negocio?

    Prioridad: interruptor explícito en Configuración (SI/NO) manda;
    si está vacío, decide el paquete; sin paquete, todo en SI
    (comportamiento histórico, compatible con hojas viejas).
    """
    explicito = _cfg(nombre, "").strip().upper()
    if explicito in ("SI", "NO"):
        return explicito == "SI"
    p = paquete()
    if p in _FUNCIONES_POR_PAQUETE:
        return bool(_FUNCIONES_POR_PAQUETE[p].get(nombre, True))
    return True


def canal_negocio_activo(canal: str) -> bool:
    """Switch por canal del negocio (canal_whatsapp, canal_messenger...).

    Vacío = SI para WhatsApp (el canal vivo) y NO para los demás
    (diseñados, apagados hasta conectar). El documento maestro
    Negocios puede mandar este valor vía NEGOCIOS_SHEET_ID.
    """
    valor = _cfg(f"canal_{canal}", "").strip().upper()
    if valor in ("SI", "NO"):
        return valor == "SI"
    return canal == "whatsapp"


def nombre_recepcionista() -> str:
    """El nombre de la recepcionista (la persona que es el robot)."""
    return _cfg("nombre_asistente", "") or (settings.recepcionista_nombre or "Ana").strip()


def nombre_negocio() -> str:
    """El nombre del negocio, o "" si no se configuró."""
    return _cfg("nombre_negocio", "") or (settings.negocio_nombre or "").strip()


def tipo_negocio() -> str:
    """El giro del negocio (clínica, restaurante, taller...)."""
    return _cfg("tipo_negocio", "") or (settings.negocio_tipo or "clínica").strip()


def frase_cierre() -> str:
    """Lo que el robot dice de noche, en vez de "ya cerramos"."""
    nombre = nombre_negocio()
    if nombre:
        return f"En {nombre} ya cerraron por hoy, pero yo te atiendo igual"
    return "El negocio ya cerró por hoy, pero yo te atiendo igual"
