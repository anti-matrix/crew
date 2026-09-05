# Crew

Real-time multi-agent orchestrator for opencode, written in **Python**.

It replaces the turn-based, synchronous native subagent tree (Alpha → Omega →
Bureaucrat → workers via the `Task` tool) with **warm, long-lived agent
sessions** driven by a deterministic async supervisor. opencode is just the
agent runtime; Python owns the graph.

## Architecture

```
                         USER
                          │
                          ▼
        ┌─────────────────────────────┐
        │  PRIMARY LANE (co-primaries) │
        │   ALPHA ◄────► OMEGA         │   ← plan handshake, bounded cycles
        └──────────────┬──────────────┘
                       │ spec
                       ▼
                   BUREAUCRAT            ← dispatch plan (structured JSON)
                       │
          ┌────────────┴────────────┐
          ▼            ▼            ▼
      ACADEMIC      AMODEI     PEER-REVIEWER   ← workers, dependency-ordered waves
          └────────────┬────────────┘
                       │
        ┌──────────────┴──────────────┐
        │  PARALLEL AUDIT LANE        │
        │  ESCRIBE (Python copy + LLM)│  ← continuous, feeds back to Alpha/Omega
        │  BENJAMIN (audit/report)    │
        └─────────────────────────────┘
```

Agents don't talk to each other directly. Each is a warm opencode session; they
reply with **typed messages** and the supervisor routes, validates lanes
(`router.py`), schedules parallel waves with `asyncio`, and applies termination
rules (`supervisor.py`). Routing is deterministic code — not an LLM deciding
when to hand off.

## What this fixes over native mode

- **No `subagent_depth` cap** — the graph is flat; Python owns it.
- **Real concurrency** — independent worker tasks run in the same async wave
  (`asyncio.gather`). No threads, no GIL lock contention: agent turns are ~95%
  network wait, which is exactly what `asyncio` is for.
- **No synchronous single-return** — sessions stay warm across turns.
- **Front-loaded user interaction** — Alpha and Benjamin raise clarifying
  questions *before* work starts, batched through the user channel, so you stop
  nitpicking after the fact.
- **Escribe is deterministic** — the faithful record append is pure Python file
  copy (`scribe.py`, no tokens). Only the small rolling summary goes through
  the (free) model, from a bounded diff.

## Install

```bash
cd crew
python -m pip install -e .          # installs httpx dependency
```

## Run

The default flow opens the opencode TUI in your project and hands it an
initial prompt:

```bash
cd crew
python crew.py --cwd "C:\path\to\project"
```

The TUI opens with the crew greeting you; type your request and interact
normally. `--goal` is optional and only pre-seeds the initial prompt:

```bash
python crew.py --cwd "C:\path\to\project" --goal "add a dark mode toggle"
echo "add a dark mode toggle" | python crew.py --cwd "C:\path\to\project"
```

Skip the TUI and run one full orchestrator round headless:

```bash
python crew.py --headless --cwd "C:\path\to\project" --goal "your request"
```

Already have a TUI open (started with `opencode --port 4096`)? Push into it:

```bash
python crew.py --url http://localhost:4096 --goal "your request"
```

Your normal opencode TUI is a separate process — this one reads the same agent
definitions and credentials but shares no sessions or state.

## Configuration

- **Models / lanes / budgets** live in `crew/roles.py`. Point `escribe` at your
  free model there — its only model task is a short summary, so a small context
  window is fine.
- **Permission sandboxing** is inherited from the agent definitions in
  `~/.config/opencode/agent/*.md` (e.g. `academic` can't edit). The supervisor
  doesn't re-open that; tune those `.md` files to tighten fences.

## The crew (unchanged roles)

`alpha` (front door, accepts/rejects) · `omega` (planner) · `bureaucrat`
(dispatcher) · `academic` (research) · `amodei` (implementer, sole writer) ·
`peer-reviewer` (review) · `escribe` (archivist) · `benjamin` (audit/report).

## Files

- `crew/supervisor.py` — the round loop (interpret → plan → refine → dispatch →
  execute → review → audit → report) and termination rules.
- `crew/agent.py` — warm-session wrapper (`spawn` + `send`, JSON fallback).
- `crew/opencode.py` — async HTTP client over `opencode serve`.
- `crew/router.py` — lane table (who may message whom, as code).
- `crew/scribe.py` — deterministic record append + context summary.
- `crew/user_channel.py` — batched `ask_user` (stdin).
- `crew/jsonx.py` — balanced-brace JSON extraction from agent replies.
- `crew/types.py`, `crew/roles.py` — message/enum/role definitions.
