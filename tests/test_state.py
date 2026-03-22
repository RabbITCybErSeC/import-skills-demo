from datetime import datetime, timedelta, timezone

from mtls_demo.protocol import AgentRegistration, CommandResultUpdate, EnqueueCommandRequest
from mtls_demo.state import StateStore


def test_state_store_command_lifecycle(tmp_path):
    store = StateStore(str(tmp_path / "state.sqlite3"))
    store.init_db()

    registered = store.register_agent(
        AgentRegistration(agent_id="agent-1", display_name="Agent One", capabilities=["shell"])
    )
    assert registered.agent_id == "agent-1"
    assert registered.status == "online"

    queued = store.enqueue_command(
        EnqueueCommandRequest(agent_id="agent-1", command="echo hi", timeout_seconds=5)
    )
    assert queued.status == "queued"

    leased = store.lease_next_command("agent-1")
    assert leased is not None
    assert leased.command_id == queued.command_id
    assert leased.status == "in_progress"

    completed = store.complete_command(
        queued.command_id,
        CommandResultUpdate(exit_code=0, stdout="hi\n", stderr=""),
    )
    assert completed.status == "completed"
    assert completed.stdout == "hi\n"

    commands = store.list_commands(agent_id="agent-1")
    assert len(commands) == 1
    assert commands[0].command_id == queued.command_id


def test_prune_stale_agents(tmp_path):
    store = StateStore(str(tmp_path / "state.sqlite3"))
    store.init_db()

    store.register_agent(AgentRegistration(agent_id="stale-agent", display_name="Old Agent"))
    stale_time = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    with store._connect() as connection:
        connection.execute(
            "UPDATE agents SET last_seen = ?, updated_at = ? WHERE agent_id = ?",
            (stale_time, stale_time, "stale-agent"),
        )
        connection.commit()

    pruned = store.prune_stale_agents(stale_after_seconds=60)

    assert pruned == ["stale-agent"]
    assert store.get_agent("stale-agent") is None
