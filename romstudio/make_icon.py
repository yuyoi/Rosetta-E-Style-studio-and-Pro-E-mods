"""PRO-E Studio app icon, the OCTA Control recipe: zoom into the art, GBA-screen pixels, chrome rim, bold label.

  py -3.11 make_icon.py RAW.png [out_dir]      -> app_icon.png + rosetta_proe.ico (+ preview)
  py -3.11 make_icon.py --sheet RAW1 RAW2 ...  -> finished candidates side by side (sheet_final.png)
"""
import os, sys
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
S, RIM = 1024, 46
SILVER = [(0, (244, 246, 248)), (0.18, (185, 190, 196)), (0.45, (226, 229, 232)), (0.62, (140, 146, 153)), (1, (214, 217, 221))]


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


def gba(im, px=96):
    """GBA screen: down to px x px, back up with hard edges and a dark grid between the pixels"""
    n = im.size[0]
    small = im.resize((px, px), Image.BOX)
    big = small.resize((n, n), Image.NEAREST)
    d = ImageDraw.Draw(big, 'RGBA')
    step = n / px
    for i in range(1, px):
        x = round(i * step)
        d.line((x, 0, x, n), fill=(0, 0, 0, 70), width=2)
        d.line((0, x, n, x), fill=(0, 0, 0, 70), width=2)
    return big


def label(img, lines, top=True):
    d = ImageDraw.Draw(img)
    y = 110 if top else S - 330
    for text, size in lines:
        f = ImageFont.truetype('ariblk.ttf', size)
        w = d.textlength(text, font=f)
        d.text(((S - w) / 2, y), text, font=f, fill=(255, 255, 255), stroke_width=max(8, size // 9), stroke_fill=(10, 10, 12))
        y += int(size * 1.08)
    return img


def build(raw, crop=0.14):
    im = Image.open(raw).convert('RGB')
    w, h = im.size
    c = int(min(w, h) * crop)
    inner = im.crop((c, c, w - c, h - c)).resize((S - 2 * RIM, S - 2 * RIM), Image.LANCZOS)
    inner = gba(inner)
    out = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    m = Image.new('L', (S, S), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, S - 1, S - 1), radius=190, fill=255)
    out.paste(gradient(), (0, 0), m)
    m2 = Image.new('L', (S, S), 0)
    ImageDraw.Draw(m2).rounded_rectangle((RIM, RIM, S - 1 - RIM, S - 1 - RIM), radius=150, fill=255)
    pane = Image.new('RGB', (S, S))
    pane.paste(inner, (RIM, RIM))
    out.paste(pane, (0, 0), m2)
    d = ImageDraw.Draw(out)
    d.rounded_rectangle((RIM - 4, RIM - 4, S - RIM + 3, S - RIM + 3), radius=154, outline=(0, 0, 0, 200), width=8)
    return label(out, [('E STYLE', 168), ('STUDIO', 150)])


if __name__ == '__main__':
    if sys.argv[1] == '--sheet':
        ims = [build(p).resize((300, 300), Image.LANCZOS) for p in sys.argv[2:]]
        sheet = Image.new('RGB', (len(ims) * 320 + 20, 380), (20, 20, 24))
        dd = ImageDraw.Draw(sheet)
        for i, im in enumerate(ims):
            sheet.paste(im, (20 + i * 320, 20), im)
            dd.text((20 + i * 320 + 140, 330), 'ABCDEFGH'[i], fill=(240, 240, 240), font=ImageFont.truetype('arialbd.ttf', 30))
        out = os.path.join(os.path.dirname(sys.argv[2]), 'sheet_final.png')
        sheet.save(out)
        print(out)
    else:
        od = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, 'assets')
        ic = build(sys.argv[1])
        ic.save(os.path.join(od, 'app_icon.png'))
        ic.save(os.path.join(od, 'rosetta_proe.ico'), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        prev = Image.new('RGB', (560, 300), (30, 32, 36))
        x = 10
        for sz in (256, 128, 48, 32, 16):
            r = ic.resize((sz, sz), Image.LANCZOS)
            prev.paste(r, (x, 20), r)
            x += sz + 12
        prev.save(os.path.join(od, 'app_icon_preview.png'))
        print('ok')
