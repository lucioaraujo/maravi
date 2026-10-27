"""Testes leves do ensaio por padrões espectrais, sem tocar no áudio do autor."""
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from explore_timbre_components import component_masks


class TimbreComponentsTests(unittest.TestCase):
    def test_masks_partition_positive_spectrogram_bins(self):
        templates = np.array([[1.0, 0.1], [0.2, 1.0]], dtype=np.float32)
        activations = np.array([[0.8, 0.4], [0.3, 0.6]], dtype=np.float32)
        masks = component_masks(templates, activations)
        self.assertEqual(masks.shape, (2, 2, 2))
        self.assertTrue(np.all(masks >= 0))
        np.testing.assert_allclose(masks.sum(axis=0), np.ones((2, 2)), atol=1e-6)


if __name__ == "__main__":
    unittest.main()
