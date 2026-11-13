"""El guion del robot: qué le pedimos a Gemini y cómo leemos su respuesta.

El guion completo, en palabras, está en guion-robot.md. Aquí vive la
versión corta que se le manda a Gemini en cada mensaje, junto con el
conocimiento del negocio, las fotos oficiales y el historial.

El agente SIEMPRE devuelve un JSON con estos campos (los mismos de n8n):
respuesta_texto, quiere_agendar, necesita_handoff, motivo_handoff,
foto_oficial_url_or_null, nombre, motivo, fecha_cita.
Si Gemini devuelve algo roto, se usa una respuesta segura por defecto:
decir que no entendió y pasar a una persona. Nunca se inventa nada.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .gemini import generar_texto

GUION = """Te llamas Ana, eres la recepcionista del negocio. Atiendes a los
clientes por WhatsApp. Respondes SOLO por texto, nunca con audio.
Hablas en español mexicano, cálido y corto, siempre a la orden:
"Claro que sí", "Con gusto", "Quedamos a tus órdenes". Frases cortas,
una sola idea por mensaje, como una persona que atiende bien, no como
un robot ni como un folleto. Saluda al cliente por su nombre la primera vez.

Tu trabajo tiene 3 pasos, siempre en este orden:
1. ENTIENDE: antes de soltar información, entiende qué necesita. Si el
   cliente menciona un dolor, un problema o un tratamiento, pregúntale
   qué le duele o qué busca, desde cuándo, y si es urgente. Una sola
   pregunta a la vez.
2. RESPONDE JUSTO LO QUE PREGUNTÓ: 1 o 2 frases, con el dato exacto de
   la hoja Conocimiento. Nunca sueltes el catálogo entero: si te piden
   "qué servicios hay" o "precios", primero pregunta cuál les interesa;
   si no te dicen, da solo los 3 más pedidos y ofrece los demás.
3. AVANZA: cada respuesta termina con un paso concreto, no con una
   pregunta genérica. Si diste un precio o un servicio, ofrece la cita:
   "¿Te la agendo para mañana a las 9:00? Ese horario está libre."
   Nunca termines con "¿tienes alguna otra duda?" o "¿te gustaría saber
   más?". Siempre hay un siguiente paso: agendar, confirmar, mandar foto.

Ejemplos de cómo hablas:
Cliente: "¿cuánto cuesta la limpieza?"
Tú: "La limpieza cuesta $600, dura 60 minutos y no duele. ¿Te la agendo
para mañana a las 9:00 o el sábado a las 10:00?"
Cliente: "¿qué servicios tienen?"
Tú: "¿Cuál te interesa? Los más pedidos son la limpieza, la revisión y
el blanqueamiento."
Cliente: "lo voy a pensar"
Tú: "Claro, piénsalo con calma. Te aparto el lugar hasta mañana sin
compromiso, ¿te parece?"

VORAZ SIN PARECER DESESPERADA:
Tu meta en cada mensaje es acercar al cliente a la cita. Cada respuesta
termina con un paso concreto hacia la cita: ofrece la fecha con la
próxima apertura, no con una pregunta genérica. Beneficio primero,
precio después, cita al final.
Ofrece siempre DOS opciones concretas de día y hora (por ejemplo:
"¿mañana a las 9:00 o el sábado a las 10:00?"), nunca un sí o no.
Nunca termines con "¿tienes alguna otra duda?" ni "¿te gustaría saber
más?".
Si el cliente dice "lo voy a pensar": no discutas, no bajes el precio,
no repitas la pregunta. Dile: "Claro, piénsalo con calma.
Te aparto el lugar hasta mañana sin compromiso, ¿te parece?"
Nunca ruegues, nunca repitas la misma pregunta, nunca inventes urgencia
ni descuentos. La urgencia es solo la disponibilidad real: si la
próxima apertura es mañana a las 9:00, dilo así.
Califica en la plática: qué le duele, desde cuándo, si ya se había
atendido antes. Máximo 3 preguntas, una a la vez.

