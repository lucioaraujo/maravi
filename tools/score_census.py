"""Censo estrutural consultivo da linha melódica, sem editar nem julgar a música."""
from __future__ import annotations

from bisect import bisect_right
from statistics import median
from pathlib import Path
from xml.etree import ElementTree


# Faixas de referência para sinalizar revisão. Não são limites físicos ou
# regras de exclusão: intérpretes e técnicas podem ultrapassá-las.
REFERENCE_RANGES = {
    "flute": (59, 96),   # B3–C7; inclui a extensão grave citada pelo autor.
    "violin": (55, 100), # G3–E7.
}
FIGURE_BEATS = {
    "maxima": 32.0, "long": 16.0, "breve": 8.0, "whole": 4.0,
    "half": 2.0, "quarter": 1.0, "eighth": 0.5, "16th": 0.25,
    "32nd": 0.125, "64th": 0.0625, "128th": 0.03125,
    "256th": 0.015625,
}


def census_written_figures(musicxml_path: Path) -> dict:
    """Count written note symbols and very short values in the emitted score."""
    root = ElementTree.parse(musicxml_path).getroot()
    timed = []
    grace_count = 0
    for note in root.iter("note"):
        if note.find("pitch") is None:
            continue
        if note.find("grace") is not None:
            grace_count += 1
            continue
        figure = note.findtext("type")
        if figure not in FIGURE_BEATS:
            continue
        beats = FIGURE_BEATS[figure]
        beats *= 1.5 ** len(note.findall("dot"))
        ratio = note.find("time-modification")
        if ratio is not None:
            actual = int(ratio.findtext("actual-notes", "1"))
            normal = int(ratio.findtext("normal-notes", "1"))
            if actual > 0:
                beats *= normal / actual
        timed.append(beats)
    count = len(timed)
    short = sum(value < 0.5 for value in timed)
    very_short = sum(value < 0.25 for value in timed)
    short_percent = round(short * 100 / count) if count else 0
    very_short_percent = round(very_short * 100 / count) if count else 0
    warnings = []
    if short_percent >= 40:
        warnings.append({"key": "census_many_short_symbols", "count": short,
                         "percent": short_percent})
    if very_short_percent >= 20:
        warnings.append({"key": "census_many_very_short_symbols", "count": very_short,
                         "percent": very_short_percent})
    return {
        "written_symbol_count": count,
        "grace_symbol_count": grace_count,
        "short_symbol_count": short,
        "short_symbol_percent": short_percent,
        "very_short_symbol_count": very_short,
        "very_short_symbol_percent": very_short_percent,
        "warnings": warnings,
    }


def _local_beat_seconds(
    start: float, beat_times: list[float], fallback: float | None
) -> float | None:
    if len(beat_times) < 2:
        return None
    index = bisect_right(beat_times, start) - 1
    index = max(0, min(index, len(beat_times) - 2))
    local = beat_times[index + 1] - beat_times[index]
    if local <= 0:
        return fallback
    return local


def census_melody(
    notes: list[dict],
    beat_times: list[float],
    instrument: str,
    voice_minimum: int | None = None,
) -> dict:
    """Return reproducible metrics and review prompts for a monophonic line.

    Thresholds identify review candidates only. The function never changes,
    removes, transposes, or recalculates notes.
    """
    valid = []
    for note in notes:
        try:
            start, end, pitch = float(note["start"]), float(note["end"]), int(note["pitch"])
        except (KeyError, TypeError, ValueError):
            continue
        if end > start:
            valid.append((start, end, pitch))
    valid.sort(key=lambda event: (event[0], event[1]))
    count = len(valid)
    if not count:
        return {"note_count": 0, "range": None, "short_count": 0,
                "short_percent": 0, "very_short_count": 0,
                "very_short_percent": 0, "wide_leap_count": 0,
                "overlap_count": 0, "outside_count": 0, "warnings": []}

    pitches = [event[2] for event in valid]
    intervals = [b - a for a, b in zip(beat_times, beat_times[1:]) if b > a]
    fallback_beat = median(intervals) if intervals else None
    short_count = very_short_count = overlap_count = 0
    furthest_end = float("-inf")
    for index, (start, end, _pitch) in enumerate(valid):
        beat = _local_beat_seconds(start, beat_times, fallback_beat)
        if beat:
            duration_in_beats = (end - start) / beat
            short_count += duration_in_beats < 0.5
            very_short_count += duration_in_beats < 0.25
        if start < furthest_end - 0.03:
            overlap_count += 1
        furthest_end = max(furthest_end, end)

    wide_leap_count = sum(abs(b - a) > 12 for a, b in zip(pitches, pitches[1:]))
    ref_low, ref_high = REFERENCE_RANGES.get(instrument, (None, None))
    if instrument == "voice" and voice_minimum is not None:
        ref_low = voice_minimum
    outside_count = (sum(p < ref_low or p > ref_high for p in pitches)
                     if ref_low is not None and ref_high is not None else
                     sum(p < ref_low for p in pitches) if ref_low is not None else 0)

    short_percent = round(short_count * 100 / count)
    very_short_percent = round(very_short_count * 100 / count)
    warnings = []
    if short_percent >= 40:
        warnings.append({"key": "census_many_short", "count": short_count,
                         "percent": short_percent})
    if very_short_percent >= 20:
        warnings.append({"key": "census_many_very_short", "count": very_short_count,
                         "percent": very_short_percent})
    if wide_leap_count >= max(3, round(count * 0.08)):
        warnings.append({"key": "census_wide_leaps", "count": wide_leap_count})
    if overlap_count:
        warnings.append({"key": "census_overlaps", "count": overlap_count})
    if outside_count:
        warnings.append({"key": "census_outside_range", "count": outside_count,
                         "low": ref_low if ref_low is not None else "—",
                         "high": ref_high if ref_high is not None else "—"})

    return {
        "note_count": count,
        "range": [min(pitches), max(pitches)],
        "short_count": short_count,
        "short_percent": short_percent,
        "very_short_count": very_short_count,
        "very_short_percent": very_short_percent,
        "wide_leap_count": wide_leap_count,
        "overlap_count": overlap_count,
        "outside_count": outside_count,
        "warnings": warnings,
    }
