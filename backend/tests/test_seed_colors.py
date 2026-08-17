"""Seed agency colors must be hex, not hsl() — the color picker (item 2) only
understands hex."""
import re

from app.services.seed import DEFAULT_AGENCIES

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def test_seed_agency_colors_are_hex():
    for agency in DEFAULT_AGENCIES:
        assert _HEX_RE.match(agency["color"]), f"{agency['name']!r} color is not hex: {agency['color']!r}"
