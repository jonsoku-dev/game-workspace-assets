import json
import unittest

from PIL import Image, ImageDraw

from pixel_asset_pipeline.raster import process, validate


PALETTE = [(0, 0, 0), (255, 255, 255), (200, 40, 40)]


class RasterTests(unittest.TestCase):
    def draft(self):
        image = Image.new("RGBA", (40, 30))
        ImageDraw.Draw(image).rectangle((12, 3, 21, 22), fill=(205, 30, 30, 255))
        return image

    def test_character_fits_visible_bounds_with_baseline(self):
        source = self.draft()
        before = source.tobytes()
        result = process(source, 32, PALETTE, 3, "character")
        self.assertEqual(result.getchannel("A").getbbox(), (9, 1, 23, 30))
        self.assertTrue(validate(result, 32, PALETTE, 3, "character")["passed"])
        self.assertEqual(source.tobytes(), before)

    def test_icon_centers_without_outline_growth(self):
        image = Image.new("RGBA", (8, 8))
        ImageDraw.Draw(image).rectangle((2, 2, 5, 5), fill=(*PALETTE[2], 255))
        image.putpixel((3, 3), (*PALETTE[1], 255))
        result = process(image, 8, PALETTE, 3, "icon")
        self.assertEqual(result.getchannel("A").getbbox(), (1, 1, 7, 7))
        self.assertIn((*PALETTE[1], 255), [color for _, color in result.getcolors(64)])
        self.assertTrue(validate(result, 8, PALETTE, 3, "icon")["passed"])

    def test_alpha_palette_limit_and_isolation(self):
        image = self.draft()
        image.putpixel((1, 1), (255, 255, 255, 255))
        image.putpixel((13, 5), (255, 255, 255, 150))
        result = process(image, 32, PALETTE, 1, "item")
        report = validate(result, 32, PALETTE, 1, "item")
        self.assertTrue(report["passed"])
        self.assertEqual(report["metrics"]["color_count"], 1)
        self.assertEqual(report["metrics"]["isolated_pixels"], 0)
        json.dumps(report)

    def test_optional_outline_keeps_tiny_highlight_and_margin(self):
        image = Image.new("RGBA", (8, 8))
        ImageDraw.Draw(image).rectangle((2, 2, 3, 3), fill=(*PALETTE[2], 255))
        image.putpixel((2, 2), (*PALETTE[1], 255))
        result = process(image, 8, PALETTE, 3, "icon", outline=PALETTE[0])
        colors = {color for _, color in result.getcolors(64)}
        self.assertIn((*PALETTE[1], 255), colors)
        self.assertIn((*PALETTE[0], 255), colors)
        self.assertEqual(result.getchannel("A").getbbox(), (1, 1, 7, 7))
        self.assertTrue(validate(result, 8, PALETTE, 3, "icon")["passed"])
        character = process(self.draft(), 32, PALETTE, 2, "character", outline=PALETTE[0])
        self.assertTrue(validate(character, 32, PALETTE, 2, "character")["passed"])
        with self.assertRaises(ValueError):
            process(image, 8, PALETTE, 3, "icon", outline=(1, 2, 3))

    def test_large_draft_and_corner_speck(self):
        image = Image.new("RGBA", (1024, 1024))
        ImageDraw.Draw(image).rectangle((300, 200, 500, 800), fill=(*PALETTE[2], 255))
        image.putpixel((0, 0), (*PALETTE[1], 255))
        result = process(image, 32, PALETTE, 3, "character")
        self.assertTrue(validate(result, 32, PALETTE, 3, "character")["passed"])
        self.assertEqual(result.getchannel("A").getbbox()[3], 30)

    def test_refuses_empty_opaque_and_single_pixel(self):
        for image in (Image.new("RGBA", (8, 8)),
                      Image.new("RGB", (8, 8), "white")):
            with self.assertRaises(ValueError):
                process(image, 16, PALETTE, 3, "icon")
        image = Image.new("RGBA", (8, 8))
        image.putpixel((4, 4), (255, 255, 255, 255))
        with self.assertRaises(ValueError):
            process(image, 16, PALETTE, 3, "icon")

    def test_validation_observes_invalid_input_without_repair(self):
        image = Image.new("RGBA", (9, 8))
        image.putpixel((0, 0), (1, 2, 3, 100))
        before = image.tobytes()
        report = validate(image, 8, PALETTE, 3, "icon")
        self.assertFalse(report["passed"])
        for check in ("size", "binary_alpha", "palette", "isolated_ratio", "clear_edges"):
            self.assertFalse(report["checks"][check], check)
        self.assertEqual(before, image.tobytes())

    def test_isolated_ratio_is_strictly_below_three_percent(self):
        image = Image.new("RGBA", (32, 32))
        draw = ImageDraw.Draw(image)
        draw.rectangle((2, 2, 10, 11), fill=(0, 0, 0, 255))
        draw.line((2, 12, 8, 12), fill=(0, 0, 0, 255))
        for point in ((20, 20), (23, 23), (26, 26)):
            image.putpixel(point, (0, 0, 0, 255))
        report = validate(image, 32, PALETTE, 3, "icon")
        self.assertEqual(report["metrics"]["isolated_ratio"], 0.03)
        self.assertFalse(report["checks"]["isolated_ratio"])
        image.putpixel((26, 26), (0, 0, 0, 0))
        self.assertTrue(validate(image, 32, PALETTE, 3, "icon")["passed"])

    def test_empty_opaque_and_color_limit_validation(self):
        empty = validate(Image.new("RGBA", (8, 8)), 8, PALETTE, 3, "item")
        self.assertFalse(empty["checks"]["nonempty"])
        opaque = validate(Image.new("RGBA", (8, 8), "white"), 8, PALETTE, 3, "item")
        self.assertFalse(opaque["checks"]["transparency"])
        image = process(self.draft(), 16, PALETTE, 3, "item")
        image.putpixel((7, 7), (*PALETTE[1], 255))
        self.assertFalse(validate(image, 16, PALETTE, 1, "item")["checks"]["color_limit"])

    def test_rejects_invalid_options_and_tiles(self):
        for size, palette, limit, kind in ((7, PALETTE, 3, "icon"),
                                          (512, PALETTE, 3, "icon"),
                                          (16, [], 3, "icon"),
                                          (16, [(256, 0, 0)], 1, "icon"),
                                          (16, PALETTE, 0, "icon"),
                                          (16, PALETTE, 3, "tile")):
            with self.assertRaises(ValueError):
                process(self.draft(), size, palette, limit, kind)


if __name__ == "__main__":
    unittest.main()
