"""Pré-análise curta: limites e ausência honesta de inferência instrumental."""
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import wave

from tools.key_detection import detect_key, detect_key_from_weights, pitch_class_durations


ROOT = Path(__file__).resolve().parent.parent


class AnalyzeAudioPreviewTests(unittest.TestCase):
    def _run_preview(self, path: Path, channel: str = "mix") -> dict:
        environment = os.environ.copy()
        environment.update(OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
                           NUMBA_NUM_THREADS="1")
        run = subprocess.run(
            [sys.executable, "-B", str(ROOT / "tools/analyze_audio_preview.py"),
             str(path), "--channel", channel],
            capture_output=True, text=True, timeout=45, env=environment,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout)

    def test_key_from_weights_is_same_calculation_as_melody(self):
        melody = [
            {"pitch": pitch, "start": index, "end": index + 0.5}
            for index, pitch in enumerate((60, 64, 67, 72, 64, 67))
        ]
        self.assertEqual(detect_key(melody),
                         detect_key_from_weights(pitch_class_durations(melody)))

    def test_silent_stereo_preview_does_not_invent_music(self):
        with tempfile.TemporaryDirectory(prefix="maravi-preview-test-") as folder:
            path = Path(folder) / "stereo.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(2)
                wav.setsampwidth(2)
                wav.setframerate(8000)
                wav.writeframes(struct.pack("<hh", 0, 0) * 24000)
            result = self._run_preview(path, "left")
            self.assertEqual(result["channels"], 2)
            self.assertEqual(result["selected_channel"], "left")
            self.assertEqual(result["sample_seconds"], 3.0)
            for field in ("bpm", "key_name", "instrument", "meter"):
                self.assertIsNone(result[field])

    def test_tonal_excerpt_still_does_not_identify_instrument_or_meter(self):
        with tempfile.TemporaryDirectory(prefix="maravi-preview-test-") as folder:
            path = Path(folder) / "tones.wav"
            sample_rate = 11025
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(sample_rate)
                samples = bytearray()
                for index in range(sample_rate * 4):
                    seconds = index / sample_rate
                    envelope = 0.4 if (seconds % 0.5) < 0.38 else 0.0
                    signal = sum(math.sin(2 * math.pi * frequency * seconds)
                                 for frequency in (261.63, 329.63, 392.0)) / 3
                    samples.extend(struct.pack("<h", int(18000 * envelope * signal)))
                wav.writeframes(samples)
            result = self._run_preview(path)
            self.assertEqual(result["sample_seconds"], 4.0)
            self.assertIsInstance(result["key_name"], str)
            self.assertIsNone(result["instrument"])
            self.assertIsNone(result["meter"])


if __name__ == "__main__":
    unittest.main()
