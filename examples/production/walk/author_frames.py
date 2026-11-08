"""Author four native-pixel poses; no image generation, scaling, or cleanup."""
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parents[1] / "codex-scout-styled" / "asset.png"
INK = (39, 22, 37, 255)
PANTS = (70, 74, 48, 255)
GREEN = (102, 115, 63, 255)
LEATHER = (108, 58, 48, 255)
LIGHT = (170, 82, 51, 255)
DARK = (69, 50, 53, 255)


def leg(draw, pants, boot, seam, light, near):
    draw.polygon(pants, fill=PANTS, outline=INK)
    draw.line(seam, fill=GREEN if near else DARK, width=2)
    draw.polygon(boot, fill=LEATHER if near else DARK, outline=INK)
    draw.line(light, fill=LIGHT if near else LEATHER, width=2)


def author():
    with Image.open(SOURCE) as image:
        source = image.convert("RGBA")
    # Each limb has its own knee, cuff, and toe. The near boot carries the highlight.
    poses = [
        [([(20, 37), (24, 37), (22, 40), (19, 42), (16, 41)],
          [(16, 40), (20, 41), (20, 43), (22, 44), (22, 45), (14, 45), (14, 43)],
          [(21, 38), (18, 40)], [(16, 43), (19, 44)], False),
         ([(26, 37), (30, 37), (32, 40), (34, 42), (30, 43), (27, 40)],
          [(30, 41), (34, 41), (34, 43), (37, 44), (37, 45), (29, 45), (29, 43)],
          [(29, 38), (31, 40)], [(31, 43), (34, 44)], True)],
        [([(20, 37), (24, 37), (23, 40), (21, 42), (17, 42), (17, 39)],
          [(17, 40), (21, 40), (22, 42), (20, 43), (16, 43), (15, 42)],
          [(21, 38), (19, 40)], [(17, 41), (20, 42)], False),
         ([(26, 37), (30, 37), (29, 40), (29, 42), (25, 42), (24, 40)],
          [(25, 41), (29, 41), (29, 43), (32, 44), (32, 45), (24, 45), (24, 43)],
          [(27, 38), (27, 40)], [(26, 43), (29, 44)], True)],
        [([(20, 37), (24, 37), (28, 39), (32, 42), (29, 43), (24, 40)],
          [(29, 41), (33, 41), (33, 43), (36, 44), (36, 45), (28, 45), (28, 43)],
          [(23, 38), (28, 40)], [(30, 43), (33, 44)], False),
         ([(26, 37), (30, 37), (27, 40), (24, 42), (20, 42), (21, 40)],
          [(20, 41), (24, 41), (23, 43), (25, 44), (25, 45), (17, 45), (17, 43)],
          [(27, 38), (23, 40)], [(20, 43), (22, 44)], True)],
        [([(20, 37), (24, 37), (24, 40), (24, 42), (20, 42), (19, 40)],
          [(20, 41), (24, 41), (24, 43), (27, 44), (27, 45), (19, 45), (19, 43)],
          [(22, 38), (22, 40)], [(21, 43), (24, 44)], False),
         ([(26, 37), (30, 37), (33, 39), (32, 42), (28, 42), (28, 40)],
          [(29, 40), (33, 40), (34, 42), (32, 43), (28, 43), (27, 42)],
          [(29, 38), (31, 40)], [(29, 41), (32, 42)], True)],
    ]
    folder = ROOT / "frames"
    folder.mkdir(exist_ok=True)
    frames = []
    for index, pose in enumerate(poses):
        frame = source.copy()
        draw = ImageDraw.Draw(frame)
        draw.rectangle((0, 38, 47, 47), fill=(0, 0, 0, 0))
        for limb in pose:
            leg(draw, *limb)
        # Retain the cloak's hanging edge above the back leg.
        frame.paste(source.crop((0, 38, 18, 40)), (0, 38))
        assert frame.getbbox()[3] == 46
        assert frame.crop((0, 0, 48, 37)).tobytes() == source.crop((0, 0, 48, 37)).tobytes()
        assert {color for _, color in frame.getcolors()} <= {color for _, color in source.getcolors()}
        frame.save(folder / f"{index + 1:02}.png")
        frames.append(frame)
    assert len({frame.tobytes() for frame in frames}) == 4


if __name__ == "__main__":
    author()
