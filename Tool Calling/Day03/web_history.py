import asyncio
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from prompt import SYSTEM_PROMPT


SESSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
SESSION_VERSION = 1


def utc_now_iso():
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def new_turn_id():
    return uuid.uuid4().hex[:12]


class WebHistoryStore:
    """以 data/web_sessions/<session_id>.json 保存 Web 会话。"""

    def __init__(self, root="data/web_sessions"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._chmod(self.root, 0o700)

    @staticmethod
    def new_session_id():
        return uuid.uuid4().hex

    @staticmethod
    def is_valid_session_id(session_id):
        return (
            isinstance(session_id, str)
            and bool(SESSION_ID_RE.fullmatch(session_id))
        )

    @staticmethod
    def _chmod(path, mode):
        try:
            os.chmod(path, mode)
        except OSError:
            pass

    def _path(self, session_id):
        if not self.is_valid_session_id(session_id):
            raise ValueError("invalid session id")
        return self.root / f"{session_id}.json"

    def create(self, session_id=None):
        session_id = session_id or self.new_session_id()
        now = utc_now_iso()
        state = {
            "version": SESSION_VERSION,
            "session_id": session_id,
            "created_at": now,
            "updated_at": now,
            "turns": [],
        }
        return self.save(state)

    def load(self, session_id):
        if not self.is_valid_session_id(session_id):
            raise ValueError("invalid session id")

        path = self._path(session_id)
        if not path.exists():
            return self.create(session_id)

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._quarantine(path)
            return self.create(session_id)

        if (
            not isinstance(data, dict)
            or data.get("version") != SESSION_VERSION
            or not isinstance(data.get("turns"), list)
        ):
            self._quarantine(path)
            return self.create(session_id)

        data["session_id"] = session_id
        data["turns"] = [
            turn for turn in data["turns"] if isinstance(turn, dict)
        ]
        data.setdefault("created_at", utc_now_iso())
        return data

    def save(self, state):
        session_id = state.get("session_id")
        if not self.is_valid_session_id(session_id):
            raise ValueError("invalid session id")

        state["version"] = SESSION_VERSION
        state["updated_at"] = utc_now_iso()

        path = self._path(session_id)
        tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")

        tmp_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
        self._chmod(path, 0o600)
        return state

    def clear(self, session_id):
        """用空会话覆盖当前文件，而不是删除其他文件。"""
        return self.create(session_id)

    def _quarantine(self, path):
        try:
            backup = path.with_name(f"{path.name}.corrupt-{int(time.time())}")
            path.replace(backup)
        except OSError:
            pass


class ConversationSession:
    """单个浏览器会话；turns 是事实来源，messages 由 turns 派生。"""

    def __init__(self, session_id, state, store):
        self.session_id = session_id
        self.store = store
        self.created_at = state.get("created_at") or utc_now_iso()
        self.turns = list(state.get("turns") or [])
        self.lock = asyncio.Lock()
        self.processing = False
        self.messages = self._build_messages()

    def _initial_messages(self):
        return [{"role": "system", "content": SYSTEM_PROMPT}]

    def _build_messages(self):
        messages = self._initial_messages()
        for turn in self.turns:
            if not isinstance(turn, dict):
                continue
            if turn.get("answer") is not None and turn.get("status") != "failed":
                messages.append({
                    "role": "user",
                    "content": turn.get("question", ""),
                })
                messages.append({
                    "role": "assistant",
                    "content": turn["answer"],
                })
        return messages

    @property
    def busy(self):
        return self.processing or self.lock.locked()

    def add_turn(self, turn):
        """追加一轮并持久化；返回是否成功写入文件。"""
        turn["turn_index"] = len(self.turns) + 1
        self.turns.append(turn)

        if turn.get("answer") is not None and turn.get("status") != "failed":
            self.messages.append({
                "role": "user",
                "content": turn.get("question", ""),
            })
            self.messages.append({
                "role": "assistant",
                "content": turn["answer"],
            })

        try:
            self._persist()
            return True
        except Exception:
            return False

    def _persist(self):
        self.store.save({
            "version": SESSION_VERSION,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": utc_now_iso(),
            "turns": self.turns,
        })

    def history_summary(self):
        summaries = []
        for turn in self.turns:
            if not isinstance(turn, dict):
                continue
            trace = turn.get("trace")
            if not isinstance(trace, dict):
                trace = {}
            error = trace.get("error")
            if not isinstance(error, dict):
                error = {}
            summaries.append({
                "turn_id": turn.get("turn_id"),
                "turn_index": turn.get("turn_index"),
                "question": turn.get("question", ""),
                "answer": turn.get("answer"),
                "status": turn.get("status", "failed"),
                "created_at": turn.get("created_at"),
                "finished_at": turn.get("finished_at"),
                "has_trace": bool(trace),
                "error_message": error.get("message"),
            })
        return summaries

    def get_turn(self, turn_id):
        for turn in self.turns:
            if isinstance(turn, dict) and turn.get("turn_id") == turn_id:
                return turn
        return None

    def reset(self):
        self.store.clear(self.session_id)
        self.turns = []
        self.messages = self._initial_messages()


class SessionManager:
    """按浏览器 Cookie 管理会话；单进程内缓存。"""

    def __init__(self, store=None):
        self.store = store or WebHistoryStore()
        self.sessions = {}

    def create_new(self):
        state = self.store.create()
        session = ConversationSession(state["session_id"], state, self.store)
        self.sessions[session.session_id] = session
        return session

    def get_or_create(self, session_id=None):
        if WebHistoryStore.is_valid_session_id(session_id):
            existing = self.sessions.get(session_id)
            if existing is not None:
                return existing

            state = self.store.load(session_id)
            session = ConversationSession(session_id, state, self.store)
            self.sessions[session_id] = session
            return session

        return self.create_new()
