"""Offline tests: no API key, no network, no Whisper download."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from videorag import media, timeutil
from videorag.answer import Answerer
from videorag.index import Doc, VideoIndex, rrf, tokenize
from videorag.transcribe import Segment, chunk

# ── helpers ──────────────────────────────────────────────────────────────────


def fake_embed(texts: list[str]) -> np.ndarray:
    """Bag-of-words hashing embedder: deterministic, good enough to rank by shared words."""
    vecs = np.zeros((len(texts), 256), dtype=np.float32)
    for i, t in enumerate(texts):
        for tok in tokenize(t):
            vecs[i, hash(tok) % 256] += 1
    return vecs / np.clip(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-9, None)


def demo_index() -> VideoIndex:
    docs = [
        Doc("s0", "speech", 0, 14, "We installed the first hive on the library roof in 2019."),
        Doc("s1", "speech", 14, 30, "If you get stung, scrape the sting out with a fingernail."),
        Doc("v0", "screen", 0, 14, "Slide 'Our apiary': Number of hives: 6. Roof height: 24 m."),
        Doc("v1", "screen", 14, 30, "Slide 'Beginner kit': Bee suit 120 €, Smoker 35 €."),
    ]
    return VideoIndex.build(docs, fake_embed)


class ScriptedLLM:
    """Plays back assistant messages; records what it was sent."""

    def __init__(self, replies: list[dict]):
        self.replies, self.sent = list(replies), []
        self.stats = {"api_calls": 0, "cache_hits": 0}

    def chat(self, messages, tools=None, tool_choice="auto", **kw):
        self.sent.append({"messages": [dict(m) for m in messages], "tool_choice": tool_choice})
        return self.replies.pop(0)

    def embed(self, texts):
        return fake_embed(texts)

    def describe_image(self, path, prompt, **kw):
        return "A slide reading 'Roof height: 24 m'."


def tool_call(name: str, args: dict, cid: str = "c1") -> dict:
    return {"role": "assistant", "content": "", "tool_calls": [{"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


# ── timeutil ─────────────────────────────────────────────────────────────────


def test_format_and_parse_round_trip():
    assert timeutil.fmt(83.4) == "01:23"
    assert timeutil.fmt_span(12, 24) == "[00:12–00:24]"
    assert timeutil.fmt_span(12, 12.2) == "[00:12]"
    assert timeutil.parse("01:23") == 83 and timeutil.parse("83") == 83 and timeutil.parse(7) == 7


def test_citations_are_extracted():
    text = "Six hives [00:12–00:24], suit 120 € [1:02] and [00:30-00:41]."
    assert timeutil.citations(text) == [(12, 24), (62, 62), (30, 41)]


# ── chunking ─────────────────────────────────────────────────────────────────


def test_chunks_cover_everything_with_overlap():
    segs = [Segment(i * 5.0, i * 5.0 + 5, f"sentence {i}") for i in range(10)]  # 50 s
    chunks = chunk(segs, target=15, overlap=1)
    assert chunks[0].start == 0 and chunks[-1].end == 50
    assert all(c.end - c.start >= 15 for c in chunks[:-1])
    assert "sentence 2" in chunks[0].text and chunks[1].text.startswith("sentence 2")  # overlap


def test_short_audio_gives_one_chunk():
    assert len(chunk([Segment(0, 3, "hello")])) == 1


# ── search ───────────────────────────────────────────────────────────────────


def test_rrf_rewards_agreement():
    fused = rrf([[1, 2, 3], [3, 1, 2]])
    assert max(fused, key=fused.get) == 1


def test_search_filters_by_kind_and_finds_exact_numbers():
    idx = demo_index()
    speech = idx.search("roof hive installed", fake_embed, k=1, kinds=("speech",))
    assert speech[0].id == "s0"
    screen = idx.search("how high is the roof height", fake_embed, k=1, kinds=("screen",))
    assert screen[0].id == "v0"
    assert all(d.kind == "screen" for d in idx.search("suit price", fake_embed, k=4, kinds=("screen",)))


def test_index_save_load(tmp_path: Path):
    idx = demo_index()
    idx.save(tmp_path)
    again = VideoIndex.load(tmp_path)
    assert [d.id for d in again.docs] == [d.id for d in idx.docs]
    assert np.allclose(again.vectors, idx.vectors)


# ── keyframes ────────────────────────────────────────────────────────────────


@pytest.fixture()
def slide_video(tmp_path: Path) -> Path:
    """3 'slides' of 3 s each; slides 2 and 3 differ only by a line of text (the case that used to be missed)."""
    path = tmp_path / "slides.mp4"
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (320, 180))
    for slide in range(3):
        for _ in range(30):
            img = np.full((180, 320, 3), (30, 35, 30), np.uint8)
            cv2.putText(img, "Title", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (230, 230, 230), 2)
            if slide >= 1:
                cv2.putText(img, "Hives: 6", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (230, 230, 230), 2)
            if slide == 2:
                cv2.putText(img, "Price 120", (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 1, (230, 230, 230), 2)
            out.write(img)
    out.release()
    return path


def test_one_keyframe_per_slide(slide_video: Path, tmp_path: Path):
    frames = media.keyframes(slide_video, tmp_path / "frames", step=0.5)
    assert [round(f.time) for f in frames] == [0, 3, 6]
    assert all(f.path.exists() for f in frames)


def test_frame_at(slide_video: Path, tmp_path: Path):
    assert media.frame_at(slide_video, 7.0, tmp_path / "f.jpg").exists()


# ── answering ────────────────────────────────────────────────────────────────


def test_simple_mode_only_sees_speech(tmp_path: Path):
    llm = ScriptedLLM([{"role": "assistant", "content": "I could not find it in the video."}])
    ans = Answerer(demo_index(), llm, tmp_path / "v.mp4", tmp_path).ask("How high is the roof?", "simple")
    prompt = llm.sent[0]["messages"][1]["content"]
    assert "(on screen)" not in prompt and "(speech)" in prompt
    assert ans.llm_calls == 2  # one embedding + one chat


def test_multimodal_mode_sees_the_screen(tmp_path: Path):
    llm = ScriptedLLM([{"role": "assistant", "content": "The roof is 24 m high [00:00–00:14]."}])
    ans = Answerer(demo_index(), llm, tmp_path / "v.mp4", tmp_path).ask("How high is the roof?", "multimodal")
    assert "Roof height: 24 m" in llm.sent[0]["messages"][1]["content"]
    assert ans.citations == [(0, 14)]


def test_agent_runs_tools_then_answers(tmp_path: Path, slide_video: Path):
    llm = ScriptedLLM([
        tool_call("search_screen", {"query": "roof height"}),
        tool_call("look_at_frame", {"timestamp": "00:04", "question": "What height is written?"}, "c2"),
        {"role": "assistant", "content": "24 m, shown at [00:04]."},
    ])
    ans = Answerer(demo_index(), llm, slide_video, tmp_path).ask("How high is the roof?", "agentic")
    assert [t["tool"] for t in ans.trace] == ["search_screen", "look_at_frame"]
    tool_msgs = [m for m in llm.sent[-1]["messages"] if m["role"] == "tool"]
    assert len(tool_msgs) == 2 and "Roof height: 24 m" in tool_msgs[0]["content"]
    assert ans.answer.startswith("24 m") and ans.citations == [(4, 4)]


def test_agent_is_forced_to_answer_after_max_steps(tmp_path: Path):
    loop = [tool_call("search_speech", {"query": "x"}, f"c{i}") for i in range(3)]
    llm = ScriptedLLM(loop + [{"role": "assistant", "content": "Best effort."}])
    ans = Answerer(demo_index(), llm, tmp_path / "v.mp4", tmp_path, max_steps=3).ask("?", "agentic")
    assert llm.sent[-1]["tool_choice"] == "none" and ans.answer == "Best effort."


def test_unknown_mode_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError):
        Answerer(demo_index(), ScriptedLLM([]), tmp_path / "v.mp4", tmp_path).ask("?", "magic")
