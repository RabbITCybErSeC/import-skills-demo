from __future__ import annotations

import argparse
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request

from mtls_demo.auth import (
    AUTH_AGENT_HEADER,
    AUTH_SIGNATURE_HEADER,
    AUTH_TIMESTAMP_HEADER,
    resolve_shared_secret,
    verify_signature,
)
from mtls_demo.protocol import AgentRecord, AgentRegistration, CommandLease, CommandRecord, CommandResultUpdate, EnqueueCommandRequest
from mtls_demo.state import StateStore


DEFAULT_DB_PATH = Path("demo.sqlite3")


async def verify_agent_auth(request: Request, expected_agent_id: str | None = None) -> str:
    agent_id = request.headers.get(AUTH_AGENT_HEADER, "")
    timestamp = request.headers.get(AUTH_TIMESTAMP_HEADER, "")
    signature = request.headers.get(AUTH_SIGNATURE_HEADER, "")
    if not agent_id or not timestamp or not signature:
        raise HTTPException(status_code=401, detail="Missing authentication headers")
    if expected_agent_id is not None and agent_id != expected_agent_id:
        raise HTTPException(status_code=403, detail="Agent identity mismatch")
    body = await request.body()
    if not verify_signature(
        request.app.state.shared_secret,
        request.method,
        request.url.path,
        agent_id,
        timestamp,
        signature,
        body,
    ):
        raise HTTPException(status_code=401, detail="Invalid request signature")
    return agent_id


def create_app(db_path: str = str(DEFAULT_DB_PATH), shared_secret: str = "dev-shared-secret") -> FastAPI:
    store = StateStore(db_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        store.init_db()
        yield

    app = FastAPI(title="mTLS Demo Server", version="0.1.0", lifespan=lifespan)
    app.state.store = store
    app.state.shared_secret = shared_secret

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/agents/register", response_model=AgentRecord)
    async def register_agent(registration: AgentRegistration, request: Request) -> AgentRecord:
        await verify_agent_auth(request, registration.agent_id)
        return request.app.state.store.register_agent(registration)

    @app.get("/agents", response_model=list[AgentRecord])
    def list_agents(request: Request) -> list[AgentRecord]:
        return request.app.state.store.list_agents()

    @app.post("/agents/{agent_id}/heartbeat", response_model=AgentRecord)
    async def heartbeat(agent_id: str, request: Request) -> AgentRecord:
        await verify_agent_auth(request, agent_id)
        agent = request.app.state.store.mark_agent_seen(agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        return agent

    @app.post("/agents/{agent_id}/commands/lease", response_model=CommandLease)
    async def lease_command(agent_id: str, request: Request) -> CommandLease:
        await verify_agent_auth(request, agent_id)
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
    async def submit_result(command_id: str, result: CommandResultUpdate, request: Request) -> CommandRecord:
        store: StateStore = request.app.state.store
        command = store.get_command(command_id)
        if command is None:
            raise HTTPException(status_code=404, detail="Command not found")
        await verify_agent_auth(request, command.agent_id)
        store.mark_agent_seen(command.agent_id)
        return store.complete_command(command_id, result)

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the demo server over plain HTTP")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--shared-secret", default=os.getenv("MTLS_DEMO_SHARED_SECRET"))
    args = parser.parse_args()

    app = create_app(args.db_path, shared_secret=resolve_shared_secret(args.shared_secret))
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
