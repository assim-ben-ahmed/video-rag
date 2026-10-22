"""Generates the demo video and its evaluation questions.

A fictional 8-slide "Rooftop Beekeeping" briefing, narrated with the offline system voice (pyttsx3). Facts are
split on purpose: some are only spoken, some only appear on the slides, and some need both. That makes it a fair
test of what a transcript-only RAG can and cannot answer.

    python scripts/make_demo_video.py          ->  demo/rooftop-bees.mp4, demo/timeline.json, demo/questions.json
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "demo"
W, H = 1280, 720
BG, INK, MUTED, HONEY, GREEN = (24, 33, 27), (241, 236, 222), (170, 180, 168), (238, 176, 52), (120, 178, 120)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    names = (["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold else ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"])
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def canvas(title: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 10), fill=HONEY)
    d.text((80, 60), title, font=font(54, True), fill=INK)
    d.text((80, H - 60), "Rooftop Bees · beginner briefing", font=font(22), fill=MUTED)
    return img, d


def bullets(d: ImageDraw.ImageDraw, items: list[str], y: int = 190, size: int = 40) -> None:
    for item in items:
        d.ellipse((84, y + 16, 100, y + 32), fill=HONEY)
        d.text((124, y), item, font=font(size), fill=INK)
        y += int(size * 1.9)


def hexagon(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int, fill) -> None:
    import math

    pts = [(cx + r * math.cos(math.radians(60 * i + 30)), cy + r * math.sin(math.radians(60 * i + 30))) for i in range(6)]
    d.polygon(pts, fill=fill)


# ── slides: (draw function, narration) ───────────────────────────────────────


def s_title():
    img, d = canvas("")
    for i, (x, y) in enumerate([(930, 260), (1030, 318), (930, 376), (1030, 202), (1130, 260)]):
        hexagon(d, x, y, 58, HONEY if i % 2 == 0 else (196, 140, 40))
    d.text((80, 230), "Rooftop Beekeeping", font=font(76, True), fill=INK)
    d.text((80, 340), "A beginner briefing", font=font(44), fill=HONEY)
    return img


def s_apiary():
    img, d = canvas("Our apiary")
    bullets(d, ["Number of hives: 6", "Roof height: 24 m", "Open to members only"])
    return img


def s_colony():
    img, d = canvas("A colony through the year")
    months = ["Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct"]
    values = [12, 25, 45, 60, 52, 40, 28, 15]  # thousands of bees
    x0, base, bw = 140, 600, 110
    for i, (m, v) in enumerate(zip(months, values)):
        x = x0 + i * (bw + 15)
        top = base - v * 6
        d.rectangle((x, top, x + bw, base), fill=HONEY if m == "Jun" else GREEN)
        d.text((x + 30, base + 10), m, font=font(26), fill=MUTED)
    d.text((x0 + 3 * (bw + 15) - 30, base - 60 * 6 - 50), "June: 60,000 bees", font=font(30, True), fill=INK)
    d.text((80, 140), "Bees per colony (thousands)", font=font(28), fill=MUTED)
    return img


def s_safety():
    img, d = canvas("Safety rules")
    bullets(d, ["Always wear the full suit", "Light the smoker before opening", "Never open the hive below 15 °C"])
    return img


def s_kit():
    img, d = canvas("Beginner kit")
    rows = [("Bee suit", "120 €"), ("Smoker", "35 €"), ("Hive tool", "12 €"), ("Gloves", "18 €")]
    y = 200
    for name, price in rows:
        d.rectangle((80, y, 900, y + 78), outline=(70, 84, 72), width=2)
        d.text((110, y + 16), name, font=font(40), fill=INK)
        d.text((720, y + 16), price, font=font(40, True), fill=HONEY)
        y += 90
    return img


def s_queen():
    img, d = canvas("Our queen")
    d.ellipse((160, 260, 520, 440), fill=(196, 140, 40))  # body
    for k in range(4):
        d.rectangle((250 + k * 60, 268, 275 + k * 60, 432), fill=(40, 30, 20))
    d.ellipse((470, 300, 590, 400), fill=(60, 45, 30))  # head
    d.ellipse((205, 310, 255, 360), fill=(40, 110, 230))  # blue dot on the thorax
    d.ellipse((230, 180, 400, 300), outline=MUTED, width=3)  # wing
    d.text((660, 300), "Queen marked with a", font=font(40), fill=INK)
    d.text((660, 360), "blue dot (2024)", font=font(40, True), fill=(110, 160, 250))
    return img


def s_harvest():
    img, d = canvas("The harvest")
    for i in range(3):
        x = 140 + i * 230
        d.rounded_rectangle((x, 260, x + 170, 500), radius=24, fill=HONEY)
        d.rectangle((x + 20, 230, x + 150, 270), fill=(120, 90, 50))
    d.text((860, 320), "Jar price:", font=font(40), fill=MUTED)
    d.text((860, 380), "9 € / 250 g", font=font(54, True), fill=INK)
    return img


def s_join():
    img, d = canvas("Join us")
    bullets(d, ["Workshops every Saturday at 10:00", "Contact: bees@rooftop.example"])
    return img


SLIDES = [
    (s_title, "Welcome to this short briefing on rooftop beekeeping. In the next few minutes I will explain how our "
              "rooftop apiary works and what you need to get started."),
    (s_apiary, "We installed our very first hive on the roof of the city library in the spring of 2019. "
               "Since then the apiary has grown, as you can see on this slide."),
    (s_colony, "A colony changes a lot during the year. At the height of the season, the queen can lay up to two "
               "thousand eggs a day. The chart shows how the population evolves month by month."),
    (s_safety, "Safety comes first, and the rules on this slide are not optional. And if you do get stung, scrape the "
               "sting out with a fingernail. Never pinch it, because that pushes more venom in."),
    (s_kit, "Here is what the beginner kit costs. Good news: during your first year, the association lends you a "
            "smoker for free."),
    (s_queen, "Our current queen is a Buckfast queen. She came from a breeder in Brittany, and she is calm and very "
              "productive."),
    (s_harvest, "We harvest once a year, in late August. Last year we collected about forty two kilograms of honey."),
    (s_join, "Thank you for watching. The next beginner session starts on the third of October. We hope to see you "
             "on the roof."),
]

# expected answers: any of the alternatives in each group must appear (all groups required)
QUESTIONS = [
    # spoken only
    ("When was the first hive installed?", [["2019"]], "speech", 1),
    ("On which building was the first hive installed?", [["library"]], "speech", 1),
    ("How many eggs can the queen lay per day?", [["2000", "2,000", "2 000", "two thousand"]], "speech", 2),
    ("What should you do if you get stung?", [["scrape"]], "speech", 3),
    ("What does the association lend beginners for free?", [["smoker"]], "speech", 4),
    ("What breed is the queen?", [["buckfast"]], "speech", 5),
    ("How much honey was collected last year?", [["42", "forty two", "forty-two"]], "speech", 6),
    ("When does the next beginner session start?", [["october"]], "speech", 7),
    # shown only
    ("How many hives are there on the roof?", [["6", "six"]], "screen", 1),
    ("How high is the roof?", [["24"]], "screen", 1),
    ("In which month does the colony peak, and how many bees does it have then?", [["june"], ["60,000", "60 000", "60000", "sixty thousand"]], "screen", 2),
    ("Below what temperature should the hive never be opened?", [["15"]], "screen", 3),
    ("How much does the bee suit cost?", [["120"]], "screen", 4),
    ("What colour is the mark on the queen?", [["blue"]], "screen", 5),
    ("What is the price of a jar of honey?", [["9 €", "9€", "9 euro", "€9", "nine"]], "screen", 6),
    ("On which day are the workshops held?", [["saturday"]], "screen", 7),
    # needs both
    ("What is the total price of the four items in the beginner kit?", [["185"]], "both", 4),
    ("Which breed is the queen, and in which year was she marked?", [["buckfast"], ["2024"]], "both", 5),
    ("In which month is the honey harvested, and how much does a jar cost?", [["august"], ["9 €", "9€", "9 euro", "€9", "nine"]], "both", 6),
]


def narrate(texts: list[str], folder: Path) -> list[Path]:
    import pyttsx3

    engine = pyttsx3.init()
    engine.setProperty("rate", 165)
    voices = engine.getProperty("voices")
    english = [v for v in voices if "en" in (v.id + v.name).lower() and ("david" in v.name.lower() or "zira" in v.name.lower())]
    if english:
        engine.setProperty("voice", english[0].id)
    paths = []
    for i, text in enumerate(texts):
        p = folder / f"narration_{i}.wav"
        engine.save_to_file(text, str(p))
        paths.append(p)
    engine.runAndWait()
    return paths


def wav_seconds(p: Path) -> float:
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


def main() -> None:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    OUT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        audio = narrate([n for _, n in SLIDES], tmpdir)
        timeline, segments, t = [], [], 0.0
        for i, ((draw, narration), wav) in enumerate(zip(SLIDES, audio)):
            png = tmpdir / f"slide_{i}.png"
            draw().save(png)
            dur = round(wav_seconds(wav) + 1.6, 2)  # 0.6 s lead-in + 1 s pause after the narration
            seg = tmpdir / f"seg_{i}.mp4"
            subprocess.run(
                [ffmpeg, "-y", "-loglevel", "error", "-loop", "1", "-framerate", "25", "-i", str(png), "-i", str(wav),
                 "-af", "adelay=600:all=1,apad", "-t", str(dur), "-c:v", "libx264", "-tune", "stillimage",
                 "-pix_fmt", "yuv420p", "-r", "25", "-c:a", "aac", "-b:a", "96k", "-ar", "44100", str(seg)],
                check=True,
            )
            segments.append(seg)
            timeline.append({"slide": i, "title": draw.__name__[2:], "start": round(t, 2), "end": round(t + dur, 2), "narration": narration})
            t += dur
        listing = tmpdir / "list.txt"
        listing.write_text("".join(f"file '{s.as_posix()}'\n" for s in segments), encoding="utf-8")
        video = OUT / "rooftop-bees.mp4"
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy",
                        "-movflags", "+faststart", str(video)], check=True)

    (OUT / "timeline.json").write_text(json.dumps(timeline, indent=1), encoding="utf-8")
    qs = [{"id": i + 1, "question": q, "expected": exp, "modality": mod, "slide": s} for i, (q, exp, mod, s) in enumerate(QUESTIONS)]
    (OUT / "questions.json").write_text(json.dumps(qs, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{video} ({t:.0f} s, {len(SLIDES)} slides, {len(qs)} questions)")


if __name__ == "__main__":
    sys.exit(main())
