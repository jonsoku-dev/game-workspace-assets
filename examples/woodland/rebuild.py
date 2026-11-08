"""Rebuild sprites offline from a preexisting image-tool atlas, outside the plugin."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
# Cuts lie inside alpha<128 gutters measured in this exact 1254px atlas.
ASSETS = [
    ("scout", "character", 48, (0, 0, 399, 459), "Woodland scout with a green hood and quiver."),
    ("forager", "character", 48, (399, 0, 822, 459), "Mushroom-hatted woodland forager carrying a basket."),
    ("owl-cartographer", "character", 48, (822, 0, 1254, 459), "Blue-cloaked owl cartographer holding a parchment map."),
    ("compass", "icon", 32, (0, 459, 399, 798), "Brass compass with a cream dial and rust needle."),
    ("acorn", "icon", 24, (399, 459, 822, 798), "Ochre acorn with a textured moss-green cap."),
    ("feather", "icon", 32, (822, 459, 1254, 798), "Warm golden woodland feather."),
    ("lantern", "item", 32, (0, 798, 399, 1254), "Brass lantern with softly colored teal glass."),
    ("field-pack", "item", 32, (399, 798, 822, 1254), "Rust leather field pack with brass buckles and a bedroll."),
    ("hatchet", "item", 32, (822, 798, 1254, 1254), "Steel camping hatchet with an ochre wrapped handle."),
]


def main():
    sibling = Path(sys.executable).parent / "pixel-asset"
    executable = str(sibling) if sibling.is_file() else shutil.which("pixel-asset")
    if not executable:
        raise SystemExit("Install this project first: python -m pip install -e .")
    atlas = Image.open(ROOT / "atlas.png").convert("RGBA")
    assert atlas.size == (1254, 1254), "Crop coordinates require the original atlas"
    alpha = atlas.getchannel("A").point(lambda a: 255 if a >= 128 else 0)
    for x in (399, 822):
        assert alpha.crop((x, 0, x + 1, 1254)).getbbox() is None, "Crop cuts foreground"
    for y in (459, 798):
        assert alpha.crop((0, y, 1254, y + 1)).getbbox() is None, "Crop cuts foreground"
    results = []
    previews = []
    with tempfile.TemporaryDirectory(prefix="woodland-rebuild-") as temporary:
        stage = Path(temporary)
        for name, kind, size, box, prompt in ASSETS:
            draft = stage / f"{name}.png"
            atlas.crop(box).save(draft)
            request = stage / f"{name}.request.json"
            payload = {"schema_version": 1, "kind": kind, "size": size,
                       "prompt": prompt, "profile": str(ROOT / "style.json")}
            if name == "scout":
                payload = json.loads((ROOT / "scout.request.json").read_text())
                payload["profile"] = str(ROOT / payload["profile"])
            request.write_text(json.dumps(payload))
            bundle = stage / name
            subprocess.run([executable, "build", "--request", str(request),
                            "--out", str(bundle), "--draft", str(draft)], check=True)
            report = json.loads((bundle / "validation.json").read_text())
            assert report["passed"], f"{name}: {report}"
            sprite = Image.open(bundle / "asset.png").convert("RGBA")
            assert sprite.size == (size, size)
            previews.append((name, kind, size, sprite.copy()))
            results.append({"name": name, "kind": kind, "size": size,
                            "source_box": list(box), **report})
        sprites = ROOT / "sprites"
        sprites.mkdir(exist_ok=True)
        for name, _, _, sprite in previews:
            sprite.save(sprites / f"{name}.png")
    sheet = Image.new("RGB", (864, 900), "#E8DFCB")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, (name, kind, size, sprite) in enumerate(previews):
        col, row = index % 3, index // 3
        scale = 5 if size == 48 else 6 if size == 32 else 8
        enlarged = sprite.resize((size * scale, size * scale), Image.Resampling.NEAREST)
        x = col * 288 + (288 - enlarged.width) // 2
        y = row * 300 + 10 + (240 - enlarged.height) // 2
        sheet.paste(enlarged, (x, y), enlarged)
        label = f"{name.replace('-', ' ').title()}  /  {size} px"
        bounds = draw.textbbox((0, 0), label, font=font)
        draw.text((col * 288 + (288 - bounds[2]) // 2, row * 300 + 270),
                  label, fill="#453235", font=font)
    sheet.save(ROOT / "contact-sheet.png")
    summary = {"schema_version": 1, "source": "atlas.png", "profile": "style.json",
               "source_origin": "Preexisting generated example; rebuilt locally without network access",
               "resampling": "nearest", "passed": all(r["passed"] for r in results),
               "asset_count": len(results), "assets": results}
    (ROOT / "results.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Rebuilt {len(results)} sprites; all validation checks passed.")


if __name__ == "__main__":
    main()
