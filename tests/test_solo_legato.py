"""A união opt-in de alturas sustentadas não deve apagar outras alturas."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from octave_fix import fix_octave_errors
from transcribe_monophonic import (correct_isolated_octave_spikes,
                                   filter_below_pitch, join_contiguous_same_pitch,
                                   melody_to_midi, run_pipeline)


class SoloLegatoTests(unittest.TestCase):
    def test_mixed_flute_limit_precedes_voice_selection_and_octave_fix(self):
        class StopBeforeAudioAnalysis(Exception):
            pass

        events = [
            (0.0, 1.0, 72, 0.8, None),
            (0.5, 0.7, 47, 0.9, None),
        ]
        with patch("basic_pitch.inference.predict", return_value=(None, None, events)), patch(
            "octave_fix.fix_octave_errors", side_effect=StopBeforeAudioAnalysis,
        ) as octave_fix:
            with self.assertRaises(StopBeforeAudioAnalysis):
                run_pipeline(Path("audio-nao-aberto.wav"), minimum_pitch=59)
        self.assertEqual(len(octave_fix.call_args.args[0]), 1)
        self.assertEqual(octave_fix.call_args.args[0][0]["pitch"], 72)
        self.assertEqual(octave_fix.call_args.args[0][0]["end"], 1.0)

    def test_flute_register_discards_lower_notes_but_keeps_low_b(self):
        source = [
            {"start": 0.0, "end": 0.4, "pitch": 47, "amplitude": 0.8},
            {"start": 0.4, "end": 0.8, "pitch": 58, "amplitude": 0.8},
            {"start": 0.8, "end": 1.2, "pitch": 59, "amplitude": 0.8},
            {"start": 1.2, "end": 1.6, "pitch": 60, "amplitude": 0.8},
        ]
        kept, excluded = filter_below_pitch(source, 59)
        self.assertEqual([note["pitch"] for note in kept], [59, 60])
        self.assertEqual([note["start"] for note in kept], [0.8, 1.2])
        self.assertEqual(excluded, 2)
        self.assertEqual(len(source), 4)

    def test_confirmed_flute_low_b_survives_automatic_octave_fix(self):
        source = [{"pitch": 83} for _ in range(40)]
        source[5]["pitch"] = 59
        source[6]["pitch"] = 35
        generic = fix_octave_errors(source)
        flute = fix_octave_errors(source, preserve_low_register_from=59)
        flute_local = fix_octave_errors(
            source, preserve_low_register_from=59, local_continuity=True,
        )
        self.assertNotEqual(generic["melody"][5]["pitch"], 59)
        self.assertEqual(flute["melody"][5]["pitch"], 59)
        self.assertEqual(flute_local["melody"][5]["pitch"], 59)
        self.assertNotEqual(flute["melody"][6]["pitch"], 35)
        self.assertEqual(source[5]["pitch"], 59)

    def test_isolated_octave_spike_can_resolve_to_flute_low_b(self):
        source = [
            {"start": 0.0, "end": 0.3, "pitch": 59},
            {"start": 0.3, "end": 0.4, "pitch": 83},
            {"start": 0.4, "end": 0.7, "pitch": 59},
        ]
        output, count = correct_isolated_octave_spikes(source)
        self.assertEqual(count, 1)
        self.assertEqual([n["pitch"] for n in output], [59, 59, 59])
        self.assertEqual(source[1]["pitch"], 83)

    def test_midi_program_is_explicit_playback_timbre_not_source_detection(self):
        note = [{"start": 0.0, "end": 0.5, "pitch": 59, "amplitude": 0.8}]
        generic = melody_to_midi(note, program=0)
        default = melody_to_midi(note)
        flute = melody_to_midi(note, program=73)
        self.assertEqual(generic.instruments[0].program, 0)
        self.assertEqual(default.instruments[0].program, 0)
        self.assertEqual(flute.instruments[0].program, 73)
        self.assertEqual(generic.instruments[0].notes[0].pitch, 59)
        self.assertEqual(flute.instruments[0].notes[0].pitch, 59)

    def test_short_octave_spike_is_corrected_but_full_high_note_survives(self):
        source = [
            {"start": 0.0, "end": 0.3, "pitch": 72},
            {"start": 0.3, "end": 0.4, "pitch": 84},
            {"start": 0.4, "end": 0.7, "pitch": 72},
            {"start": 0.7, "end": 1.4, "pitch": 84},
            {"start": 1.4, "end": 1.7, "pitch": 72},
        ]
        output, count = correct_isolated_octave_spikes(source)
        self.assertEqual(count, 1)
        self.assertEqual([n["pitch"] for n in output], [72, 72, 72, 84, 72])
        self.assertEqual(source[1]["pitch"], 84)

    def test_joins_only_contiguous_equal_pitches(self):
        source = [
            {"start": 0.0, "end": 0.2, "pitch": 85, "amplitude": 0.6},
            {"start": 0.2, "end": 0.5, "pitch": 85, "amplitude": 0.8},
            {"start": 0.5, "end": 0.7, "pitch": 83, "amplitude": 0.7},
            {"start": 0.7, "end": 0.9, "pitch": 85, "amplitude": 0.7},
            {"start": 1.0, "end": 1.2, "pitch": 85, "amplitude": 0.6},
        ]
        result = join_contiguous_same_pitch(source)
        self.assertEqual([(n["start"], n["end"], n["pitch"]) for n in result],
                         [(0.0, 0.5, 85), (0.5, 0.7, 83),
                          (0.7, 0.9, 85), (1.0, 1.2, 85)])
        self.assertEqual(result[0]["amplitude"], 0.8)
        self.assertEqual(source[0]["end"], 0.2)

    def test_long_sustain_stays_one_note(self):
        pieces = [{"start": i * 0.5, "end": (i + 1) * 0.5,
                   "pitch": 77, "amplitude": 0.5} for i in range(9)]
        result = join_contiguous_same_pitch(pieces)
        self.assertEqual(len(result), 1)
        self.assertEqual((result[0]["start"], result[0]["end"]), (0.0, 4.5))


if __name__ == "__main__":
    unittest.main()
