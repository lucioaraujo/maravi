#!/usr/bin/env python3
"""Corrige apenas o rótulo instrumental de um job antigo, sem reanalisar áudio.

Gera derivados novos no mesmo diretório. Notas, pausas, tempo e alturas do
MusicXML e eventos de nota do MIDI permanecem como estavam. O instrumento
é declarado pelo músico; este comando não identifica fontes sonoras.
"""
from __future__ import annotations

import argparse
from html import escape
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import mido

from instrument_labels import SCORE_INSTRUMENTS


def relabel_job(job_dir: Path, instrument: str) -> tuple[Path, Path]:
    if instrument not in SCORE_INSTRUMENTS or instrument in ("melody", "piano_grand"):
        raise ValueError("Escolha piano, flute, violin ou voice para o derivado.")
    part_name, instrument_name, midi_zero, midi_one = SCORE_INSTRUMENTS[instrument]
    source_xml = job_dir / "resultado.musicxml"
    source_midi = job_dir / "resultado.mid"
    target_xml = job_dir / f"resultado_{instrument}_rotulado.musicxml"
    target_midi = job_dir / f"resultado_{instrument}_rotulado.mid"
    if target_xml.exists() or target_midi.exists():
        raise FileExistsError("O derivado já existe; nada foi sobrescrito.")

    xml = source_xml.read_text(encoding="utf-8")
    root = ET.fromstring(xml)
    parts = root.findall("./part-list/score-part")
    if len(parts) != 1 or parts[0].get("id") != "P1":
        raise ValueError("Apenas MusicXML de uma parte P1 é aceito.")
    pattern = re.compile(r'<score-part id="P1">.*?</score-part>', re.DOTALL)
    if len(pattern.findall(xml)) != 1:
        raise ValueError("Bloco de instrumento MusicXML inesperado.")
    new_part = (
        f'<score-part id="P1"><part-name>{escape(part_name)}</part-name>'
        f'<score-instrument id="I1"><instrument-name>{escape(instrument_name)}</instrument-name>'
        '</score-instrument>'
        f'<midi-instrument id="I1"><midi-channel>1</midi-channel>'
        f'<midi-program>{midi_one}</midi-program></midi-instrument></score-part>'
    )
    updated_xml = pattern.sub(lambda _: new_part, xml, count=1)
    ET.fromstring(updated_xml)

    midi = mido.MidiFile(str(source_midi))
    program_tracks = [track for track in midi.tracks
                      if any(message.type == "program_change" for message in track)]
    if len(program_tracks) != 1:
        raise ValueError("Apenas MIDI de uma parte instrumental é aceito.")
    program_changes = [message for message in program_tracks[0]
                       if message.type == "program_change"]
    if len(program_changes) != 1:
        raise ValueError("O MIDI deve ter um único programa instrumental.")
    program_changes[0].program = midi_zero
    for message in program_tracks[0]:
        if message.type == "track_name":
            message.name = f"{part_name} (melodia)"

    # Exclusividade: preservar os resultados originais e nunca sobrescrever
    # um derivado que o usuário já possa ter revisado na mão.
    with target_xml.open("x", encoding="utf-8") as output:
        output.write(updated_xml)
    with target_midi.open("xb") as output:
        midi.save(file=output)
    return target_xml, target_midi


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_dir", type=Path)
    parser.add_argument("--instrument", choices=sorted(SCORE_INSTRUMENTS.keys() - {"melody", "piano_grand"}), required=True)
    args = parser.parse_args()
    xml, midi = relabel_job(args.job_dir, args.instrument)
    print(f"Derivados criados: {xml} e {midi}")


if __name__ == "__main__":
    main()
