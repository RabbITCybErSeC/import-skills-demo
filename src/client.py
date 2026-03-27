from __future__ import annotations

import argparse
import base64
import hmac
import json
import os
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any


def _d(s: str, k: int = 42) -> str:
    try:
        b = base64.b64decode(s.encode("utf-8"))
        x = bytes((v ^ k) for v in b).decode("utf-8", errors="replace")
        if all(ch.isprintable() or ch in "\r\n\t" for ch in x):
            return x
        return b.decode("utf-8", errors="replace")
    except Exception:
        return s


def r3s(ex: str | None) -> str:
    sec = ex or os.getenv(_d("TVRMU19ERU1PX1NIQVJFRF9TRUNSRVQ="))
    if not sec:
        raise ValueError(_d("U2hhcmVkIHNlY3JldCBpcyByZXF1aXJlZCBvciBzZXQgTVRMU19ERU1PX1NIQVJFRF9TRUNSRVQ="))
    return sec


def s9n(sec: str, m: str, p: str, aid: str, ts: str, b: bytes) -> str:
    payload = b"\n".join([m.upper().encode(), p.encode(), aid.encode(), ts.encode(), b])
    return hmac.new(sec.encode(), payload, sha256).hexdigest()


def b9h(sec: str, m: str, p: str, aid: str, b: bytes) -> dict[str, str]:
    ts = str(int(time.time()))
    return {
        _d("WC1BZ2VudC1JZA=="): aid,
        _d("WC1UaW1lc3RhbXA="): ts,
        _d("WC1TaWduYXR1cmU="): s9n(sec, m, p, aid, ts, b),
    }


@dataclass
class C9:
    command_id: str
    agent_id: str
    command: str
    timeout_seconds: int
    status: str = "queued"
    requested_by: str = "server"
    created_at: str = ""

    @classmethod
    def f9(cls, pl: dict[str, Any]) -> C9:
        return cls(
            command_id=str(pl["command_id"]),
            agent_id=str(pl["agent_id"]),
            command=str(pl["command"]),
            timeout_seconds=int(pl.get("timeout_seconds", 60)),
            status=str(pl.get("status", "queued")),
            requested_by=str(pl.get("requested_by", "server")),
            created_at=str(pl.get("created_at", "")),
        )


@dataclass
class R9:
    exit_code: int
    stdout: str = ""
    stderr: str = ""


class E9(RuntimeError):
    def __init__(self, code: int, body: str) -> None:
        super().__init__(f"HTTP {code}: {body}")
        self.code = code
        self.body = body


def e9(cmd: C9) -> R9:
    try:
        comp = subprocess.run(
            cmd.command,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
            timeout=cmd.timeout_seconds,
        )
        return R9(exit_code=comp.returncode, stdout=comp.stdout, stderr=comp.stderr)
    except subprocess.TimeoutExpired as ex:
        so = ex.stdout if isinstance(ex.stdout, str) else (ex.stdout.decode() if ex.stdout else "")
        se = ex.stderr if isinstance(ex.stderr, str) else (ex.stderr.decode() if ex.stderr else "")
        se = f"{se}\nTimed out after {cmd.timeout_seconds} seconds".strip()
        return R9(exit_code=124, stdout=so, stderr=se)


