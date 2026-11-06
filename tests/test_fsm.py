"""The control flow state machine only allows listed transitions."""
from state import fsm
from state.state_manager import StateManager


def _fresh():
    machine = fsm.FSM(StateManager())
    if machine.state != fsm.IDLE:
        machine.transition(fsm.IDLE, force=True)
    return machine


def test_starts_idle_and_follows_the_natro_loop():
    m = _fresh()
    assert m.state == fsm.IDLE
    assert m.transition(fsm.RESETTING)
    assert m.transition(fsm.CONVERTING)
    assert m.transition(fsm.TRAVELING)
    assert m.transition(fsm.GATHERING)
    assert m.transition(fsm.RESETTING)
    assert m.transition(fsm.PAUSED)
    assert m.transition(fsm.RESETTING)
    assert m.transition(fsm.IDLE)


def test_illegal_transition_is_rejected():
    m = _fresh()
    assert not m.can_transition(fsm.GATHERING)
    assert m.transition(fsm.GATHERING) is False
    assert m.state == fsm.IDLE


def test_callbacks_fire_on_enter_and_exit():
    m = _fresh()
    seen = []
    m.on_exit(fsm.IDLE, lambda *a: seen.append("exit-idle"))
    m.on_enter(fsm.RESETTING, lambda *a: seen.append("enter-resetting"))
    m.transition(fsm.RESETTING)
    assert seen == ["exit-idle", "enter-resetting"]
    m.transition(fsm.IDLE, force=True)


def test_snapshot_has_the_fields_the_remote_page_reads():
    snap = StateManager().snapshot()
    for key in ("state", "detail", "field", "backpack_pct", "runtime_seconds", "cycles", "converts", "deaths", "remote_urls"):
        assert key in snap
