#!/usr/bin/env python3
"""Compara alturas de um MIDI vocal com F0 do stem em janelas curtas.

É uma auditoria de hipóteses, não separação de fontes nem correção automática:
um rastreador monofônico pode acompanhar cello residual ou errar oitavas.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path


def parse_window(value: str) -> tuple[float, float]:
    try:
        start, end = (float(part) for part in value.split(":"))
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError("Use início:fim em segundos") from exc
    if not 0 <= start < end or end - start > 15:
        raise argparse.ArgumentTypeError("Cada janela deve ter no máximo 15 s")
    return start, end


def classify_note(midi_pitch: int, estimated_pitch: float | None,
                  voiced_ratio: float, probability: float,
                  spread: float, frame_count: int) -> str:
    if (estimated_pitch is None or frame_count < 5 or voiced_ratio < 0.6
            or probability < 0.65 or spread > 0.6):
        return "inconclusivo"
    difference = midi_pitch - estimated_pitch
    if abs(difference) <= 0.6:
        return "compativel"
    if any(abs(abs(difference) - octave) <= 0.6 for octave in (12, 24)):
        return "oitava_suspeita"
    return "altura_divergente"


def audit_window(audio_path: Path, midi_notes: list, start: float, end: float) -> list[dict]:
    import librosa
    import numpy as np
    import soundfile as sf

    with sf.SoundFile(audio_path) as audio:
        if end > len(audio) / audio.samplerate:
            raise ValueError("Janela ultrapassa o áudio")
        audio.seek(round(start * audio.samplerate))
        signal = audio.read(round((end - start) * audio.samplerate),
                            dtype="float32", always_2d=True).mean(axis=1)
        sample_rate = audio.samplerate
    signal = librosa.resample(signal, orig_sr=sample_rate, target_sr=22050)
    f0, _, voiced_probability = librosa.pyin(
        signal, sr=22050, hop_length=256, frame_length=2048,
        fmin=librosa.note_to_hz("G3"), fmax=librosa.note_to_hz("C6"),
        n_thresholds=30,
    )
    times = np.arange(len(f0)) * 256 / 22050 + start
    result = []
    for index, note in enumerate(midi_notes, start=1):
        if not start <= note.start < end:
            continue
        duration = note.end - note.start
        margin = min(0.08, duration * 0.2)
        from_time, until_time = note.start + margin, min(note.end - margin, end)
        selected = (times >= from_time) & (times <= until_time)
        finite = selected & np.isfinite(f0)
        count = int(np.count_nonzero(finite))
        ratio = count / max(1, int(np.count_nonzero(selected)))
        if count:
            values = librosa.hz_to_midi(f0[finite])
            estimate = float(np.median(values))
            spread = float(np.median(np.abs(values - estimate)))
            probability = float(np.median(voiced_probability[finite]))
        else:
            estimate, spread, probability = None, 0.0, 0.0
        status = classify_note(note.pitch, estimate, ratio, probability, spread, count)
        result.append({
            "note": index, "start_seconds": round(note.start, 3),
            "end_seconds": round(note.end, 3), "midi_pitch": note.pitch,
            "estimated_midi_pitch": None if estimate is None else round(estimate, 2),
            "voiced_ratio": round(ratio, 2),
            "voiced_probability": round(probability, 2),
            "pitch_spread_semitones": round(spread, 2),
            "voiced_frames": count, "status": status,
        })
    return result


def audit(audio_path: Path, midi_path: Path,
          windows: list[tuple[float, float]]) -> dict:
    import pretty_midi

    if not windows:
        raise ValueError("É necessária pelo menos uma janela")
    ordered = sorted(windows)
    if any(current[0] < previous[1] for previous, current in zip(ordered, ordered[1:])):
        raise ValueError("Janelas sobrepostas duplicariam notas")
    midi = pretty_midi.PrettyMIDI(str(midi_path))
    if len(midi.instruments) != 1:
        raise ValueError("É esperada uma única linha MIDI")
    notes = sorted(midi.instruments[0].notes, key=lambda note: note.start)
    rows = []
    for start, end in ordered:
        rows.extend(audit_window(audio_path, notes, start, end))
    counts = {key: sum(row["status"] == key for row in rows) for key in (
        "compativel", "oitava_suspeita", "altura_divergente", "inconclusivo")}
    return {
        "audio_path": str(audio_path), "midi_path": str(midi_path),
        "audio_sha256": sha256(audio_path.read_bytes()).hexdigest(),
        "midi_sha256": sha256(midi_path.read_bytes()).hexdigest(),
        "windows_seconds": ordered, "note_count": len(rows), "counts": counts,
        "method": "librosa.pyin no stem vocal, G3-C6, 22050 Hz, janelas <=15 s",
        "limit": "F0 monofônico não identifica cantora nem distingue cello residual; rótulos são pistas para escuta, nunca correções automáticas.",
        "notes": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    parser.add_argument("midi", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--window", type=parse_window, action="append", required=True,
                        help="início:fim em segundos; repetir para janelas distintas")
    args = parser.parse_args()
    if args.output_json.exists() or not args.output_json.parent.is_dir():
        parser.error("A saída já existe ou a pasta de destino não existe")
    result = audit(args.audio, args.midi, args.window)
    with args.output_json.open("x", encoding="utf-8") as destination:
        json.dump(result, destination, ensure_ascii=False, indent=2)
        destination.write("\n")
    print(json.dumps({"notes": result["note_count"], "counts": result["counts"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
