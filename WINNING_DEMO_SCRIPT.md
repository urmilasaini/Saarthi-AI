# Saarthi AI Winning Demo Script

## Core Pitch

Saarthi AI is a proactive commute-planning agent for Lucknow. It does not just answer "how long will this route take?" It decides when you should leave, checks hidden local risks, remembers your past commutes in MongoDB, and uses MongoDB MCP so the chat agent can reason over real commute history.

The winning idea:

> Navigation apps react to traffic. Saarthi acts before the delay happens.

---

## 3-Minute Demo Structure

### 0:00-0:20 - Hook

Show the homepage or map screen.

Say:

> In Lucknow, traffic is not only about cars. A normal commute can be delayed by rain, Bada Mangal bhandaras, Charbagh station rush, Ekana match traffic, or sudden police diversions. Google Maps tells you what is happening now. Saarthi tells you when to leave before you get late.

Goal:

- Make the problem feel real.
- Show that this is not a generic chatbot.

---

### 0:20-0:55 - Enter A Real Commute

Use this demo input:

```text
From: Gomti Nagar
To: Hazratganj
Arrive by: 9:30 AM
Mode: car
```

Click the planning button.

Say:

> Saarthi now geocodes the locations, simulates multiple future departure times, checks weather, festivals, public events, and advisories, then computes a deterministic risk score.

Point out:

- Live progress steps
- Route map
- ETA curve
- Risk score
- Recommended leave-by time

Goal:

- Show multi-step agent behavior.
- Show tool use and planning.

---

### 0:55-1:30 - Explain The Smartness

When the result appears, focus on the risk score and departure recommendation.

Say:

> The key difference is that Saarthi does not ask the LLM to guess. It first gathers real signals. Traffic delay, rain, festivals, events, and advisories feed into a transparent 0-100 risk score. Gemini then explains the result in plain language.

Point out:

- Risk score
- Factors list
- Tips
- ETA/departure curve

Goal:

- Make it clear the system is engineered, not just prompted.

---

### 1:30-2:05 - Ask The Agent

Open Ask Saarthi chat.

Ask:

```text
Any festival tomorrow near Hazratganj?
```

Say:

> Now we move from planning to agentic follow-up. Ask Saarthi can call tools, check local festival context, and explain why that matters for the commute.

If the answer mentions local event/festival context, say:

> This is local intelligence. The agent is not only routing; it understands Lucknow-specific risks.

Goal:

- Show natural language follow-up.
- Show city-specific intelligence.

---

### 2:05-2:35 - MongoDB MCP Partner Moment

Show README or terminal smoke test output if available:

```bash
python check_chatbot_mcp.py --mcp-only
```

Expected proof:

```text
MongoDB ping OK
MCP OK, tools found: aggregate, find, list-collections
PASS: MCP is available and required MongoDB tools are listed.
```

Say:

> MongoDB is not just a database here. Saarthi stores commute outcomes in MongoDB Atlas, then uses MongoDB MCP tools like find and aggregate so the agent can answer questions about real commute history.

Then say:

> For example, after enough saved plans, the user can ask: Which day is worst for my Charbagh commute? The answer comes from MongoDB history, not hallucinated memory.

Goal:

- Make the partner integration impossible to miss.
- Show MCP is meaningful and testable.

---

### 2:35-2:55 - Reliability And Proof

Show test command or README Quality Proof section.

Say:

> We also built this for demo reliability. The project has 121 mocked tests, strict MCP smoke checks, API caching, fallback LLM providers, and clean error handling for live service failures.

Show:

```bash
python -m pytest tests -q
```

Expected:

```text
121 passed
```

Goal:

- Convince judges this is not a fragile prototype.

---

### 2:55-3:00 - Closing Line

Say:

> Saarthi is a commute companion that thinks ahead: it predicts risk, acts with tools, remembers history, and uses MongoDB MCP to turn stored trips into useful decisions.

End on the map/chat UI.

---

## Exact Video Recording Checklist

Before recording:

1. Start the app:

```bash
uvicorn main:app --reload
```

2. Verify tests:

```bash
python -m pytest tests -q
```

3. Verify MCP:

```bash
python check_chatbot_mcp.py --mcp-only
```

4. Open:

```text
http://127.0.0.1:8000
```

5. Keep these tabs/windows ready:

- App UI
- Terminal with test output
- Terminal with MCP smoke output
- README Quality Proof section

---

## Best Demo Questions

Use these in the chat:

```text
Any festival tomorrow near Hazratganj?
```

```text
What if I leave 30 minutes later?
```

```text
Which day is worst for my Charbagh commute?
```

```text
Is rain likely to affect this route today?
```

---

## Judge-Focused Talking Points

Use these phrases naturally:

- "This is proactive, not reactive."
- "The LLM explains; the system verifies."
- "MongoDB is the agent's memory layer."
- "MongoDB MCP gives the agent query tools over real commute history."
- "The risk score is deterministic and auditable."
- "The app is city-specific, not a generic route wrapper."
- "The demo is backed by tests and smoke checks."

---

## What Makes This A Winning Idea

### Real-world pain

Late arrivals are not caused only by traffic. They are caused by hidden local context. Saarthi solves that practical daily problem.

### Strong agent behavior

The system plans, calls tools, compares options, stores results, and answers follow-up questions.

### Meaningful MongoDB integration

MongoDB stores memory, powers TTL caching, and is exposed through MCP for agentic querying.

### Good demo clarity

Judges can see the full loop:

```text
plan -> simulate -> score -> explain -> store -> ask -> query memory
```

### Built with reliability

Tests, fallback providers, caching, and MCP smoke checks reduce demo risk.

---

## Backup Plan If Live APIs Fail

If traffic/weather/event APIs fail during recording:

1. Show the error handling in the UI.
2. Say:

> Live APIs fail in real life, so Saarthi is built to degrade safely. The app keeps the user informed instead of crashing.

3. Show the test output and MCP smoke test.
4. Use README architecture to explain the intended flow.

---

## Short Devpost Description

Saarthi AI is a proactive commute-planning agent for Lucknow, India. It simulates future departure windows, checks traffic, weather, festivals, events, and advisories, computes an auditable risk score, and uses Gemini to explain the best leave-by time. MongoDB Atlas stores commute history and TTL cache data, while MongoDB MCP gives the Ask Saarthi agent direct tools to query saved commute patterns. The result is a local, memory-backed commute companion that acts before the delay happens.

---

## One-Line Submission Tagline

Saarthi AI: the commute agent that predicts delay before you leave and remembers every trip through MongoDB MCP.
