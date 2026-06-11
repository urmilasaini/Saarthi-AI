"""ADK-powered ask agent. Drop-in replacement for the manual tool-calling loop.

Uses Google ADK 2.x with InMemoryRunner (sync) so the existing FastAPI SSE
endpoints need no changes. The MCP toolset connects to MongoDB Atlas and gives
Gemini read-only find/aggregate access to the Saarthi database.
"""

import logging
import os
import shutil
import uuid
import asyncio
import inspect
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from google.genai import types as genai_types

from app import config
from app.agents.prompts import ASK_AGENT_SYSTEM
from app.tools import geocode, traffic, weather, festivals, events, advisories
from app.history import get_route_history, get_route_patterns
from app.providers import llm

logger = logging.getLogger("saarthi.adk")
TZ = ZoneInfo(config.TIMEZONE)

# ADK reads GOOGLE_API_KEY; keep it aligned with the same key the app uses.
_key = config.gemini_key()
if _key:
    os.environ["GOOGLE_API_KEY"] = _key

# ADK defaults to Vertex AI when GOOGLE_CLOUD_PROJECT is set; force developer API.
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "0")


def _ensure_runner_session(runner: InMemoryRunner, user_id: str, session_id: str):
    """Create the ADK session before runner.run() looks it up."""
    create_session = runner.session_service.create_session
    result = create_session(
        app_name=runner.app_name,
        user_id=user_id,
        session_id=session_id,
    )
    if inspect.isawaitable(result):
        return asyncio.run(result)
    return result


def _build_agent() -> LlmAgent:
    """Create the ADK agent. Built fresh per request — MCP server restarts each time."""
    tools: list = [
        geocode.geocode_place,
        traffic.get_route,
        traffic.compare_departures,
        weather.get_weather,
        festivals.get_festivals,
        events.get_events,
        advisories.get_police_advisories,
        get_route_history,
        get_route_patterns,
    ]

    uri = config.mongodb_mcp_uri()
    if uri:
        command = config.mongodb_mcp_command()
        if not shutil.which(command):
            logger.warning(
                "MongoDB MCP command %r was not found; continuing without MCP tools. "
                "Install Node.js 22.13+ for npx, or set MONGODB_MCP_COMMAND.",
                command,
            )
        else:
            mcp_env = os.environ.copy()
            mcp_env.update(
                {
                    "MDB_MCP_CONNECTION_STRING": uri,
                    "MDB_MCP_TELEMETRY": "disabled",
                    "MDB_MCP_LOGGERS": "stderr",
                }
            )
            if config.mongodb_mcp_read_only():
                mcp_env["MDB_MCP_READ_ONLY"] = "true"

            tools.append(
                MCPToolset(
                    connection_params=StdioConnectionParams(
                        server_params=StdioServerParameters(
                            command=command,
                            args=config.mongodb_mcp_args(),
                            env=mcp_env,
                        )
                    ),
                    # Expose the read/metadata tools Saarthi needs for commute history Q&A.
                    tool_filter=[
                        "find",
                        "aggregate",
                        "count",
                        "list-databases",
                        "list-collections",
                        "collection-schema",
                    ],
                )
            )
    else:
        logger.warning("MONGODB_URI not set — MongoDB MCP tools unavailable")

    return LlmAgent(
        model=config.GEMINI_MODELS[0],
        name="saarthi_ask_agent",
        instruction=ASK_AGENT_SYSTEM,
        tools=tools,
    )


def _fallback_answer(question: str, full_question: str, error: Exception | str | None = None):
    """Use the app's normal LLM fallback chain when ADK/MCP has a bad day."""
    today = datetime.now(TZ).date()
    tool_context = {}
    for label, day in (("today", today), ("tomorrow", today + timedelta(days=1))):
        try:
            tool_context[f"festivals_{label}"] = festivals.get_festivals(day.isoformat())
            tool_context[f"events_{label}"] = events.get_events(day.isoformat())
        except Exception as tool_error:
            tool_context[f"{label}_lookup_error"] = str(tool_error)

    if error:
        logger.warning("Falling back from ADK Ask agent: %s", error)

    result = llm.chat(
        [
            {"role": "system", "content": ASK_AGENT_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"{full_question}\n\n"
                    "ADK/MCP was unavailable or returned no text. "
                    "Use this limited fallback context if relevant, and be clear "
                    "about anything you could not verify:\n"
                    f"{json.dumps(tool_context, default=str)}"
                ),
            },
        ],
        temperature=0.2,
    )
    text = (result.get("text") or "").strip()
    if not text:
        text = "I could not get a reliable answer from the model. Please try again in a minute."
    return {
        "type": "answer",
        "text": text,
        "provider": f"{result.get('provider', 'llm')}-fallback",
        "steps": [f"fallback_after_adk({question[:80]!r})"],
    }


def agent_ask_stream_adk(question: str, history: list | None = None):
    """Sync generator yielding the same event dicts as the original agent_ask_stream.

    Yields {"type": "tool", "name", "args"} for each tool call, then
    {"type": "answer", "text", "provider", "steps"}.
    Falls back to an error event on any ADK failure.
    """
    now = datetime.now(TZ)
    context_line = f"(Current date/time in Lucknow: {now.strftime('%A %Y-%m-%d %H:%M')})"

    if history:
        prior = "\n".join(
            f"{t['role'].upper()}: {str(t.get('content', ''))[:500]}"
            for t in (history or [])[-8:]
        )
        full_question = f"Prior conversation:\n{prior}\n\nNew question: {context_line}\n\n{question}"
    else:
        full_question = f"{context_line}\n\n{question}"

    try:
        agent = _build_agent()
        runner = InMemoryRunner(agent=agent)
        user_id = "web"
        session_id = str(uuid.uuid4())
        _ensure_runner_session(runner, user_id, session_id)

        user_message = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=full_question)],
        )

        steps: list[str] = []
        final_text = ""

        for event in runner.run(
            user_id=user_id,
            session_id=session_id,
            new_message=user_message,
        ):
            # Yield tool-call events so the frontend can show the thinking steps
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "function_call") and part.function_call:
                        name = part.function_call.name
                        args = dict(part.function_call.args) if part.function_call.args else {}
                        steps.append(f"{name}({args})")
                        yield {"type": "tool", "name": name, "args": args}

            if event.is_final_response():
                if event.content and event.content.parts:
                    final_text = "".join(
                        getattr(part, "text", "") or ""
                        for part in event.content.parts
                    ).strip()

        if not final_text:
            yield _fallback_answer(
                question,
                full_question,
                "ADK completed without a final text response",
            )
            return

        yield {
            "type": "answer",
            "text": final_text,
            "provider": "gemini-adk",
            "steps": steps,
        }

    except Exception as error:
        logger.error("ADK agent error: %s", error, exc_info=True)
        try:
            yield _fallback_answer(question, full_question, error)
        except Exception as fallback_error:
            logger.error("Fallback Ask agent error: %s", fallback_error, exc_info=True)
            yield {"type": "error", "message": str(fallback_error)}
