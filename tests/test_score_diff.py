"""Testes sintéticos: nenhuma partitura de terceiros entra no repositório."""
from pathlib import Path
import tempfile
import unittest

from tools.score_diff import compare_scores, read_score


def _score(measure: str, divisions: int = 480) -> str:
    return ("<?xml version='1.0' encoding='utf-8'?>"
            "<score-partwise version='4.0'><part-list><score-part id='P1'>"
            "<part-name>Flauta</part-name></score-part></part-list><part id='P1'>"
            f"<measure number='1'><attributes><divisions>{divisions}</divisions></attributes>"
            f"{measure}</measure></part></score-partwise>")


def _note(step: str = "C", duration: int = 480, extra: str = "", layout: str = "") -> str:
    return (f"<note {layout}><pitch><step>{step}</step><octave>4</octave></pitch>"
            f"<duration>{duration}</duration><type>quarter</type>{extra}</note>")


class ScoreDiffTests(unittest.TestCase):
    def compare(self, left: str, right: str) -> tuple[str, ...]:
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder) / "a.musicxml", Path(folder) / "b.musicxml"
            a.write_text(left, encoding="utf-8")
            b.write_text(right, encoding="utf-8")
            return compare_scores(read_score(a), read_score(b)).get(("P1", "1"), ())

    def test_ignores_export_layout_and_normalizes_divisions(self):
        original = _score(_note())
        revised = _score("<print new-system='yes'/>" + _note(duration=960, layout="default-x='99'"), 960)
        self.assertEqual(self.compare(original, revised), ())

    def test_divisions_change_inside_measure(self):
        original = _score(_note() + _note("D"))
        revised = _score(_note() + "<attributes><divisions>960</divisions></attributes>"
                         + _note("D", duration=960))
        self.assertEqual(self.compare(original, revised), ())

    def test_separates_pitch_from_duration(self):
        original = _score(_note())
        self.assertEqual(self.compare(original, _score(_note("D"))), ("alturas",))
        self.assertEqual(self.compare(original, _score(_note(duration=240))), ("ritmo",))

    def test_detects_tuplet_grace_link_and_barline(self):
        original = _score(_note())
        revised = _score(
            "<note><grace slash='yes'/><pitch><step>D</step><octave>4</octave></pitch>"
            "<type>16th</type><notations><slur type='start' number='9'/></notations></note>"
            + _note(extra="<time-modification><actual-notes>5</actual-notes>"
                    "<normal-notes>4</normal-notes></time-modification>"
                    "<notations><slur type='stop' number='9'/></notations>")
            + "<barline location='right'><bar-style>light-light</bar-style></barline>")
        self.assertEqual(self.compare(original, revised),
                         ("alturas", "ritmo", "ligacoes", "barras"))

    def test_detects_articulation_harmony_and_text(self):
        original = _score(_note())
        revised = _score(
            "<direction><direction-type><words>Swing</words></direction-type></direction>"
            "<harmony><root><root-step>D</root-step></root><kind>minor-seventh</kind></harmony>"
            + _note(extra="<notations><articulations><staccato/></articulations></notations>"))
        self.assertEqual(self.compare(original, revised),
                         ("ornamentos", "cifras", "textos"))

    def test_written_accidental_is_not_confused_with_pitch(self):
        original = _score(_note())
        revised = _score(_note(extra="<accidental cautionary='yes'>natural</accidental>"))
        self.assertEqual(self.compare(original, revised), ("ornamentos",))

    def test_rejects_duplicate_measure(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "duplo.musicxml"
            path.write_text(_score(_note()).replace("</measure>", "</measure><measure number='1'/>", 1),
                            encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicado"):
                read_score(path)


if __name__ == "__main__":
    unittest.main()
