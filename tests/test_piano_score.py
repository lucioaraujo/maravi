"""Duas pautas reais, acordes, vozes, compassos completos e MIDI independente."""
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from piano_score import piano_notes_from_events, piano_to_midi, write_piano_musicxml


class PianoScoreTests(unittest.TestCase):
    def test_grand_staff_retains_polyphony_and_fills_measures(self):
        events = [
            (0.0, 2.0, 48, 0.8, None),      # mão sugerida inferior
            (0.0, 1.0, 64, 0.8, None),
            (0.0, 1.0, 67, 0.7, None),      # acorde na pauta superior
            (1.0, 2.0, 62, 0.8, None),
            (1.5, 2.5, 43, 0.8, None),      # sobreposição na pauta inferior
            (1.75, 2.25, 72, 0.8, None),   # nota ligada sobre a barra
            (0.0, 1.0, 15, 0.8, None),     # fora do piano
        ]
        notes = piano_notes_from_events(events)
        self.assertEqual(len(notes), 6)
        midi = piano_to_midi(notes, 120, 4, 4)
        self.assertEqual(len(midi.instruments), 2)
        self.assertEqual([len(part.notes) for part in midi.instruments], [4, 2])
        with tempfile.TemporaryDirectory(prefix="maravi-piano-test-") as folder:
            path = Path(folder) / "piano.musicxml"
            write_piano_musicxml(notes, [i * 0.5 for i in range(8)], str(path),
                                 4, 4, 0.0, 120, work_title="Teste & piano")
            root = ET.parse(path).getroot()
        self.assertEqual(root.findtext("./part/measure/attributes/staves"), "2")
        self.assertEqual(root.findtext("./part/measure/attributes/clef[@number='1']/sign"), "G")
        self.assertEqual(root.findtext("./part/measure/attributes/clef[@number='2']/sign"), "F")
        self.assertEqual(root.findtext("./work/work-title"), "Teste & piano")
        measures = root.findall("./part/measure")
        self.assertEqual(len(measures), 2)
        first_notes = measures[0].findall("note")
        self.assertTrue(any(note.find("chord") is not None for note in first_notes))
        self.assertEqual({note.findtext("staff") for note in first_notes}, {"1", "2"})
        self.assertTrue(any(note.find("tie[@type='start']") is not None
                            for note in first_notes))
        for note in first_notes:
            tags = [child.tag for child in note]
            if "tie" in tags:
                self.assertLess(tags.index("tie"), tags.index("voice"))
        self.assertTrue(any(note.find("tie[@type='stop']") is not None
                            for note in measures[1].findall("note")))
        for measure in measures:
            elapsed = 0
            for child in measure:
                if child.tag == "backup":
                    self.assertEqual(elapsed, 96)
                    elapsed = 0
                elif child.tag == "note" and child.find("chord") is None:
                    elapsed += int(child.findtext("duration"))
            self.assertEqual(elapsed, 96)


if __name__ == "__main__":
    unittest.main()
