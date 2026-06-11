"""Smoke-test Ask Saarthi chat and MongoDB MCP.

This is an integration test: it uses your real .env, starts the MongoDB MCP
server, and calls the running FastAPI chat stream.

Run:
    python check_chatbot_mcp.py

Optional:
    python check_chatbot_mcp.py --url http://127.0.0.1:8000
"""

import argparse
import asyncio
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from app import config
from pymongo import MongoClient

if sys.platform.startswith("win") and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


REQUIRED_MCP_TOOLS = {
    "find",
    "aggregate",
    "list-collections",
}


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


def print_step(message: str) -> None:
    print(f"[check] {message}")


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def format_exception(error: BaseException, indent: int = 0) -> str:
    prefix = "  " * indent
    lines = [f"{prefix}{type(error).__name__}: {error}"]
    nested = getattr(error, "exceptions", None)
    if nested:
        for child in nested:
            lines.append(format_exception(child, indent + 1))
    cause = getattr(error, "__cause__", None)
    if cause:
        lines.append(f"{prefix}Caused by:")
        lines.append(format_exception(cause, indent + 1))
    return "\n".join(lines)


def mcp_command() -> str:
    return os.getenv("MONGODB_MCP_COMMAND", "npx").strip() or "npx"


def mcp_args() -> list[str]:
    raw = os.getenv("MONGODB_MCP_ARGS", "-y,mongodb-mcp-server@latest,--readOnly")
    return [part.strip() for part in raw.split(",") if part.strip()]


def _mcp_frame(payload: dict) -> bytes:
    return (json.dumps(payload) + "\n").encode("utf-8")


def _read_mcp_message(stream):
    line = stream.readline()
    if not line:
        raise RuntimeError("MCP server closed stdout")
    return json.loads(line.decode("utf-8"))


def _manual_stdio_list_tools(command: str, args: list[str], env: dict, timeout: int) -> set[str]:
    proc = subprocess.Popen(
        [command, *args],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    messages = queue.Queue()

    def reader():
        try:
            while True:
                messages.put(_read_mcp_message(proc.stdout))
        except Exception as error:
            messages.put(error)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()

    def send(payload):
        proc.stdin.write(_mcp_frame(payload))
        proc.stdin.flush()

    def receive(expected_id=None):
        try:
            while True:
                item = messages.get(timeout=timeout)
                if isinstance(item, Exception):
                    raise item
                if expected_id is None or item.get("id") == expected_id:
                    return item
        except queue.Empty:
            raise TimeoutError("timed out waiting for MCP response")

    try:
        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "saarthi-smoke-test", "version": "1.0"},
                },
            }
        )
        init_response = receive(1)
        if "error" in init_response:
            raise RuntimeError(f"MCP initialize failed: {init_response['error']}")

        send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools_response = receive(2)
        if "error" in tools_response:
            raise RuntimeError(f"MCP tools/list failed: {tools_response['error']}")
        return {tool["name"] for tool in tools_response.get("result", {}).get("tools", [])}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


async def check_mcp_server(timeout: int) -> set[str]:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ModuleNotFoundError as error:
        fail(f"Python MCP SDK is missing: {error}. Run: python -m pip install -r requirements.txt")

    uri = config.mongodb_mcp_uri()
    if not uri:
        fail("MONGODB_URI is not set in .env")

    try:
        MongoClient(uri, serverSelectionTimeoutMS=10000).admin.command("ping")
    except Exception as error:
        fail(f"MongoDB ping failed before MCP startup:\n{format_exception(error)}")
    print_step("MongoDB ping OK")

    command = mcp_command()
    args = mcp_args()
    command_path = shutil.which(command)
    if not command_path:
        fail(
            f"MCP command '{command}' was not found. "
            "Install Node.js 22.13+ for npx, or set MONGODB_MCP_COMMAND."
        )

    env = os.environ.copy()
    env.update(
        {
            "MDB_MCP_CONNECTION_STRING": uri,
            "MDB_MCP_READ_ONLY": os.getenv("MONGODB_MCP_READ_ONLY", "true"),
            "MDB_MCP_TELEMETRY": "disabled",
            "MDB_MCP_LOGGERS": "stderr",
        }
    )

    print_step(f"starting MCP server: {command} {' '.join(args)}")
    server_params = StdioServerParameters(command=command, args=args, env=env)

    async def run_client() -> set[str]:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                return {tool.name for tool in tools.tools}

    try:
        names = await asyncio.wait_for(run_client(), timeout=timeout)
    except Exception as error:
        print_step(f"Python MCP client failed, trying raw stdio probe: {type(error).__name__}")
        try:
            names = _manual_stdio_list_tools(command_path, args, env, timeout)
        except Exception as manual_error:
            fail(
                "MCP server did not initialize/list tools:\n"
                f"Python client:\n{format_exception(error)}\n"
                f"Raw stdio probe:\n{format_exception(manual_error)}"
            )

    missing = REQUIRED_MCP_TOOLS - names
    if missing:
        fail(f"MCP started, but required tools are missing: {sorted(missing)}. Found: {sorted(names)}")

    print_step(f"MCP OK, tools found: {', '.join(sorted(REQUIRED_MCP_TOOLS))}")
    return names


def check_chat_stream(base_url: str, question: str, timeout: int) -> dict:
    params = urllib.parse.urlencode({"question": question, "history": "[]"})
    url = f"{base_url.rstrip('/')}/api/ask/stream?{params}"
    request = urllib.request.Request(url, headers={"Accept": "text/event-stream"})

    print_step(f"calling chat stream: {url}")
    events = []
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload:
                    continue
                data = json.loads(payload)
                events.append(data)
                if data.get("type") == "done":
                    break
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")[:500]
        fail(f"chat endpoint returned HTTP {error.code}: {body}")
    except urllib.error.URLError as error:
        fail(f"could not reach chat endpoint at {base_url}: {error}")
    except Exception as error:
        fail(f"chat stream failed: {error}")

    errors = [event for event in events if event.get("type") == "error"]
    if errors:
        fail(f"chat returned error: {errors[-1].get('message')}")

    answers = [event for event in events if event.get("type") == "answer"]
    if not answers:
        fail("chat stream finished without an answer event")

    answer = answers[-1]
    text = (answer.get("text") or "").strip()
    if not text:
        fail(f"chat answer text is empty. Full answer event: {answer}")

    print_step(f"chat OK via {answer.get('provider', 'unknown')}")
    print("Answer preview:")
    print(text[:600])
    return answer


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Ask Saarthi chat + required MongoDB MCP.")
    parser.add_argument("--url", default=os.getenv("SAARTHI_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--question", default="Any festival tomorrow near Hazratganj?")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--mcp-only", action="store_true", help="Only test MongoDB MCP, not the chat endpoint.")
    args = parser.parse_args()

    load_env_file(Path(".env"))
    load_env_file(Path("code") / ".env")

    if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        fail("GEMINI_API_KEY or GOOGLE_API_KEY is not set in .env")

    asyncio.run(check_mcp_server(args.timeout))
    if args.mcp_only:
        print("PASS: MCP is available and required MongoDB tools are listed.")
    else:
        check_chat_stream(args.url, args.question, args.timeout)
        print("PASS: MCP is available and Ask Saarthi chat returned a non-empty answer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
