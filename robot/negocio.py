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
    """
    try:
        from . import sheets

        return sheets.leer_configuracion()
    except Exception:  # noqa: BLE001 - sin configuración, defaults
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
