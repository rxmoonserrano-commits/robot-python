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
    sheet_id: str = os.getenv(
        "GOOGLE_SHEETS_ID", "1RfkuuvTf5f-YkhPkQnWzi0X95RpUoy3oHoDx00hFONo"
    )
    # Archivo JSON de la cuenta de servicio de Google (Sheets + Calendar).
    # Se comparte la hoja con el correo de esa cuenta (ver README, paso 3).
    google_credentials_json: str = os.getenv(
        "GOOGLE_CREDENTIALS_JSON", "credenciales-google.json"
    )

    # --- Inteligencia artificial gratis: Google Gemini ---
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    # Si Google retira el modelo de arriba, se prueba este, también gratis.
    gemini_model_fallback: str = os.getenv("GEMINI_MODEL_FALLBACK", "gemini-2.5-flash")

    # --- WhatsApp Cloud API (Meta for Developers) ---
    whatsapp_token: str = os.getenv("WHATSAPP_TOKEN", "")
    whatsapp_phone_number_id: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    # Palabra secreta que inventas tú para verificar el webhook. Meta la pide.
    verify_token: str = os.getenv("VERIFY_TOKEN", "robot-whatsapp-verifica")

    # --- Correo del dueño (alertas de handoff y reporte semanal) ---
    owner_email: str = os.getenv("OWNER_EMAIL", "dueno@empresa.com")
    # Para mandar correos por Gmail con SMTP (contraseña de aplicación, no tu clave).
    gmail_user: str = os.getenv("GMAIL_USER", "")
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

    # --- Versión 2: calidad Apple ---
    # Nombre del negocio (opcional, solo para los mensajes).
    negocio_nombre: str = os.getenv("NEGOCIO_NOMBRE", "")
    # Segundos que el robot espera, después del ÚLTIMO mensaje del cliente,
    # antes de contestar. Si llega otro mensaje, el contador se reinicia.
    # Así lee todo junto en vez de contestar mensaje por mensaje.
    espera_agrupar_segundos: int = int(os.getenv("ESPERA_AGRUPAR_SEGUNDOS", "7"))


# Una sola instancia que importa todo el proyecto.
settings = Settings()


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
