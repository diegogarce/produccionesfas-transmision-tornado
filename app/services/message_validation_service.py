"""
Servicio para validar mensajes de chat y Q&A con reglas de throttling, duplicados y longitud.
"""
import hashlib
import re
import unicodedata
import tornado.ioloop
import functools

from app.services.redis_cache import get_redis_cache

MESSAGE_MAX_LENGTH = 200
THROTTLE_WINDOW_SECONDS = 3
DUPLICATE_WINDOW_SECONDS = 20  # 10-30s como se discutió
DUPLICATE_THRESHOLD = 500

def _normalize_text(text: str) -> str:
    """Normaliza el texto para comparación (lower, sin acentos, un solo espacio)."""
    if not isinstance(text, str): # Handle non-string inputs
        return ""
    normalized = text.lower()
    normalized = unicodedata.normalize("NFD", normalized).encode("ascii", "ignore").decode("utf-8")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


import typing

async def validate_message(event_id: typing.Optional[int], user_id: typing.Optional[int], message_text: str, message_type: str = "chat") -> tuple[bool, str]:
    """
    Valida un mensaje contra reglas de longitud, throttling y duplicados.
    Returns (is_valid, error_message)
    """
    if event_id is None or user_id is None:
        return False, "Faltan datos de evento o usuario para validar el mensaje."

    redis_client = get_redis_cache()
    if redis_client is None: # Si Redis no está disponible, no aplicamos validaciones basadas en Redis
        # Solo validación de longitud
        if not isinstance(message_text, str) or len(message_text) > MESSAGE_MAX_LENGTH:
            return False, "Mensaje demasiado largo (máximo 200 caracteres)."
        return True, "" # Si no hay Redis, solo pasa por longitud

    # 1. Validación de longitud
    if not isinstance(message_text, str) or len(message_text) > MESSAGE_MAX_LENGTH:
        return False, "Mensaje demasiado largo (máximo 200 caracteres)."

    # 2. Throttling
    throttle_key = f"throttle:{message_type}:{event_id}:{user_id}"
    # SETNX sets if key does not exist. Returns 1 if set, 0 if already exists.
    # We want to allow 1 message per window, so if SETNX returns 0, it means a message was sent recently.
    # Use run_in_executor for blocking Redis call
    loop = tornado.ioloop.IOLoop.current()
    set_func = functools.partial(redis_client.set, throttle_key, "1", ex=THROTTLE_WINDOW_SECONDS, nx=True)
    if not await loop.run_in_executor(None, set_func):
        return False, f"Espera {THROTTLE_WINDOW_SECONDS} segundos para enviar otro mensaje."

    # 3. Detección de duplicados masivos
    normalized_message = _normalize_text(message_text)
    if normalized_message: # Only check for duplicates if there's actual content after normalization
        message_hash = hashlib.sha1(normalized_message.encode("utf-8")).hexdigest()
        duplicate_key = f"duplicate:{message_type}:{event_id}:{message_hash}"
        
        # INCR increments the value of key by one. If key does not exist, it is set to 0 before performing the operation.
        # We use pipeline to ensure atomicity for INCR and EXPIRE.
        pipe = redis_client.pipeline()
        pipe.incr(duplicate_key)
        pipe.expire(duplicate_key, DUPLICATE_WINDOW_SECONDS)
        # Use run_in_executor for blocking Redis pipeline execution
        loop = tornado.ioloop.IOLoop.current()
        results = await loop.run_in_executor(None, pipe.execute)
        current_count = results[0]

        if current_count >= DUPLICATE_THRESHOLD:
            # Consider blocking this specific message hash for a longer period if it's a persistent attack
            # For now, just reject this message and let the counter expire normally.
            return False, "Se detectó spam masivo, por favor reformula tu mensaje."

    return True, ""