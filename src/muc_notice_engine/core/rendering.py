"""可选的卡片图片渲染（matplotlib）。

移植自 astrbot_plugin_MUC_Notices/notice_card.py（仅保留 render_notices，
去掉与 LLM 摘要卡相关的部分）。matplotlib 为可选依赖，延迟导入。
"""

from __future__ import annotations

import logging
import os
import textwrap

logger = logging.getLogger(__name__)

_MATPLOTLIB = None
_FONT_READY = False
_BADGE = None
_BADGE_FAILED = False

_BADGE_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "muc_badge.png")

# 民大配色
MUC_RED = "#7a1128"
MUC_ACCENT = "#c8102e"
MUC_GRAY = "#9a958f"
MUC_BG = "#f6f3ee"
CARD_BG = "#ffffff"
CARD_BORDER = "#ece6dd"
CARD_SHADOW = "#ded7cb"
TEXT_DARK = "#20201e"
TEXT_BODY = "#5a564f"
WHITE = "#FFFFFF"


def _require_matplotlib():
    global _MATPLOTLIB
    if _MATPLOTLIB is not None:
        return _MATPLOTLIB
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.font_manager as fm
        import matplotlib.image as mpimg
        import matplotlib.pyplot as plt
        from matplotlib.offsetbox import AnnotationBbox, OffsetImage
        from matplotlib.patches import Circle, FancyBboxPatch
    except ImportError as exc:  # pragma: no cover - depends on optional dep
        raise RuntimeError(
            "卡片渲染需要 matplotlib，请安装：pip install 'muc-notice-engine[render]'"
        ) from exc

    _MATPLOTLIB = {
        "plt": plt,
        "fm": fm,
        "mpimg": mpimg,
        "FancyBboxPatch": FancyBboxPatch,
        "Circle": Circle,
        "OffsetImage": OffsetImage,
        "AnnotationBbox": AnnotationBbox,
    }
    return _MATPLOTLIB


def _setup_font() -> None:
    global _FONT_READY
    if _FONT_READY:
        return
    m = _require_matplotlib()
    plt, fm = m["plt"], m["fm"]

    font_paths = [
        os.path.join(os.path.dirname(__file__), "..", "fonts", "NotoSansSC-Medium.ttf"),
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansSC-Medium.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    ]
    loaded = False
    for font_path in font_paths:
        if font_path and os.path.exists(font_path):
            try:
                fm.fontManager.addfont(font_path)
                # 用字体自带 family name 写入 rcParams，否则会静默回退到无中文字形的字体。
                font_name = fm.FontProperties(fname=font_path).get_name()
                current = plt.rcParams.get("font.sans-serif", [])
                if isinstance(current, str):
                    current = [current]
                plt.rcParams["font.sans-serif"] = [font_name] + list(current)
                loaded = True
                break
            except Exception as exc:  # noqa: BLE001
                logger.debug("字体加载失败 %s: %s", font_path, exc)

    if not loaded:
        plt.rcParams["font.sans-serif"] = [
            "WenQuanYi Micro Hei",
            "Noto Sans CJK SC",
            "PingFang SC",
            "Microsoft YaHei",
            "SimHei",
        ]
    plt.rcParams["axes.unicode_minus"] = False
    _FONT_READY = True


def _load_badge():
    global _BADGE, _BADGE_FAILED
    if _BADGE is not None or _BADGE_FAILED:
        return _BADGE
    mpimg = _require_matplotlib()["mpimg"]
    try:
        _BADGE = mpimg.imread(_BADGE_PATH)
    except Exception as exc:  # noqa: BLE001
        logger.warning("校徽图片加载失败: %s", exc)
        _BADGE_FAILED = True
    return _BADGE


def _text_width(text: str, cjk_w: float = 0.118, ascii_w: float = 0.062) -> float:
    width = 0.0
    for ch in text:
        code = ord(ch)
        if (
            0x4E00 <= code <= 0x9FFF
            or 0x3000 <= code <= 0x303F
            or 0xFF00 <= code <= 0xFFEF
        ):
            width += cjk_w
        else:
            width += ascii_w
    return width


def _wrap(text: str, width: int, max_lines: int | None = None) -> str:
    if not text:
        return ""
    lines = textwrap.wrap(text, width=width) or [""]
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        if len(last) > 1:
            last = last[:-1].rstrip() + "…"
        lines[-1] = last
    return "\n".join(lines)


