"""Session lifecycle management and persistence to JSON files."""

import json
import os
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from loguru import logger

from backend.app.config import settings


class SessionManager:
    """Manages agent session lifecycle: create, update, persist, replay."""

    def __init__(self, max_active_sessions: int = 10):
        self._active_sessions: dict[str, dict] = {}
        self._max_sessions = max_active_sessions
        os.makedirs(f"{settings.data_dir}/sessions", exist_ok=True)
        os.makedirs(f"{settings.data_dir}/screenshots", exist_ok=True)

    def create_session(self, session_id: str) -> dict:
        if len(self._active_sessions) >= self._max_sessions:
            raise HTTPException(
                status_code=429,
                detail=f"Too many active sessions (max {self._max_sessions})",
            )
        session = {
            "session_id": session_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "running",
            "task": "",
            "execution_log": [],
            "final_answer": "",
            "token_usage": {},
        }
        self._active_sessions[session_id] = session
        return session

    def update(self, session_id: str, **kwargs) -> None:
        if session_id in self._active_sessions:
            self._active_sessions[session_id].update(kwargs)

    def append_log(self, session_id: str, entry: dict) -> None:
        if session_id in self._active_sessions:
            self._active_sessions[session_id]["execution_log"].append(entry)

    def persist(self, session_id: str) -> str:
        session = self._active_sessions.get(session_id)
        if not session:
            return ""
        session["status"] = "completed"
        filepath = f"{settings.data_dir}/sessions/{session_id}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(session, f, ensure_ascii=False, indent=2, default=str)
        logger.info("Session {} persisted to {}", session_id, filepath)
        return filepath

    def get_history(self, session_id: str) -> dict | None:
        filepath = f"{settings.data_dir}/sessions/{session_id}.json"
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        return self._active_sessions.get(session_id)

    def get_replay(self, session_id: str) -> list[dict]:
        session = self.get_history(session_id)
        if not session:
            return []
        return [
            {
                "step_index": i,
                "step": e.get("step", ""),
                "screenshot_path": e.get("screenshot_path", ""),
                "timestamp": e.get("timestamp", ""),
            }
            for i, e in enumerate(session.get("execution_log", []))
        ]

    def list_sessions(self) -> list[dict]:
        """返回会话列表，每个会话含 id、task 摘要、创建时间、状态。"""
        sessions_dir = Path(f"{settings.data_dir}/sessions")
        if not sessions_dir.exists():
            return []
        results = []
        for f in sorted(sessions_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                results.append({
                    "id": data.get("session_id", f.stem),
                    "task_summary": (data.get("task", "") or "")[:30],
                    "created_at": data.get("created_at", ""),
                    "status": data.get("status", "unknown"),
                })
            except (json.JSONDecodeError, OSError):
                continue
        return results

    def delete_session(self, session_id: str) -> bool:
        """删除会话持久化文件。返回 True 表示删除成功。"""
        filepath = Path(f"{settings.data_dir}/sessions/{session_id}.json")
        if filepath.exists():
            filepath.unlink()
            logger.info("Session {} deleted", session_id)
            return True
        return False

    async def schedule_cleanup(self, session_id: str, mcp_client=None, delay_minutes: int = None) -> None:
        if delay_minutes is None:
            delay_minutes = settings.session_ttl_minutes
        await asyncio.sleep(delay_minutes * 60)
        if session_id in self._active_sessions:
            del self._active_sessions[session_id]
        if mcp_client:
            await mcp_client.close()
        logger.info("Session {} cleaned up after {} minutes", session_id, delay_minutes)
