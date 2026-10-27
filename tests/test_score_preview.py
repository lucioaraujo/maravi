"""Prévia visual usa dados do MusicXML, sem inferência ou MuseScore externo."""
from pathlib import Path
import tempfile
import unittest

from webapp.score_preview import render_score_preview


def score(notes: str, second: str = "", fifths: int = 0) -> str:
    return (
        '<score-partwise version="4.0"><part id="P1"><measure number="1">'
        '<attributes><divisions>24</divisions>'
        f'<key><fifths>{fifths}</fifths></key>'
        '<time><beats>4</beats><beat-type>4</beat-type></time>'
        '<clef><sign>G</sign><line>2</line></clef></attributes>'
        f'{notes}</measure>{second}</part></score-partwise>'
    )


def note(step: str, octave: int, figure: str, alter: str = "") -> str:
    return (f'<note><pitch><step>{step}</step>{alter}<octave>{octave}</octave></pitch>'
            f'<duration>24</duration><type>{figure}</type></note>')


class ScorePreviewTests(unittest.TestCase):
    def render(self, xml: str) -> str | None:
        with tempfile.TemporaryDirectory(prefix="maravi-preview-test-") as folder:
            path = Path(folder) / "score.musicxml"
            path.write_text(xml, encoding="utf-8")
            return render_score_preview(path)

    def test_preview_uses_notes_rests_and_measure_numbers_from_xml(self):
        xml = score(
            note("C", 4, "quarter")
            + '<note><rest/><duration>12</duration><type>eighth</type></note>'
            + note("D", 4, "eighth", "<alter>1</alter>")
            + note("E", 4, "half"),
            '<measure number="2">' + note("F", 4, "whole") + '</measure>',
        )
        svg = self.render(xml)
        self.assertIsNotNone(svg)
        self.assertIn("Compasso 1", svg)
        self.assertIn("Compasso 2", svg)
        self.assertIn("C+04 — quarter", svg)
        self.assertIn("D+14 — eighth", svg)
        self.assertIn("Pausa: eighth", svg)
        self.assertIn("♯", svg)
        self.assertIn("<ellipse", svg)

    def test_key_signature_changes_visible_accidental(self):
        xml = score(note("B", 4, "quarter", "<alter>-1</alter>")
                    + note("B", 4, "quarter"), fifths=-1)
        svg = self.render(xml)
        self.assertIsNotNone(svg)
        self.assertIn("♭", svg)  # armadura
        self.assertIn("♮", svg)  # si natural depois de si bemol

    def test_dot_tuplet_and_tie_are_taken_from_xml(self):
        first = ("<note><pitch><step>C</step><octave>4</octave></pitch>"
                 "<duration>8</duration><type>eighth</type><dot/>"
                 '<tie type="start"/><time-modification><actual-notes>3</actual-notes>'
                 '<normal-notes>2</normal-notes></time-modification>'
                 '<notations><tuplet type="start"/><tied type="start"/></notations></note>')
        second = ("<note><pitch><step>C</step><octave>4</octave></pitch>"
                  '<duration>8</duration><type>eighth</type><tie type="stop"/></note>')
        svg = self.render(score(first + second))
        self.assertIsNotNone(svg)
        self.assertIn('>3</text>', svg)
        self.assertIn('<circle', svg)
        self.assertIn('fill="none" stroke="#5cb3a9" stroke-width="2"', svg)

    def test_invalid_and_unsupported_scores_do_not_claim_a_preview(self):
        self.assertIsNone(self.render("<score-partwise/>"))
        self.assertIsNone(self.render("<score-partwise"))
        self.assertIsNone(self.render(score('<note><chord/><rest/><type>quarter</type></note>')))
        self.assertIsNone(self.render(score(note("C", 4, "quarter") * 97)))


if __name__ == "__main__":
    unittest.main()
