"""Memory service for guide skill.

Provides two-layer memory:
1) Short-term memory per session with history compression.
2) Long-term user profile persisted in shared Redis for multi-instance deployment.

If Redis is not available, falls back to local in-process memory + JSON profile file.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

from loguru import logger
from langchain_core.messages import HumanMessage, SystemMessage

try:
    from redis import Redis
except Exception:
    Redis = None

from .llm_service import get_llm


class MemoryService:
    """Session memory + persisted profile memory."""

    def __init__(self):
        backend_dir = Path(__file__).resolve().parents[2]
        self._data_dir = backend_dir / "data"
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._redis_namespace = (
            os.getenv("MEMORY_REDIS_NAMESPACE", "trip_agent:memory").strip()
            or "trip_agent:memory"
        )
        self._session_ttl_seconds = self._parse_int_env(
            "MEMORY_SESSION_TTL_SECONDS", default=3 * 24 * 3600
        )
        self._redis = self._init_redis_client()

        self._profile_path = self._data_dir / "user_profiles.json"
        self._profiles: Dict[str, Dict[str, Any]] = self._load_profiles()

        self._session_messages: Dict[str, List[Dict[str, str]]] = {}
        self._session_summary: Dict[str, str] = {}

        self._lock = threading.Lock()
        self._max_short_messages = 6
        self._compress_token_threshold = 2800

    @staticmethod
    def _parse_int_env(name: str, default: int) -> int:
        raw = os.getenv(name, "").strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            logger.warning(f"环境变量 {name} 不是整数，使用默认值 {default}")
            return default

    def _init_redis_client(self):
        redis_url = (os.getenv("MEMORY_REDIS_URL") or os.getenv("REDIS_URL") or "").strip()
        if not redis_url:
            logger.warning("未配置 MEMORY_REDIS_URL/REDIS_URL，MemoryService 使用本地回退存储")
            return None

        if Redis is None:
            logger.warning("未安装 redis Python 包，MemoryService 使用本地回退存储")
            return None

        try:
            client = Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
                health_check_interval=30,
            )
            client.ping()
            logger.info("MemoryService 已连接 Redis，共享记忆模式启用")
            return client
        except Exception as e:
            logger.warning(f"Redis 连接失败，MemoryService 使用本地回退存储: {e}")
            return None

    @property
    def using_redis(self) -> bool:
        return self._redis is not None

    def _key(self, *parts: str) -> str:
        return ":".join([self._redis_namespace, *parts])

    def _default_profile(self) -> Dict[str, Any]:
        return {
            "budget": "",
            "travel_style": "",
            "disliked": [],
            "history_destinations": [],
        }

    def _load_profiles(self) -> Dict[str, Dict[str, Any]]:
        if not self._profile_path.exists():
            return {}
        try:
            data = json.loads(self._profile_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning(f"用户画像文件读取失败，已重置为空: {e}")
            return {}

    def _save_profiles(self) -> None:
        self._profile_path.write_text(
            json.dumps(self._profiles, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _get_session_messages(self, sid: str) -> List[Dict[str, str]]:
        if self._redis:
            raw_items = self._redis.lrange(self._key("session", sid, "messages"), 0, -1)
            messages: List[Dict[str, str]] = []
            for item in raw_items:
                try:
                    obj = json.loads(item)
                    if isinstance(obj, dict):
                        messages.append(
                            {
                                "role": str(obj.get("role", "user")),
                                "content": str(obj.get("content", "")),
                            }
                        )
                except Exception:
                    continue
            return messages
        return list(self._session_messages.get(sid, []))

    def _set_session_messages(self, sid: str, messages: List[Dict[str, str]]) -> None:
        if self._redis:
            key = self._key("session", sid, "messages")
            pipe = self._redis.pipeline()
            pipe.delete(key)
            if messages:
                payload = [json.dumps(m, ensure_ascii=False) for m in messages]
                pipe.rpush(key, *payload)
            if self._session_ttl_seconds > 0:
                pipe.expire(key, self._session_ttl_seconds)
            pipe.execute()
            return
        self._session_messages[sid] = list(messages)

    def _get_session_summary(self, sid: str) -> str:
        if self._redis:
            value = self._redis.get(self._key("session", sid, "summary"))
            return (value or "").strip()
        return str(self._session_summary.get(sid, ""))

    def _set_session_summary(self, sid: str, summary: str) -> None:
        text = (summary or "").strip()
        if self._redis:
            key = self._key("session", sid, "summary")
            if text:
                if self._session_ttl_seconds > 0:
                    self._redis.set(key, text, ex=self._session_ttl_seconds)
                else:
                    self._redis.set(key, text)
            else:
                self._redis.delete(key)
            return
        if text:
            self._session_summary[sid] = text
        elif sid in self._session_summary:
            self._session_summary.pop(sid, None)

    def _get_profile(self, sid: str) -> Dict[str, Any]:
        if self._redis:
            raw = self._redis.hgetall(self._key("profile", sid))
            if not raw:
                return {}

            disliked: List[str] = []
            destinations: List[str] = []
            try:
                disliked_raw = raw.get("disliked", "[]")
                disliked_obj = json.loads(disliked_raw)
                if isinstance(disliked_obj, list):
                    disliked = [str(x) for x in disliked_obj if str(x).strip()]
            except Exception:
                disliked = []

            try:
                destinations_raw = raw.get("history_destinations", "[]")
                destinations_obj = json.loads(destinations_raw)
                if isinstance(destinations_obj, list):
                    destinations = [str(x) for x in destinations_obj if str(x).strip()]
            except Exception:
                destinations = []

            return {
                "budget": str(raw.get("budget", "")),
                "travel_style": str(raw.get("travel_style", "")),
                "disliked": disliked,
                "history_destinations": destinations,
            }

        data = self._profiles.get(sid)
        if not isinstance(data, dict):
            return {}

        profile = self._default_profile()
        profile["budget"] = str(data.get("budget", ""))
        profile["travel_style"] = str(data.get("travel_style", ""))
        profile["disliked"] = [str(x) for x in data.get("disliked", []) if str(x).strip()]
        profile["history_destinations"] = [
            str(x) for x in data.get("history_destinations", []) if str(x).strip()
        ]
        return profile

    def _set_profile(self, sid: str, profile: Dict[str, Any]) -> None:
        safe_profile = self._default_profile()
        safe_profile["budget"] = str(profile.get("budget", "")).strip()
        safe_profile["travel_style"] = str(profile.get("travel_style", "")).strip()
        safe_profile["disliked"] = [
            str(x).strip() for x in profile.get("disliked", []) if str(x).strip()
        ]
        safe_profile["history_destinations"] = [
            str(x).strip() for x in profile.get("history_destinations", []) if str(x).strip()
        ]

        if self._redis:
            self._redis.hset(
                self._key("profile", sid),
                mapping={
                    "budget": safe_profile["budget"],
                    "travel_style": safe_profile["travel_style"],
                    "disliked": json.dumps(safe_profile["disliked"], ensure_ascii=False),
                    "history_destinations": json.dumps(
                        safe_profile["history_destinations"], ensure_ascii=False
                    ),
                    "updated_at": str(int(time.time())),
                },
            )
            return

        self._profiles[sid] = safe_profile
        self._save_profiles()

    @staticmethod
    def _estimate_tokens(messages: List[Dict[str, str]]) -> int:
        text = "\n".join(m.get("content", "") for m in messages)
        # Rough estimate for Chinese/English mixed text.
        return max(1, len(text) // 2)

    @staticmethod
    def _extract_budget(text: str) -> str:
        m = re.search(r"预算\s*([0-9]{3,6})\s*元?", text)
        if m:
            return f"{m.group(1)}元"
        if "低预算" in text or "穷游" in text:
            return "低预算"
        if "高预算" in text or "豪华" in text:
            return "高预算"
        return ""

    @staticmethod
    def _extract_style(text: str) -> str:
        style_map = {
            "历史": "文化探索",
            "博物馆": "文化探索",
            "拍照": "摄影打卡",
            "美食": "美食优先",
            "亲子": "亲子游",
            "休闲": "轻松慢游",
            "徒步": "户外徒步",
        }
        for k, v in style_map.items():
            if k in text:
                return v
        return ""

    @staticmethod
    def _extract_disliked(text: str) -> List[str]:
        dislikes: List[str] = []
        m = re.findall(r"(?:不要|不想|避免)\s*([^，。；,.]{1,10})", text)
        for item in m:
            item = item.strip()
            if item and item not in dislikes:
                dislikes.append(item)
        return dislikes

    def _compress_history(self, session_id: str) -> None:
        messages = self._get_session_messages(session_id)
        if len(messages) <= self._max_short_messages and self._estimate_tokens(messages) <= self._compress_token_threshold:
            return

        keep_recent = messages[-self._max_short_messages:]
        old_messages = messages[:-self._max_short_messages]
        if not old_messages:
            return

        raw_old_text = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')}" for m in old_messages
        )
        summary = ""

        try:
            llm = get_llm()
            prompt = (
                "请将以下对话历史压缩为不超过120字的中文摘要，重点保留：用户预算、偏好、禁忌、"
                "已讨论目的地和关键约束。\n\n"
                f"{raw_old_text}"
            )
            resp = llm.invoke([
                SystemMessage(content="你是对话压缩助手。"),
                HumanMessage(content=prompt),
            ])
            summary = (getattr(resp, "content", "") or "").strip()
        except Exception as e:
            logger.warning(f"历史摘要失败，使用规则摘要: {e}")

        if not summary:
            summary = "；".join(
                (m.get("content", "")[:30] for m in old_messages[-3:] if m.get("content"))
            )

        self._set_session_summary(session_id, summary[:240])
        self._set_session_messages(session_id, keep_recent)

    def record_turn(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
        city: str = "",
        attraction_name: str = "",
    ) -> None:
        sid = (session_id or "default").strip() or "default"

        with self._lock:
            msgs = self._get_session_messages(sid)
            msgs.append({"role": "user", "content": user_message})
            msgs.append({"role": "assistant", "content": assistant_message})
            self._set_session_messages(sid, msgs)

            profile = self._get_profile(sid)

            budget = self._extract_budget(user_message)
            if budget:
                profile["budget"] = budget

            style = self._extract_style(user_message)
            if style:
                profile["travel_style"] = style

            disliked = self._extract_disliked(user_message)
            existing_disliked = profile.setdefault("disliked", [])
            for item in disliked:
                if item not in existing_disliked:
                    existing_disliked.append(item)

            destinations = profile.setdefault("history_destinations", [])
            for place in (city, attraction_name):
                place = (place or "").strip()
                if place and place not in destinations:
                    destinations.append(place)

            self._compress_history(sid)
            self._set_profile(sid, profile)

    def build_context(self, session_id: str) -> str:
        sid = (session_id or "default").strip() or "default"

        with self._lock:
            profile = self._get_profile(sid)
            summary = self._get_session_summary(sid)
            recent = self._get_session_messages(sid)

        lines: List[str] = []

        if profile:
            lines.append("[长期偏好]")
            if profile.get("budget"):
                lines.append(f"- 预算: {profile['budget']}")
            if profile.get("travel_style"):
                lines.append(f"- 风格: {profile['travel_style']}")
            if profile.get("disliked"):
                lines.append(f"- 避免: {', '.join(profile['disliked'][:5])}")
            if profile.get("history_destinations"):
                lines.append(f"- 历史目的地: {', '.join(profile['history_destinations'][:8])}")

        if summary:
            lines.append("[短期摘要]")
            lines.append(summary)

        if recent:
            lines.append("[最近对话]")
            for m in recent[-4:]:
                role = "用户" if m.get("role") == "user" else "助手"
                lines.append(f"- {role}: {m.get('content', '')[:80]}")

        return "\n".join(lines).strip()


_memory_service_instance: MemoryService | None = None


def get_memory_service() -> MemoryService:
    global _memory_service_instance
    if _memory_service_instance is None:
        _memory_service_instance = MemoryService()
    return _memory_service_instance
