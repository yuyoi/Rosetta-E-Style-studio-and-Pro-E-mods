"""PRO-E Studio icon in the Rosetta LCD splash look (like the OCTA-CAPTURE boot screen): a white backlit LCD with
blue-violet pixels, the hex girl + ROSETTA splash on top and E STYLE STUDIO under it, in a dark bezel + chrome rim.

  py -3.11 make_icon_lcd.py            -> candidates sheet (assets/appicon_lcd/sheet.png)
  py -3.11 make_icon_lcd.py PICK       -> assets/app_icon.png + assets/rosetta_proe.ico
"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
SPLASH = os.path.join(HERE, 'assets', 'icon_src', 'rosetta_splash_128x64.png')   # white = ink
OUT = os.path.join(HERE, 'assets', 'appicon_lcd')
S, RIM = 1024, 46
SILVER = [(0, (244, 246, 248)), (0.18, (185, 190, 196)), (0.45, (226, 229, 232)), (0.62, (140, 146, 153)), (1, (214, 217, 221))]
INK, BG, BG_EDGE = (82, 70, 190), (236, 239, 244), (196, 202, 212)


def text_bits(text, w, h, size, font='consolab.ttf'):
    """1-bit text, centred in w x h (no anti-aliasing = LCD pixels)"""
    im = Image.new('1', (w, h), 0)
    d = ImageDraw.Draw(im)
    d.fontmode = '1'
    f = ImageFont.truetype(font, size)
    l, t, r, b = d.textbbox((0, 0), text, font=f)
    d.text(((w - (r - l)) / 2 - l, (h - (b - t)) / 2 - t), text, font=f, fill=1)
    return np.asarray(im, dtype=bool)


def screen(kind):
    """the LCD content as a bool pixel array"""
    sp = np.asarray(Image.open(SPLASH).convert('L')) > 127            # 128 x 64
    if kind == 'A':                                                     # splash + E STYLE / STUDIO
        px = np.zeros((112, 128), bool)
        px[0:64] = sp
        px[66:88] = text_bits('E STYLE', 128, 22, 21)
        px[88:110] = text_bits('STUDIO', 128, 22, 21)
    elif kind == 'B':                                                   # splash + one line E STYLE STUDIO
        px = np.zeros((84, 128), bool)
        px[0:64] = sp
        px[66:82] = text_bits('E STYLE STUDIO', 128, 16, 13)
    elif kind == 'C':                                                   # girl only (no ROSETTA word) + big E STYLE
        px = np.zeros((102, 128), bool)
        px[0:42] = sp[0:42]
        px[44:74] = text_bits('E STYLE', 128, 30, 28)
        px[74:100] = text_bits('STUDIO', 128, 26, 24)
    else:                                                               # D: the OCTA splash as it is
        px = sp.copy()
    return px


def lcd(px, size):
    """pixel array -> a backlit LCD picture: square pixels with thin row/column gaps, faint ghost grid, glow"""
    h, w = px.shape
    cell = size // max(w, h)
    pad_x, pad_y = (size // cell - w) // 2, (size // cell - h) // 2     # the whole glass is lit, content centred
    px = np.pad(px, ((pad_y, size // cell - h - pad_y), (pad_x, size // cell - w - pad_x)))
    h, w = px.shape
    W, H = w * cell, h * cell
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.hypot((xx - W / 2) / (W / 2), (yy - H / 2) / (H / 2)) / 1.414
    bg = np.array(BG, float) * (1 - r[..., None] * 0.25) + np.array(BG_EDGE, float) * (r[..., None] * 0.25)
    img = bg.copy()
    on = np.kron(px, np.ones((cell, cell), bool))
    gap = (yy % cell == cell - 1) | (xx % cell == cell - 1)            # the dot-matrix gaps between pixels
    ink = np.array(INK, float)
    img[on & ~gap] = ink
    img[on & gap] = ink * 0.55 + bg[on & gap] * 0.45
    ghost = ~on & ~gap
    img[ghost] = img[ghost] * 0.985                                    # unlit pixels slightly visible, like real LCD
    out = Image.fromarray(img.clip(0, 255).astype(np.uint8))
    return out.resize((size, size), Image.NEAREST)


def gradient():
    g = Image.new('RGB', (1, S))
    for y in range(S):
        t = y / (S - 1)
        for (t0, c0), (t1, c1) in zip(SILVER, SILVER[1:]):
            if t0 <= t <= t1:
                k = (t - t0) / (t1 - t0)
                g.putpixel((0, y), tuple(round(a + (b - a) * k) for a, b in zip(c0, c1)))
                break
    return g.resize((S, S))


def build(kind):
    out = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    m = Image.new('L', (S, S), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, S - 1, S - 1), radius=190, fill=255)
    out.paste(gradient(), (0, 0), m)
    bez = 40                                                            # dark bezel like her panel around the LCD
    m2 = Image.new('L', (S, S), 0)
    ImageDraw.Draw(m2).rounded_rectangle((RIM, RIM, S - 1 - RIM, S - 1 - RIM), radius=150, fill=255)
    out.paste(Image.new('RGB', (S, S), (22, 24, 30)), (0, 0), m2)
    inner = S - 2 * (RIM + bez)
    glass = lcd(screen(kind), inner)
    m3 = Image.new('L', (inner, inner), 0)
    ImageDraw.Draw(m3).rounded_rectangle((0, 0, inner - 1, inner - 1), radius=40, fill=255)
    out.paste(glass, (RIM + bez, RIM + bez), m3)
    d = ImageDraw.Draw(out)                                             # bevel: light top-left, dark bottom-right
    o = RIM + bez
    d.rounded_rectangle((o - 10, o - 10, S - o + 9, S - o + 9), radius=48, outline=(150, 156, 166, 255), width=10)
    d.rounded_rectangle((RIM - 4, RIM - 4, S - RIM + 3, S - RIM + 3), radius=154, outline=(0, 0, 0, 200), width=8)
    return out


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    if len(sys.argv) > 1:
        ic = build(sys.argv[1])
        a = os.path.join(HERE, 'assets')
        ic.save(os.path.join(a, 'app_icon.png'))
        ic.save(os.path.join(a, 'rosetta_proe.ico'), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        prev = Image.new('RGB', (560, 300), (30, 32, 36))
        x = 10
        for sz in (256, 128, 48, 32, 16):
            rr = ic.resize((sz, sz), Image.LANCZOS)
            prev.paste(rr, (x, 20), rr)
            x += sz + 12
        prev.save(os.path.join(a, 'app_icon_preview.png'))
        print('ok')
    else:
        ims = [build(k) for k in 'ABCD']
        sheet = Image.new('RGB', (4 * 340 + 20, 420), (20, 20, 24))
        dd = ImageDraw.Draw(sheet)
        for i, im in enumerate(ims):
            t = im.resize((320, 320), Image.LANCZOS)
            sheet.paste(t, (20 + i * 340, 20), t)
            sm = im.resize((48, 48), Image.LANCZOS)
            sheet.paste(sm, (20 + i * 340 + 200, 352), sm)
            dd.text((20 + i * 340 + 140, 360), 'ABCD'[i], fill=(240, 240, 240), font=ImageFont.truetype('arialbd.ttf', 30))
        sheet.save(os.path.join(OUT, 'sheet.png'))
        print(os.path.join(OUT, 'sheet.png'))