def render_notices(notices: list[dict], save_path: str) -> str:
    """把通知列表渲染为卡片 PNG，返回 save_path。"""
    m = _require_matplotlib()
    plt = m["plt"]
    _setup_font()
    FancyBboxPatch = m["FancyBboxPatch"]
    Circle = m["Circle"]
    OffsetImage = m["OffsetImage"]
    AnnotationBbox = m["AnnotationBbox"]

    n = len(notices)
    card_width = 7.9
    left = 0.35
    right = left + card_width

    TOP_PAD = 0.18
    BADGE_ROW_H = 0.32
    TITLE_LINE_H = 0.29
    SUMMARY_GAP = 0.10
    SUMMARY_LINE_H = 0.22
    BOTTOM_PAD = 0.20

    prepared = []
    for item in notices:
        source = item.get("source", item.get("source_key", ""))
        title = _wrap(item.get("title", ""), width=32, max_lines=2)
        date = item.get("date", "")
        if date.endswith(" 00:00"):
            date = date[: -len(" 00:00")]
        summary = _wrap(item.get("summary", "")[:120], width=38, max_lines=3)

        title_lines = title.count("\n") + 1 if title else 0
        summary_lines = summary.count("\n") + 1 if summary else 0

        card_h = TOP_PAD + BADGE_ROW_H + title_lines * TITLE_LINE_H + BOTTOM_PAD
        if summary:
            card_h += SUMMARY_GAP + summary_lines * SUMMARY_LINE_H
        prepared.append(
            {
                "source": source,
                "title": title,
                "date": date,
                "summary": summary,
                "card_h": card_h,
            }
        )

    gap = 0.16
    header_h = 0.68
    footer_h = 0.45
    top_margin = 0.3
    content_h = sum(p["card_h"] for p in prepared) + gap * max(n - 1, 0)
    fig_height = max(2.6, top_margin + header_h + 0.2 + content_h + footer_h)

    fig, ax = plt.subplots(figsize=(8.6, fig_height))
    ax.set_xlim(0, 8.6)
    ax.set_ylim(0, fig_height)
    ax.axis("off")
    fig.patch.set_facecolor(MUC_BG)
    ax.set_facecolor(MUC_BG)

    y = fig_height - top_margin

    header = FancyBboxPatch(
        (left, y - header_h),
        card_width,
        header_h,
        boxstyle="round,pad=0,rounding_size=0.12",
        facecolor=MUC_RED,
        edgecolor="none",
    )
    ax.add_patch(header)

    badge_cx, badge_cy = left + 0.34, y - header_h / 2
    badge_img = _load_badge()
    title_x = left + 0.62
    if badge_img is not None:
        badge_box = OffsetImage(badge_img, zoom=0.13, alpha=0.55)
        badge_box.image.axes = ax
        ax.add_artist(
            AnnotationBbox(badge_box, (badge_cx, badge_cy), frameon=False, pad=0, zorder=3)
        )
    else:
        ax.add_patch(
            Circle((badge_cx, badge_cy), 0.045, facecolor=WHITE, edgecolor="none", alpha=0.85)
        )
        title_x = left + 0.55
    ax.text(
        title_x,
        y - header_h / 2,
        "中央民族大学 · 通知聚合",
        fontsize=13.5,
        fontweight="bold",
        ha="left",
        va="center",
        color=WHITE,
    )
    ax.text(
        right - 0.3,
        y - header_h / 2 - 0.12,
        f"共 {n} 条通知",
        fontsize=8,
        ha="right",
        va="center",
        color="#f0d9de",
    )
    y -= header_h + 0.22

    for idx, p in enumerate(prepared):
        card_h = p["card_h"]
        card_y = y - card_h

        shadow = FancyBboxPatch(
            (left + 0.045, card_y - 0.035),
            card_width,
            card_h,
            boxstyle="round,pad=0,rounding_size=0.09",
            facecolor=CARD_SHADOW,
            edgecolor="none",
            alpha=0.55,
        )
        ax.add_patch(shadow)

        card = FancyBboxPatch(
            (left, card_y),
            card_width,
            card_h,
            boxstyle="round,pad=0,rounding_size=0.09",
            facecolor=CARD_BG,
            edgecolor=CARD_BORDER,
            linewidth=0.8,
        )
        ax.add_patch(card)

        stripe = FancyBboxPatch(
            (left, card_y + 0.1),
            0.055,
            card_h - 0.2,
            boxstyle="round,pad=0,rounding_size=0.02",
            facecolor=MUC_ACCENT,
            edgecolor="none",
        )
        ax.add_patch(stripe)

        text_x = left + 0.28
        cursor_y = card_y + card_h - TOP_PAD

        if p["source"]:
            label = p["source"]
            badge_w = _text_width(label) + 0.26
            badge = FancyBboxPatch(
                (text_x, cursor_y - BADGE_ROW_H / 2 - 0.11),
                badge_w,
                0.22,
                boxstyle="round,pad=0,rounding_size=0.11",
                facecolor="#f3dbe0",
                edgecolor="none",
            )
            ax.add_patch(badge)
            ax.text(
                text_x + badge_w / 2,
                cursor_y - BADGE_ROW_H / 2,
                label.strip(),
                fontsize=7,
                color=MUC_ACCENT,
                fontweight="bold",
                ha="center",
                va="center",
            )
        if p["date"]:
            ax.text(
                right - 0.28,
                cursor_y - BADGE_ROW_H / 2,
                p["date"],
                fontsize=7.5,
                color=MUC_GRAY,
                ha="right",
                va="center",
            )

        cursor_y -= BADGE_ROW_H

        if p["title"]:
            ax.text(
                text_x,
                cursor_y,
                p["title"],
                fontsize=10,
                fontweight="bold",
                color=TEXT_DARK,
                va="top",
                linespacing=1.4,
            )
            cursor_y -= (p["title"].count("\n") + 1) * TITLE_LINE_H

        if p["summary"]:
            cursor_y -= SUMMARY_GAP
            ax.text(
                text_x,
                cursor_y,
                p["summary"],
                fontsize=8,
                color=TEXT_BODY,
                va="top",
                linespacing=1.5,
            )

        y = card_y - (gap if idx < n - 1 else 0)

    footer_y = footer_h * 0.55
    ax.plot(
        [left + 0.2, right - 0.2],
        [footer_y + 0.2, footer_y + 0.2],
        color=CARD_BORDER,
        linewidth=1,
    )
    ax.text(
        (left + right) / 2,
        footer_y - 0.02,
        "MucNoticeEngine",
        fontsize=7.5,
        color=MUC_GRAY,
        ha="center",
        va="center",
    )

    fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=MUC_BG, pad_inches=0.25)
    plt.close(fig)
    return save_path