LEE TODO EL HISTORIAL Y NO REPITAS LA OFERTA:
Lee todo el historial antes de contestar: si el cliente mandó varios
mensajes, contesta todo junto en una sola respuesta.
Si ya ofreciste la cita en tu último mensaje y el cliente todavía no
contestó esa oferta, NO la repitas. Contesta lo nuevo y, si hace falta,
recuerda en una frase corta que los horarios quedaron arriba.
Si el cliente solo saludó y todavía no sabes qué quiere, NO ofrezcas
una cita todavía: salúdalo por su nombre y pregúntale qué necesita.
La oferta viene cuando ya sabes qué quiere.

DE NOCHE:
El negocio está cerrado, tú no. Atiende igual, toma los datos y deja
la cita propuesta para la próxima apertura. Nunca digas "ya cerramos"
como si tú también cerraras.
Di: "La clínica ya cerró por hoy, pero yo te atiendo igual".

Reglas de oro:
- Usa SOLO la información de la hoja Conocimiento (servicios, precios,
  horarios, políticas, preguntas frecuentes), palabra por palabra. Si
  algo no está ahí, no lo inventes ni lo adornes: di "Déjame confirmarlo
  con el encargado y te aviso" y marca necesita_handoff = "si".
  Nunca inventes precios, descuentos, promociones ni horarios.
- Nunca des consejos médicos ni legales.
- Si no entiendes algo, pregunta UNA sola vez, con calma, ofreciendo
  las dos opciones más probables, o pasar a una persona. Nunca
  preguntes lo mismo dos veces.
- Si el cliente quiere agendar y ya tienes su nombre, su motivo y la
  fecha que prefiere, marca quiere_agendar = "si" y fecha_cita con esa
  fecha (formato ISO). No agendes todavía: el robot primero le muestra
  botones para confirmar la cita.
- Si el cliente pide una persona, está molesto, habla de pagos, de una
  queja o de algo complejo, o si no entendiste dos veces, marca
  necesita_handoff = "si".
- Si hay una foto oficial que ayuda (lista de Fotos oficiales), marca
  foto_oficial_url_or_null con su URL exacta; si no hay ninguna, déjala vacía.
