"""高能二次元电击特效模块。

彻底抛弃老旧档案相框/变灰滤镜，采用：
1. 全画幅等比保留原图通透色彩（不加发闷发暗滤镜、不加多余相框/字样）
2. 纯正加法发光 (Additive Glow / Linear Dodge) + 四层高斯模糊光晕
3. 动漫级大转折分形电弧（带自然分支与受击飞溅火花，避开面部五官，环绕放电）
4. 高档位受击震颤色散 (RGB Split)
5. 雷击档动态放电 GIF (多帧形态跳变 + 剧烈受击抖动)
"""

from __future__ import annotations

import io
import math
import random
from typing import Literal

from PIL import Image, ImageChops, ImageDraw, ImageFilter

TierName = Literal["静电", "家用", "工业", "高压", "雷击"]


def _load_square_avatar(raw_bytes: bytes, size: int = 512) -> Image.Image:
    """等比裁切居中缩放为 size x size，无留白，保持原汁原味。"""
    im = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    w, h = im.size
    min_side = min(w, h)
    left = (w - min_side) // 2
    top = (h - min_side) // 2
    cropped = im.crop((left, top, left + min_side, top + min_side))
    return cropped.resize((size, size), Image.LANCZOS)


def _rgb_split(im_rgb: Image.Image, offset: int = 2) -> Image.Image:
    """二次元轻微电击受击震颤/色散 (RGB Split)。"""
    if offset <= 0:
        return im_rgb
    r, g, b = im_rgb.split()
    r = ImageChops.offset(r, offset, 0)
    b = ImageChops.offset(b, -offset, 0)
    return Image.merge("RGB", (r, g, b))


def _create_lightning_branch(
    start: tuple[float, float],
    end: tuple[float, float],
    max_disp: float = 25,
    steps: int = 5,
    rng: random.Random | None = None,
) -> list[tuple[float, float]]:
    """生成一条自然大转折线段。"""
    if rng is None:
        rng = random.Random()
    sx, sy = start
    ex, ey = end
    dx = ex - sx
    dy = ey - sy
    length = math.hypot(dx, dy)
    if length < 5:
        return [start, end]
    nx = -dy / length
    ny = dx / length

    pts = [start]
    for i in range(1, steps):
        t = i / float(steps)
        disp = rng.gauss(0, max_disp)
        px = sx + dx * t + nx * disp
        py = sy + dy * t + ny * disp
        pts.append((px, py))
    pts.append(end)
    return pts


def _create_lightning_bolt(
    start: tuple[float, float],
    end: tuple[float, float],
    max_disp: float = 35,
    steps: int = 7,
    branch_prob: float = 0.5,
    rng: random.Random | None = None,
) -> dict:
    """生成主干及其分支。"""
    if rng is None:
        rng = random.Random()
    main_pts = _create_lightning_branch(start, end, max_disp=max_disp, steps=steps, rng=rng)

    branches = []
    for i in range(1, len(main_pts) - 1):
        if rng.random() < branch_prob:
            p_start = main_pts[i]
            p_prev = main_pts[i - 1]
            dx = p_start[0] - p_prev[0]
            dy = p_start[1] - p_prev[1]
            l = math.hypot(dx, dy)
            if l < 1:
                continue
            angle = rng.choice([-1, 1]) * rng.uniform(0.4, 0.9)
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            rx = (dx * cos_a - dy * sin_a) / l
            ry = (dx * sin_a + dy * cos_a) / l

            b_len = rng.uniform(30, 80)
            b_end = (p_start[0] + rx * b_len, p_start[1] + ry * b_len)
            b_pts = _create_lightning_branch(p_start, b_end, max_disp=b_len * 0.25, steps=4, rng=rng)
            branches.append(b_pts)

    return {"main": main_pts, "branches": branches}


