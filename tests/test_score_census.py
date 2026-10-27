import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "webapp"))

from score_census import census_melody, census_written_figures
from i18n import LANGUAGES, translate


class ScoreCensusTests(unittest.TestCase):
    def test_flags_fragmentation_and_keeps_notes_unchanged(self):
        notes = [
            {"start": 0.0, "end": 0.1, "pitch": 60},
            {"start": 0.1, "end": 0.2, "pitch": 84},
            {"start": 0.2, "end": 0.3, "pitch": 61},
            {"start": 0.3, "end": 0.4, "pitch": 62},
            {"start": 0.4, "end": 0.5, "pitch": 86},
            {"start": 0.5, "end": 0.6, "pitch": 63},
        ]
        before = [dict(note) for note in notes]
        report = census_melody(notes, [0.0, 0.5, 1.0], "flute")
        keys = {warning["key"] for warning in report["warnings"]}
        self.assertEqual(notes, before)
        self.assertEqual(report["note_count"], 6)
        self.assertEqual(report["range"], [60, 86])
        self.assertIn("census_many_short", keys)
        self.assertIn("census_many_very_short", keys)
        self.assertIn("census_wide_leaps", keys)

    def test_flags_voice_register_without_using_a_universal_upper_limit(self):
        report = census_melody(
            [{"start": 0, "end": 0.5, "pitch": 54},
             {"start": 0.5, "end": 1.0, "pitch": 90}],
            [0, 0.5, 1.0], "voice", voice_minimum=55,
        )
        range_warning = next(
            warning for warning in report["warnings"]
            if warning["key"] == "census_outside_range"
        )
        self.assertEqual(range_warning["count"], 1)
        self.assertEqual(range_warning["low"], 55)
        self.assertEqual(range_warning["high"], "—")

    def test_reports_overlaps_and_has_no_alert_for_a_regular_line(self):
        overlapping = census_melody(
            [{"start": 0.0, "end": 0.7, "pitch": 60},
             {"start": 0.5, "end": 1.0, "pitch": 62}],
            [0, 0.5, 1.0], "melody",
        )
        self.assertIn("census_overlaps", {w["key"] for w in overlapping["warnings"]})

        regular = census_melody(
            [{"start": 0.0, "end": 0.5, "pitch": 60},
             {"start": 0.5, "end": 1.0, "pitch": 62}],
            [0, 0.5, 1.0], "melody",
        )
        self.assertEqual(regular["warnings"], [])

    def test_empty_or_malformed_notes_are_safe(self):
        report = census_melody([{"pitch": 60}], [], "melody")
        self.assertEqual(report["note_count"], 0)
        self.assertEqual(report["warnings"], [])

    def test_census_copy_formats_in_all_four_languages(self):
        warning_keys = (
            "census_many_short", "census_many_very_short", "census_wide_leaps",
            "census_overlaps", "census_outside_range", "census_source_unisolated",
            "census_many_short_symbols", "census_many_very_short_symbols",
        )
        for lang in LANGUAGES:
            with self.subTest(language=lang):
                summary = translate(
                    lang, "census_summary", count=12, low=55, high=80,
                    short=50, very_short=25,
                )
                self.assertNotIn("{", summary)
                written = translate(lang, "census_written_summary", count=10,
                                    short=30, very_short=10, grace=2)
                self.assertNotIn("{", written)
                for key in warning_keys:
                    message = translate(
                        lang, key, count=3, percent=50, low=55, high=96,
                    )
                    self.assertNotIn("{", message)

    def test_written_figure_census_counts_tuplets_and_grace_notes(self):
        xml = """<score-partwise><part id="P1"><measure>
        <note><pitch><step>C</step><octave>4</octave></pitch><type>quarter</type></note>
        <note><pitch><step>D</step><octave>4</octave></pitch><type>eighth</type></note>
        <note><pitch><step>E</step><octave>4</octave></pitch><type>16th</type></note>
        <note><pitch><step>F</step><octave>4</octave></pitch><type>eighth</type>
          <time-modification><actual-notes>3</actual-notes><normal-notes>2</normal-notes></time-modification>
        </note>
        <note><pitch><step>A</step><octave>4</octave></pitch><type>32nd</type></note>
        <note><grace/><pitch><step>G</step><octave>4</octave></pitch><type>16th</type></note>
        </measure></part></score-partwise>"""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "score.musicxml"
            path.write_text(xml, encoding="utf-8")
            report = census_written_figures(path)
        self.assertEqual(report["written_symbol_count"], 5)
        self.assertEqual(report["short_symbol_count"], 3)
        self.assertEqual(report["very_short_symbol_count"], 1)
        self.assertEqual(report["grace_symbol_count"], 1)


if __name__ == "__main__":
    unittest.main()