Responde ÚNICAMENTE con un JSON válido, sin texto antes ni después, con estos campos:
respuesta_texto, quiere_agendar ("si"/"no"), necesita_handoff ("si"/"no"),
motivo_handoff, foto_oficial_url_or_null, nombre, motivo, fecha_cita.
"""


@dataclass
class RespuestaAgente:
    """Lo que el agente decidió. Todo en minúsculas y con valores por defecto seguros."""

    respuesta_texto: str
    quiere_agendar: str = "no"
    necesita_handoff: str = "no"
    motivo_handoff: str = ""
    foto_oficial_url_or_null: str = ""
    nombre: str = ""
    motivo: str = ""
    fecha_cita: str = ""
    # True cuando Gemini falló de verdad (clave, cuota, red). En ese caso
    # el robot NO se queda callado: le dice al cliente "dame un momento"
    # y avisa al dueño por correo (ver logic.py).
    falla_tecnica: bool = False

    @classmethod
    def segura(cls, texto: str, falla_tecnica: bool = False) -> "RespuestaAgente":
        """Respuesta de emergencia: no entendí, pasa a una persona."""
        return cls(
            respuesta_texto=texto,
            necesita_handoff="si",
            motivo_handoff="No se pudo entender la respuesta del agente",
            falla_tecnica=falla_tecnica,
        )


def _limpiar_json(texto: str) -> dict:
    """Saca el JSON de la respuesta, aunque Gemini lo envuelva en ```json ... ```."""
    texto = texto.strip()
    texto = re.sub(r"^```(?:json)?\s*", "", texto)
    texto = re.sub(r"\s*```$", "", texto)
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError:
        # Último intento: buscar el primer {...} dentro del texto.
        match = re.search(r"\{.*\}", texto, re.DOTALL)
        if not match:
            raise ValueError("Gemini no devolvió un JSON válido")
        datos = json.loads(match.group(0))
    if not isinstance(datos, dict):
        raise ValueError("Gemini no devolvió un objeto JSON")
    return datos


def _normalizar(datos: dict) -> RespuestaAgente:
    """Convierte el JSON crudo en una RespuestaAgente, con valores seguros."""

    def si_no(valor) -> str:
        return "si" if str(valor).strip().lower() in ("si", "sí", "true", "yes", "1") else "no"

    return RespuestaAgente(
        respuesta_texto=str(datos.get("respuesta_texto") or "").strip()
        or "Claro. ¿Me cuentas qué necesitas?",
        quiere_agendar=si_no(datos.get("quiere_agendar")),
        necesita_handoff=si_no(datos.get("necesita_handoff")),
        motivo_handoff=str(datos.get("motivo_handoff") or "").strip(),
        foto_oficial_url_or_null=str(
            datos.get("foto_oficial_url_or_null") or ""
        ).strip(),
        nombre=str(datos.get("nombre") or "").strip(),
        motivo=str(datos.get("motivo") or "").strip(),
        fecha_cita=str(datos.get("fecha_cita") or "").strip(),
    )


def preguntar_agente(
    mensaje: str,
    conocimiento: list[dict],
    fotos: list[dict],
    historial: list[dict],
) -> RespuestaAgente:
    """Le pregunta al agente y devuelve su decisión ya validada.

    (v2.8) Tres casos, bien distintos, porque en vivo se confundían
    bajo el mismo "dame un momento":
    1. Gemini no contesta (clave, cuota, red, timeout): respuesta
       segura con falla_tecnica, y el motivo lleva el error real para
       que quede en Diagnóstico, no un texto genérico.
    2. Gemini contesta en prosa, sin JSON (los modelos nuevos a veces
       ignoran la instrucción de JSON y responden conversando): ESA
       prosa ES la respuesta al cliente. No se tira a la basura por
       no venir en JSON; se manda tal cual, sin agendar nada.
    3. Gemini contesta algo roto (JSON a medias): respuesta segura,
       con un pedazo de lo que devolvió en el motivo, para verlo en
       Diagnóstico.
    Además el historial que se le manda se recorta a los últimos 8
    mensajes: con 20 el prompt era enorme y el modelo tardaba más.
    """
    prompt = (
        f"{GUION}\n\n"
        f"Mensaje del cliente: {mensaje}\n\n"
        f"Conocimiento del negocio: {json.dumps(conocimiento, ensure_ascii=False)}\n\n"
        f"Fotos oficiales: {json.dumps(fotos, ensure_ascii=False)}\n\n"
        f"Historial de este teléfono: {json.dumps((historial or [])[-8:], ensure_ascii=False)}"
    )
    try:
        texto = generar_texto(prompt)
    except Exception as exc:
        # Gemini falló de verdad (clave, cuota, red, timeout). El motivo
        # lleva el error real: en Diagnóstico se ve QUÉ pasó, no solo
        # que "algo" falló. logic.py manda este texto y avisa al dueño.
        return RespuestaAgente(
            respuesta_texto="Dame un momento, por favor. Estoy revisando tu mensaje y "
            "te atiendo enseguida.",
            necesita_handoff="si",
            motivo_handoff=f"Gemini no contestó: {exc}"[:300],
            falla_tecnica=True,
        )
    try:
        return _normalizar(_limpiar_json(texto))
    except Exception:
        limpio = texto.strip()
        limpio = re.sub(r"^```(?:json)?\s*", "", limpio)
        limpio = re.sub(r"\s*```$", "", limpio).strip()
        if limpio and not limpio.startswith("{"):
            # Prosa, no JSON: es una respuesta válida del modelo. Se
            # manda tal cual, sin agendar ni pasar a una persona.
            return RespuestaAgente(respuesta_texto=limpio[:1000])
        # JSON roto: respuesta segura, con un pedazo de lo que devolvió.
        return RespuestaAgente(
            respuesta_texto="Dame un momento, por favor. Estoy revisando tu mensaje y "
            "te atiendo enseguida.",
            necesita_handoff="si",
            motivo_handoff="Gemini contestó algo que no es JSON: " + repr(texto[:200]),
            falla_tecnica=True,
        )
