"""Three ways to answer a question about an indexed video.

- simple:     transcript only (the classic text RAG baseline)
- multimodal: one hybrid search over speech and on-screen descriptions
- agentic:    the model decides: search speech, search the screen, or look at one frame with a precise question
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import media, timeutil
from .index import Doc, VideoIndex
from .llm import MistralClient

MODES = ("simple", "multimodal", "agentic")

SYSTEM = (
    "You answer questions about one video, using only the evidence provided. Each evidence line starts with "
    "its timestamp. Cite every fact with its timestamp exactly as [mm:ss] or [mm:ss–mm:ss]. If the evidence "
    "does not contain the answer, say that you could not find it in the video rather than guessing. "
    "If the answer requires combining or adding up values from the evidence, do it and show the calculation. "
    "Answer in the language of the question, in 1-4 sentences."
)

AGENT_SYSTEM = SYSTEM + (
    " You can call tools to gather evidence before answering. Speech and the screen often carry different "
    "information: numbers, names, prices and chart values are frequently only shown, not said. Strategy: "
    "(1) in your first step, call search_speech and search_screen together; "
    "(2) only call look_at_frame on a timestamp returned by a search, when its description is too vague; "
    "(3) for a question with several parts, make sure every part is supported, searching again if needed; "
    "(4) stop calling tools as soon as you have the evidence, then answer."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_speech",
            "description": "Search what is said in the video (the transcript). Returns timestamped passages.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "What to look for"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_screen",
            "description": "Search what is shown on screen (slides, text, charts, objects). Returns timestamped descriptions.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "What to look for"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "look_at_frame",
            "description": "Look at the video frame at a given moment and answer a precise visual question about it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timestamp": {"type": "string", "description": "Moment to look at, as mm:ss"},
                    "question": {"type": "string", "description": "What to read or check in the frame"},
                },
                "required": ["timestamp", "question"],
            },
        },
    },
]


@dataclass
class Answer:
    mode: str
    question: str
    answer: str
    citations: list[tuple[float, float]]
    evidence: list[dict]
    trace: list[dict] = field(default_factory=list)
    latency_s: float = 0.0
    llm_calls: int = 0

    def to_dict(self) -> dict:
        return self.__dict__ | {"citations": [list(c) for c in self.citations]}


class _Counted:
    """Per-question view of the client that counts its own calls (safe when questions run concurrently)."""

    def __init__(self, llm: MistralClient):
        self._llm, self.calls = llm, 0

    def chat(self, *a, **kw):
        self.calls += 1
        return self._llm.chat(*a, **kw)

    def embed(self, *a, **kw):
        self.calls += 1
        return self._llm.embed(*a, **kw)

    def describe_image(self, *a, **kw):
        self.calls += 1
        return self._llm.describe_image(*a, **kw)


class Answerer:
    def __init__(self, index: VideoIndex, llm: MistralClient, video: Path, workdir: Path, max_steps: int = 5):
        self.index, self.llm, self.video, self.workdir, self.max_steps = index, llm, video, workdir, max_steps

    def ask(self, question: str, mode: str = "agentic") -> Answer:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        llm = _Counted(self.llm)
        t0 = time.perf_counter()
        result = self._agentic(question, llm) if mode == "agentic" else self._single_shot(question, mode, llm)
        result.latency_s = round(time.perf_counter() - t0, 2)
        result.llm_calls = llm.calls
        return result

    # ── simple / multimodal ─────────────────────────────────────────────────

    def _single_shot(self, question: str, mode: str, llm: _Counted) -> Answer:
        kinds = ("speech",) if mode == "simple" else ("speech", "screen")
        docs = self.index.search(question, llm.embed, k=5 if mode == "simple" else 8, kinds=kinds)
        docs.sort(key=lambda d: d.start)
        evidence = "\n".join(d.evidence() for d in docs) or "(no evidence)"
        msg = llm.chat(
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Evidence:\n{evidence}\n\nQuestion: {question}"},
            ]
        )
        text = (msg.get("content") or "").strip()
        return Answer(mode, question, text, timeutil.citations(text), [_doc_dict(d) for d in docs])

    # ── agentic ─────────────────────────────────────────────────────────────

    def _agentic(self, question: str, llm: _Counted) -> Answer:
        messages: list[dict] = [
            {"role": "system", "content": AGENT_SYSTEM},
            {"role": "user", "content": question},
        ]
        trace: list[dict] = []
        seen: dict[str, dict] = {}
        for step in range(self.max_steps + 1):
            final_turn = step == self.max_steps
            msg = llm.chat(messages, tools=TOOLS, tool_choice="none" if final_turn else "auto")
            calls = msg.get("tool_calls") or []
            if not calls:
                text = (msg.get("content") or "").strip()
                return Answer("agentic", question, text, timeutil.citations(text), list(seen.values()), trace)
            messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
            for call in calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                output, docs = self._run_tool(name, args, llm)
                for d in docs:
                    seen.setdefault(d["id"], d)
                trace.append({"step": step + 1, "tool": name, "args": args, "result": output[:600]})
                messages.append({"role": "tool", "name": name, "content": output, "tool_call_id": call["id"]})
        return Answer("agentic", question, "I could not reach an answer.", [], list(seen.values()), trace)

    def _run_tool(self, name: str, args: dict, llm: _Counted) -> tuple[str, list[dict]]:
        if name in ("search_speech", "search_screen"):
            kind = "speech" if name == "search_speech" else "screen"
            docs = self.index.search(str(args.get("query", "")), llm.embed, k=4, kinds=(kind,))
            docs.sort(key=lambda d: d.start)
            return ("\n".join(d.evidence() for d in docs) or "No results."), [_doc_dict(d) for d in docs]
        if name == "look_at_frame":
            try:
                t = timeutil.parse(args.get("timestamp", "0"))
            except ValueError:
                return "Invalid timestamp, use mm:ss.", []
            path = media.frame_at(self.video, t + 0.5, self.workdir / "looks" / f"t{int(t * 10):06d}.jpg")
            seen = llm.describe_image(path, f"{args.get('question', 'Describe this frame.')} Quote any visible text exactly.")
            doc = Doc(f"look@{t:.0f}", "screen", t, t, seen, frame=None)
            return doc.evidence(), [_doc_dict(doc)]
        return f"Unknown tool {name}.", []


def _doc_dict(d: Doc) -> dict:
    return {"id": d.id, "kind": d.kind, "start": d.start, "end": d.end, "text": d.text, "frame": d.frame}
