from mtls_demo.agent.client import CommandRecord, execute_command


def make_command(command: str, timeout_seconds: int = 2) -> CommandRecord:
    return CommandRecord(
        command_id="cmd-1",
        agent_id="agent-1",
        command=command,
        requested_by="test",
        timeout_seconds=timeout_seconds,
        status="queued",
        created_at="2026-03-22T00:00:00+00:00",
    )


def test_execute_command_success():
    result = execute_command(make_command('python3 -c "print(\'hello\')"'))
    assert result.exit_code == 0
    assert result.stdout.strip() == "hello"


def test_execute_command_timeout():
    result = execute_command(
        make_command('python3 -c "import time; time.sleep(2)"', timeout_seconds=1)
    )
    assert result.exit_code == 124
    assert "Timed out" in result.stderr
