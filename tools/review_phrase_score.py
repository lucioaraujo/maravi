#!/usr/bin/env python3
"""Cria derivado editorial de um MusicXML monofônico já transcrito.

Uso local para comparar escrita por frases sem repetir a inferência do áudio.
Nunca sobrescreve entrada ou saída existente. Se houver MIDI correspondente,
mantém seus tempos e pode corrigir apenas picos isolados de oitava no derivado.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import xml.etree.ElementTree as ET

from musicxml_writer import TICKS_PER_BEAT, write_musicxml
from transcribe_monophonic import correct_isolated_octave_spikes

STEP_PITCH = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def read_monophonic_score(path: Path) -> tuple[list[dict], dict]:
    root = ET.parse(path).getroot()
    part = root.find("part")
    if part is None:
        raise ValueError("MusicXML sem parte melódica")
    attributes = part.find("measure/attributes")
    if attributes is None:
        raise ValueError("MusicXML sem fórmula de compasso")
    divisions = int(attributes.findtext("divisions", "0"))
    if divisions != TICKS_PER_BEAT:
        raise ValueError(f"divisões incompatíveis: {divisions}")
    notes: list[dict] = []
    cursor = 0
    for measure in part.findall("measure"):
        for event in measure.findall("note"):
            if event.find("chord") is not None or event.find("backup") is not None:
                raise ValueError("somente partitura monofônica é aceita")
            duration = int(event.findtext("duration", "0"))
            if duration <= 0:
                raise ValueError("evento sem duração")
            if event.find("rest") is None:
                pitch_element = event.find("pitch")
                if pitch_element is None:
                    raise ValueError("nota sem altura")
                pitch = (12 * (int(pitch_element.findtext("octave")) + 1)
                         + STEP_PITCH[pitch_element.findtext("step")]
                         + int(pitch_element.findtext("alter", "0")))
                if event.find('tie[@type="stop"]') is not None:
                    if not notes or notes[-1]["end"] != cursor or notes[-1]["pitch"] != pitch:
                        raise ValueError("ligadura de duração inconsistente")
                    notes[-1]["end"] += duration
                else:
                    notes.append({"start": cursor, "end": cursor + duration,
                                  "pitch": pitch, "amplitude": 0.8})
            cursor += duration
    metadata = {
        "beats_per_measure": int(attributes.findtext("time/beats", "4")),
        "beat_unit": int(attributes.findtext("time/beat-type", "4")),
        "key_fifths": int(attributes.findtext("key/fifths", "0")),
        "key_mode": attributes.findtext("key/mode", "major"),
        "work_title": root.findtext("work/work-title"),
        "composer": root.findtext("identification/creator[@type='composer']"),
    }
    sound = part.find("measure/direction/sound")
    metadata["display_bpm"] = float(sound.get("tempo", "120")) if sound is not None else 120.0
    if not notes:
        raise ValueError("MusicXML sem notas")
    return notes, metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_xml", type=Path)
    parser.add_argument("output_xml", type=Path)
    parser.add_argument("--source-midi", type=Path)
    parser.add_argument("--output-midi", type=Path)
    parser.add_argument("--harmonic-spikes", action="store_true")
    args = parser.parse_args()
    if args.output_xml.exists() or (args.output_midi and args.output_midi.exists()):
        parser.error("saída já existe: nenhum arquivo será sobrescrito")
    if args.source_xml == args.output_xml or (args.source_midi and args.source_midi == args.output_midi):
        parser.error("origem e saída devem ser diferentes")
    if args.harmonic_spikes and not args.source_midi:
        parser.error("--harmonic-spikes requer --source-midi")
    if bool(args.source_midi) != bool(args.output_midi):
        parser.error("informe --source-midi e --output-midi juntos")

    notes, metadata = read_monophonic_score(args.source_xml)
    corrected = 0
    midi = None
    if args.source_midi:
        import pretty_midi

        midi = pretty_midi.PrettyMIDI(str(args.source_midi))
        if len(midi.instruments) != 1:
            raise ValueError("MIDI deve conter exatamente uma linha melódica")
        midi_notes = sorted(midi.instruments[0].notes, key=lambda note: note.start)
        if len(midi_notes) != len(notes):
            raise ValueError("MIDI e MusicXML não têm a mesma quantidade de ataques")
        if [note.pitch for note in midi_notes] != [note["pitch"] for note in notes]:
            raise ValueError("MIDI e MusicXML divergem nas alturas; revisar antes de derivar")
        if args.harmonic_spikes:
            reference = [{"start": note.start, "end": note.end, "pitch": note.pitch}
                         for note in midi_notes]
            corrected_notes, corrected = correct_isolated_octave_spikes(reference)
            for index, (midi_note, score_note) in enumerate(zip(midi_notes, notes)):
                midi_note.pitch = score_note["pitch"] = corrected_notes[index]["pitch"]

    # Escala editorial em segundos só para reutilizar o escritor. Os ticks
    # originais são reconstruídos exatamente; o MIDI preserva a execução real.
    seconds_per_beat = 60.0 / metadata["display_bpm"]
    score_melody = [{"start": n["start"] / TICKS_PER_BEAT * seconds_per_beat,
                     "end": n["end"] / TICKS_PER_BEAT * seconds_per_beat,
                     "pitch": n["pitch"], "amplitude": n["amplitude"]} for n in notes]
    beat_count = int(max(note["end"] for note in notes) / TICKS_PER_BEAT) + 5
    beat_times = [i * seconds_per_beat for i in range(beat_count)]
    write_musicxml(score_melody, beat_times, str(args.output_xml),
                   downbeat_time=0.0, readable_notation=True, phrase_downbeats=True,
                   part_name="Flauta", instrument_name="Flute", midi_program=74,
                   **metadata)
    if midi is not None:
        midi.write(str(args.output_midi))
    print(f"Notas: {len(notes)}; picos de oitava corrigidos: {corrected}")
    print(f"MusicXML editorial: {args.output_xml}")
    if args.output_midi:
        print(f"MIDI com tempos preservados: {args.output_midi}")


if __name__ == "__main__":
    main()
