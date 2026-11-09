import unittest

from pixel_asset_pipeline.bundle import gif_timeline


class GifTimelineTests(unittest.TestCase):
    def test_cumulative_rounding_does_not_drift(self):
        timeline = gif_timeline([33] * 30)            # 990ms of 33ms frames
        self.assertEqual(sum(d for _, d in timeline), 990)
        self.assertTrue(all(d >= 20 for _, d in timeline))

    def test_no_delay_of_ten_or_less_is_written(self):
        timeline = gif_timeline([5, 120, 8, 4, 200])
        self.assertTrue(all(d >= 20 for _, d in timeline))
        self.assertEqual(sum(d for _, d in timeline), 340)
        self.assertEqual([i for i, _ in timeline], [1, 4])  # short exposures merge into a neighbour

    def test_exact_tick_durations_are_unchanged(self):
        self.assertEqual(gif_timeline([100, 40, 60]), [(0, 100), (1, 40), (2, 60)])


if __name__ == '__main__':
    unittest.main()
