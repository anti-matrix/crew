"""The supervisor — the deterministic round loop.

Replaces the turn-based native subagent tree with an explicit state machine that
owns the graph, schedules parallelism, and enforces termination rules in code.

Round shape:

    interpret (alpha) ──► plan (alpha <─► omega handshake)
       ──► refine (omega + benjamin preflight, user-answered)
       ──► dispatch (bureaucrat ──► task graph)
       ──► execute (workers in dependency-ordered parallel waves)
       ──► review (peer-reviewer)
       ──► audit (escribe + benjamin loop, quiescence-detected)
       ──► report (benjamin)
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from .agent import Agent
from . import log
from .opencode import OpenCode
from .roles import BUDGETS, ROLES
from .scribe import Scribe
from .types import AgentName, AGENTS, Message
from .user_channel import Asked, UserChannel


def _as_dict(v: Any) -> dict | None:
    return v if isinstance(v, dict) else None


class Supervisor:
    def __init__(self, cwd: str, interactive: bool = True) -> None:
        self.cwd = cwd
        self.scribe = Scribe(cwd)
        self.user = UserChannel(interactive)
        self.agents: dict[AgentName, Agent] = {}
        self.bus: dict[str, list[Message]] = {}

    # -- lifecycle -----------------------------------------------------------

    async def spawn_all(self, oc: OpenCode) -> None:
        for name in AGENTS:
            a = await Agent.spawn(oc, name, ROLES[name])
            self.agents[name] = a
            log.info(f"spawned {name} (session {a.session_id})")

    def get(self, name: AgentName) -> Agent:
        return self.agents[name]

    async def run(self, goal: str) -> dict:
        log.section("ROUND START")
        self.scribe.ensure_dir()
        self.scribe.append(
            f"\n## Round {time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())}\n"
        )

        plan = await self.plan(goal)
        if plan is None:
            return {"status": "aborted", "reason": "no plan"}

        plan = await self.refine(plan)

        tasks = await self.dispatch(plan)
        if not tasks:
            log.warn("bureaucrat produced no tasks")
            return {"status": "aborted", "reason": "no tasks"}

        results = await self.execute(tasks)

        review_flags = await self.review(plan, results)

        audit = await self.audit(plan, results, review_flags)

        report = await self.final_report(goal, plan, tasks, results, review_flags, audit)

        self._print_report(report)
        return {"status": "done", "report": report}

    # -- phase 1: interpret + plan handshake ---------------------------------

    async def plan(self, goal: str) -> str | None:
        alpha = self.get("alpha")
        omega = self.get("omega")

        interp = await alpha.send(
            f'The user gave this request:\n\n"""{goal}"""\n\n'
            "Interpret it: refine the goal, state the scope, list constraints and "
            "assumptions, and raise any clarifying questions you genuinely need "
            "answered before work starts (empty array if none). Reply with JSON only.",
            json_out=True,
        )
        d = _as_dict(interp.structured) or {}
        questions = d.get("questions") or []

        context: dict[str, Any] = {
            "answers": [],
            "assumptions": d.get("assumptions") or [],
        }

        if questions:
            log.agent("alpha", f"asking {len(questions)} clarifying question(s) upfront")
            asked = await self._ask_user(
                [
                    {"question": (q.get("question") or "") + (f" ({q['why']})" if q.get("why") else ""),
                     "requester": "alpha"}
                    for q in questions
                    if isinstance(q, dict) and q.get("question")
                ]
            )
            context["answers"] = [a.__dict__ for a in asked]

        goal_line = d.get("goal") or goal
        last_spec = ""

        for _ in range(BUDGETS.plan_cycles):
            prop = await omega.send(
                f'Produce a detailed, self-contained spec for this goal:\n\n"""{goal_line}"""\n\n'
                f"Context: constraints={d.get('constraints') or []}, "
                f"assumptions={context['assumptions']}, "
                f"user answers={context['answers']}"
                + (f"\nAlpha's prior objections to address: {context['objections']}"
                   if context.get("objections") else "")
                + "\n\nThe spec must be executable by Bureaucrat and the workers in one pass. "
                "Reply with JSON only.",
                json_out=True,
            )
            pd = _as_dict(prop.structured)
            if not pd:
                continue
            last_spec = pd.get("spec") or ""

            verdict = await alpha.send(
                f'Omega proposed this plan:\n\n"""{last_spec}"""\n\n'
                "Return a verdict: accept, object (with reasons), or ask_user (with one "
                "specific question). Reply with JSON only.",
                json_out=True,
            )
            vd = _as_dict(verdict.structured)
            if not vd:
                continue

            v = vd.get("verdict")
            if v == "accept":
                log.agent("alpha", "accepted the plan")
                return last_spec
            if v == "ask_user" and vd.get("question"):
                asked = await self._ask_user([{"question": vd["question"], "requester": "alpha"}])
                context["answers"].extend(a.__dict__ for a in asked)
            elif v == "object":
                context["objections"] = vd.get("reasons") or "unspecified objection"
                log.agent("alpha", f"objected: {context['objections'][:120]}")

        log.warn("alpha and omega did not converge on a plan")
        await self._ask_user([
            {"question": "The crew couldn't converge on a plan. Give direction, or type 'proceed'.",
             "requester": "alpha"}
        ])
        return last_spec or goal_line

    # -- phase 2: refine -------------------------------------------

    async def refine(self, plan: str) -> str:
        benjamin = self.get("benjamin")
        omega = self.get("omega")

        pre = await benjamin.send(
            f'Before the crew builds anything, review this plan and find what would embarrass us later:\n\n"""{plan}"""\n\n'
            "Flag gaps, ambiguities, or risky assumptions. If there are details only the user can "
            "decide, raise them as questions (the user answers before we build). Reply with JSON only.",
            json_out=True,
        )
        pd = _as_dict(pre.structured) or {}
        flags = pd.get("flags") or []
        questions = pd.get("questions") or []
        ready = pd.get("ready", True)

        answers: list[Asked] = []
        if questions:
            answers = await self._ask_user([
                {"question": q.get("question") or "", "requester": "benjamin"}
                for q in questions if isinstance(q, dict) and q.get("question")
            ])

        if ready and not flags:
            log.agent("benjamin", "preflight: no flags, ready to build")
            return plan

        if flags:
            revised = await omega.send(
                f'Revise this spec to address the following review flags and user answers:\n\n'
                f'SPEC:\n"""{plan}"""\n\n'
                f'FLAGS:\n' + "\n".join(f"- [{f.get('severity')}] {f.get('subject')}: {f.get('detail')}" for f in flags)
                + f"\n\nUSER ANSWERS:\n{[a.__dict__ for a in answers]}\n\n"
                "Return only the revised spec text.",
            )
            return revised.text or plan
        return plan

    # -- phase 3: dispatch -----------------------------------------

    async def dispatch(self, plan: str) -> list[dict]:
        bureaucrat = self.get("bureaucrat")
        reply = await bureaucrat.send(
            f'Turn this spec into the fewest, most focused tasks that fully cover it, with dependencies:\n\n"""{plan}"""\n\n'
            "Choose a worker per task: academic (research/read), amodei (implement/edit), "
            "peer-reviewer (review). Amodei is the only writer. Reply with JSON only.",
            json_out=True,
        )
        d = _as_dict(reply.structured) or {}
        tasks = d.get("tasks") or []
        return [t for t in tasks if isinstance(t, dict)]

    # -- phase 4: execute workers in parallel waves --------------------------

    async def execute(self, tasks: list[dict]) -> list[dict]:
        done: set[str] = set()
        results: list[dict] = []
        remaining = list(tasks)

        while remaining:
            wave = [
                t for t in remaining
                if all(d in done for d in (t.get("dependsOn") or []))
            ]
            if not wave:
                log.warn("unresolvable task dependencies; aborting remaining tasks")
                break

            log.section(f"EXECUTE ({len(wave)} in parallel)")
            wave_results = await asyncio.gather(*(self._run_task(t) for t in wave))
            for r in wave_results:
                results.append(r)
                done.add(r["taskId"])
            remaining = [t for t in remaining if t.get("id") not in done]

        return results

    async def _run_task(self, task: dict) -> dict:
        worker: AgentName = task.get("worker", "academic")
        agent = self.get(worker)
        tid = task.get("id") or uuid.uuid4().hex[:8]
        log.agent(worker, f"task {tid}: {(task.get('objective') or '')[:80]}")

        brief_lines = [
            f"You are assigned one task in this project (cwd: {self.cwd}).",
            "",
            f"OBJECTIVE:\n{task.get('objective')}",
        ]
        files = task.get("files") or []
        if files:
            brief_lines.append("\nFILES/AREAS TO TOUCH:\n- " + "\n- ".join(files))
        if task.get("constraints"):
            brief_lines.append(f"\nCONSTRAINTS:\n{task['constraints']}")
        if task.get("done"):
            brief_lines.append(f"\nDEFINITION OF DONE:\n{task['done']}")
        brief_lines.append(
            "\nWhen finished, report exactly what you did, what you changed, and how you "
            "verified it. Be concise."
        )

        reply = await agent.send("\n".join(brief_lines))

        result = {
            "taskId": tid,
            "worker": worker,
            "status": "failed" if reply.error else "ok",
            "summary": reply.error or reply.text,
        }
        self._record(
            Message(
                id=uuid.uuid4().hex,
                type="result",
                from_=worker,
                to="orchestrator",
                payload=result,
            )
        )
        return result

    # -- phase 5: peer review --------------------------------------

    async def review(self, plan: str, results: list[dict]) -> list[dict]:
        amodei_out = [r["summary"] for r in results if r.get("worker") == "amodei" and r.get("status") == "ok"]
        if not amodei_out:
            return []

        reviewer = self.get("peer-reviewer")
        reply = await reviewer.send(
            f'Review the implementation against this spec:\n\n"""{plan}"""\n\n'
            f'Amodei reports:\n"""' + "\n\n".join(amodei_out) + '"""\n\n'
            "Inspect the working tree for correctness, bugs, edge cases, security, and "
            "convention violations. Return a prioritized list of issues. Reply with JSON only.",
            json_out=True,
        )
        d = _as_dict(reply.structured) or {}
        return d.get("flags") or []

    # -- phase 6: audit loop ---------------------------------------

    async def audit(
        self,
        plan: str,
        results: list[dict],
        review_flags: list[dict],
    ) -> dict:
        escribe = self.get("escribe")
        benjamin = self.get("benjamin")

        aggregate: dict[str, Any] = {
            "flags": list(review_flags),
            "questions": [],
            "quiescent": False,
        }

        for _ in range(BUDGETS.audit_cycles):
            tail = self.scribe.read_transcript()
            prior = self.scribe.read_context()
            summary = await escribe.send(
                "Update the concise current-state summary from the latest activity below. "
                "Match a terse 'state / last done / pending / key decisions' shape. "
                "Write ONLY the summary text (it will be saved to escribe_context.md).\n\n"
                f"PRIOR SUMMARY:\n{prior or '(none)'}\n\n"
                f"LATEST ACTIVITY:\n{tail}",
            )
            if summary.text and not summary.error:
                self.scribe.write_context(summary.text)

            check = await benjamin.send(
                "Read the current-state summary and tell me, plainly, whether the work is sound. "
                "Flag anything that diverges from the plan or needs a human decision. "
                "If nothing new to flag, set quiescent=true. Reply with JSON only.\n\n"
                f'PLAN:\n"""{plan}"""\n\n'
                f'SUMMARY:\n"""{summary.text or prior}"""',
                json_out=True,
            )
            d = _as_dict(check.structured) or {}
            aggregate["flags"].extend(d.get("flags") or [])
            aggregate["questions"].extend(d.get("questions") or [])
            if d.get("quiescent"):
                aggregate["quiescent"] = True
                break

        return aggregate

    # -- phase 7: report -------------------------------------------

    async def final_report(
        self,
        goal: str,
        plan: str,
        tasks: list[dict],
        results: list[dict],
        review_flags: list[dict],
        audit: dict,
    ) -> dict:
        benjamin = self.get("benjamin")
        reply = await benjamin.send(
            "Write the closing report to the user for this round. Reply with JSON only.\n\n"
            f"GOAL: {goal}\n\nPLAN:\n\"\"\"{plan}\"\"\"\n\n"
            f"TASKS: {', '.join(str(t.get('id')) + '(' + str(t.get('worker')) + ')' for t in tasks)}\n\n"
            f"RESULTS:\n" + "\n".join(f"- {r['taskId']} [{r['status']}] {r['summary'][:200]}"
                                     for r in results)
            + "\n\n"
            f"REVIEW FLAGS:\n" + ("\n".join(f"- [{f.get('severity')}] {f.get('subject')}" for f in review_flags) or "(none)")
            + "\n\n"
            f"AUDIT FLAGS:\n" + ("\n".join(f"- [{f.get('severity')}] {f.get('subject')}: {f.get('detail')}" for f in audit.get('flags', [])) or "(none)"),
            json_out=True,
        )
        d = _as_dict(reply.structured) or {}
        return {
            "done": d.get("done") or [r["taskId"] for r in results if r.get("status") == "ok"],
            "pending": d.get("pending") or [],
            "issues": d.get("issues") or [],
            "questionsForUser": d.get("questionsForUser") or [],
            "nextStep": d.get("nextStep") or "",
        }

    # -- helpers -----------------------------------------------------

    def _record(self, msg: Message) -> None:
        self.bus.setdefault(msg.to, []).append(msg)
        self.scribe.record(msg)

    async def _ask_user(self, questions: list[dict]) -> list[Asked]:
        if not questions:
            return []
        for q in questions:
            self.user.add(q["question"], q["requester"])
        asked = await self.user.ask_all()
        for a in asked:
            self._record(
                Message(
                    id=uuid.uuid4().hex,
                    type="user_answer",
                    from_="user",
                    to="alpha" if a.requester == "alpha" else "benjamin",
                    payload={"question": a.question, "answer": a.answer},
                )
            )
        return asked

    def _print_report(self, r: dict) -> None:
        log.section("REPORT")
        for key, label in (
            ("done", "DONE"),
            ("pending", "PENDING"),
            ("issues", "ISSUES"),
            ("questionsForUser", "QUESTIONS FOR USER"),
        ):
            items = r.get(key) or []
            print(f"{label}:\n" + "\n".join(f"  - {i}" for i in items) or f"{label}: (none)")
        print(f"NEXT STEP: {r.get('nextStep') or '(none)'}")
