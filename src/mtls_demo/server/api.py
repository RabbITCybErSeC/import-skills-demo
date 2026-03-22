from __future__ import annotations

import argparse
import ssl
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request

from mtls_demo.protocol import AgentRecord, AgentRegistration, CommandLease, CommandRecord, CommandResultUpdate, EnqueueCommandRequest
from mtls_demo.state import StateStore


DEFAULT_DB_PATH = Path("demo.sqlite3")


def create_app(db_path: str = str(DEFAULT_DB_PATH)) -> FastAPI:
    store = StateStore(db_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        store.init_db()
        yield

    app = FastAPI(title="mTLS Demo Server", version="0.1.0", lifespan=lifespan)
    app.state.store = store

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/agents/register", response_model=AgentRecord)
    def register_agent(registration: AgentRegistration, request: Request) -> AgentRecord:
        return request.app.state.store.register_agent(registration)

    @app.get("/agents", response_model=list[AgentRecord])
    def list_agents(request: Request) -> list[AgentRecord]:
        return request.app.state.store.list_agents()

    @app.post("/agents/{agent_id}/heartbeat", response_model=AgentRecord)
    def heartbeat(agent_id: str, request: Request) -> AgentRecord:
        agent = request.app.state.store.mark_agent_seen(agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        return agent

    @app.post("/agents/{agent_id}/commands/lease", response_model=CommandLease)
    def lease_command(agent_id: str, request: Request) -> CommandLease:
        store: StateStore = request.app.state.store
        agent = store.mark_agent_seen(agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        return CommandLease(command=store.lease_next_command(agent_id))

    @app.post("/commands", response_model=CommandRecord, status_code=201)
    def enqueue_command(command: EnqueueCommandRequest, request: Request) -> CommandRecord:
        store: StateStore = request.app.state.store
        if store.get_agent(command.agent_id) is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        return store.enqueue_command(command)

    @app.get("/commands", response_model=list[CommandRecord])
    def list_commands(
        request: Request,
        agent_id: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[CommandRecord]:
        return request.app.state.store.list_commands(agent_id=agent_id, limit=limit)

    @app.post("/commands/{command_id}/result", response_model=CommandRecord)
    def submit_result(command_id: str, result: CommandResultUpdate, request: Request) -> CommandRecord:
        store: StateStore = request.app.state.store
        command = store.get_command(command_id)
        if command is None:
            raise HTTPException(status_code=404, detail="Command not found")
        store.mark_agent_seen(command.agent_id)
        return store.complete_command(command_id, result)

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the mTLS demo server")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--ssl-certfile", required=True)
    parser.add_argument("--ssl-keyfile", required=True)
    parser.add_argument("--ssl-ca-certs", required=True)
    parser.add_argument(
        "--allow-without-client-certs",
        action="store_true",
        help="Disable client certificate enforcement for troubleshooting",
    )
    args = parser.parse_args()

    app = create_app(args.db_path)
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        ssl_certfile=args.ssl_certfile,
        ssl_keyfile=args.ssl_keyfile,
        ssl_ca_certs=args.ssl_ca_certs,
        ssl_cert_reqs=ssl.CERT_NONE if args.allow_without_client_certs else ssl.CERT_REQUIRED,
    )


if __name__ == "__main__":
    main()
