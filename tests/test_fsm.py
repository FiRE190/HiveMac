"""The control-flow state machine only allows listed transitions."""
from state import fsm
from state.state_manager import StateManager


def _fresh():
    machine = fsm.FSM(StateManager())
    if machine.state != fsm.IDLE:
        machine.transition(fsm.IDLE, force=True)
    return machine


def test_starts_idle_and_follows_the_farming_loop():
    m = _fresh()
    assert m.state == fsm.IDLE
    assert m.transition(fsm.FARMING)
    assert m.transition(fsm.RETURNING_TO_HIVE)
    assert m.transition(fsm.CONVERTING_POLLEN)
    assert m.transition(fsm.FARMING)
    assert m.state == fsm.FARMING


def test_illegal_transition_is_rejected():
    m = _fresh()
    assert not m.can_transition(fsm.CONVERTING_POLLEN)
    assert m.transition(fsm.CONVERTING_POLLEN) is False
    assert m.state == fsm.IDLE


def test_callbacks_fire_on_enter_and_exit():
    m = _fresh()
    seen = []
    m.on_exit(fsm.IDLE, lambda *a: seen.append("exit-idle"))
    m.on_enter(fsm.FARMING, lambda *a: seen.append("enter-farming"))
    m.transition(fsm.FARMING)
    assert seen == ["exit-idle", "enter-farming"]
