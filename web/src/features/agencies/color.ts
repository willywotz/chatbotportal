/** Sensible default swatch used whenever a color value can't be parsed. */
export const DEFAULT_HEX_COLOR = "#2563eb";

const HSL_RE = /^hsl\(\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)%\s*\)$/i;
const HEX_RE = /^#[0-9a-f]{6}$/i;

/** Parses a `hsl(H S% L%)` string into a `#rrggbb` hex string. */
export function hslToHex(input: string): string {
  const match = input.match(HSL_RE);
  if (!match) return DEFAULT_HEX_COLOR;

  const h = Number(match[1]);
  const s = Number(match[2]) / 100;
  const l = Number(match[3]) / 100;
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;

  let [r, g, b] = [0, 0, 0];
  if (h < 60) [r, g, b] = [c, x, 0];
  else if (h < 120) [r, g, b] = [x, c, 0];
  else if (h < 180) [r, g, b] = [0, c, x];
  else if (h < 240) [r, g, b] = [0, x, c];
  else if (h < 300) [r, g, b] = [x, 0, c];
  else [r, g, b] = [c, 0, x];

  const toHex = (v: number) => Math.round((v + m) * 255).toString(16).padStart(2, "0");
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

/** Returns a valid `#rrggbb` for any legacy (hsl) or hex color, or the default. */
export function toHexColor(value: string | undefined | null): string {
  if (!value) return DEFAULT_HEX_COLOR;
  const trimmed = value.trim();
  if (HEX_RE.test(trimmed)) return trimmed.toLowerCase();
  if (/^hsl\(/i.test(trimmed)) return hslToHex(trimmed);
  return DEFAULT_HEX_COLOR;
}
