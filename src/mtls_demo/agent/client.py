from __future__ import annotations

import argparse
import json
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any

from mtls_demo.auth import build_auth_headers, resolve_shared_secret


@dataclass
class CommandRecord:
    command_id: str
    agent_id: str
    command: str
    timeout_seconds: int
    status: str = "queued"
    requested_by: str = "server"
    created_at: str = ""

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> CommandRecord:
        return cls(
            command_id=str(payload["command_id"]),
            agent_id=str(payload["agent_id"]),
            command=str(payload["command"]),
            timeout_seconds=int(payload.get("timeout_seconds", 60)),
            status=str(payload.get("status", "queued")),
            requested_by=str(payload.get("requested_by", "server")),
            created_at=str(payload.get("created_at", "")),
        )


@dataclass
class CommandResultUpdate:
    exit_code: int
    stdout: str = ""
    stderr: str = ""


class ApiError(RuntimeError):
    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"HTTP {status_code}: {body}")
        self.status_code = status_code
        self.body = body


def execute_command(command: CommandRecord) -> CommandResultUpdate:
    try:
        completed = subprocess.run(
            command.command,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
            timeout=command.timeout_seconds,
        )
        return CommandResultUpdate(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout.decode() if exc.stdout else "")
        stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr.decode() if exc.stderr else "")
        message = f"Timed out after {command.timeout_seconds} seconds"
        stderr = f"{stderr}\n{message}".strip()
        return CommandResultUpdate(exit_code=124, stdout=stdout, stderr=stderr)


class AgentRunner:
    def __init__(
        self,
        server_url: str,
        agent_id: str,
        shared_secret: str,
        ssl_context: ssl.SSLContext,
        request_timeout: float,
        display_name: str | None,
        capabilities: list[str],
        metadata: dict[str, Any],
        poll_interval: float,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.agent_id = agent_id
        self.shared_secret = shared_secret
        self.ssl_context = ssl_context
        self.request_timeout = request_timeout
        self.display_name = display_name
        self.capabilities = capabilities
        self.metadata = metadata
        self.poll_interval = poll_interval

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = b""
        headers: dict[str, str] = {}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        headers.update(build_auth_headers(self.shared_secret, method, path, self.agent_id, body))
        request = urllib.request.Request(
            url=f"{self.server_url}{path}",
            data=body if method.upper() != "GET" else None,
            headers=headers,
            method=method.upper(),
        )
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout, context=self.ssl_context) as response:
                raw = response.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            raise ApiError(exc.code, body_text) from exc

    def register(self) -> None:
        self._request(
            "POST",
            "/agents/register",
            {
                "agent_id": self.agent_id,
                "display_name": self.display_name,
                "capabilities": self.capabilities,
                "metadata": self.metadata,
            },
        )

    def lease_command(self) -> CommandRecord | None:
        try:
            payload = self._request("POST", f"/agents/{self.agent_id}/commands/lease")
        except ApiError as exc:
            if exc.status_code == 404:
                self.register()
                return None
            raise
        command = payload.get("command")
        if command is None:
            return None
        return CommandRecord.from_payload(command)

    def submit_result(self, command_id: str, result: CommandResultUpdate) -> None:
        self._request("POST", f"/commands/{command_id}/result", asdict(result))

    def run(self, once: bool = False) -> int:
        self.register()
        while True:
            command = self.lease_command()
            if command is None:
                if once:
                    return 0
                time.sleep(self.poll_interval)
                continue
            result = execute_command(command)
            self.submit_result(command.command_id, result)
            if once:
                return 0


def parse_metadata(items: list[str]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for item in items:
        key, _, value = item.partition("=")
        if not key or not _:
            raise ValueError(f"Invalid metadata entry: {item}")
        metadata[key] = value
    return metadata


def build_ssl_context(ca_certs: str | None, insecure: bool) -> ssl.SSLContext:
    if insecure:
        return ssl._create_unverified_context()
    if ca_certs:
        return ssl.create_default_context(cafile=ca_certs)
    return ssl.create_default_context()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the lean demo agent")
    parser.add_argument("--server-url", default="https://127.0.0.1:8443")
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--display-name")
    parser.add_argument("--capability", action="append", default=[])
    parser.add_argument("--metadata", action="append", default=[])
    parser.add_argument("--shared-secret")
    parser.add_argument("--ca-certs")
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--request-timeout", type=float, default=10.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    metadata = parse_metadata(args.metadata)
    runner = AgentRunner(
        server_url=args.server_url,
        agent_id=args.agent_id,
        shared_secret=resolve_shared_secret(args.shared_secret),
        ssl_context=build_ssl_context(args.ca_certs, args.insecure),
        request_timeout=args.request_timeout,
        display_name=args.display_name,
        capabilities=list(args.capability),
        metadata=metadata,
        poll_interval=args.poll_interval,
    )
    raise SystemExit(runner.run(once=args.once))


if __name__ == "__main__":
    main()
