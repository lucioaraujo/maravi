"""Confere a estimativa de F0 em áudio controlado, sem corrigir a pauta."""
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from audit_vocal_pitch import audit_window, parse_window


class VocalPitchAuditTests(unittest.TestCase):
    def test_sine_a4_flags_octave_hypothesis_without_rewriting_note(self):
        with tempfile.TemporaryDirectory(prefix="maravi-f0-test-") as folder:
            path = Path(folder) / "source.wav"
            sample_rate = 22050
            time = np.arange(sample_rate, dtype=np.float32) / sample_rate
            signal = (0.25 * np.sin(2 * np.pi * 440 * time)).astype(np.float32)
            sf.write(path, signal, sample_rate)
            note = SimpleNamespace(start=0.1, end=0.9, pitch=81)
            rows = audit_window(path, [note], 0.0, 1.0)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "oitava_suspeita")
            self.assertAlmostEqual(rows[0]["estimated_midi_pitch"], 69, delta=0.3)
            self.assertEqual(note.pitch, 81)

    def test_window_cap_prevents_unbounded_single_analysis(self):
        self.assertEqual(parse_window("10:25"), (10.0, 25.0))
        with self.assertRaises(Exception):
            parse_window("10:26")


if __name__ == "__main__":
    unittest.main()
