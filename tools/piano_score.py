"""Primeira escrita polifônica de piano em duas pautas, sem inferir mãos reais.

Cada evento detectado mantém sua altura e tempo; o registro separa as pautas
(dó4/MIDI 60 como divisão inicial). Não usar este rascunho como atribuição
verificada da mão direita/esquerda numa gravação polifônica ou orquestrada.
"""
from __future__ import annotations

from collections import defaultdict
from math import ceil
from pathlib import Path
from xml.sax.saxutils import escape

from musicxml_writer import TICKS_PER_BEAT, figure_for_ticks, midi_note_to_xml_pitch


PIANO_LOW = 21
PIANO_HIGH = 108
PIANO_SPLIT = 60
GRID_TICKS = 6  # semicolcheia; não inventa quiálteras na primeira versão


def piano_notes_from_events(events: list[tuple]) -> list[dict]:
    """Preserva polifonia; ignora apenas alturas fora do piano e eventos vazios."""
    return sorted(
        ({"start": float(start), "end": float(end), "pitch": int(pitch),
          "amplitude": float(amplitude)}
         for start, end, pitch, amplitude, *_ in events
         if end > start and PIANO_LOW <= int(pitch) <= PIANO_HIGH),
        key=lambda note: (note["start"], note["pitch"], note["end"]),
    )


def piano_to_midi(notes: list[dict], bpm: float, beats_per_measure: int,
                  beat_unit: int, split: int = PIANO_SPLIT):
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    pm.time_signature_changes.append(
        pretty_midi.TimeSignature(beats_per_measure, beat_unit, 0.0)
    )
    upper = pretty_midi.Instrument(program=0, name="Piano - pauta superior")
    lower = pretty_midi.Instrument(program=0, name="Piano - pauta inferior")
    for note in notes:
        target = upper if note["pitch"] >= split else lower
        target.notes.append(pretty_midi.Note(
            velocity=max(1, min(127, round(note["amplitude"] * 127))),
            pitch=note["pitch"], start=note["start"], end=note["end"],
        ))
    pm.instruments.extend((upper, lower))
    return pm


def _quantized_groups(notes: list[dict], beat_times: list[float],
                      downbeat_time: float, split: int):
    from beat_grid import time_to_step

    anchor = time_to_step(downbeat_time, beat_times, TICKS_PER_BEAT)
    grouped: dict[int, dict[tuple[int, int], set[int]]] = {1: defaultdict(set), 2: defaultdict(set)}
    for note in notes:
        start = max(0, round((time_to_step(note["start"], beat_times, TICKS_PER_BEAT)
                               - anchor) / GRID_TICKS) * GRID_TICKS)
        end = round((time_to_step(note["end"], beat_times, TICKS_PER_BEAT)
                     - anchor) / GRID_TICKS) * GRID_TICKS
        end = max(start + GRID_TICKS, end)
        staff = 1 if note["pitch"] >= split else 2
        grouped[staff][(start, end)].add(note["pitch"])
    return {
        staff: [(start, end, tuple(sorted(pitches)))
                for (start, end), pitches in sorted(groups.items())]
        for staff, groups in grouped.items()
    }


def _voices(groups: list[tuple[int, int, tuple[int, ...]]]):
    """Distribui durações sobrepostas em vozes; acordes iguais ficam juntos."""
    voices: list[list[tuple[int, int, tuple[int, ...]]]] = []
    voice_ends: list[int] = []
    for group in groups:
        start, end, _ = group
        for index, voice_end in enumerate(voice_ends):
            if start >= voice_end:
                voices[index].append(group)
                voice_ends[index] = end
                break
        else:
            voices.append([group])
            voice_ends.append(end)
    return voices or [[]]


def _emit_span(lines: list[str], duration: int, voice: int, staff: int,
               pitches: tuple[int, ...] | None, key_fifths: int,
               tie_stop: bool = False, tie_start: bool = False) -> None:
    """Escreve figuras binárias exatas; liga notas partidas por barra/figura."""
    remaining = duration
    first = True
    while remaining:
        ticks, kind, dots, tuplet = figure_for_ticks(remaining)
        if tuplet is not None or ticks % GRID_TICKS:
            raise ValueError("Duração do piano fora da grade binária")
        last = ticks == remaining
        for chord_index, pitch in enumerate(pitches or (None,)):
            lines.append("<note>")
            if chord_index:
                lines.append("<chord/>")
            if pitch is None:
                lines.append("<rest/>")
            else:
                step, alter, octave = midi_note_to_xml_pitch(pitch, key_fifths)
                lines.append(f"<pitch><step>{step}</step>")
                if alter:
                    lines.append(f"<alter>{alter}</alter>")
                lines.append(f"<octave>{octave}</octave></pitch>")
            lines.append(f"<duration>{ticks}</duration>")
            has_stop = pitch is not None and (tie_stop or not first)
            has_start = pitch is not None and (tie_start or not last)
            if has_stop:
                lines.append('<tie type="stop"/>')
            if has_start:
                lines.append('<tie type="start"/>')
            lines.append(f"<voice>{voice}</voice>")
            lines.append(f"<type>{kind}</type>")
            if dots:
                lines.append("<dot/>")
            lines.append(f"<staff>{staff}</staff>")
            if has_stop or has_start:
                lines.append("<notations>")
                if has_stop:
                    lines.append('<tied type="stop"/>')
                if has_start:
                    lines.append('<tied type="start"/>')
                lines.append("</notations>")
            lines.append("</note>")
        remaining -= ticks
        first = False


