"""实际渲染回归：固定种子，不联网、不生成样例文件。"""

from __future__ import annotations

import io

import pytest
from PIL import Image, UnidentifiedImageError

from volt_toy_core import effects


@pytest.fixture
def raw() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (200, 120), (200, 100, 50)).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.mark.parametrize("tier", ["静电", "家用", "工业", "高压", "雷击"])
def test_static_tiers_are_png_and_deterministic(raw, tier):
    output = effects.render(raw, tier=tier, volt=220, kwh=0.15, seed=42)
    assert output == effects.render(raw, tier=tier, volt=220, kwh=0.15, seed=42)
    with Image.open(io.BytesIO(output)) as image:
        assert image.format == "PNG"
        assert image.size == (512, 512)
        image.load()


def test_lightning_gif_frames_and_timing(raw):
    output = effects.render_gif(raw, volt=900, kwh=1.5, seed=42)
    assert output == effects.render_gif(raw, volt=900, kwh=1.5, seed=42)
    with Image.open(io.BytesIO(output)) as image:
        assert image.format == "GIF"
        assert image.size == (512, 512)
        assert image.n_frames == 3
        assert image.info["loop"] == 0
        durations, pixels = [], []
        for frame in range(image.n_frames):
            image.seek(frame)
            durations.append(image.info["duration"])
            pixels.append(image.convert("RGB").tobytes())
        assert durations == [90, 90, 650]
        assert len(set(pixels)) == 3


@pytest.mark.parametrize("renderer", [effects.render, effects.render_gif])
def test_bad_source_raises_for_adapter_fallback(renderer):
    with pytest.raises(UnidentifiedImageError):
        renderer(b"not an image")
