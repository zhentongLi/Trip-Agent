"""
音频 TTS 路由

POST /api/audio/speak  →  返回 audio/mpeg 流（ElevenLabs 生成）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from loguru import logger

from ...dependencies import get_async_redis
from ...services.tts_service import text_to_speech

router = APIRouter(prefix="/api/audio", tags=["音频TTS"])


class SpeakRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000, description="要朗读的文本")


@router.post(
    "/speak",
    summary="文本转语音",
    description="调用 ElevenLabs 将文本转为 MP3，支持中文。结果 Redis 缓存 24h。",
    response_class=Response,
    responses={
        200: {"content": {"audio/mpeg": {}}, "description": "MP3 音频流"},
        503: {"description": "TTS 服务不可用（未配置 API Key 或上游故障）"},
    },
)
async def speak(
    body: SpeakRequest,
    redis=Depends(get_async_redis),
) -> Response:
    logger.info(f"[audio] TTS 请求 chars={len(body.text)}")
    audio = await text_to_speech(body.text, redis=redis)
    if audio is None:
        return Response(
            content=b"",
            status_code=503,
            media_type="application/json",
            headers={"X-TTS-Error": "unavailable"},
        )
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "public, max-age=86400",
            "Content-Length": str(len(audio)),
        },
    )
