import json

import pytest

from prompt import SYSTEM_PROMPT
from web_history import ConversationSession, WebHistoryStore


def make_store(tmp_path):
    return WebHistoryStore(tmp_path / "web_sessions")


def make_session(store):
    state = store.create()
    return ConversationSession(state["session_id"], state, store)


def test_create_append_load_and_clear(tmp_path):
    store = make_store(tmp_path)
    session = make_session(store)

    saved = session.add_turn({
        "turn_id": "turn_1",
        "question": "北京天气怎么样？",
        "answer": "北京今天晴。",
        "status": "success",
        "trace": {"status": "success", "rounds": []},
    })

    assert saved is True
    path = store.root / f"{session.session_id}.json"
    assert path.exists()
    assert not list(store.root.glob("*.tmp"))

    loaded = store.load(session.session_id)
    assert len(loaded["turns"]) == 1
    assert loaded["turns"][0]["turn_index"] == 1

    summary = session.history_summary()
    assert summary[0]["turn_id"] == "turn_1"
    assert summary[0]["answer"] == "北京今天晴。"
    assert summary[0]["has_trace"] is True

    session.reset()
    assert session.turns == []
    assert session.messages == [{"role": "system", "content": SYSTEM_PROMPT}]
    assert store.load(session.session_id)["turns"] == []


def test_failed_turn_is_saved_but_not_in_model_context(tmp_path):
    store = make_store(tmp_path)
    session = make_session(store)

    session.add_turn({
        "turn_id": "turn_failed",
        "question": "北京天气怎么样？",
        "answer": None,
        "status": "failed",
        "trace": {
            "status": "failed",
            "error": {"message": "模型服务调用失败，请稍后重试"},
        },
    })

    assert len(session.turns) == 1
    assert session.messages == [{"role": "system", "content": SYSTEM_PROMPT}]
    summary = session.history_summary()
    assert summary[0]["status"] == "failed"
    assert summary[0]["answer"] is None
    assert summary[0]["error_message"] == "模型服务调用失败，请稍后重试"


def test_corrupt_file_is_quarantined(tmp_path):
    store = make_store(tmp_path)
    session_id = store.new_session_id()
    path = store.root / f"{session_id}.json"
    path.write_text("{not valid json", encoding="utf-8")

    state = store.load(session_id)

    assert state["turns"] == []
    assert list(store.root.glob(f"{session_id}.json.corrupt-*"))
    # 损坏文件被隔离后，会创建一个新的空会话文件
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["turns"] == []


def test_invalid_session_id_is_rejected(tmp_path):
    store = make_store(tmp_path)

    with pytest.raises(ValueError):
        store.load("../escape")
    with pytest.raises(ValueError):
        store.load("not-a-uuid")

    assert not (store.root.parent / "escape.json").exists()


def test_sessions_are_isolated(tmp_path):
    store = make_store(tmp_path)
    session_a = make_session(store)
    session_b = make_session(store)

    session_a.add_turn({
        "turn_id": "turn_a",
        "question": "北京",
        "answer": "晴",
        "status": "success",
        "trace": {"status": "success"},
    })
    session_b.add_turn({
        "turn_id": "turn_b",
        "question": "上海",
        "answer": "多云",
        "status": "success",
        "trace": {"status": "success"},
    })

    loaded_a = store.load(session_a.session_id)
    loaded_b = store.load(session_b.session_id)

    assert [turn["turn_id"] for turn in loaded_a["turns"]] == ["turn_a"]
    assert [turn["turn_id"] for turn in loaded_b["turns"]] == ["turn_b"]
    assert session_a.messages[1]["content"] == "北京"
    assert session_b.messages[1]["content"] == "上海"


def test_saved_state_contains_no_system_prompt_in_turns(tmp_path):
    store = make_store(tmp_path)
    session = make_session(store)

    session.add_turn({
        "turn_id": "turn_1",
        "question": "北京",
        "answer": "晴",
        "status": "success",
        "trace": {"status": "success", "rounds": []},
    })

    text = (store.root / f"{session.session_id}.json").read_text(encoding="utf-8")
    assert SYSTEM_PROMPT not in text
    assert "sk-" not in text


def test_store_file_is_json_and_versioned(tmp_path):
    store = make_store(tmp_path)
    session = make_session(store)
    session.add_turn({
        "turn_id": "turn_1",
        "question": "北京",
        "answer": "晴",
        "status": "success",
        "trace": {"status": "success"},
    })

    data = json.loads(
        (store.root / f"{session.session_id}.json").read_text(encoding="utf-8")
    )
    assert data["version"] == 1
    assert data["session_id"] == session.session_id
    assert isinstance(data["turns"], list)
