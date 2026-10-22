"""Benchmarks the three answering modes on the demo video.

    python scripts/evaluate.py            # ingest the demo (once), ask the 19 questions in every mode
    python scripts/evaluate.py --rebuild  # re-ingest from scratch

Writes reports/metrics.json and reports/eval.md. API responses are cached in data/cache, so a re-run is free and
reproducible; latencies are only meaningful on the first (uncached) run and are reported from it.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from videorag.answer import MODES, Answerer  # noqa: E402
from videorag.config import settings  # noqa: E402
from videorag.index import VideoIndex  # noqa: E402
from videorag.ingest import ingest  # noqa: E402
from videorag.llm import from_settings  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"
REPORTS = ROOT / "reports"


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace(" ", " ").replace(" ", " ").lower()
    return text.replace("euros", "€").replace("euro", "€")


def correct(answer: str, expected: list[list[str]]) -> bool:
    a = norm(answer)
    return all(any(norm(alt) in a for alt in group) for group in expected)


def overlaps(span: tuple[float, float], window: tuple[float, float], slack: float = 1.5) -> bool:
    return span[0] <= window[1] + slack and span[1] >= window[0] - slack


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()

    video = DEMO / "rooftop-bees.mp4"
    timeline = json.loads((DEMO / "timeline.json").read_text(encoding="utf-8"))
    questions = json.loads((DEMO / "questions.json").read_text(encoding="utf-8"))
    workdir = settings.videos_dir / "demo"
    llm = from_settings(settings)

    if args.rebuild and workdir.exists():
        shutil.rmtree(workdir)
    if not (workdir / "docs.json").exists():
        index = ingest(video, workdir, llm, settings.whisper_model, progress=lambda s, f, m: print(f"  [{f:4.0%}] {m}"))
    else:
        index = VideoIndex.load(workdir)
    manifest = json.loads((workdir / "manifest.json").read_text(encoding="utf-8"))

    answerer = Answerer(index, llm, video, workdir, settings.agent_max_steps)
    rows = []
    for q in questions:
        window = (timeline[q["slide"]]["start"], timeline[q["slide"]]["end"])
        for mode in MODES:
            calls_before = llm.stats["api_calls"]
            ans = answerer.ask(q["question"], mode)
            fresh = llm.stats["api_calls"] > calls_before
            rows.append({
                "id": q["id"], "question": q["question"], "modality": q["modality"], "mode": mode,
                "correct": correct(ans.answer, q["expected"]),
                "cited_right_moment": any(overlaps(c, window) for c in ans.citations),
                "evidence_hit": any(overlaps((e["start"], e["end"]), window, 0.0) for e in ans.evidence),
                "llm_calls": ans.llm_calls,
                "latency_s": ans.latency_s if fresh else None,
                "tools": [t["tool"] for t in ans.trace],
                "answer": ans.answer,
            })
            print(f"{q['id']:>2} {mode:<10} {'OK ' if rows[-1]['correct'] else '-- '} {ans.answer[:90]!r}")

    summary = defaultdict(dict)
    for mode in MODES:
        for group in ("speech", "screen", "both", "all"):
            sel = [r for r in rows if r["mode"] == mode and (group == "all" or r["modality"] == group)]
            lat = [r["latency_s"] for r in sel if r["latency_s"] is not None]
            summary[mode][group] = {
                "n": len(sel),
                "accuracy": round(sum(r["correct"] for r in sel) / len(sel), 3),
                "cited_right_moment": round(sum(r["cited_right_moment"] for r in sel) / len(sel), 3),
                "evidence_hit": round(sum(r["evidence_hit"] for r in sel) / len(sel), 3),
                "avg_llm_calls": round(sum(r["llm_calls"] for r in sel) / len(sel), 2),
                "median_latency_s": sorted(lat)[len(lat) // 2] if lat else None,
            }

    REPORTS.mkdir(exist_ok=True)
    meta = {
        "video_seconds": manifest["duration"], "speech_chunks": manifest["speech_chunks"],
        "keyframes": len(manifest["keyframes"]), "ingest_seconds": manifest["ingest_seconds"],
        "chat_model": settings.chat_model, "vision_model": settings.vision_model,
        "embed_model": settings.embed_model, "whisper_model": settings.whisper_model,
    }
    (REPORTS / "metrics.json").write_text(json.dumps({"meta": meta, "summary": summary, "rows": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    (REPORTS / "eval.md").write_text(render(meta, summary, rows), encoding="utf-8")
    print(f"\nWrote {REPORTS / 'eval.md'}")


def pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def render(meta: dict, summary: dict, rows: list[dict]) -> str:
    lines = [
        "# Evaluation on the demo video",
        "",
        f"Demo: `demo/rooftop-bees.mp4`, {meta['video_seconds']:.0f} s, {meta['speech_chunks']} speech chunks, "
        f"{meta['keyframes']} keyframes. Models: chat `{meta['chat_model']}`, vision `{meta['vision_model']}`, "
        f"embeddings `{meta['embed_model']}`, Whisper `{meta['whisper_model']}` (local, CPU). "
        f"Ingestion took {meta['ingest_seconds']:.0f} s.",
        "",
        "19 questions: 8 answered only by the narration, 8 only by what is on screen, 3 that need both. "
        "An answer is correct when it contains the expected facts; a citation is right when it points inside the "
        "slide where the fact appears.",
        "",
        "## Accuracy by question type",
        "",
        "| Mode | Spoken only (8) | Shown only (8) | Both (3) | **All (19)** | Cited the right moment | LLM calls / question | Median latency |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for mode, s in summary.items():
        lat = s["all"]["median_latency_s"]
        lines.append(
            f"| {mode} | {pct(s['speech']['accuracy'])} | {pct(s['screen']['accuracy'])} | {pct(s['both']['accuracy'])} | "
            f"**{pct(s['all']['accuracy'])}** | {pct(s['all']['cited_right_moment'])} | {s['all']['avg_llm_calls']} | "
            f"{f'{lat:.1f} s' if lat is not None else 'n/a'} |"
        )
    lines += ["", "## Every answer", "", "| # | Type | Question | Mode | ✓ | Answer |", "|---|---|---|---|---|---|"]
    for r in rows:
        ans = r["answer"].replace("\n", " ").replace("|", "\\|")
        lines.append(f"| {r['id']} | {r['modality']} | {r['question']} | {r['mode']} | {'✅' if r['correct'] else '❌'} | {ans} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
