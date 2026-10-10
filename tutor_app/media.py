from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

from tutor_app.course import slide_texts

WIDTH = 1280
HEIGHT = 720


class VideoBuildError(RuntimeError):
    """A lesson video could not be rendered."""


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_names = (
        ("C:/Windows/Fonts/segoeuib.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
        if bold
        else ("C:/Windows/Fonts/segoeui.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    )
    for name in font_names:
        if Path(name).is_file():
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _render(title: str, body: str, number: int, total: int) -> bytes:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#111b2d")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((60, 56, WIDTH - 60, HEIGHT - 60), radius=26, fill="#182741", outline="#354b70", width=2)
    draw.rounded_rectangle((98, 98, 112, HEIGHT - 102), radius=7, fill="#80a7ff")
    draw.text((146, 105), "UTORA  ·  YOUR LEARNING STUDIO", font=_font(20, True), fill="#a9c0ff")
    y = 168
    for line in textwrap.wrap(" ".join(title.split()), width=40)[:2]:
        draw.text((146, y), line, font=_font(48, True), fill="#ffffff")
        y += 62
    y += 24
    for line in textwrap.wrap(" ".join(body.split()), width=62)[:8]:
        draw.text((148, y), line, font=_font(29), fill="#e3ebfb")
        y += 46
    draw.line((146, HEIGHT - 138, WIDTH - 116, HEIGHT - 138), fill="#354b70", width=2)
    draw.text((146, HEIGHT - 115), "Small steps. Clear ideas. Your own pace.", font=_font(19), fill="#a9b8cf")
    draw.text((WIDTH - 180, HEIGHT - 118), f"{number:02d} / {total:02d}", font=_font(20, True), fill="#a9c0ff")
    return image.tobytes()


def make_video(course: dict, lesson: dict) -> bytes:
    try:
        slides = slide_texts(course, lesson)
        with tempfile.TemporaryDirectory(prefix="utora-video-") as directory:
            output = Path(directory) / "lesson.mp4"
            writer = imageio_ffmpeg.write_frames(
                str(output),
                (WIDTH, HEIGHT),
                fps=1,
                codec="libx264",
                pix_fmt_in="rgb24",
                pix_fmt_out="yuv420p",
                macro_block_size=None,
                output_params=["-movflags", "+faststart"],
            )
            writer.send(None)
            try:
                for number, (title, body) in enumerate(slides, start=1):
                    frame = _render(title, body, number, len(slides))
                    for _ in range(3):
                        writer.send(frame)
            finally:
                writer.close()
            result = output.read_bytes()
        if len(result) < 1024 or b"ftyp" not in result[:64]:
            raise VideoBuildError("The renderer did not produce a valid MP4.")
        return result
    except VideoBuildError:
        raise
    except (OSError, RuntimeError, ValueError, ImportError, BrokenPipeError) as exc:
        raise VideoBuildError(
            "The local video renderer could not create an MP4. Check that the project dependencies installed correctly."
        ) from exc
