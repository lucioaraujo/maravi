"""Verifica preservação da melodia e rastreio de mudanças na adaptação."""
from pathlib import Path
from types import SimpleNamespace
from hashlib import sha256
import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

import pretty_midi

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from adapt_voice_to_flute import adapt_score, plan_octave_adaptation


SCORE = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
<work><work-title>Estudo vocal</work-title></work>
<identification><creator type="composer">Autora</creator></identification>
<part-list><score-part id="P1"><part-name>Voz</part-name>
<score-instrument id="I1"><instrument-name>Voice</instrument-name></score-instrument>
<midi-instrument id="I1"><midi-channel>1</midi-channel><midi-program>54</midi-program></midi-instrument>
</score-part></part-list>
<part id="P1">
<measure number="1"><attributes><divisions>24</divisions><time><beats>4</beats>
<beat-type>4</beat-type></time></attributes>
<note><pitch><step>G</step><octave>3</octave></pitch><duration>96</duration>
<tie type="start"/><type>whole</type></note></measure>
<measure number="2"><note><pitch><step>G</step><octave>3</octave></pitch>
<duration>24</duration><tie type="stop"/><type>quarter</type></note>
<note><rest/><duration>24</duration><type>quarter</type></note>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>24</duration>
<type>quarter</type></note>
<note><rest/><duration>24</duration><type>quarter</type></note></measure>
</part></score-partwise>"""


class VoiceToFluteTests(unittest.TestCase):
    def test_phrase_shift_keeps_unresolved_melody_intact(self):
        notes = [SimpleNamespace(pitch=p, start=s, end=e) for p, s, e in (
            (55, 0.0, 0.3), (64, 0.3, 0.6),
            (55, 1.2, 1.5), (89, 1.5, 1.8),
        )]
        adapted, phrases = plan_octave_adaptation(notes)
        self.assertEqual(adapted, [67, 76, 55, 89])
        self.assertEqual([entry["octave_shift"] for entry in phrases], [12, 0])
        self.assertFalse(phrases[1]["uniform_shift_possible"])
        self.assertEqual(phrases[1]["outside_count"], 1)

    def test_derivative_preserves_source_ties_timing_and_provenance(self):
        with tempfile.TemporaryDirectory(prefix="maravi-flute-test-") as folder:
            root = Path(folder)
            xml = root / "voice.musicxml"
            xml.write_text(SCORE, encoding="utf-8")
            midi = pretty_midi.PrettyMIDI(initial_tempo=120)
            voice = pretty_midi.Instrument(program=53, name="Voz")
            voice.notes = [
                pretty_midi.Note(90, 55, 0.0, 2.5),
                pretty_midi.Note(90, 60, 3.0, 3.5),
            ]
            midi.instruments.append(voice)
            source_midi = root / "voice.mid"
            midi.write(str(source_midi))
            originals = (xml.read_bytes(), source_midi.read_bytes())

            prefix = root / "flute_review"
            report = adapt_score(xml, source_midi, prefix)
            self.assertEqual((xml.read_bytes(), source_midi.read_bytes()), originals)
            self.assertEqual(report["note_count"], 2)
            self.assertEqual(report["shifted_note_count"], 1)
            self.assertEqual(report["outside_before"], 1)
            self.assertEqual(report["outside_after"], 0)
            result = ET.parse(prefix.with_suffix(".musicxml")).getroot()
            self.assertEqual(
                [pitch.findtext("octave") for pitch in result.findall(".//part/measure/note/pitch")],
                ["4", "4", "4"],
            )
            self.assertEqual(result.findtext("identification/creator"), "Autora")
            self.assertEqual(result.findtext("part-list/score-part/midi-instrument/midi-program"), "74")
            adapted_midi = pretty_midi.PrettyMIDI(str(prefix.with_suffix(".mid")))
            self.assertEqual(adapted_midi.instruments[0].program, 73)
            self.assertEqual([note.pitch for note in adapted_midi.instruments[0].notes], [67, 60])
            self.assertAlmostEqual(adapted_midi.instruments[0].notes[0].end, 2.5, places=3)
            with self.assertRaises(FileExistsError):
                adapt_score(xml, source_midi, prefix)

    def test_optional_pitch_audit_only_changes_matching_octave_evidence(self):
        with tempfile.TemporaryDirectory(prefix="maravi-audit-test-") as folder:
            root = Path(folder)
            xml = root / "voice.musicxml"
            xml.write_text(SCORE.replace("<step>G</step><octave>3</octave>",
                                         "<step>A</step><octave>5</octave>")
                                .replace("<step>C</step><octave>4</octave>",
                                         "<step>G</step><octave>3</octave>"), encoding="utf-8")
            midi = pretty_midi.PrettyMIDI(initial_tempo=120)
            voice = pretty_midi.Instrument(program=53)
            voice.notes = [pretty_midi.Note(90, 81, 0.0, 2.5),
                           pretty_midi.Note(90, 55, 3.0, 3.5)]
            midi.instruments.append(voice)
            source_midi = root / "voice.mid"
            midi.write(str(source_midi))
            audit = root / "audit.json"
            payload = {"midi_sha256": sha256(source_midi.read_bytes()).hexdigest(),
                       "notes": [{"note": 1, "status": "oitava_suspeita",
                                  "midi_pitch": 81, "start_seconds": 0.0,
                                  "estimated_midi_pitch": 69.0}]}
            audit.write_text(json.dumps(payload), encoding="utf-8")
            report = adapt_score(xml, source_midi, root / "flute", audit_json=audit)
            self.assertEqual(report["audit_corrections"][0]["to_pitch"], 69)
            self.assertEqual([n.pitch for n in pretty_midi.PrettyMIDI(
                str(root / "flute.mid")).instruments[0].notes], [69, 67])
            self.assertEqual(ET.parse(xml).getroot().findtext(".//part/measure/note/pitch/octave"), "5")
            payload["midi_sha256"] = "0" * 64
            audit.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "não corresponde"):
                adapt_score(xml, source_midi, root / "rejected", audit_json=audit)


if __name__ == "__main__":
    unittest.main()
