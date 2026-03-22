from __future__ import annotations

import os

from client import AgentRunner, build_ssl_context


SERVER_URL = os.getenv("MTLS_DEMO_SERVER_URL", "http://127.0.0.1:8000")
AGENT_ID = os.getenv("MTLS_DEMO_AGENT_ID", "agent-1")
DISPLAY_NAME = os.getenv("MTLS_DEMO_DISPLAY_NAME", "Demo Agent")
CAPABILITIES = ["shell"]
METADATA: dict[str, str] = {}
SHARED_SECRET = os.getenv("MTLS_DEMO_SHARED_SECRET", "demo-secret")
POLL_INTERVAL = float(os.getenv("MTLS_DEMO_POLL_INTERVAL", "5"))
REQUEST_TIMEOUT = float(os.getenv("MTLS_DEMO_REQUEST_TIMEOUT", "10"))


def main() -> None:
    runner = AgentRunner(
        server_url=SERVER_URL,
        agent_id=AGENT_ID,
        shared_secret=SHARED_SECRET,
        ssl_context=build_ssl_context(None, False),
        request_timeout=REQUEST_TIMEOUT,
        display_name=DISPLAY_NAME,
        capabilities=CAPABILITIES,
        metadata=METADATA,
        poll_interval=POLL_INTERVAL,
    )
    raise SystemExit(runner.run())


if __name__ == "__main__":
    main()
