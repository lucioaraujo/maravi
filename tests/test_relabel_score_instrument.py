"""Relabel instrumental não modifica o material musical nem o original."""
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

import mido

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from relabel_score_instrument import relabel_job


class RelabelTests(unittest.TestCase):
    def test_grand_staff_cannot_be_created_by_relabeling_one_line(self):
        with self.assertRaises(ValueError):
            relabel_job(Path("nao-aberto"), "piano_grand")

    def test_piano_derivative_preserves_note_events_and_originals(self):
        source_xml = Path(__file__).parent / "fixtures" / "one_measure.musicxml"
        with tempfile.TemporaryDirectory(prefix="maravi-relabel-test-") as folder:
            job = Path(folder)
            xml = job / "resultado.musicxml"
            xml.write_bytes(source_xml.read_bytes())
            midi = mido.MidiFile()
            midi.tracks.append(mido.MidiTrack())
            midi.tracks[0].append(mido.MetaMessage("track_name", name="flauta"))
            midi.tracks[0].append(mido.Message("program_change", program=73, time=0))
            midi.tracks[0].append(mido.Message("note_on", note=60, velocity=80, time=12))
            midi.tracks[0].append(mido.Message("note_off", note=60, velocity=0, time=24))
            source_mid = job / "resultado.mid"
            midi.save(str(source_mid))
            original_xml, original_midi = xml.read_bytes(), source_mid.read_bytes()

            out_xml, out_midi = relabel_job(job, "piano")
            self.assertEqual((xml.read_bytes(), source_mid.read_bytes()),
                             (original_xml, original_midi))
            old_root = ET.fromstring(original_xml)
            new_root = ET.parse(out_xml).getroot()
            self.assertEqual(ET.tostring(old_root.find("./part")),
                             ET.tostring(new_root.find("./part")))
            self.assertEqual(new_root.findtext("./part-list/score-part/part-name"), "Piano")
            self.assertEqual(new_root.findtext("./part-list/score-part/midi-instrument/midi-program"), "1")
            result_midi = mido.MidiFile(str(out_midi))
            self.assertEqual([x.program for x in result_midi.tracks[0]
                              if x.type == "program_change"], [0])
            self.assertEqual([(x.type, x.note, x.time) for x in result_midi.tracks[0]
                              if x.type in ("note_on", "note_off")],
                             [("note_on", 60, 12), ("note_off", 60, 24)])
            with self.assertRaises(FileExistsError):
                relabel_job(job, "piano")


if __name__ == "__main__":
    unittest.main()
