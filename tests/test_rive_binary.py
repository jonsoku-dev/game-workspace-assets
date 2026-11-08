import struct
import unittest
from io import BytesIO

from PIL import Image

from pixel_asset_pipeline.rive_binary import bake


def png(color="red", size=(16, 16)):
    output = BytesIO()
    Image.new("RGBA", size, color).save(output, format="PNG")
    return output.getvalue()


def objects(data):
    """Read the small schema subset to assert exported public wire contracts."""
    stream = BytesIO(data)

    def uint():
        value = shift = 0
        while True:
            byte = stream.read(1)[0]
            value |= (byte & 127) << shift
            if byte < 128:
                return value
            shift += 7

    assert stream.read(4) == b"RIVE"
    assert (uint(), uint(), uint(), uint()) == (7, 0, 0, 0)
    result = []
    while stream.tell() < len(data):
        kind, properties = uint(), {}
        while key := uint():
            if key in {4, 55, 138, 203, 212}:
                value = stream.read(uint())
            elif key in {7, 8, 18, 70, 140, 157, 207, 208, 380, 381}:
                value = struct.unpack("<f", stream.read(4))[0]
            else:
                value = uint()
            properties[key] = value
        result.append((kind, properties))
    return result


class RiveBinaryTests(unittest.TestCase):
    def test_self_contained_deterministic_assets_and_exact_timing(self):
        red, green = png(), png("lime")
        actions = [("idle", True, [(red, 101), (red, 2), (green, 202)]),
                   ("attack", False, [(green, 77), (red, 123)])]
        binary = bake(16, 16, actions)
        self.assertEqual(binary, bake(16, 16, actions))
        decoded = objects(binary)
        self.assertEqual([p[212] for kind, p in decoded if kind == 106], [red, green])
        self.assertEqual(sum(kind == 100 for kind, _ in decoded), 2)
        animations = [p for kind, p in decoded if kind == 31]
        self.assertEqual([(p[55], p[56], p[57], p[59]) for p in animations],
                         [(b"idle", 1000, 305, 1), (b"attack", 1000, 200, 0)])
        self.assertIn((30, {67: 103, 68: 0, 70: 0.0}), decoded)
        self.assertIn((30, {67: 103, 68: 0, 70: 1.0}), decoded)
        self.assertEqual([p[151] for kind, p in decoded if kind == 65], [3, 3, 4])
        self.assertEqual([p[157] for kind, p in decoded if kind == 70], [0.0, 1.0])
        self.assertEqual([p[149] for kind, p in decoded if kind == 61], [0, 1])

    def test_each_action_explicitly_resets_every_image(self):
        decoded = objects(bake(16, 16, [("a", True, [(png(), 10)]),
                                       ("b", False, [(png("blue"), 10)])]))
        timelines = []
        current = None
        for kind, properties in decoded:
            if kind == 31:
                current = []
                timelines.append(current)
            elif kind == 30:
                current.append(properties)
        self.assertEqual(timelines, [
            [{67: 0, 68: 0, 70: 1.0}, {67: 0, 68: 0, 70: 0.0}],
            [{67: 0, 68: 0, 70: 0.0}, {67: 0, 68: 0, 70: 1.0}],
        ])

    def test_rejects_invalid_inputs(self):
        image = png()
        cases = [
            (0, 16, [("idle", True, [(image, 1)])]),
            (16, 16, []),
            (16, 16, [("", True, [(image, 1)])]),
            (16, 16, [("idle", True, [])]),
            (16, 16, [("idle", 1, [(image, 1)])]),
            (16, 16, [("idle", True, [(image, 0)])]),
            (16, 16, [("idle", True, [(image, 1.5)])]),
            (16, 16, [("idle", True, [(image, True)])]),
            (16, 16, [("idle", True, [(image, 2**24 + 1)])]),
            (16, 16, [("idle", True, [(b"not a PNG", 1)])]),
            (16, 16, [("idle", True, [(png(size=(8, 8)), 1)])]),
            (16, 16, [("idle", True, [(image, 1)]), ("idle", True, [(image, 1)])]),
        ]
        for args in cases:
            with self.subTest(args=args[:2], actions=[a[0] for a in args[2]]):
                with self.assertRaises(ValueError):
                    bake(*args)


if __name__ == "__main__":
    unittest.main()