def _render_additive_electric(
    base_im: Image.Image,
    bolts_data: list[dict],
    sparks: list[dict],
    color_rgb: tuple[int, int, int] = (255, 205, 30),
    main_width: int = 4,
    split: int = 0,
) -> Image.Image:
    size = base_im.size

    # 受击色散
    base_work = _rgb_split(base_im, split) if split > 0 else base_im

    l_atm = Image.new("RGBA", size, (0, 0, 0, 0))
    l_wide = Image.new("RGBA", size, (0, 0, 0, 0))
    l_inner = Image.new("RGBA", size, (0, 0, 0, 0))
    l_core = Image.new("RGBA", size, (0, 0, 0, 0))

    d_atm = ImageDraw.Draw(l_atm)
    d_wide = ImageDraw.Draw(l_wide)
    d_inner = ImageDraw.Draw(l_inner)
    d_core = ImageDraw.Draw(l_core)
    # Saturated contour keeps the white-hot core readable against white backgrounds.
    contour = (12, 92, 205) if color_rgb[2] > color_rgb[0] else (190, 92, 8)
    low_tier = main_width <= 3

    for item in bolts_data:
        main_pts = item["main"]
        w = item.get("width", main_width)

        # Main channel
        d_atm.line(main_pts, fill=color_rgb + (95 if low_tier else 70,), width=w * 12 if low_tier else w * 10, joint="curve")
        d_wide.line(main_pts, fill=color_rgb + (205 if low_tier else 160,), width=w * 5 if low_tier else w * 4, joint="curve")
        d_inner.line(main_pts, fill=color_rgb + (255,), width=w * 2 + (2 if low_tier else 0), joint="curve")
        if low_tier:
            d_core.line(main_pts, fill=contour + (255,), width=max(6, w + 4), joint="curve")
        d_core.line(main_pts, fill=(255, 255, 255, 255), width=max(1, w - 1), joint="curve")

        # Branches
        for b_pts in item["branches"]:
            bw = max(1, w // 2)
            d_wide.line(b_pts, fill=color_rgb + (170 if low_tier else 130,), width=bw * (4 if low_tier else 3), joint="curve")
            d_inner.line(b_pts, fill=color_rgb + (240 if low_tier else 220,), width=bw * 2, joint="curve")
            if low_tier:
                d_core.line(b_pts, fill=contour + (255,), width=4, joint="curve")
            d_core.line(b_pts, fill=(255, 255, 255, 255), width=1, joint="curve")

    # Sparks
    for sp in sparks:
        sx, sy = sp["pos"]
        r = sp.get("r", 2)
        d_wide.ellipse([sx - r * 3, sy - r * 3, sx + r * 3, sy + r * 3], fill=color_rgb + (150,))
        d_inner.ellipse([sx - r * 1.5, sy - r * 1.5, sx + r * 1.5, sy + r * 1.5], fill=color_rgb + (240,))
        d_core.ellipse([sx - r * 0.7, sy - r * 0.7, sx + r * 0.7, sy + r * 0.7], fill=(255, 255, 255, 255))

    b_atm = l_atm.filter(ImageFilter.GaussianBlur(26))
    b_wide = l_wide.filter(ImageFilter.GaussianBlur(8))
    b_inner = l_inner.filter(ImageFilter.GaussianBlur(3))
    b_core = l_core.filter(ImageFilter.GaussianBlur(1.0))

    glow_total = Image.alpha_composite(b_atm, b_wide)
    glow_total = Image.alpha_composite(glow_total, b_inner)
    glow_total = Image.alpha_composite(glow_total, b_core)

    # Saturating additive blend, implemented with Pillow only.
    base_rgb = base_work.convert("RGB")
    glow_rgba = glow_total.convert("RGBA")
    glow_alpha = glow_rgba.getchannel("A")
    premultiplied = Image.merge(
        "RGB",
        tuple(ImageChops.multiply(channel, glow_alpha) for channel in glow_rgba.convert("RGB").split()),
    )
    return ImageChops.add(base_rgb, premultiplied)


def _build_tier_layout(tier: str, rng: random.Random) -> tuple:
    """生成档位电弧布局（避开正中心面部，环绕放电）。"""
    if tier == "静电":
        color = (80, 215, 255)
        split = 0
        w = 2
        b1 = _create_lightning_bolt((140, 50), (220, 110), max_disp=16, steps=5, branch_prob=0.3, rng=rng)
        b2 = _create_lightning_bolt((380, 80), (430, 170), max_disp=16, steps=5, branch_prob=0.3, rng=rng)
        bolts = [{"main": b1["main"], "branches": b1["branches"], "width": w},
                 {"main": b2["main"], "branches": b2["branches"], "width": w}]
        sparks = [{"pos": (140 + rng.uniform(-10, 10), 50 + rng.uniform(-10, 10)), "r": 2} for _ in range(3)]
        return color, bolts, sparks, w, split

    elif tier == "家用":
        color = (255, 205, 30)  # 高能金黄
        split = 0
        w = 3
        b1 = _create_lightning_bolt((60, -10), (190, 180), max_disp=26, steps=6, branch_prob=0.45, rng=rng)
        b2 = _create_lightning_bolt((460, 10), (330, 210), max_disp=26, steps=6, branch_prob=0.45, rng=rng)
        b3 = _create_lightning_bolt((110, 480), (200, 360), max_disp=22, steps=5, branch_prob=0.3, rng=rng)
        bolts = [{"main": b1["main"], "branches": b1["branches"], "width": w},
                 {"main": b2["main"], "branches": b2["branches"], "width": w},
                 {"main": b3["main"], "branches": b3["branches"], "width": w}]
        sparks = [{"pos": (rng.uniform(80, 430), rng.uniform(80, 430)), "r": rng.uniform(1.5, 3)} for _ in range(6)]
        return color, bolts, sparks, w, split

    elif tier == "工业":
        color = (60, 195, 255)  # 电浆苍蓝
        split = 2
        w = 4
        b1 = _create_lightning_bolt((80, -15), (180, 190), max_disp=30, steps=6, branch_prob=0.5, rng=rng)
        b2 = _create_lightning_bolt((450, -10), (340, 220), max_disp=30, steps=6, branch_prob=0.5, rng=rng)
        b3 = _create_lightning_bolt((10, 320), (170, 310), max_disp=24, steps=5, branch_prob=0.4, rng=rng)
        b4 = _create_lightning_bolt((505, 340), (350, 330), max_disp=24, steps=5, branch_prob=0.4, rng=rng)
        bolts = [{"main": b["main"], "branches": b["branches"], "width": w} for b in [b1, b2, b3, b4]]
        sparks = [{"pos": (rng.uniform(50, 460), rng.uniform(50, 460)), "r": rng.uniform(2, 3.5)} for _ in range(12)]
        return color, bolts, sparks, w, split

    elif tier == "高压":
        color = (180, 120, 255)  # 高压狂暴紫
        split = 3
        w = 4
        b1 = _create_lightning_bolt((140, -20), (220, 160), max_disp=32, steps=6, branch_prob=0.6, rng=rng)
        b2 = _create_lightning_bolt((380, -20), (300, 170), max_disp=32, steps=6, branch_prob=0.6, rng=rng)
        b3 = _create_lightning_bolt((0, 220), (160, 260), max_disp=28, steps=5, branch_prob=0.5, rng=rng)
        b4 = _create_lightning_bolt((512, 240), (360, 270), max_disp=28, steps=5, branch_prob=0.5, rng=rng)
        b5 = _create_lightning_bolt((160, 520), (230, 380), max_disp=26, steps=5, branch_prob=0.4, rng=rng)
        b6 = _create_lightning_bolt((360, 520), (290, 390), max_disp=26, steps=5, branch_prob=0.4, rng=rng)
        bolts = [{"main": b["main"], "branches": b["branches"], "width": w} for b in [b1, b2, b3, b4, b5, b6]]
        sparks = [{"pos": (rng.uniform(40, 470), rng.uniform(40, 470)), "r": rng.uniform(2, 4)} for _ in range(18)]
        return color, bolts, sparks, w, split

    else:  # 雷击
        color = (205, 170, 255)  # 天劫紫白
        split = 4
        w = 5
        b1 = _create_lightning_bolt((210, -20), (240, 530), max_disp=40, steps=8, branch_prob=0.7, rng=rng)
        b2 = _create_lightning_bolt((40, 40), (180, 220), max_disp=32, steps=6, branch_prob=0.6, rng=rng)
        b3 = _create_lightning_bolt((480, 50), (340, 230), max_disp=32, steps=6, branch_prob=0.6, rng=rng)
        b4 = _create_lightning_bolt((20, 420), (180, 340), max_disp=28, steps=5, branch_prob=0.5, rng=rng)
        b5 = _create_lightning_bolt((500, 430), (330, 350), max_disp=28, steps=5, branch_prob=0.5, rng=rng)
        bolts = [{"main": b["main"], "branches": b["branches"], "width": w} for b in [b1, b2, b3, b4, b5]]
        sparks = [{"pos": (rng.uniform(30, 480), rng.uniform(30, 480)), "r": rng.uniform(2.5, 4.5)} for _ in range(25)]
        return color, bolts, sparks, w, split


def render(
    raw: bytes,
    *,
    tier: str = "家用",
    volt: int = 220,
    kwh: float = 0.12,
    seed: int | None = None,
) -> bytes:
    """静态电击特效头像。任何异常由调用方回落原头像。"""
    rng = random.Random(seed if seed is not None else volt * 31 + int(kwh * 1000))
    base = _load_square_avatar(raw, size=512)
    color, bolts, sparks, w, split = _build_tier_layout(tier, rng)
    res = _render_additive_electric(base, bolts, sparks, color_rgb=color, main_width=w, split=split)
    out = io.BytesIO()
    res.save(out, format="PNG", optimize=True)
    return out.getvalue()


def render_gif(
    raw: bytes,
    *,
    volt: int = 900,
    kwh: float = 1.4,
    tier: str = "雷击",
    seed: int | None = None,
) -> bytes:
    """雷击档动态电击 GIF（3 帧电弧跳跃 + 画面剧烈震颤）。"""
    base_seed = seed if seed is not None else volt * 17 + int(kwh * 100)
    base = _load_square_avatar(raw, size=512)
    frames = []
    shakes = [(0, 0), (2, -3), (-2, 2)]

    for i in range(3):
        rng = random.Random(base_seed + i * 37)
        color, bolts, sparks, w, split = _build_tier_layout(tier, rng)
        dx, dy = shakes[i]
        shaken = ImageChops.offset(base, dx, dy)
        res = _render_additive_electric(shaken, bolts, sparks, color_rgb=color, main_width=w, split=split)
        frames.append(res)

    out = io.BytesIO()
    p_frames = [f.convert("P", palette=Image.ADAPTIVE, colors=128) for f in frames]
    p_frames[0].save(
        out,
        format="GIF",
        save_all=True,
        append_images=p_frames[1:],
        duration=[90, 90, 650],
        loop=0,
        optimize=True,
    )
    return out.getvalue()
