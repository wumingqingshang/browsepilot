"""Session lifecycle management and persistence to JSON files."""

import json
import os
import asyncio
import shutil
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

    def _delete_session_files(self, session_id: str):
        """Delete session JSON + all associated screenshots + empty dirs."""
        filepath = Path(f"{settings.data_dir}/sessions/{session_id}.json")
        if filepath.exists():
            try:
                data = json.loads(filepath.read_text(encoding="utf-8"))
                for entry in data.get("execution_log", []):
                    screenshot_path = entry.get("screenshot_path", "")
                    if screenshot_path:
                        try:
                            Path(screenshot_path).unlink(missing_ok=True)
                        except OSError:
                            pass
            except (json.JSONDecodeError, OSError):
                pass
            filepath.unlink(missing_ok=True)

        screenshots_dir = Path(f"{settings.data_dir}/screenshots")
        session_screenshots = screenshots_dir / session_id
        if session_screenshots.exists():
            try:
                session_screenshots.rmdir()
            except OSError:
                pass

    async def schedule_cleanup(self, session_id: str, mcp_client=None, delay_minutes: int = None) -> None:
        if delay_minutes is None:
            delay_minutes = settings.session_ttl_minutes
        await asyncio.sleep(delay_minutes * 60)

        # 1. Clean up disk files
        self._delete_session_files(session_id)

        # 2. Clean up memory
        if session_id in self._active_sessions:
            del self._active_sessions[session_id]

        # 3. Close MCP (if provided)
        if mcp_client:
            await mcp_client.close()

        logger.info("Session {} cleaned up after {} minutes", session_id, delay_minutes)

    def cleanup_on_startup(self):
        """Scan and delete sessions beyond count limit and orphan screenshots."""
        max_count = getattr(settings, 'max_sessions_count', 100)
        sessions_dir = Path(f"{settings.data_dir}/sessions")
        if not sessions_dir.exists():
            return

        sessions = sorted(sessions_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
        if len(sessions) > max_count:
            for old in sessions[:-(max_count)]:
                session_id = old.stem
                logger.info("Startup cleanup: removing old session {}", session_id)
                self._delete_session_files(session_id)

        self._cleanup_orphan_screenshots()

    def _cleanup_orphan_screenshots(self):
        """Delete screenshot dirs with no corresponding session JSON."""
        screenshots_dir = Path(f"{settings.data_dir}/screenshots")
        if not screenshots_dir.exists():
            return
        for child in screenshots_dir.iterdir():
            if child.is_dir():
                session_json = Path(f"{settings.data_dir}/sessions/{child.name}.json")
                if not session_json.exists():
                    shutil.rmtree(child, ignore_errors=True)
                    logger.info("Removed orphan screenshots: {}", child)

    def check_storage_before_write(self) -> bool:
        """Check data/ dir size, trigger emergency cleanup if over limit."""
        max_storage_mb = getattr(settings, 'max_storage_mb', 500)
        total_size = self._get_data_dir_size()
        if total_size > max_storage_mb * 1024 * 1024:
            logger.warning("Storage {} MB exceeds limit {} MB, emergency cleanup",
                           total_size // (1024 * 1024), max_storage_mb)
            self._emergency_cleanup(ratio=0.2)
            if self._get_data_dir_size() > max_storage_mb * 1024 * 1024:
                logger.warning("Storage still full after cleanup")
                return False
        return True

    def _get_data_dir_size(self) -> int:
        total = 0
        data_dir = Path(settings.data_dir)
        if not data_dir.exists():
            return 0
        for f in data_dir.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
        return total

    def _emergency_cleanup(self, ratio: float = 0.2):
        """Delete the oldest ratio of sessions to free space."""
        sessions_dir = Path(f"{settings.data_dir}/sessions")
        if not sessions_dir.exists():
            return
        sessions = sorted(sessions_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
        to_delete = int(len(sessions) * ratio)
        for old in sessions[:to_delete]:
            self._delete_session_files(old.stem)
