from fastapi.testclient import TestClient

from mtls_demo.auth import build_auth_headers
from mtls_demo.server.api import create_app


def test_api_round_trip(tmp_path):
    shared_secret = "test-secret"
    app = create_app(str(tmp_path / "state.sqlite3"), shared_secret=shared_secret)

    def signed_post(client: TestClient, path: str, agent_id: str, payload: dict | None = None):
        body = b""
        headers: dict[str, str]
        if payload is not None:
            import json

            body = json.dumps(payload).encode("utf-8")
            headers = {"Content-Type": "application/json"}
        else:
            headers = {}
        headers = build_auth_headers(shared_secret, "POST", path, agent_id, body)
        if payload is not None:
            headers["Content-Type"] = "application/json"
        return client.post(path, content=body or None, headers=headers)

    with TestClient(app) as client:
        response = signed_post(
            client,
            "/agents/register",
            "agent-1",
            {"agent_id": "agent-1", "display_name": "Demo Agent", "capabilities": ["shell"]},
        )
        assert response.status_code == 200

        queued = client.post(
            "/commands",
            json={"agent_id": "agent-1", "command": "echo hi", "timeout_seconds": 5},
        )
        assert queued.status_code == 201
        command_id = queued.json()["command_id"]

        lease = signed_post(client, "/agents/agent-1/commands/lease", "agent-1")
        assert lease.status_code == 200
        assert lease.json()["command"]["command_id"] == command_id

        result = signed_post(
            client,
            f"/commands/{command_id}/result",
            "agent-1",
            {"exit_code": 0, "stdout": "hi\n", "stderr": ""},
        )
        assert result.status_code == 200
        assert result.json()["status"] == "completed"

        commands = client.get("/commands")
        assert commands.status_code == 200
        assert len(commands.json()) == 1


def test_agent_auth_is_required(tmp_path):
    app = create_app(str(tmp_path / "state.sqlite3"), shared_secret="test-secret")

    with TestClient(app) as client:
        response = client.post(
            "/agents/register",
            json={"agent_id": "agent-1", "display_name": "Demo Agent", "capabilities": ["shell"]},
        )
        assert response.status_code == 401
