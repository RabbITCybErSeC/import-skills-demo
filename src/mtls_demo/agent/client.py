from __future__ import annotations

import argparse
import subprocess
import time
from typing import Any

import httpx

from mtls_demo.protocol import AgentRegistration, CommandLease, CommandRecord, CommandResultUpdate, dump_model, validate_model


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
        client: httpx.Client,
        agent_id: str,
        display_name: str | None,
        capabilities: list[str],
        metadata: dict[str, Any],
        poll_interval: float,
    ) -> None:
        self.client = client
        self.agent_id = agent_id
        self.display_name = display_name
        self.capabilities = capabilities
        self.metadata = metadata
        self.poll_interval = poll_interval

    def register(self) -> None:
        registration = AgentRegistration(
            agent_id=self.agent_id,
            display_name=self.display_name,
            capabilities=self.capabilities,
            metadata=self.metadata,
        )
        response = self.client.post("/agents/register", json=dump_model(registration, exclude_none=True))
        response.raise_for_status()

    def lease_command(self) -> CommandRecord | None:
        response = self.client.post(f"/agents/{self.agent_id}/commands/lease")
        if response.status_code == 404:
            self.register()
            return None
        response.raise_for_status()
        payload = validate_model(CommandLease, response.json())
        return payload.command

    def submit_result(self, command_id: str, result: CommandResultUpdate) -> None:
        response = self.client.post(
            f"/commands/{command_id}/result",
            json=dump_model(result),
        )
        response.raise_for_status()

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the demo agent")
    parser.add_argument("--server-url", default="https://127.0.0.1:8443")
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--display-name")
    parser.add_argument("--capability", action="append", default=[])
    parser.add_argument("--metadata", action="append", default=[])
    parser.add_argument("--certfile", required=True)
    parser.add_argument("--keyfile", required=True)
    parser.add_argument("--ca-certs", required=True)
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--request-timeout", type=float, default=10.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    metadata = parse_metadata(args.metadata)
    with httpx.Client(
        base_url=args.server_url.rstrip("/"),
        cert=(args.certfile, args.keyfile),
        verify=args.ca_certs,
        timeout=args.request_timeout,
    ) as client:
        runner = AgentRunner(
            client=client,
            agent_id=args.agent_id,
            display_name=args.display_name,
            capabilities=list(args.capability),
            metadata=metadata,
            poll_interval=args.poll_interval,
        )
        raise SystemExit(runner.run(once=args.once))


if __name__ == "__main__":
    main()
