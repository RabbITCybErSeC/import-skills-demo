from fastapi.testclient import TestClient

from mtls_demo.server.api import create_app


def test_api_round_trip(tmp_path):
    app = create_app(str(tmp_path / "state.sqlite3"))

    with TestClient(app) as client:
        response = client.post(
            "/agents/register",
            json={"agent_id": "agent-1", "display_name": "Demo Agent", "capabilities": ["shell"]},
        )
        assert response.status_code == 200

        queued = client.post(
            "/commands",
            json={"agent_id": "agent-1", "command": "echo hi", "timeout_seconds": 5},
        )
        assert queued.status_code == 201
        command_id = queued.json()["command_id"]

        lease = client.post("/agents/agent-1/commands/lease")
        assert lease.status_code == 200
        assert lease.json()["command"]["command_id"] == command_id

        result = client.post(
            f"/commands/{command_id}/result",
            json={"exit_code": 0, "stdout": "hi\n", "stderr": ""},
        )
        assert result.status_code == 200
        assert result.json()["status"] == "completed"

        commands = client.get("/commands")
        assert commands.status_code == 200
        assert len(commands.json()) == 1
