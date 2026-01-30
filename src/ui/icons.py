"""Generate tray icons programmatically using Pillow."""

from PIL import Image, ImageDraw

ICON_SIZE = 64


def _create_base_icon(fill_color: str, ring_color: str, dot: bool = False, dot_color: str = "white") -> Image.Image:
    """Create a circular icon with optional center dot."""
    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Outer circle
    margin = 4
    draw.ellipse(
        [margin, margin, ICON_SIZE - margin, ICON_SIZE - margin],
        fill=fill_color,
        outline=ring_color,
        width=3,
    )

    # Inner microphone shape (simplified as vertical bar + base)
    cx, cy = ICON_SIZE // 2, ICON_SIZE // 2
    # Mic body
    draw.rounded_rectangle(
        [cx - 6, cy - 14, cx + 6, cy + 4],
        radius=6,
        fill=dot_color,
    )
    # Mic stand arc
    draw.arc(
        [cx - 12, cy - 8, cx + 12, cy + 12],
        start=0, end=180,
        fill=dot_color,
        width=2,
    )
    # Mic stand line
    draw.line([cx, cy + 12, cx, cy + 18], fill=dot_color, width=2)
    # Mic base
    draw.line([cx - 6, cy + 18, cx + 6, cy + 18], fill=dot_color, width=2)

    if dot:
        # Recording indicator dot (top-right)
        draw.ellipse([ICON_SIZE - 18, 2, ICON_SIZE - 4, 16], fill=dot_color)

    return img


def icon_idle() -> Image.Image:
    """Gray icon - app is idle, ready to record."""
    return _create_base_icon(
        fill_color="#5A5A5A",
        ring_color="#404040",
        dot_color="white",
    )


def icon_recording() -> Image.Image:
    """Red icon with pulsing dot - currently recording."""
    return _create_base_icon(
        fill_color="#DC2626",
        ring_color="#991B1B",
        dot=True,
        dot_color="white",
    )


def icon_transcribing() -> Image.Image:
    """Amber/yellow icon - processing transcription."""
    return _create_base_icon(
        fill_color="#D97706",
        ring_color="#92400E",
        dot_color="white",
    )