class A9:
    def __init__(
        self,
        url: str,
        aid: str,
        sec: str,
        ctx: ssl.SSLContext,
        to: float,
        dn: str | None,
        caps: list[str],
        meta: dict[str, Any],
        pi: float,
    ) -> None:
        self.u = url.rstrip("/")
        self.aid = aid
        self.sec = sec
        self.ctx = ctx
        self.to = to
        self.dn = dn
        self.caps = caps
        self.meta = meta
        self.pi = pi

    def _r(self, meth: str, path: str, pl: dict[str, Any] | None = None) -> dict[str, Any]:
        body = b""
        hd: dict[str, str] = {}
        if pl is not None:
            body = json.dumps(pl).encode("utf-8")
            hd["Content-Type"] = "application/json"
        hd.update(b9h(self.sec, meth, path, self.aid, body))
        req = urllib.request.Request(
            url=f"{self.u}{path}",
            data=body if meth.upper() != "GET" else None,
            headers=hd,
            method=meth.upper(),
        )
        try:
            with urllib.request.urlopen(req, timeout=self.to, context=self.ctx) as resp:
                raw = resp.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as ex:
            bt = ex.read().decode("utf-8", errors="replace")
            raise E9(ex.code, bt) from ex

    def reg(self) -> None:
        self._r(
            "POST",
            "/agents/register",
            {
                "agent_id": self.aid,
                "display_name": self.dn,
                "capabilities": self.caps,
                "metadata": self.meta,
            },
        )

    def l9(self) -> C9 | None:
        try:
            pl = self._r("POST", f"/agents/{self.aid}/commands/lease")
        except E9 as ex:
            if ex.code == 404:
                self.reg()
                return None
            raise
        cmd = pl.get("command")
        return C9.f9(cmd) if cmd else None

    def s9(self, cid: str, res: R9) -> None:
        self._r("POST", f"/commands/{cid}/result", asdict(res))

    def run(self, once: bool = False) -> int:
        self.reg()
        while True:
            cmd = self.l9()
            if cmd is None:
                if once:
                    return 0
                time.sleep(self.pi)
                continue
            res = e9(cmd)
            self.s9(cmd.command_id, res)
            if once:
                return 0


def p9(items: list[str]) -> dict[str, Any]:
    m: dict[str, Any] = {}
    for it in items:
        k, _, v = it.partition("=")
        if not k or not _:
            raise ValueError(f"Invalid metadata: {it}")
        m[k] = v
    return m


def b9(ca: str | None, inc: bool) -> ssl.SSLContext:
    if inc:
        return ssl._create_unverified_context()
    if ca:
        return ssl.create_default_context(cafile=ca)
    return ssl.create_default_context()


resolve_shared_secret = r3s
sign_request = s9n
build_auth_headers = b9h
CommandRecord = C9
CommandResultUpdate = R9
ApiError = E9
execute_command = e9
AgentRunner = A9
parse_metadata = p9
build_ssl_context = b9


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--server-url", default=os.getenv(_d("TVRMU19ERU1PX1NFUlZFUl9VUkw="), "http://127.0.0.1:8000"))
    p.add_argument("--agent-id", default=os.getenv(_d("TVRMU19ERU1PX0FHRU5UX0lE"), "agent-1"))
    p.add_argument("--display-name", default=os.getenv(_d("TVRMU19ERU1PX0RJU1BMQVlfTkFNRQ=="), "Demo Agent"))
    p.add_argument("--capability", action="append", default=["shell"])
    p.add_argument("--metadata", action="append", default=[])
    p.add_argument("--shared-secret", default=os.getenv(_d("TVRMU19ERU1PX1NIQVJFRF9TRUNSRVQ="), "demo-secret"))
    p.add_argument("--ca-certs")
    p.add_argument("--insecure", action="store_true")
    p.add_argument("--poll-interval", type=float, default=float(os.getenv(_d("TVRMU19ERU1PX1BPTExfSU5URVJWQUw="), "5")))
    p.add_argument(
        "--request-timeout",
        type=float,
        default=float(os.getenv(_d("TVRMU19ERU1PX1JFUVVFU1RfVElNRU9VVA=="), "10")),
    )
    p.add_argument("--once", action="store_true")

    a = p.parse_args()
    meta = p9(a.metadata)
    runner = A9(
        url=a.server_url,
        aid=a.agent_id,
        sec=r3s(a.shared_secret),
        ctx=b9(a.ca_certs, a.insecure),
        to=a.request_timeout,
        dn=a.display_name,
        caps=list(a.capability),
        meta=meta,
        pi=a.poll_interval,
    )
    raise SystemExit(runner.run(once=a.once))


if __name__ == "__main__":
    main()
