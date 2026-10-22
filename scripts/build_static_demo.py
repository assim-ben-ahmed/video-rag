"""Builds the recorded demo used by the web app when no server is running (GitHub Pages): web/demo/.

    python scripts/build_static_demo.py

Answers are produced by the real pipeline (Answerer) on the demo index; API responses come from data/cache, so after
`scripts/evaluate.py` this is free. Latencies are taken from reports/metrics.json (the uncached run).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from videorag.answer import MODES, Answerer  # noqa: E402
from videorag.config import settings  # noqa: E402
from videorag.index import VideoIndex  # noqa: E402
from videorag.llm import from_settings  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEMO, OUT = ROOT / "demo", ROOT / "web" / "demo"


def main() -> None:
    index_dir = DEMO / "index"
    manifest = json.loads((index_dir / "manifest.json").read_text(encoding="utf-8"))
    questions = json.loads((DEMO / "questions.json").read_text(encoding="utf-8"))
    metrics = json.loads((ROOT / "reports" / "metrics.json").read_text(encoding="utf-8"))
    recorded = {(r["id"], r["mode"]): r for r in metrics["rows"]}

    llm = from_settings(settings)
    answerer = Answerer(VideoIndex.load(index_dir), llm, DEMO / "rooftop-bees.mp4", settings.videos_dir / "demo", settings.agent_max_steps)

    answers = {}
    for q in questions:
        for mode in MODES:
            a = answerer.ask(q["question"], mode).to_dict()
            rec = recorded[(q["id"], mode)]
            a["latency_s"] = rec["latency_s"]
            a["correct"] = rec["correct"]
            if a["answer"] != rec["answer"]:
                print(f"note: q{q['id']} {mode} differs from the evaluation run (cache miss)")
            answers[f"{q['id']}:{mode}"] = a

    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copy(DEMO / "rooftop-bees.mp4", OUT / "rooftop-bees.mp4")
    frames = OUT / "frames"
    shutil.rmtree(frames, ignore_errors=True)
    shutil.copytree(index_dir / "frames", frames)
    data = {
        "video": "rooftop-bees.mp4",
        "duration": manifest["duration"],
        "language": manifest["language"],
        "keyframes": manifest["keyframes"],
        "segments": manifest["segments"],
        "questions": questions,
        "answers": answers,
        "summary": metrics["summary"],
        "meta": metrics["meta"],
    }
    (OUT / "data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"web/demo/data.json: {len(answers)} answers, API calls this run: {llm.stats['api_calls']} (cache hits {llm.stats['cache_hits']})")


if __name__ == "__main__":
    main()
