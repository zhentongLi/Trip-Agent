"""
ElevenLabs TTS 服务

功能：
  - 将文本转为 MP3 音频字节（eleven_multilingual_v2 模型，中文流畅）
  - 对相同文本做 Redis 缓存（TTL 24h），避免重复计费
  - 不可用时静默降级，不影响主流程
"""
from __future__ import annotations

import hashlib
import os
from typing import Optional

import httpx
from loguru import logger

# ── 配置 ──────────────────────────────────────────────────────────────────────

_API_KEY    = os.environ.get("ELEVENLABS_API_KEY", "")
_VOICE_ID   = os.environ.get("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")  # Bella（多语言）
_MODEL_ID   = "eleven_multilingual_v2"
_TTS_URL    = f"https://api.elevenlabs.io/v1/text-to-speech/{_VOICE_ID}"
_MAX_CHARS  = 500   # 单次最大字符数，防止超额消耗
_CACHE_TTL  = 86400  # Redis 缓存 TTL（24 小时）
_NS         = "tts:"  # Redis key 前缀


def _truncate(text: str) -> str:
    """超长文本智能截断（在句号处截断）"""
    if len(text) <= _MAX_CHARS:
        return text
    cut = text[:_MAX_CHARS]
    for sep in ("。", "！", "？", ".", "!", "?"):
        idx = cut.rfind(sep)
        if idx > _MAX_CHARS // 2:
            return cut[: idx + 1]
    return cut


def _cache_key(text: str) -> str:
    h = hashlib.md5(f"{_VOICE_ID}:{text}".encode()).hexdigest()[:16]
    return f"{_NS}{h}"


async def _redis_get(redis, key: str) -> Optional[bytes]:
    if redis is None:
        return None
    try:
        data = await redis.get(key)
        return data if isinstance(data, bytes) else (data.encode() if data else None)
    except Exception as e:
        logger.warning(f"[tts] Redis GET 失败: {e}")
        return None


async def _redis_set(redis, key: str, data: bytes) -> None:
    if redis is None:
        return
    try:
        await redis.setex(key, _CACHE_TTL, data)
    except Exception as e:
        logger.warning(f"[tts] Redis SET 失败: {e}")


async def text_to_speech(text: str, redis=None) -> Optional[bytes]:
    """
    将文本转为 MP3 字节。

    Args:
        text:  要朗读的文本（自动截断至 _MAX_CHARS 字）
        redis: 可选 AsyncRedis 实例，传入时启用缓存

    Returns:
        MP3 bytes；失败时返回 None
    """
    if not _API_KEY:
        logger.warning("[tts] ELEVENLABS_API_KEY 未配置，跳过 TTS")
        return None

    text = _truncate(text.strip())
    if not text:
        return None

    # 尝试缓存读取
    cache_key = _cache_key(text)
    cached = await _redis_get(redis, cache_key)
    if cached:
        logger.debug(f"[tts] 缓存命中 key={cache_key[:12]}")
        return cached

    # 调用 ElevenLabs API
    headers = {
        "xi-api-key": _API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": _MODEL_ID,
        "voice_settings": {
            "stability": 0.45,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(_TTS_URL, headers=headers, json=payload)
            resp.raise_for_status()
            audio = resp.content
            logger.success(f"[tts] 生成成功 chars={len(text)} bytes={len(audio)}")
            await _redis_set(redis, cache_key, audio)
            return audio

    except httpx.HTTPStatusError as e:
        logger.error(f"[tts] ElevenLabs HTTP 错误 {e.response.status_code}: {e.response.text[:200]}")
    except Exception as e:
        logger.error(f"[tts] ElevenLabs 调用失败: {e}")

    return None
