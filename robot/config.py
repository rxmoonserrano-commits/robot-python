"""Configuración del robot. Todo sale de variables de entorno (.env).

Nada secreto va escrito en el código: las claves viven en el archivo .env,
que nunca se sube a ningún lado. Si falta una clave, el robot lo dice claro
al arrancar, en vez de fallar a medias.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()  # Lee el archivo .env si existe, en la misma carpeta del proyecto.


@dataclass
class Settings:
    """Un solo lugar con todos los ajustes. Cambia aquí, no en cada archivo."""

    # --- Google Sheets: el documento oficial del negocio (ya es el de Jose) ---
    sheet_id: str = os.getenv("GOOGLE_SHEETS_ID", "")
    # Archivo JSON de la cuenta de servicio de Google (Sheets + Calendar).
    # Se comparte la hoja con el correo de esa cuenta (ver README, paso 3).
    google_credentials_json: str = os.getenv(
        "GOOGLE_CREDENTIALS_JSON", "credenciales-google.json"
    )

    # --- Inteligencia artificial gratis: Google Gemini ---
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    # Los modelos y sus tarifas dependen de la cuenta de Google. Se
    # configuran explícitamente después de verificarlos; no se inventa
    # un modelo por defecto ni se declara que sea gratuito o vigente.
    gemini_model: str = os.getenv("GEMINI_MODEL", "").strip()
    gemini_model_fallback: str = os.getenv("GEMINI_MODEL_FALLBACK", "").strip()

    # --- WhatsApp Cloud API (Meta for Developers) ---
    whatsapp_token: str = os.getenv("WHATSAPP_TOKEN", "")
    whatsapp_phone_number_id: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    # PIN de 6 dígitos para registrar el número en la Cloud API (opcional).
    # Sin él, el registro se hace sin PIN de dos pasos (v3.20.12).
    whatsapp_register_pin: str = os.getenv("WHATSAPP_REGISTER_PIN", "")
    # ID de la cuenta de WhatsApp Business (WABA) donde vive el número real.
    # La app debe suscribirse a ESA cuenta para que Meta reenvíe los mensajes
    # al webhook; sin esto, los números agregados por WhatsApp Manager no
    # entregan nada aunque estén registrados (v3.20.13). Se encuentra en
    # Business Settings → WhatsApp accounts → la cuenta (en la URL).
    whatsapp_waba_id: str = os.getenv("WHATSAPP_WABA_ID", "")
    # Palabra secreta que inventas tú para verificar el webhook. Meta la pide.
    verify_token: str = os.getenv("VERIFY_TOKEN", "robot-whatsapp-verifica")

    # --- Correo del dueño (alertas de handoff y reporte semanal) ---
    owner_email: str = os.getenv("OWNER_EMAIL", "dueno@empresa.com")
    # Para mandar correos por Gmail con SMTP (contraseña de aplicación, no tu clave).
    gmail_user: str = os.getenv("GMAIL_USER", "")

    # --- Correo saliente configurable (v3.22.0) ---
    # El robot manda correos por SMTP. Por defecto usa Gmail
    # (smtp.gmail.com:587 con GMAIL_USER/GMAIL_APP_PASSWORD).
    # Si el dueño solo tiene otro correo (p. ej. iCloud de Apple:
    # smtp.mail.me.com:587), basta poner SMTP_HOST, SMTP_USER y
    # SMTP_PASSWORD (contraseña de aplicación del proveedor) en
    # Render; GMAIL_* queda como respaldo histórico.
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    gmail_app_password: str = os.getenv("GMAIL_APP_PASSWORD", "")

    # --- Calendario y negocio ---
    calendar_id: str = os.getenv("CALENDAR_ID", "primary")
    timezone: str = os.getenv("TIMEZONE", "America/Mazatlan")
    # Duración de cada cita en minutos. En la versión de n8n esto era un error:
    # ponía inicio = fin. Aquí la cita dura lo que tú digas (60 por defecto).
    duracion_cita_minutos: int = int(os.getenv("DURACION_CITA_MINUTOS", "60"))
    # Horas que el robot se calla cuando una persona atiende un chat.
    pausa_humano_horas: int = int(os.getenv("PAUSA_HUMANO_HORAS", "2"))

    # --- Reporte semanal ---
    # Lunes 08:00, hora del negocio.
    reporte_dia_semana: str = os.getenv("REPORTE_DIA", "mon")
    reporte_hora: int = int(os.getenv("REPORTE_HORA", "8"))
    reporte_minuto: int = int(os.getenv("REPORTE_MINUTO", "0"))
    # Reporte mensual (v3.21.0, Aloara): día 1 del mes a las 08:00,
    # cubre el mes calendario anterior.
    reporte_mensual_dia: int = int(os.getenv("REPORTE_MENSUAL_DIA", "1"))

    # --- Perfil del negocio (v3.0): que el robot hable del negocio de verdad ---
    # Nombre del negocio (opcional): si está, la recepcionista lo usa
    # ("En Clínica Dental Sonrisa ya cerraron por hoy..."); si no,
    # dice "el negocio". Antes este dato existía pero nadie lo usaba.
    negocio_nombre: str = os.getenv("NEGOCIO_NOMBRE", "")
    # Tipo de negocio, CON artículo ("una clínica", "un restaurante",
    # "un taller"): le dice a la IA de qué negocio es recepcionista.
    # Por defecto, la clínica ficticia de las pruebas; cámbialo al
    # desplegar para un negocio real.
    negocio_tipo: str = os.getenv("NEGOCIO_TIPO", "una clínica")
    # Nombre de la recepcionista (la persona que es el robot).
    recepcionista_nombre: str = os.getenv("RECEPCIONISTA_NOMBRE", "Ana")

    # --- Seguridad (v3.0) ---
    # Clave para /pausa y /reporte-semanal: sin ella, esos endpoints
    # están cerrados (antes cualquiera podía silenciar el robot).
    # La crea el instalador; en Render va como variable de entorno.
    admin_token: str = os.getenv("ADMIN_TOKEN", "")
    # Secreto de la app de Meta (Meta for Developers → tu app → Configuración
    # básica → Secreto de la app): verifica la firma de cada webhook.
    # Si está vacío, el webhook rechaza solicitudes con 503.
    meta_app_secret: str = os.getenv("META_APP_SECRET", "")
    # Segundos que el robot espera, después del ÚLTIMO mensaje del cliente,
    # antes de contestar. Si llega otro mensaje, el contador se reinicia.
    # Así lee todo junto en vez de contestar mensaje por mensaje.
    espera_agrupar_segundos: int = int(os.getenv("ESPERA_AGRUPAR_SEGUNDOS", "15"))


# Una sola instancia que importa todo el proyecto.
settings = Settings()


def correo_saliente() -> tuple[str, int, str, str]:
    """(host, puerto, usuario, contraseña) efectivos para mandar correo.

    SMTP_* manda; si no están puestos, se usa Gmail (GMAIL_*) como
    antes. Así el mismo robot sale de Gmail o de iCloud sin tocar
    código: solo cambian las variables en Render.
    """
    return (
        settings.smtp_host,
        settings.smtp_port,
        settings.smtp_user or settings.gmail_user,
        settings.smtp_password or settings.gmail_app_password,
    )


def correo_configurado() -> bool:
    """¿Hay usuario y contraseña para mandar correos?"""
    _host, _puerto, usuario, contrasena = correo_saliente()
    return bool(usuario and contrasena)


def faltan_claves() -> list[str]:
    """Lista las claves obligatorias que todavía no están en el .env."""
    faltantes = []
    if not settings.gemini_api_key:
        faltantes.append("GEMINI_API_KEY")
    if not settings.whatsapp_token:
        faltantes.append("WHATSAPP_TOKEN")
    if not settings.whatsapp_phone_number_id:
        faltantes.append("WHATSAPP_PHONE_NUMBER_ID")
    return faltantes
