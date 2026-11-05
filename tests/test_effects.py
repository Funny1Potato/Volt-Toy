"""测试 effects 模块的基本合成与异常回退行为。"""

from __future__ import annotations

import io
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from PIL import Image

from volt_toy_core import effects

def test_effects_smoke():
    # 生成一张简单测试纯色图
    test_im = Image.new("RGB", (200, 200), (200, 100, 50))
    buf = io.BytesIO()
    test_im.save(buf, format="JPEG")
    raw = buf.getvalue()

    for tier in ["静电", "家用", "工业", "高压", "雷击"]:
        out = effects.render(raw, tier=tier, volt=220, kwh=0.15, seed=42)
        assert isinstance(out, bytes)
        assert len(out) > 0
        im_out = Image.open(io.BytesIO(out))
        assert im_out.size == (512, 512)

    gif_out = effects.render_gif(raw, volt=900, kwh=1.5, seed=42)
    assert isinstance(gif_out, bytes)
    assert len(gif_out) > 0
    im_gif = Image.open(io.BytesIO(gif_out))
    assert im_gif.format == "GIF"
    assert getattr(im_gif, "n_frames", 1) >= 2

if __name__ == "__main__":
    test_effects_smoke()
    print("test_effects_smoke passed!")
