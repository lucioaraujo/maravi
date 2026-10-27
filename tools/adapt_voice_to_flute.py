#!/usr/bin/env python3
"""Cria um rascunho de flauta a partir de MusicXML e MIDI vocais concordantes.

Só desloca oitavas de frases inteiras quando todas as notas da frase cabem na
tessitura escolhida. Preserva a linha de origem e registra notas pendentes.
Não identifica a voz, não separa fontes e não aprova a transcrição musical.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import xml.etree.ElementTree as ET


STEP_PITCH = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
OCTAVE_SHIFTS = (0, 12, -12, 24, -24)


def _pitch_value(pitch: ET.Element) -> int:
    step = pitch.findtext("step")
    octave = pitch.findtext("octave")
    if step not in STEP_PITCH or octave is None:
        raise ValueError("MusicXML com altura incompleta")
    return 12 * (int(octave) + 1) + STEP_PITCH[step] + int(pitch.findtext("alter", "0"))


def _logical_notes(root: ET.Element) -> list[dict]:
    parts = root.findall("part")
    if len(parts) != 1:
        raise ValueError("A adaptação exige uma única parte monofônica")
    groups: list[dict] = []
    for measure in parts[0].findall("measure"):
        for note in measure.findall("note"):
            if note.find("chord") is not None or note.find("grace") is not None:
                raise ValueError("A adaptação não aceita acordes nem apogiaturas")
            pitch = note.find("pitch")
            if pitch is None:
                continue
            value = _pitch_value(pitch)
            is_stop = note.find('tie[@type="stop"]') is not None
            is_start = note.find('tie[@type="start"]') is not None
            if is_stop:
                if not groups or groups[-1]["pitch"] != value or not groups[-1]["tie_open"]:
                    raise ValueError("Ligadura de duração inconsistente no MusicXML")
                groups[-1]["elements"].append(pitch)
                groups[-1]["tie_open"] = is_start
            else:
                if groups and groups[-1]["tie_open"]:
                    raise ValueError("Ligadura de duração aberta no MusicXML")
                groups.append({"pitch": value, "elements": [pitch],
                               "measure": measure.get("number", "?"),
                               "tie_open": is_start})
    if not groups or groups[-1]["tie_open"]:
        raise ValueError("MusicXML vazio ou com ligadura de duração aberta")
    return groups


def plan_octave_adaptation(notes: list, *, low: int = 59, high: int = 96,
                           phrase_gap: float = 0.4) -> tuple[list[int], list[dict]]:
    """Devolve alturas e decisões por frase; nenhuma nota é excluída."""
    if not 0 <= low <= high <= 127 or phrase_gap <= 0:
        raise ValueError("Tessitura ou pausa de frase inválida")
    if not notes:
        raise ValueError("Nenhuma nota melódica disponível")
    phrases: list[list[int]] = [[0]]
    for index in range(1, len(notes)):
        if notes[index].start - notes[index - 1].end >= phrase_gap:
            phrases.append([index])
        else:
            phrases[-1].append(index)
    adapted = [int(note.pitch) for note in notes]
    decisions: list[dict] = []
    for phrase_number, indexes in enumerate(phrases, start=1):
        source = [int(notes[i].pitch) for i in indexes]
        possible = [shift for shift in OCTAVE_SHIFTS
                    if all(low <= pitch + shift <= high for pitch in source)]
        shift = possible[0] if possible else 0
        if possible:
            for i in indexes:
                adapted[i] += shift
        decisions.append({
            "phrase": phrase_number,
            "first_note": indexes[0] + 1,
            "last_note": indexes[-1] + 1,
            "start_seconds": round(float(notes[indexes[0]].start), 3),
            "end_seconds": round(float(notes[indexes[-1]].end), 3),
            "pitch_min": min(source),
            "pitch_max": max(source),
            "octave_shift": shift,
            "uniform_shift_possible": bool(possible),
            "outside_count": sum(pitch < low or pitch > high for pitch in source) if not possible else 0,
        })
    return adapted, decisions


def adapt_score(source_xml: Path, source_midi: Path, output_prefix: Path,
                *, low: int = 59, high: int = 96, phrase_gap: float = 0.4,
                audit_json: Path | None = None) -> dict:
    """Publica MusicXML, MIDI e relatório novos após validar a correspondência."""
    import pretty_midi

    source_xml, source_midi, output_prefix = map(Path, (source_xml, source_midi, output_prefix))
    outputs = [output_prefix.with_suffix(ext) for ext in (".musicxml", ".mid", ".json")]
    if not output_prefix.parent.is_dir() or any(path.exists() for path in outputs):
        raise FileExistsError("Pasta de saída ausente ou um dos derivados já existe")

    root = ET.parse(source_xml).getroot()
    groups = _logical_notes(root)
    midi = pretty_midi.PrettyMIDI(str(source_midi))
    if len(midi.instruments) != 1:
        raise ValueError("O MIDI precisa conter uma só linha melódica")
    notes = sorted(midi.instruments[0].notes, key=lambda note: note.start)
    if len(notes) != len(groups) or [note.pitch for note in notes] != [g["pitch"] for g in groups]:
        raise ValueError("MusicXML e MIDI divergem em quantidade ou altura das notas")
    tentative_pitch = [note.pitch for note in notes]
    audit_corrections = []
    if audit_json is not None:
        audit_json = Path(audit_json)
        pitch_audit = json.loads(audit_json.read_text(encoding="utf-8"))
        if pitch_audit.get("midi_sha256") != sha256(source_midi.read_bytes()).hexdigest():
            raise ValueError("Auditoria não corresponde ao MIDI vocal de entrada")
        seen = set()
        for row in pitch_audit["notes"]:
            if row["status"] != "oitava_suspeita":
                continue
            index = int(row["note"]) - 1
            if index in seen or not 0 <= index < len(notes):
                raise ValueError("Índice de nota repetido ou fora do MIDI na auditoria")
            seen.add(index)
            original = notes[index].pitch
            if (original != row["midi_pitch"]
                    or abs(notes[index].start - row["start_seconds"]) > 0.002):
                raise ValueError("Nota da auditoria diverge do MIDI vocal")
            estimate = float(row["estimated_midi_pitch"])
            shift = min((-24, -12, 12, 24), key=lambda step: abs(original + step - estimate))
            target = original + shift
            if not 0 <= target <= 127 or abs(target - estimate) > 0.6:
                raise ValueError("Estimativa não sustenta a correção de oitava")
            tentative_pitch[index] = target
            audit_corrections.append({"note": index + 1, "measure": groups[index]["measure"],
                                      "from_pitch": original, "to_pitch": target,
                                      "estimated_pitch": estimate})
    planning_notes = [SimpleNamespace(start=note.start, end=note.end,
                                      pitch=pitch)
                      for note, pitch in zip(notes, tentative_pitch)]
    adapted, decisions = plan_octave_adaptation(planning_notes, low=low, high=high,
                                                phrase_gap=phrase_gap)
    changes = []
    for index, (note, group, target) in enumerate(zip(notes, groups, adapted), start=1):
        shift = target - note.pitch
        if shift:
            for pitch in group["elements"]:
                octave = pitch.find("octave")
                octave.text = str(int(octave.text) + shift // 12)
            changes.append({"note": index, "measure": group["measure"],
                            "start_seconds": round(note.start, 3),
                            "from_pitch": note.pitch, "to_pitch": target})
            note.pitch = target

    score_part = root.find("part-list/score-part")
    if score_part is None:
        raise ValueError("MusicXML sem identificação de parte")
    part_name = score_part.find("part-name")
    instrument_name = score_part.find("score-instrument/instrument-name")
    midi_program = score_part.find("midi-instrument/midi-program")
    if part_name is None or instrument_name is None or midi_program is None:
        raise ValueError("MusicXML sem informação instrumental completa")
    part_name.text = "Flauta (rascunho para revisão)"
    instrument_name.text = "Flute"
    midi_program.text = "74"  # MusicXML: 1-based; pretty_midi: 0-based.
    title = root.find("work/work-title")
    if title is not None and title.text:
        title.text += " — flauta (rascunho)"
    midi.instruments[0].name = "Flauta (rascunho)"
    midi.instruments[0].program = 73

    report = {
        "status": "rascunho_para_revisao_musical",
        "source_xml": str(source_xml), "source_midi": str(source_midi),
        "source_xml_sha256": sha256(source_xml.read_bytes()).hexdigest(),
        "source_midi_sha256": sha256(source_midi.read_bytes()).hexdigest(),
        "range_midi": [low, high], "phrase_gap_seconds": phrase_gap,
        "note_count": len(notes), "phrase_count": len(decisions),
        "shifted_phrase_count": sum(d["octave_shift"] != 0 for d in decisions),
        "shifted_note_count": len(changes),
        "outside_before": sum(g["pitch"] < low or g["pitch"] > high for g in groups),
        "outside_after_pitch_audit": sum(pitch < low or pitch > high for pitch in tentative_pitch),
        "outside_after": sum(pitch < low or pitch > high for pitch in adapted),
        "unresolved_phrase_count": sum(not d["uniform_shift_possible"] for d in decisions),
        "audit_json": None if audit_json is None else str(audit_json),
        "audit_json_sha256": None if audit_json is None else sha256(audit_json.read_bytes()).hexdigest(),
        "audit_corrections": audit_corrections,
        "phrases": decisions, "changes": changes,
        "limits": "Variante editorial experimental. Uma auditoria de F0 pode seguir cello residual ou errar a oitava; não identifica cantora nem aprova a transcrição musical.",
    }
    with tempfile.TemporaryDirectory(prefix="maravi-flute-", dir=output_prefix.parent) as temp:
        temp_paths = [Path(temp) / path.name for path in outputs]
        xml_body = ET.tostring(root, encoding="unicode")
        temp_paths[0].write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
            '"http://www.musicxml.org/dtds/partwise.dtd">\n' + xml_body + "\n",
            encoding="utf-8",
        )
        midi.write(str(temp_paths[1]))
        temp_paths[2].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
        verified = _logical_notes(ET.parse(temp_paths[0]).getroot())
        verified_midi = pretty_midi.PrettyMIDI(str(temp_paths[1]))
        verified_notes = sorted(verified_midi.instruments[0].notes,
                                key=lambda note: note.start)
        if ([g["pitch"] for g in verified] != adapted
                or [note.pitch for note in verified_notes] != adapted
                or any(abs(a.start - b.start) > 0.002 or abs(a.end - b.end) > 0.002
                       for a, b in zip(notes, verified_notes))):
            raise ValueError("O derivado divergiu da adaptação planejada")
        published = []
        try:
            for temporary, destination in zip(temp_paths, outputs):
                os.link(temporary, destination)  # Não substitui arquivo existente.
                published.append(destination)
        except OSError:
            for destination in published:
                destination.unlink()
            raise
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_xml", type=Path)
    parser.add_argument("source_midi", type=Path)
    parser.add_argument("output_prefix", type=Path)
    parser.add_argument("--low", type=int, default=59, help="Piso MIDI; padrão si3")
    parser.add_argument("--high", type=int, default=96, help="Teto editorial MIDI; padrão dó7")
    parser.add_argument("--phrase-gap", type=float, default=0.4,
                        help="Pausa mínima entre frases em segundos")
    parser.add_argument("--audit-json", type=Path,
                        help="Aplica somente pistas de oitava da auditoria F0 ao MIDI correspondente")
    args = parser.parse_args()
    result = adapt_score(args.source_xml, args.source_midi, args.output_prefix,
                         low=args.low, high=args.high, phrase_gap=args.phrase_gap,
                         audit_json=args.audit_json)
    print(json.dumps({key: result[key] for key in (
        "note_count", "phrase_count", "shifted_phrase_count", "shifted_note_count",
        "outside_before", "outside_after", "unresolved_phrase_count")},
        ensure_ascii=False))


if __name__ == "__main__":
    main()
