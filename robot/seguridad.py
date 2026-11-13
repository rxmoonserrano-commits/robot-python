"""Seguridad del robot: quién puede tocarlo y quién dice ser Meta.

Dos cosas, nada más:

1. Clave de dueño (ADMIN_TOKEN): /pausa y /reporte-semanal solo
   responden si traen la clave, en el header X-Admin-Token o en el
   parámetro ?token=. Sin clave configurada, están CERRADOS (antes
   cualquiera que conociera la dirección podía silenciar el robot).
   La clave la crea el instalador y va como variable en Render.

2. Firma de Meta (META_APP_SECRET): cada POST al webhook trae el
   header X-Hub-Signature-256, un HMAC-SHA256 del cuerpo con el
   secreto de la app. Si el secreto está configurado y la firma no
   coincide, el mensaje se rechaza (403) sin procesarse: nadie puede
   mandar mensajes falsos para que el robot conteste. Si el secreto
   NO está configurado, se acepta (para no romper una instalación
   que todavía no lo puso) y la revisión de salud lo avisa al arrancar.
"""

from __future__ import annotations

import hashlib
import hmac


def token_admin_ok(token_dado: str | None, token_esperado: str) -> bool:
    """¿Es la clave de dueño? Sin clave configurada, siempre NO.

    La comparación es en tiempo constante (compare_digest), para que
    no se pueda adivinar la clave midiendo cuánto tarda cada intento.
    """
    if not token_esperado or not token_dado:
        return False
    return hmac.compare_digest(str(token_dado), str(token_esperado))


def verificar_firma_meta(cuerpo: bytes, firma: str | None, secreto: str) -> bool:
    """¿Este webhook viene de Meta de verdad?

    Sin secreto configurado devuelve True (se acepta con aviso, ver
    salud.py). Con secreto, la firma tiene que ser sha256=<hmac>.
    """
    if not secreto:
        return True
    if not firma or not firma.startswith("sha256="):
        return False
    esperado = hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(firma[len("sha256="):], esperado)
