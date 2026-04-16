"""FSM state save/load/clear round-trips."""
from newsbrief.bot import fsm


def test_set_and_get_state_roundtrip(storage):
    fsm.set_user_state("42", "awaiting_schedule_input", {"x": 1}, storage)
    state, ctx = fsm.get_user_state("42", storage)
    assert state == "awaiting_schedule_input"
    assert ctx == {"x": 1}


def test_clear_state(storage):
    fsm.set_user_state("42", "awaiting_llm_key:groq", {"preset": "groq"}, storage)
    fsm.clear_user_state("42", storage)
    state, ctx = fsm.get_user_state("42", storage)
    assert state in ("", None)
    assert ctx == {}


def test_unknown_user_returns_none(storage):
    state, ctx = fsm.get_user_state("does_not_exist", storage)
    assert state is None
    assert ctx == {}


def test_is_awaiting():
    assert fsm.is_awaiting("awaiting_schedule_input") is True
    assert fsm.is_awaiting("active") is False
    assert fsm.is_awaiting(None) is False
    assert fsm.is_awaiting("") is False