def write_piano_musicxml(notes: list[dict], beat_times: list[float], path: str,
                         beats_per_measure: int, beat_unit: int,
                         downbeat_time: float, display_bpm: float,
                         key_fifths: int = 0, key_mode: str = "major",
                         work_title: str | None = None,
                         composer: str | None = None,
                         split: int = PIANO_SPLIT) -> None:
    """Uma parte Piano com claves de sol/fá, acordes e vozes independentes."""
    if not notes:
        raise ValueError("Nenhuma nota de piano foi detectada")
    if beat_unit not in (1, 2, 4, 8, 16):
        raise ValueError("Denominador de compasso inválido")
    measure_ticks = TICKS_PER_BEAT * beats_per_measure * 4 // beat_unit
    if measure_ticks <= 0 or measure_ticks % GRID_TICKS:
        raise ValueError("Este compasso não cabe na grade inicial do piano")
    groups = _quantized_groups(notes, beat_times, downbeat_time, split)
    voices = {staff: _voices(groups[staff]) for staff in (1, 2)}
    last_tick = max(end for staff_groups in groups.values() for _, end, _ in staff_groups)
    measure_count = max(1, ceil(last_tick / measure_ticks))

    lines = ['<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
             '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
             '"http://www.musicxml.org/dtds/partwise.dtd">',
             '<score-partwise version="4.0">']
    if work_title:
        lines.append(f"<work><work-title>{escape(work_title)}</work-title></work>")
    if composer:
        lines.append(f'<identification><creator type="composer">{escape(composer)}</creator></identification>')
    lines.append('<part-list><score-part id="P1"><part-name>Piano</part-name>'
                 '<score-instrument id="I1"><instrument-name>Piano</instrument-name></score-instrument>'
                 '<midi-instrument id="I1"><midi-channel>1</midi-channel>'
                 '<midi-program>1</midi-program></midi-instrument></score-part></part-list>')
    lines.append('<part id="P1">')
    for measure_index in range(measure_count):
        bar_start = measure_index * measure_ticks
        bar_end = bar_start + measure_ticks
        lines.append(f'<measure number="{measure_index + 1}">')
        if measure_index == 0:
            lines.append(f'<attributes><divisions>{TICKS_PER_BEAT}</divisions>'
                         f'<key><fifths>{key_fifths}</fifths><mode>{escape(key_mode)}</mode></key>'
                         f'<time><beats>{beats_per_measure}</beats><beat-type>{beat_unit}</beat-type></time>'
                         '<staves>2</staves><clef number="1"><sign>G</sign><line>2</line></clef>'
                         '<clef number="2"><sign>F</sign><line>4</line></clef></attributes>')
            lines.append(f'<direction><direction-type><metronome><beat-unit>quarter</beat-unit>'
                         f'<per-minute>{display_bpm:.1f}</per-minute></metronome></direction-type>'
                         f'<sound tempo="{display_bpm:.1f}"/></direction>')
        layers = []
        voice_id = 1
        for staff in (1, 2):
            for voice in voices[staff]:
                active = [group for group in voice if group[0] < bar_end and group[1] > bar_start]
                if active or voice is voices[staff][0]:
                    layers.append((voice_id, staff, active))
                voice_id += 1
        for layer_index, (voice_id, staff, active) in enumerate(layers):
            if layer_index:
                lines.append(f'<backup><duration>{measure_ticks}</duration></backup>')
            cursor = bar_start
            for start, end, pitches in active:
                clipped_start, clipped_end = max(start, bar_start), min(end, bar_end)
                if clipped_start > cursor:
                    _emit_span(lines, clipped_start - cursor, voice_id, staff, None, key_fifths)
                _emit_span(lines, clipped_end - clipped_start, voice_id, staff,
                           pitches, key_fifths, start < bar_start, end > bar_end)
                cursor = clipped_end
            if cursor < bar_end:
                _emit_span(lines, bar_end - cursor, voice_id, staff, None, key_fifths)
        lines.append('</measure>')
    lines.append('</part></score-partwise>')
    Path(path).write_text(''.join(lines), encoding='utf-8')
