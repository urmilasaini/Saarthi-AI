"""Saarthi AI — FastAPI entry point.

Run:  uvicorn main:app --reload
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app import config, netutil
from app.agents import orchestrator
from app.providers import llm
from app.providers.llm import LLMUnavailable
from app.tools import geocode

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("saarthi.api")

BASE_DIR = Path(__file__).resolve().parent
TZ = ZoneInfo(config.TIMEZONE)

PROJECT_CREDITS = {
    "project": "Saarthi AI",
    "event": "Google Cloud Rapid Agent Hackathon",
    "track": "MongoDB Partner Track",
    "copyright": "Copyright (c) 2026 Saksham Pathak, Urmila Saini, Aishrica Dhiman, Sameer Singh",
    "authors": [
        {
            "name": "Saksham Pathak",
            "github": "parthmax2",
            "contributions": [
                "Team lead",
                "UI/UX direction",
                "Frontend experience",
                "Chat UI",
                "Map-focused interaction design",
                "Visual polish",
                "Deployment readiness",
            ],
        },
        {
            "name": "Aishrica Dhiman",
            "github": "aishricadhiman",
            "contributions": [
                "Data analyst work",
                "Commute-pattern analysis",
                "Local data validation",
                "Agentic user-flow support",
                "Ask Saarthi interaction logic",
                "Demo flow and usability testing",
            ],
        },
        {
            "name": "Sameer Singh",
            "github": "sameerfcb",
            "contributions": [
                "Agent knowledge grounding",
                "Lucknow event intelligence",
                "Local commute-risk research",
                "Agent response validation",
                "Test coverage",
                "Demo scenario preparation",
            ],
        },
        {
            "name": "Urmila Saini",
            "github": "urmilasaini",
            "contributions": [
                "Agentic tool orchestration",
                "Traffic/weather/event API wiring",
                "MongoDB MCP setup",
                "Agent memory integration",
                "Docker/runtime support",
                "Smoke-test workflow",
            ],
        },
    ],
    "attribution": "Please preserve author attribution in forks, demos, writeups, and redistributed versions.",
}

app = FastAPI(
    title="Saarthi AI",
    summary="Proactive commute-planning agent for Lucknow.",
    description=(
        "Saarthi AI plans when to leave, explains why, remembers commute history, "
        "and uses MongoDB MCP to reason over stored commute data. Created by "
        "Saksham Pathak, Aishrica Dhiman, Sameer Singh, and Urmila Saini."
    ),
    contact={
        "name": "Saarthi AI Team",
        "url": "https://github.com/parthmax2/saarthi-ai",
    },
    license_info={"name": "MIT", "url": "https://opensource.org/license/mit"},
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Last line of defense: any unexpected bug becomes a clean JSON 500
    with no secrets, instead of a stack trace in the user's face."""
    logger.exception("Unhandled error on %s: %s", request.url.path, netutil.scrub_secrets(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": f"Something went wrong on our side: {netutil.friendly_error(exc)}"},
    )


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"llm_available": llm.available(), "credits": PROJECT_CREDITS},
    )


@app.get("/credits")
def credits():
    return PROJECT_CREDITS


@app.get("/api/autocomplete")
def autocomplete(q: str = Query(..., min_length=2)):
    # Suggestions are a convenience — any failure is just an empty dropdown.
    try:
        return {"suggestions": geocode.autocomplete_place(q)}
    except Exception as error:
        logger.warning("Autocomplete failed for %r: %s", q, netutil.scrub_secrets(error))
        return {"suggestions": []}


def _sse_error(message):
    """A single-error SSE stream for invalid input — the frontend shows it
    in the normal error box instead of a broken connection."""

    def stream():
        yield f"data: {json.dumps({'type': 'error', 'message': message})}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


@app.get("/api/plan/stream")
def plan_stream(
    from_place: str = Query(..., alias="from", min_length=2),
    to_place: str = Query(..., alias="to", min_length=2),
    arrive_by: str = Query(..., description="ISO datetime, e.g. 2026-06-12T09:30"),
    mode: str = Query("car"),
    from_lat: float = Query(None),
    from_lon: float = Query(None),
    to_lat: float = Query(None),
    to_lon: float = Query(None),
):
    if mode not in ("car", "bus", "truck", "taxi", "motorcycle"):
        raise HTTPException(status_code=422, detail="Invalid travel mode")

    # --- validate the deadline up front with friendly messages -------------
    try:
        deadline = datetime.fromisoformat(arrive_by)
    except ValueError:
        return _sse_error("That arrival time looks invalid — please use the date-time picker.")
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=TZ)
    now = datetime.now(TZ)
    if deadline <= now:
        return _sse_error("Your arrival deadline is in the past — pick a future time.")
    if deadline > now + timedelta(days=7):
        return _sse_error("That's more than a week away — forecasts aren't reliable that far out. Pick a closer date.")

    origin_coords = (from_lat, from_lon) if from_lat is not None and from_lon is not None else None
    dest_coords = (to_lat, to_lon) if to_lat is not None and to_lon is not None else None

    def event_stream():
        try:
            for event in orchestrator.run_plan(
                from_place, to_place, arrive_by, mode,
                origin_coords=origin_coords, dest_coords=dest_coords,
            ):
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception as error:  # never leave the browser hanging
            logger.exception("Plan stream crashed: %s", netutil.scrub_secrets(error))
            payload = {"type": "error", "message": netutil.friendly_error(error)}
            yield f"data: {json.dumps(payload)}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/ask/stream")
def ask_stream(
    question: str = Query(..., min_length=2, max_length=600),
    history: str = Query("[]", description="JSON list of prior chat turns"),
):
    if not llm.available():
        raise HTTPException(
            status_code=503,
            detail="No LLM configured. Add GEMINI_API_KEY or GROQ_API_KEY to .env",
        )
    try:
        history_list = json.loads(history)
        if not isinstance(history_list, list):
            history_list = []
    except json.JSONDecodeError:
        history_list = []

    def event_stream():
        try:
            for event in orchestrator.agent_ask_stream(question, history_list):
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception as error:
            logger.exception("Ask stream crashed: %s", netutil.scrub_secrets(error))
            payload = {"type": "error", "message": netutil.friendly_error(error)}
            yield f"data: {json.dumps(payload)}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class AskRequest(BaseModel):
    question: str


@app.post("/api/ask")
def ask(body: AskRequest):
    if not llm.available():
        raise HTTPException(
            status_code=503,
            detail="No LLM configured. Add GEMINI_API_KEY or GROQ_API_KEY to .env",
        )
    if not body.question.strip():
        raise HTTPException(status_code=422, detail="Question is empty")
    try:
        return orchestrator.agent_ask(body.question)
    except LLMUnavailable as error:
        raise HTTPException(status_code=503, detail=netutil.friendly_error(error))
    except Exception as error:
        logger.exception("Ask agent crashed: %s", netutil.scrub_secrets(error))
        raise HTTPException(status_code=500, detail=netutil.friendly_error(error))


@app.get("/api/health")
def health():
    return {"status": "ok", "llm_available": llm.available()}
