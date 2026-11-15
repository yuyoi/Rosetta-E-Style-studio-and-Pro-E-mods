"""PRO-E Studio icon, layout C (hex girl + big E STYLE / STUDIO) in the old blue grid colours:
navy glass, glowing cyan/green LED pixels, optionally the sequencer-grid picture behind them.

  py -3.11 make_icon_c.py          -> candidates sheet (assets/appicon_lcd/sheet_c.png)
  py -3.11 make_icon_c.py PICK     -> assets/app_icon.png + assets/rosetta_proe.ico
"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import make_icon_lcd as L
import make_icon as G

HERE = os.path.dirname(os.path.abspath(__file__))
GRID = os.path.join(HERE, 'assets', 'icon_src', 'seq_grid.png')  # SwarmUI flux1-schnell render
NAVY, NAVY_EDGE = (14, 26, 70), (6, 12, 36)
CYAN, GREEN, BLUE, WHITE = (70, 235, 255), (60, 235, 110), (40, 140, 255), (235, 248, 255)


def layers():
    """C content split in two masks: girl rows, text rows (128 wide, 102 high)"""
    px = L.screen('C')
    girl = np.zeros_like(px); girl[0:44] = px[0:44]
    text = np.zeros_like(px); text[44:] = px[44:]
    return girl, text


def backdrop(kind, size):
    if kind in ('3', '4'):                                     # the sequencer pic behind, GBA pixels, dimmed
        im = Image.open(GRID).convert('RGB')
        w, h = im.size
        c = int(w * 0.14)
        im = G.gba(im.crop((c, c, w - c, h - c)).resize((size, size), Image.LANCZOS))
        a = np.asarray(im, float) * (0.42 if kind == '3' else 0.62)
        return a
    yy, xx = np.mgrid[0:size, 0:size]
    r = np.clip(np.hypot(xx - size / 2, yy - size / 2) / (size * 0.7), 0, 1)[..., None]
    return np.array(NAVY, float) * (1 - r) + np.array(NAVY_EDGE, float) * r


def glass(kind, size):
    girl, text = layers()
    cols = {'1': (CYAN, CYAN), '2': (CYAN, GREEN), '3': (CYAN, WHITE), '4': (CYAN, None)}[kind]
    h, w = girl.shape
    cell = size // max(w, h)
    n = size // cell
    py, px_ = (n - h) // 2, (n - w) // 2
    pad = lambda m: np.pad(m, ((py, n - h - py), (px_, n - w - px_)))
    girl, text = pad(girl), pad(text)
    big = lambda m: np.kron(m, np.ones((cell, cell), bool))[:size, :size]
    G_, T_ = big(girl), big(text)
    G_ = np.pad(G_, ((0, size - G_.shape[0]), (0, size - G_.shape[1])))
    T_ = np.pad(T_, ((0, size - T_.shape[0]), (0, size - T_.shape[1])))
    yy, xx = np.mgrid[0:size, 0:size]
    gap = (yy % cell == cell - 1) | (xx % cell == cell - 1)
    bg = backdrop(kind, size)
    lit = np.zeros((size, size, 3))
    lit[G_] = cols[0]
    if cols[1]: lit[T_] = cols[1]
    on = G_ | (T_ if cols[1] else False)
    glow = Image.fromarray(lit.astype(np.uint8)).filter(ImageFilter.GaussianBlur(cell * 1.6))
    img = bg + np.asarray(glow, float) * 0.85                  # LED glow on the glass
    if kind in ('1', '2'):
        img[~on & ~gap] += 10                                  # faint unlit dot grid
    img[on & ~gap] = lit[on & ~gap]
    img[on & gap] = lit[on & gap] * 0.5 + img[on & gap] * 0.5
    out = Image.fromarray(img.clip(0, 255).astype(np.uint8))
    if kind == '4':                                            # old bold white label like the grid icon
        G.S = size
        d = ImageDraw.Draw(out)
        y = int(size * 0.47)
        for t, s in (('E STYLE', int(size * 0.17)), ('STUDIO', int(size * 0.15))):
            f = ImageFont.truetype('ariblk.ttf', s)
            d.text(((size - d.textlength(t, font=f)) / 2, y), t, font=f, fill=(255, 255, 255),
                   stroke_width=max(6, s // 9), stroke_fill=(10, 10, 12))
            y += int(s * 1.08)
        G.S = 1024
    return out


def build(kind):
    S, RIM, bez = L.S, L.RIM, 40
    out = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    m = Image.new('L', (S, S), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, S - 1, S - 1), radius=190, fill=255)
    out.paste(L.gradient(), (0, 0), m)
    m2 = Image.new('L', (S, S), 0)
    ImageDraw.Draw(m2).rounded_rectangle((RIM, RIM, S - 1 - RIM, S - 1 - RIM), radius=150, fill=255)
    out.paste(Image.new('RGB', (S, S), (10, 12, 20)), (0, 0), m2)
    inner = S - 2 * (RIM + bez)
    g = glass(kind, inner)
    m3 = Image.new('L', (inner, inner), 0)
    ImageDraw.Draw(m3).rounded_rectangle((0, 0, inner - 1, inner - 1), radius=40, fill=255)
    out.paste(g, (RIM + bez, RIM + bez), m3)
    d = ImageDraw.Draw(out)
    o = RIM + bez
    d.rounded_rectangle((o - 10, o - 10, S - o + 9, S - o + 9), radius=48, outline=(40, 60, 110, 255), width=10)
    d.rounded_rectangle((RIM - 4, RIM - 4, S - RIM + 3, S - RIM + 3), radius=154, outline=(0, 0, 0, 200), width=8)
    return out


if __name__ == '__main__':
    os.makedirs(L.OUT, exist_ok=True)
    if len(sys.argv) > 1:
        ic = build(sys.argv[1])
        a = os.path.join(HERE, 'assets')
        ic.save(os.path.join(a, 'app_icon.png'))
        ic.save(os.path.join(a, 'rosetta_proe.ico'), sizes=[(16, 16), (20, 20), (24, 24), (28, 28), (32, 32), (40, 40), (48, 48), (56, 56), (64, 64), (96, 96), (128, 128), (256, 256)])
        prev = Image.new('RGB', (560, 300), (30, 32, 36))
        x = 10
        for sz in (256, 128, 48, 32, 16):
            rr = ic.resize((sz, sz), Image.LANCZOS)
            prev.paste(rr, (x, 20), rr)
            x += sz + 12
        prev.save(os.path.join(a, 'app_icon_preview.png'))
        print('ok')
    else:
        ks = '1234'
        sheet = Image.new('RGB', (4 * 340 + 20, 420), (20, 20, 24))
        dd = ImageDraw.Draw(sheet)
        for i, k in enumerate(ks):
            im = build(k)
            t = im.resize((320, 320), Image.LANCZOS)
            sheet.paste(t, (20 + i * 340, 20), t)
            sm = im.resize((48, 48), Image.LANCZOS)
            sheet.paste(sm, (20 + i * 340 + 200, 352), sm)
            dd.text((20 + i * 340 + 140, 360), k, fill=(240, 240, 240), font=ImageFont.truetype('arialbd.ttf', 30))
        p = os.path.join(L.OUT, 'sheet_c.png')
        sheet.save(p)
        print(p)
