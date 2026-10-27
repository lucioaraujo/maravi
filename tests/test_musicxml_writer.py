"""Regressão: duração declarada e figura impressa devem concordar."""

from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from musicxml_writer import (TICKS_PER_BEAT, align_clear_phrase_starts, figure_for_ticks,
                             readable_phrase_steps, write_musicxml)
from review_phrase_score import read_monophonic_score


_TYPE_TICKS = {
    "whole": 96,
    "half": 48,
    "quarter": 24,
    "eighth": 12,
    "16th": 6,
    "32nd": 3,
    "64th": Fraction(3, 2),
}


def written_ticks(note: ET.Element) -> Fraction:
    length = Fraction(_TYPE_TICKS[note.findtext("type")])
    dots = len(note.findall("dot"))
    length *= sum((Fraction(1, 2**i) for i in range(dots + 1)), Fraction(0))
    modification = note.find("time-modification")
    if modification is not None:
        length *= Fraction(
            int(modification.findtext("normal-notes")),
            int(modification.findtext("actual-notes")),
        )
    return length


class MusicXmlDurationTests(unittest.TestCase):
    def test_voice_clef_follows_register_without_transposing_pitch(self):
        for pitch, instrument, expected_clef in (
            (50, "Voice", "F"), (67, "Voice", "G"), (50, "Flute", "G")
        ):
            with self.subTest(pitch=pitch, instrument=instrument), TemporaryDirectory() as directory:
                path = Path(directory) / "voice.musicxml"
                with patch("beat_grid.quantize_melody_to_steps",
                           return_value=[(0, 24, pitch, 0.8)]):
                    write_musicxml(
                        [{"start": 0.0, "end": 0.5, "pitch": pitch}],
                        [0.0, 0.5, 1.0], str(path), instrument_name=instrument,
                    )
                root = ET.parse(path).getroot()
                self.assertEqual(root.findtext(".//clef/sign"), expected_clef)
                octave = int(root.findtext(".//note/pitch/octave"))
                self.assertEqual(octave, pitch // 12 - 1)

    def test_measure_length_respects_time_signature_denominator(self):
        for numerator, denominator, expected_measures, ticks_per_measure in (
            (4, 4, 1, 96), (4, 8, 2, 48), (4, 16, 4, 24),
            (6, 8, 2, 72),
        ):
            with self.subTest(numerator=numerator, denominator=denominator), TemporaryDirectory() as directory:
                path = Path(directory) / "meter.musicxml"
                with patch("beat_grid.quantize_melody_to_steps",
                           return_value=[(0, ticks_per_measure * expected_measures, 60, 0.8)]):
                    write_musicxml(
                        [{"start": 0.0, "end": 2.0, "pitch": 60}],
                        [i * 0.5 for i in range(8)], str(path),
                        beats_per_measure=numerator, beat_unit=denominator,
                    )
                measures = ET.parse(path).getroot().find("part").findall("measure")
                self.assertEqual(len(measures), expected_measures)
                self.assertEqual(
                    [sum(int(note.findtext("duration")) for note in measure.findall("note"))
                     for measure in measures],
                    [ticks_per_measure] * expected_measures,
                )

    def test_variable_divisions_do_not_inflate_long_score(self):
        # Regressão do caso histórico 219 → 156 compassos: duração total
        # não pode crescer ao cortar notas por subdivisões locais variadas.
        end_tick = 7450
        intervals = []
        cursor = 0
        lengths = (22, 5, 2, 1, 49, 17, 71, 3)
        while cursor < end_tick:
            duration = lengths[len(intervals) % len(lengths)]
            end = min(cursor + duration, end_tick)
            intervals.append((cursor, end, 60 + len(intervals) % 12, 0.8))
            cursor = end
        with TemporaryDirectory() as directory:
            path = Path(directory) / "long-score.musicxml"
            with patch("beat_grid.quantize_melody_to_steps", return_value=intervals):
                write_musicxml(
                    [{"start": 0.0, "end": 1.0, "pitch": 60}],
                    [i * 0.5 for i in range(320)], str(path),
                    beats_per_measure=2,
                    beat_divisions=([1, 2, 3, 4, 6, 8] * 54),
                )
            measures = ET.parse(path).getroot().find("part").findall("measure")
            self.assertEqual(len(measures), 156)
            durations = [sum(int(n.findtext("duration")) for n in m.findall("note"))
                         for m in measures]
            self.assertEqual(durations[:-1], [48] * 155)
            self.assertEqual(durations[-1], 10)
            self.assertEqual(sum(durations), end_tick)
            notes = [n for measure in measures for n in measure.findall("note")]
            self.assertEqual(
                sum(n.find("tie[@type='start']") is not None for n in notes),
                sum(n.find("tie[@type='stop']") is not None for n in notes),
            )
            for note in notes:
                tags = [child.tag for child in note]
                if "tie" in tags:
                    self.assertLess(tags.index("duration"), tags.index("tie"))
                    self.assertLess(tags.index("tie"), tags.index("voice"))

    def test_clear_phrase_starts_only_move_score_breaths(self):
        source = [(0, 48, 60), (72, 96, 62), (120, 144, 64),
                  (150, 174, 65), (180, 204, 67)]
        aligned = align_clear_phrase_starts(source, 96)
        self.assertEqual(aligned[:3], [(0, 48, 60), (96, 120, 62), (192, 216, 64)])
        self.assertEqual(aligned[3], (222, 246, 65))  # respiração curta: não reinicia
        self.assertEqual([end - start for start, end, _ in aligned],
                         [end - start for start, end, _ in source])
        self.assertEqual(source[1], (72, 96, 62))  # entrada não é alterada

    def test_ambiguous_phrase_and_pickup_are_not_forced(self):
        self.assertEqual(align_clear_phrase_starts([(-6, 18, 60), (42, 66, 62)], 96),
                         [(-6, 18, 60), (42, 66, 62)])

    def test_fermata_only_on_long_note_before_clear_rest(self):
        quantized = [(0, 48, 60, 0.8), (96, 120, 62, 0.8),
                     (120, 144, 64, 0.8)]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "phrases.musicxml"
            with patch("beat_grid.quantize_melody_to_steps", return_value=quantized):
                write_musicxml([{"start": 0.0, "end": 1.0, "pitch": 60}],
                               [i * 0.5 for i in range(12)], str(path),
                               beats_per_measure=4, readable_notation=True,
                               phrase_downbeats=True, part_name="Flauta",
                               instrument_name="Flute", midi_program=74)
            root = ET.parse(path).getroot()
            self.assertEqual(len(root.findall(".//fermata")), 1)
            self.assertEqual(root.findtext("part-list/score-part/score-instrument/instrument-name"),
                             "Flute")
            self.assertEqual(sum(int(n.findtext("duration")) for n in
                                 root.find("part").find("measure").findall("note")), 96)
            notes, metadata = read_monophonic_score(path)
            self.assertEqual([(n["start"], n["end"], n["pitch"]) for n in notes],
                             [(0, 48, 60), (96, 120, 62), (120, 144, 64)])
            self.assertEqual(metadata["beats_per_measure"], 4)

    def test_readable_phrases_preserve_every_pitch_and_fast_ornament(self):
        source = [(0, 11, 60), (11, 25, 62), (31, 47, 64),
                  (47, 51, 65), (51, 55, 67), (61, 62, 69), (62, 64, 71)]
        result = readable_phrase_steps(source)
        self.assertEqual([pitch for _, _, pitch in result],
                         [pitch for _, _, pitch in source])
        self.assertEqual(len(result), len(source))
        self.assertEqual(result[:3], [(0, 12, 60), (12, 24, 62), (30, 48, 64)])
        for i, (start, end, _) in enumerate(result):
            self.assertGreater(end, start)
            if i:
                self.assertGreaterEqual(start, result[i - 1][1])
        self.assertLess(readable_phrase_steps([(-1, 1, 60)])[0][0], 0)

    def test_every_figure_matches_its_declared_ticks(self):
        for allow_tuplets in (False, True):
            for cap in range(1, 97):
                with self.subTest(cap=cap, allow_tuplets=allow_tuplets):
                    ticks, note_type, dots, ratio = figure_for_ticks(cap, allow_tuplets)
                    self.assertGreater(ticks, 0)
                    self.assertLessEqual(ticks, cap)
                    note = ET.Element("note")
                    ET.SubElement(note, "type").text = note_type
                    for _ in range(dots):
                        ET.SubElement(note, "dot")
                    if ratio:
                        modification = ET.SubElement(note, "time-modification")
                        ET.SubElement(modification, "actual-notes").text = str(ratio[0])
                        ET.SubElement(modification, "normal-notes").text = str(ratio[1])
                    self.assertEqual(written_ticks(note), ticks)

    def test_writer_never_overfills_a_measure_with_mismatched_figures(self):
        cases = (
            (False, [1, 4, 3, 6, 1, 3, 6, 4], set(), False),
            (False, [4] * 12, set(), False),
            (True, [4] * 12, {24, 72, 120}, False),
            (False, [4] * 12, set(), True),
        )
        # Inclui os resíduos de 22, 5, 2 e 1 ticks vistos no MusicXML
        # que o MuseScore recusou, além de um evento atravessando compassos.
        intervals = [(0, 22), (22, 24), (24, 29), (29, 30), (31, 53),
                     (53, 60), (60, 61), (61, 96), (96, 152), (152, 192)]
        quantized = [(start, end, 60 + i, 0.8)
                     for i, (start, end) in enumerate(intervals)]
        for free_rhythm, divisions, tuplet_beats, readable in cases:
            with self.subTest(free_rhythm=free_rhythm, divisions=divisions,
                              readable=readable):
                with TemporaryDirectory() as directory:
                    path = Path(directory) / "result.musicxml"
                    with patch("beat_grid.quantize_melody_to_steps", return_value=quantized):
                        write_musicxml(
                            [{"start": 0.0, "end": 4.0, "pitch": 60}],
                            [i * 0.5 for i in range(20)], str(path),
                            beats_per_measure=4, beat_divisions=divisions,
                            free_rhythm=free_rhythm, tuplet_beats=tuplet_beats,
                            readable_notation=readable,
                        )
                    measures = ET.parse(path).getroot().find("part").findall("measure")
                    self.assertEqual(len(measures), 2)
                    for measure in measures:
                        notes = measure.findall("note")
                        self.assertEqual(sum(int(n.findtext("duration")) for n in notes),
                                         4 * TICKS_PER_BEAT)
                        for note in notes:
                            self.assertEqual(written_ticks(note),
                                             int(note.findtext("duration")),
                                             f"measure {measure.get('number')}: "
                                             f"{ET.tostring(note, encoding='unicode')}")


if __name__ == "__main__":
    unittest.main()
