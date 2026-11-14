import unittest

import numpy as np

from recovered.frame_geometry import fit_frame_to_canvas


class FrameGeometryTests(unittest.TestCase):
    def test_landscape_to_portrait_center_crops_without_stretching(self):
        frame = np.zeros((4, 8, 3), dtype=np.uint8)
        for column in range(8):
            frame[:, column] = column * 20
        output = fit_frame_to_canvas(frame, 4, 8)
        self.assertEqual(output.shape, (8, 4, 3))
        # A 2x cover scale produces 16 columns; the centered four-column crop
        # must come from the middle, not from a full-width horizontal squeeze.
        self.assertGreater(int(output[4, 0, 0]), 40)
        self.assertLess(int(output[4, -1, 0]), 100)

    def test_portrait_to_landscape_center_crops_without_stretching(self):
        frame = np.zeros((8, 4, 3), dtype=np.uint8)
        for row in range(8):
            frame[row, :] = row * 20
        output = fit_frame_to_canvas(frame, 8, 4)
        self.assertEqual(output.shape, (4, 8, 3))
        self.assertGreater(int(output[0, 4, 0]), 40)
        self.assertLess(int(output[-1, 4, 0]), 100)

    def test_matching_canvas_returns_original_frame(self):
        frame = np.zeros((8, 4, 3), dtype=np.uint8)
        self.assertIs(fit_frame_to_canvas(frame, 4, 8), frame)

    def test_rejects_invalid_canvas(self):
        with self.assertRaisesRegex(ValueError, "画布"):
            fit_frame_to_canvas(np.zeros((8, 4, 3), dtype=np.uint8), 0, 8)


if __name__ == "__main__":
    unittest.main()
