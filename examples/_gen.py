"""
Faithful Python port of the tileset-base-gen rendering engine, used only to
generate the example PNGs in this folder. The real tool is index.html; this
mirrors its math so the examples match what the tool produces.

Run:  python examples/_gen.py
"""
import math
from PIL import Image

LAYOUT = [
    [4, 10, 13, 12],
    [9, 14, 15, 7],
    [2, 3, 11, 5],
    [0, 8, 6, 1],
]
QUADRANTS = [
    {"bit": 1, "col": 0, "row": 0},
    {"bit": 2, "col": 1, "row": 0},
    {"bit": 4, "col": 0, "row": 1},
    {"bit": 8, "col": 1, "row": 1},
]
OVERLAP = 0.09
MASK32 = 0xFFFFFFFF


def bit_at(col, row):
    if col < 0 or col > 1 or row < 0 or row > 1:
        return -1
    return 1 << (row * 2 + col)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(t):
    return t * t * (3 - 2 * t)


def smin(a, b, k):
    if k <= 0:
        return min(a, b)
    h = clamp(0.5 + (0.5 * (b - a)) / k, 0, 1)
    return lerp(b, a, h) - k * h * (1 - h)


def imul(a, b):
    return ((a & MASK32) * (b & MASK32)) & MASK32


def hash2(x, y, seed):
    n = imul(int(x) & MASK32, 374761393) ^ imul(int(y) & MASK32, 668265263) ^ imul(int(seed) & MASK32, 2246822519)
    n &= MASK32
    n = imul(n ^ (n >> 13), 1274126177)
    n &= MASK32
    return ((n ^ (n >> 16)) & MASK32) / 4294967295


def value_noise(x, y, seed):
    xi = math.floor(x)
    yi = math.floor(y)
    tx = smoothstep(x - xi)
    ty = smoothstep(y - yi)
    a = hash2(xi, yi, seed)
    b = hash2(xi + 1, yi, seed)
    c = hash2(xi, yi + 1, seed)
    d = hash2(xi + 1, yi + 1, seed)
    return lerp(lerp(a, b, tx), lerp(c, d, tx), ty)


def fbm(x, y, seed):
    total = 0.0
    amp = 0.55
    freq = 1.0
    norm = 0.0
    for i in range(4):
        total += value_noise(x * freq, y * freq, seed + i * 71) * amp
        norm += amp
        amp *= 0.5
        freq *= 2
    return total / norm


def rounded_box_sdf(px, py, l, t, r, b, radius):
    cx = (l + r) * 0.5
    cy = (t + b) * 0.5
    hx = (r - l) * 0.5
    hy = (b - t) * 0.5
    rad = min(radius, hx, hy)
    qx = abs(px - cx) - (hx - rad)
    qy = abs(py - cy) - (hy - rad)
    outside = math.hypot(max(qx, 0), max(qy, 0))
    inside = min(max(qx, qy), 0)
    return outside + inside - rad


def mask_sdf(mask, x, y, tile, radius, roughness):
    half = tile * 0.5
    ov = OVERLAP * tile
    ext = radius + roughness + 1
    dist = None
    for q in QUADRANTS:
        if (mask & q["bit"]) == 0:
            continue
        l = (0 - ext) if q["col"] == 0 else half - ov
        r = (tile + ext) if q["col"] == 1 else half + ov
        t = (0 - ext) if q["row"] == 0 else half - ov
        b = (tile + ext) if q["row"] == 1 else half + ov
        d = rounded_box_sdf(x, y, l, t, r, b, radius)
        dist = d if dist is None else smin(dist, d, radius)
    return 9999 if dist is None else dist


def mask_void_sdf(mask, x, y, tile, radius):
    half = tile * 0.5
    ov = OVERLAP * tile

    def filled(nb):
        return nb != -1 and (mask & nb) != 0

    dist = float("inf")
    for q in QUADRANTS:
        if (mask & q["bit"]) != 0:
            continue
        l = 0 if q["col"] == 0 else (half + ov if filled(bit_at(q["col"] - 1, q["row"])) else half)
        r = tile if q["col"] == 1 else (half - ov if filled(bit_at(q["col"] + 1, q["row"])) else half)
        t = 0 if q["row"] == 0 else (half + ov if filled(bit_at(q["col"], q["row"] - 1)) else half)
        b = tile if q["row"] == 1 else (half - ov if filled(bit_at(q["col"], q["row"] + 1)) else half)
        dist = min(dist, rounded_box_sdf(x, y, l, t, r, b, radius))
    return dist


