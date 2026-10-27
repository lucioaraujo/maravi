"""Prévia leve da saída MusicXML do Maravi; não substitui um editor de partitura.

Lê apenas os quatro primeiros compassos do MusicXML monofônico que o próprio
Maravi escreveu. A pauta é esquemática: mostra alturas, figuras, pausas,
acidentes, pontos, quiálteras e ligaduras, sem tentar engravação completa.
"""
from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

MAX_XML_BYTES = 2_000_000
MAX_MEASURES = 4
MAX_EVENTS = 96
STEPS = "CDEFGAB"
FIGURES = {"whole", "half", "quarter", "eighth", "16th", "32nd", "64th"}
SHARP_ORDER = "FCGDAEB"
FLAT_ORDER = "BEADGCF"


def _number(value: str | None, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


def _pitch_y(step: str, octave: int) -> float:
    # Linha inferior da clave de sol: mi4, y=130; cada grau = 7,5 px.
    return 130 - ((octave * 7 + STEPS.index(step)) - (4 * 7 + STEPS.index("E"))) * 7.5


def _key_alter(step: str, fifths: int) -> int:
    if fifths > 0 and step in SHARP_ORDER[:min(fifths, 7)]:
        return 1
    if fifths < 0 and step in FLAT_ORDER[:min(-fifths, 7)]:
        return -1
    return 0


def render_score_preview(path: Path) -> str | None:
    """Retorna SVG seguro ou None se o arquivo não couber no recorte suportado."""
    if not path.is_file() or path.stat().st_size > MAX_XML_BYTES:
        return None
    try:
        root = ET.fromstring(path.read_bytes())
    except ET.ParseError:
        return None
    if root.tag != "score-partwise":
        return None
    part = root.find("part")
    if part is None:
        return None
    measures = part.findall("measure")[:MAX_MEASURES]
    if not measures:
        return None

    attributes = measures[0].find("attributes")
    if attributes is None:
        return None
    fifths = _number(attributes.findtext("key/fifths"))
    beats = _number(attributes.findtext("time/beats"), 4)
    beat_type = _number(attributes.findtext("time/beat-type"), 4)
    if not (-7 <= fifths <= 7 and 1 <= beats <= 32 and beat_type in {1, 2, 4, 8, 16}):
        return None

    bars: list[list[dict]] = []
    bar_labels: list[str] = []
    total_read = 0
    for measure in measures:
        events: list[dict] = []
        number = measure.get("number", "")
        bar_labels.append(number if number.isdigit() else str(len(bars) + 1))
        accidentals: dict[tuple[str, int], int] = {}
        for note in measure.findall("note"):
            total_read += 1
            if note.find("chord") is not None or total_read > MAX_EVENTS:
                return None
            figure = note.findtext("type")
            if figure not in FIGURES:
                return None
            is_rest = note.find("rest") is not None
            event = {
                "rest": is_rest,
                "figure": figure,
                "dot": note.find("dot") is not None,
                "tie_start": any(t.get("type") == "start" for t in note.findall("tie")),
                "tie_stop": any(t.get("type") == "stop" for t in note.findall("tie")),
                "tuplet": _number(note.findtext("time-modification/actual-notes"))
                if note.find("notations/tuplet[@type='start']") is not None else 0,
            }
            if not is_rest:
                step = note.findtext("pitch/step")
                octave = _number(note.findtext("pitch/octave"), -100)
                alter = _number(note.findtext("pitch/alter"))
                if step not in STEPS or not (0 <= octave <= 9) or alter not in {-1, 0, 1}:
                    return None
                expected = accidentals.get((step, octave), _key_alter(step, fifths))
                event.update(step=step, octave=octave, alter=alter,
                             accidental={-1: "♭", 0: "♮", 1: "♯"}[alter] if alter != expected else "")
                accidentals[(step, octave)] = alter
            events.append(event)
        bars.append(events)

    total_events = sum(len(bar) for bar in bars)
    if total_events == 0 or total_events > MAX_EVENTS:
        return None
    signature_width = 18 * abs(fifths)
    widths = [max(280, 48 * len(bar) + 70) + (125 + signature_width if index == 0 else 0)
              for index, bar in enumerate(bars)]
    total_width = sum(widths)
    note_ys = [_pitch_y(e["step"], e["octave"]) for bar in bars for e in bar if not e["rest"]]
    top = min(0, min(note_ys, default=70) - 75)  # espaço para o número da quiáltera
    bottom = max(210, max(note_ys, default=130) + 45)
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="{bottom-top:g}" '
        f'viewBox="0 {top:g} {total_width} {bottom-top:g}" '
        'role="img" aria-labelledby="score-title score-desc">',
        '<title id="score-title">Primeiros compassos do MusicXML gerado</title>',
        '<desc id="score-desc">Prévia esquemática das alturas, durações, pausas e acidentes '
        'do arquivo produzido neste job. A revisão completa deve ser feita num editor de partituras.</desc>',
        f'<rect x="0" y="{top:g}" width="{total_width}" height="{bottom-top:g}" fill="#14201f"/>',
    ]
    cursor = 0
    previous_tie: tuple[dict, float, float] | None = None
    for bar_index, (bar, width) in enumerate(zip(bars, widths)):
        end = cursor + width
        for y in (70, 85, 100, 115, 130):
            out.append(f'<path d="M{cursor+12} {y}H{end-12}" stroke="#78948c" stroke-width="1.3"/>')
        out.append(f'<path d="M{end-13} 70V130" stroke="#b9c7c0" stroke-width="1.5"/>')
        out.append(f'<text x="{cursor+20}" y="35" fill="#aabdb6" font-size="16" '
                   f'font-family="sans-serif">Compasso {bar_labels[bar_index]}</text>')
        if bar_index == 0:
            out.append('<path d="M71 161C53 166 40 152 42 136C44 120 63 110 77 118C88 126 82 141 69 141C56 140 50 125 58 110C65 97 89 79 96 58C103 37 88 25 78 38C68 50 75 68 88 86C105 110 108 133 98 155C92 168 81 175 71 174" '
                       'fill="none" stroke="#e7a94c" stroke-width="4" stroke-linecap="round"/>')
            signature_steps = SHARP_ORDER[:fifths] if fifths > 0 else FLAT_ORDER[:abs(fifths)]
            signature_octaves = (5, 5, 5, 5, 4, 5, 4) if fifths > 0 else (4, 5, 4, 5, 4, 5, 4)
            symbol = "♯" if fifths > 0 else "♭"
            for sig_index, step in enumerate(signature_steps):
                sig_y = _pitch_y(step, signature_octaves[sig_index])
                out.append(f'<text x="{116 + 18*sig_index}" y="{sig_y+7:g}" '
                           f'fill="#5cb3a9" font-size="25" font-family="serif">{symbol}</text>')
            time_x = 120 + signature_width
            out.append(f'<text x="{time_x}" y="100" fill="#ede7da" font-size="30" font-family="serif">{beats}</text>')
            out.append(f'<text x="{time_x}" y="125" fill="#ede7da" font-size="30" font-family="serif">{beat_type}</text>')
        margin = 175 + signature_width if bar_index == 0 else 35
        content_width = width - margin - 27
        for index, event in enumerate(bar):
            x = cursor + margin + (index + 0.5) * content_width / max(1, len(bar))
            if event["rest"]:
                out.append(f'<g><title>Pausa: {escape(event["figure"])}</title>'
                           f'<path d="M{x-7:.1f} 98h14v5h-14z" fill="#e7a94c"/>'
                           f'<text x="{x:.1f}" y="163" text-anchor="middle" fill="#aabdb6" '
                           'font-size="12" font-family="sans-serif">pausa</text>')
                if event["dot"]:
                    out.append(f'<circle cx="{x+13:.1f}" cy="99" r="2.5" fill="#e7a94c"/>')
                out.append('</g>')
                previous_tie = None
                continue
            y = _pitch_y(event["step"], event["octave"])
            name = f'{event["step"]}{event["alter"]:+d}{event["octave"]}'
            out.append(f'<g><title>{escape(name)} — {escape(event["figure"])}</title>')
            # Linhas suplementares conforme a altura realmente escrita.
            ledger = 145
            while ledger <= y + 0.1:
                out.append(f'<path d="M{x-16:.1f} {ledger}h32" stroke="#78948c" stroke-width="1.3"/>')
                ledger += 15
            ledger = 55
            while ledger >= y - 0.1:
                out.append(f'<path d="M{x-16:.1f} {ledger}h32" stroke="#78948c" stroke-width="1.3"/>')
                ledger -= 15
            if event["accidental"]:
                out.append(f'<text x="{x-29:.1f}" y="{y+7:.1f}" fill="#5cb3a9" '
                           f'font-size="22" font-family="serif">{event["accidental"]}</text>')
            filled = event["figure"] not in {"half", "whole"}
            out.append(f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="10" ry="6.5" '
                       f'transform="rotate(-20 {x:.1f} {y:.1f})" '
                       f'fill="{"#e7a94c" if filled else "#14201f"}" stroke="#e7a94c" stroke-width="2"/>')
            if event["figure"] != "whole":
                down = y < 93
                stem_x = x - 8 if down else x + 8
                stem_end = y + 38 if down else y - 38
                out.append(f'<path d="M{stem_x:.1f} {y:.1f}V{stem_end:.1f}" '
                           'stroke="#e7a94c" stroke-width="2"/>')
                flag_count = {"eighth": 1, "16th": 2, "32nd": 3, "64th": 4}.get(event["figure"], 0)
                for flag in range(flag_count):
                    flag_y = stem_end + (-7 * flag if down else 7 * flag)
                    curve_y = flag_y - 17 if down else flag_y + 17
                    out.append(f'<path d="M{stem_x:.1f} {flag_y:.1f}q17 2 15 {curve_y-flag_y:.1f}" '
                               'fill="none" stroke="#e7a94c" stroke-width="2"/>')
            if event["dot"]:
                out.append(f'<circle cx="{x+16:.1f}" cy="{y-4:.1f}" r="2.5" fill="#e7a94c"/>')
            if event["tuplet"]:
                out.append(f'<text x="{x:.1f}" y="{y-54:.1f}" text-anchor="middle" '
                           f'fill="#5cb3a9" font-size="14" font-family="sans-serif">{event["tuplet"]}</text>')
            if previous_tie and event["tie_stop"]:
                previous, px, py = previous_tie
                if (previous["step"], previous["alter"], previous["octave"]) == (
                    event["step"], event["alter"], event["octave"]
                ) and x - px < 200:
                    out.append(f'<path d="M{px+6:.1f} {py+12:.1f}Q{(px+x)/2:.1f} '
                               f'{max(py,y)+27:.1f} {x-6:.1f} {y+12:.1f}" '
                               'fill="none" stroke="#5cb3a9" stroke-width="2"/>')
            previous_tie = (event, x, y) if event["tie_start"] else None
            out.append('</g>')
        cursor = end
    out.append('</svg>')
    return "".join(out)