def hex_rgb(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def mix(a, b, t):
    t = clamp(t, 0, 1)
    return (round(lerp(a[0], b[0], t)), round(lerp(a[1], b[1], t)), round(lerp(a[2], b[2], t)))


def shade(c, amt):
    return (clamp(round(c[0] + amt), 0, 255), clamp(round(c[1] + amt), 0, 255), clamp(round(c[2] + amt), 0, 255))


def axis_mapper(tile, g):
    if g == 0:
        return lambda o: (o // tile, o % tile)
    period = tile + g

    def m(o):
        mm = o % period
        if mm < g:
            return (-1, 0)
        return (o // period, mm - g)

    return m


def render(cfg):
    tile = cfg["tileSize"]
    radius = cfg.get("cornerRadius", 4) * (tile / 32)
    rough_in = cfg.get("edgeRoughness", 6) * (tile / 32)
    roughness = 0 if cfg.get("edgeStyle", "rough") == "clean" else rough_in
    noise_size = max(1, cfg.get("edgeFrequency", 5))
    base = hex_rgb(cfg.get("baseColor", "#73ad38"))
    edge = hex_rgb(cfg.get("edgeColor", "#2f662d"))
    edge_fade = cfg.get("edgeFade", 4) * (tile / 32)
    tex = cfg.get("textureNoise", 10)
    fleck = cfg.get("fleckAmount", 6)
    seed = cfg.get("seed", 31415) or 1
    white = cfg.get("whiteBackground", True)
    flecks_on = cfg.get("pixelFlecks", True)
    g = 1 if cfg.get("showGrid", True) else 0
    shades = max(2, round(cfg.get("shades", 4)))
    ramp = [mix(base, edge, i / (shades - 1)) for i in range(shades)]

    size = tile * 4 + g * 5
    bg = (255, 255, 255, 255) if white else (0, 0, 0, 0)
    map_axis = axis_mapper(tile, g)
    img = Image.new("RGBA", (size, size))
    px = img.load()

    for py in range(size):
        ay = map_axis(py)
        for pxx in range(size):
            ax = map_axis(pxx)
            if ax[0] < 0 or ay[0] < 0:
                px[pxx, py] = (0, 0, 0, 255)
                continue
            col, row = ax[0], ay[0]
            mask = LAYOUT[row][col]
            if mask == 0:
                px[pxx, py] = bg
                continue
            lx = ax[1] + 0.5
            ly = ay[1] + 0.5
            cx = col * tile + ax[1]
            cy = row * tile + ay[1]
            sdf = mask_sdf(mask, lx, ly, tile, radius, roughness)
            edge_noise = (fbm(cx / noise_size, cy / noise_size, seed + mask * 113) - 0.5) * roughness
            if sdf + edge_noise > 0:
                px[pxx, py] = bg
                continue
            fleck_seed = hash2(math.floor(cx / 2), math.floor(cy / 2), seed + mask * 17)
            fleck_on = flecks_on and fleck > 0 and fleck_seed > 1 - fleck / 250
            depth = mask_void_sdf(mask, lx, ly, tile, radius) - edge_noise
            amount = clamp(1 - depth / edge_fade, 0, 1) if edge_fade > 0 else 0
            level = amount * (shades - 1)
            level += (fbm(cx / 4.2, cy / 4.2, seed + 809) - 0.5) * (tex / 42) * 4
            if fleck_on:
                level += 2 if hash2(cx, cy, seed + 421) > 0.6 else 1
            color = ramp[clamp(round(level), 0, shades - 1)]
            px[pxx, py] = (color[0], color[1], color[2], 255)
    return img


def save(cfg, name, display_target=720):
    native = render(cfg)
    native.save(f"{name}.png")
    factor = max(1, round(display_target / native.width))
    up = native.resize((native.width * factor, native.height * factor), Image.NEAREST)
    up.save(f"{name}@{factor}x.png")
    print(f"{name}: native {native.width}px, display {up.width}px")


if __name__ == "__main__":
    import os

    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    save({"tileSize": 16, "edgeStyle": "rough", "baseColor": "#73ad38", "edgeColor": "#2f662d",
          "cornerRadius": 2, "edgeRoughness": 4, "edgeFrequency": 5, "edgeFade": 3,
          "textureNoise": 12, "fleckAmount": 6, "seed": 31415, "showGrid": True}, "grass-16px")

    save({"tileSize": 32, "edgeStyle": "clean", "baseColor": "#73ad38", "edgeColor": "#2f662d",
          "cornerRadius": 6, "edgeRoughness": 0, "edgeFrequency": 5, "edgeFade": 4,
          "textureNoise": 8, "fleckAmount": 4, "seed": 31415, "showGrid": True}, "grass-clean-rounded")

    save({"tileSize": 16, "edgeStyle": "rough", "baseColor": "#8a8f8b", "edgeColor": "#565b5f",
          "cornerRadius": 1, "edgeRoughness": 5, "edgeFrequency": 4, "edgeFade": 5,
          "textureNoise": 20, "fleckAmount": 12, "seed": 7, "showGrid": True}, "stone-16px")

    # Stone base at 32px, no grid: the "before" that pairs with the AI-detailed
    # cobblestone in the README and on the marketing page.
    save({"tileSize": 32, "edgeStyle": "rough", "baseColor": "#8f928d", "edgeColor": "#54585a",
          "cornerRadius": 1, "edgeRoughness": 5, "edgeFrequency": 4, "edgeFade": 6,
          "textureNoise": 22, "fleckAmount": 14, "seed": 7, "showGrid": False}, "cobblestone-base")

    save({"tileSize": 32, "edgeStyle": "clean", "baseColor": "#a67844", "edgeColor": "#5a3f2c",
          "cornerRadius": 0, "edgeRoughness": 0, "edgeFrequency": 5, "edgeFade": 0,
          "textureNoise": 6, "fleckAmount": 0, "seed": 3, "showGrid": True}, "wood-clean-32px")

    # Pure mask shape (no colour effects) for the "how it works" anatomy diagram.
    save({"tileSize": 32, "edgeStyle": "clean", "baseColor": "#73ad38", "edgeColor": "#73ad38",
          "cornerRadius": 0, "edgeRoughness": 0, "edgeFrequency": 5, "edgeFade": 0,
          "textureNoise": 0, "fleckAmount": 0, "seed": 1, "showGrid": True}, "anatomy-15-piece")
