#!/usr/bin/env python3
"""Transcreve uma partitura a partir de um arquivo MIDI (não de áudio).

Autor, 2026-08-31: "pegue o arquivo 24lemagicienbaroque (Synth).mid" -
o MIDI que o próprio Suno exporta. Já tem as notas (posição e altura
razoáveis); o que falta é notação legível. Assim o pipeline pula o
Basic Pitch inteiro - sem fragmentação, sem erro de oitava.

Dois problemas que este módulo resolve na entrada:

1. **MIDI corrompido.** O Suno exporta um meta-evento de armadura
   inválido ("18 sustenidos" aqui, "11" no ParMePerdre - ver
   `MARAVI_CONCEITO.md` seção 5). `mido`/`pretty_midi` recusam o
   arquivo. Parser binário mínimo próprio, que ignora esse meta.
2. **Notação "quadrada".** Reaproveita `write_musicxml(free_rhythm=True)`:
   cada nota grafada pela figura que a duração dela pede, sem forçar
   toda batida numa subdivisão só.

Reaproveita o resto do pipeline: `beat_grid.synthetic_beat_times` (grade
a partir do andamento), `key_detection`, e o próprio `write_musicxml`.
"""
from __future__ import annotations

import argparse
import struct
from pathlib import Path


def _read_varlen(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    while True:
        b = data[pos]
        pos += 1
        value = (value << 7) | (b & 0x7F)
        if not b & 0x80:
            return value, pos


def read_midi_notes(path: Path) -> dict:
    """Devolve `{notes, ticks_per_beat, tempo_bpm, time_signature}`.
    `notes` é uma lista de `{start, end, pitch, amplitude}` em SEGUNDOS,
    já ordenada - mesmo formato do resto do pipeline. Ignora o
    meta-evento de armadura (0x59), que o Suno costuma exportar
    inválido."""
    data = path.read_bytes()
    if data[:4] != b"MThd":
        raise ValueError("não é um arquivo MIDI (falta o cabeçalho MThd)")
    _fmt, ntrk, division = struct.unpack(">HHH", data[8:14])
    pos = 14

    tempo_us = 500000  # 120 BPM até um meta 0x51 dizer o contrário
    time_signature = None
    raw_events: list[tuple[int, int, int, int]] = []  # (tick, type, d1, d2)

    for _ in range(ntrk):
        if data[pos : pos + 4] != b"MTrk":
            break
        length = struct.unpack(">I", data[pos + 4 : pos + 8])[0]
        pos += 8
        end = pos + length
        tick = 0
        running = None
        while pos < end:
            delta, pos = _read_varlen(data, pos)
            tick += delta
            b = data[pos]
            if b == 0xFF:
                mtype = data[pos + 1]
                pos += 2
                ln, pos = _read_varlen(data, pos)
                payload = data[pos : pos + ln]
                pos += ln
                if mtype == 0x51:
                    tempo_us = int.from_bytes(payload, "big")
                elif mtype == 0x58 and len(payload) >= 2:
                    time_signature = (payload[0], 2 ** payload[1])
                # 0x59 (armadura) deliberadamente ignorado
            elif b in (0xF0, 0xF7):
                pos += 1
                ln, pos = _read_varlen(data, pos)
                pos += ln
            else:
                if b & 0x80:
                    running = b
                    pos += 1
                status = running
                if status is None:
                    break
                hi = status & 0xF0
                if hi in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
                    d1, d2 = data[pos], data[pos + 1]
                    pos += 2
                    if hi == 0x90 and d2 > 0:
                        raw_events.append((tick, 1, d1, d2))
                    elif hi == 0x80 or (hi == 0x90 and d2 == 0):
                        raw_events.append((tick, 0, d1, d2))
                elif hi in (0xC0, 0xD0):
                    pos += 1
        pos = end

    seconds_per_tick = tempo_us / 1e6 / division

    open_notes: dict[int, list[tuple[int, int]]] = {}
    notes: list[dict] = []
    for tick, kind, pitch, vel in sorted(raw_events):
        if kind == 1:
            open_notes.setdefault(pitch, []).append((tick, vel))
        elif open_notes.get(pitch):
            start_tick, start_vel = open_notes[pitch].pop(0)
            notes.append(
                {
                    "start": start_tick * seconds_per_tick,
                    "end": tick * seconds_per_tick,
                    "pitch": pitch,
                    "amplitude": start_vel / 127.0,
                }
            )
    notes.sort(key=lambda n: n["start"])

    return {
        "notes": notes,
        "ticks_per_beat": division,
        "tempo_bpm": 60e6 / tempo_us,
        "time_signature": time_signature,
    }


def snap_to_musical_grid(
    melody: list[dict],
    beat_times: list[float],
    anchor: float,
    local_tempo: bool = False,
    triplet_feel: bool = False,
) -> list[dict]:
    """Encaixa cada ATAQUE (e cada fim de nota) na grade notacional e
    devolve a melodia com esses tempos. Troca o micro-timing tocado pela
    INTENÇÃO de escrita: a partitura sai com figuras variadas e limpas
    (semínima, colcheia, colcheia pontuada, semicolcheia) em vez de um
    amontoado de 16 avos e 32 avos que nascem de arredondar o rubato numa
    grade fina (MARAVI_CONCEITO.md seção 4.5, PARTITURA vs PERFORMANCE).

    NÃO deixa "quadrado" (forçar UMA figura por batida): as figuras
    continuam variando nota a nota - some só o desvio de tempo.

    Posição ABSOLUTA, não acumulada: cada ataque é `round((t - âncora) /
    seg_por_passo)`. Acumular intervalo a intervalo (versão anterior)
    somava o erro de arredondamento e a peça inteira escorregava
    segundos (medido: deslocamento médio de 3,6 s numa melodia de flauta
    com notas longas + pausas). Com andamento macro estável - o caso
    comum, inclusive "micro variações" de ±5-10% - a grade absoluta não
    escorrega. `local_tempo=True` re-ajusta `seg_por_passo` e a origem
    por regressão linear sobre uma janela deslizante (rubato largo, tipo
    barroco), ainda sem acumular arredondamento.

    Grade: múltiplos de SEMICOLCHEIA (6 passos de 24 avos), com viés pra
    COLCHEIA (12) - só cai pra semicolcheia quando o ataque está
    claramente mais perto dela. Correção de fase impede que uma
    semicolcheia solta parta todas as colcheias seguintes em duas
    ligadas. Ataques ficam estritamente crescentes."""
    from beat_grid import step_to_time, time_to_step

    TPB = 24
    anchor_step = time_to_step(anchor, beat_times, TPB)
    real_s = [n["start"] for n in melody]
    real_e = [n["end"] for n in melody]

    # seg_por_passo macro. Estimativa inicial pelas primeiras notas...
    j = min(8, len(real_s) - 1)
    steps_j = time_to_step(real_s[j], beat_times, TPB) - anchor_step
    spt = (real_s[j] - anchor) / max(1.0, steps_j)

    # ...e, no modo macro, o ANDAMENTO (não a fase - a âncora do autor é
    # sagrada) é refinado por mínimos quadrados sobre a peça inteira:
    # atribui cada ataque ao passo de semicolcheia mais próximo e ajusta
    # `spt` pra melhor reta PASSANDO PELA ÂNCORA - repete. Sem isso, um
    # erro de 0,5% no andamento de abertura vira mais de um tempo de
    # deslize ao longo de ~50 compassos (o MuseScore, ajustando o
    # andamento à peça toda, não sofre disso; a versão anterior sofria).
    if not local_tempo:
        step_unit = 8 if triplet_feel else 6  # tercina de colcheia (24/3) vs semicolcheia (24/4)
        for _ in range(4):
            pairs = [(round(((t - anchor) / spt) / step_unit) * step_unit, t - anchor) for t in real_s]
            den = sum(g * g for g, _ in pairs)
            if den <= 0:
                break
            slope = sum(g * dt for g, dt in pairs) / den
            if not (0.5 * spt < slope < 2.0 * spt):
                break
            if abs(slope - spt) < 1e-5:
                spt = slope
                break
            spt = slope

    def phase_fix(g: int, after: int | None) -> int:
        """Uma semicolcheia solta joga todo o fluxo seguinte pra fora da
        grade de colcheia e parte cada colcheia seguinte em duas ligadas.
        Se este passo é colcheia inteira mas a posição anterior está fora
        da grade de colcheia, re-encaixa na colcheia."""
        if after is None:
            return g
        if (g - after) % 12 == 0 and after % 12 != 0:
            gg = round(g / 12) * 12
            return gg if gg > after else after + 6
        return g

    def snap_abs(raw: float, after: int | None) -> int:
        g_e = round(raw / 12) * 12
        g_s = round(raw / 6) * 6
        g = g_e if abs(raw - g_e) <= abs(raw - g_s) + 1.0 else g_s
        if after is not None and g <= after:
            g = after + 6
        return phase_fix(g, after)

    starts: list[int] = []
    tuplet_note = [False] * len(real_s)  # sobrescrito no ramo macro se detectar quiáltera

    if local_tempo:
        # RUBATO LARGO (barroco): anda intervalo a intervalo com um
        # andamento local por média móvel. Acumula, mas segue variações
        # de andamento de 2:1 que a grade absoluta não pega.
        starts.append(0)
        for i in range(1, len(real_s)):
            dt = real_s[i] - real_s[i - 1]
            ideal = dt / spt
            e = max(1, round(ideal / 12)) * 12
            s = max(1, round(ideal / 6)) * 6
            steps = e if abs(ideal - e) <= abs(ideal - s) + 2 else s
            g = phase_fix(starts[-1] + steps, starts[-1])
            starts.append(g)
            obs = dt / steps
            if 0.6 * spt < obs < 1.7 * spt:
                spt = 0.7 * spt + 0.3 * obs
    else:
        # ANDAMENTO MACRO ESTÁVEL (o caso comum, inclusive micro-variações
        # de ±5-10%): posição ABSOLUTA contra a origem. Não acumula erro de
        # arredondamento - a peça não escorrega.
        raw_pos = [(t - anchor) / spt for t in real_s]

        # QUIÁLTERA: uma janela de 3 ataques consecutivos cujos DOIS
        # intervalos internos são ambos ~ colcheia-de-tercina (8 passos de
        # 24 avos, mais perto de 8 do que de 6 ou 12) é uma tercina de
        # colcheias - encaixa em (base, base+8, base+16) e marca a batida
        # como quiáltera (o `write_musicxml` só usa figuras de tercina nas
        # batidas marcadas - `tuplet_beats`; fora delas, só binária, senão
        # a partitura enche de tercina fantasma quando a fase escorrega).
        # Detecção pelo PADRÃO DE INTERVALOS, não pelo vão total: a 3ª nota
        # da tercina costuma ser segurada, encolhendo o vão ataque-a-ataque.
        def _is_trip_eighth(x: float) -> bool:
            return abs(x - 8) < min(abs(x - 6), abs(x - 12)) - 0.5 and 6.8 < x < 9.6

        snapped_raw: list[float] = list(raw_pos)
        tuplet_note = [False] * len(real_s)
        if triplet_feel:
            # Peça INTEIRA em tercinas de colcheia: cada ataque encaixa
            # num múltiplo de 8 passos de 24 avos (3 por tempo), toda
            # batida marcada como quiáltera. `spt` já foi ajustado pra
            # grade de 8 acima (`step_unit`), então o intervalo típico
            # cai perto de 8.
            prev: float | None = None
            for j in range(len(real_s)):
                g = round(raw_pos[j] / 8) * 8
                if prev is not None and g <= prev:
                    g = prev + 8
                snapped_raw[j] = g
                tuplet_note[j] = True
                prev = g
        else:
            i = 0
            while i + 2 < len(real_s):
                d1 = raw_pos[i + 1] - raw_pos[i]
                d2 = raw_pos[i + 2] - raw_pos[i + 1]
                if _is_trip_eighth(d1) and _is_trip_eighth(d2):
                    base = round(raw_pos[i] / 12) * 12
                    snapped_raw[i], snapped_raw[i + 1], snapped_raw[i + 2] = base, base + 8, base + 16
                    tuplet_note[i] = tuplet_note[i + 1] = tuplet_note[i + 2] = True
                    i += 3
                else:
                    i += 1

        for j in range(len(real_s)):
            after = starts[-1] if starts else None
            if tuplet_note[j]:
                g = int(round(snapped_raw[j]))
                starts.append(g if after is None or g > after else after + 4)
            else:
                starts.append(snap_abs(raw_pos[j], after))

    # NOTA ESTRUTURAL: nota real longa (>= ~1,5 tempo) OU seguida de um
    # silêncio longo é ponto de apoio da leitura - o autor ancora ela num
    # tempo forte e absorve a diferença na nota anterior (visto na versão
    # manual do "Delicate": um mi que caía no tempo 3,45 foi escrito no
    # tempo 4, e a colcheia antes virou colcheia pontuada). Aqui: se o
    # ataque dela está a <= uma semicolcheia de uma SEMÍNIMA inteira,
    # encaixa nela e empurra o fim da nota anterior junto. (Semínima, não
    # colcheia: encaixar na colcheia mais próxima cria antecipações
    # fantasma atravessando a barra quando a fase já escorregou um
    # tiquinho - testado, piora o casamento com a versão manual.)
    _CLEAN = (12, 24, 36, 48, 72, 96)  # colch, semín, semín.p, mín, mín.p, semibr

    def is_structural(i: int) -> bool:
        long_note = (real_e[i] - real_s[i]) >= spt * 30
        long_rest_after = i + 1 < len(real_s) and (real_s[i + 1] - real_e[i]) > spt * 18
        return long_note or long_rest_after

    for i in range(len(real_s)):
        if is_structural(i) and not tuplet_note[i] and starts[i] % 24 != 0:
            q = round(starts[i] / 24) * 24
            lo = (starts[i - 1] + 6) if i > 0 else 0
            if lo <= q != starts[i] and (i + 1 >= len(starts) or q < starts[i + 1]):
                starts[i] = q

    # Batidas (múltiplos de 24 relativos à âncora) que devem ser escritas
    # em quiáltera - `write_musicxml` só usa figuras de tercina/sextina
    # nessas.
    tuplet_beats = {(starts[i] // 24) * 24 for i in range(len(real_s)) if tuplet_note[i]}

    # Fim de cada nota: por padrão vai até o PRÓXIMO ataque (legato - o
    # normal numa melodia; num MIDI staccato os ~30-120 ms de silêncio
    # entre notas são articulação, não pausa). Nota estrutural termina
    # numa FIGURA LIMPA e o resto do compasso vira pausa - sem ligadura
    # de "rabo" (a versão manual não tem uma ligadura sequer nas notas
    # longas: mínima + pausa, nunca mínima ligada a fusa).
    ends: list[int] = []
    for i in range(len(real_s)):
        nxt = starts[i + 1] if i + 1 < len(real_s) else None
        raw_dur = (real_e[i] - real_s[i]) / spt
        if is_structural(i):
            clean = min(_CLEAN, key=lambda c: abs(c - raw_dur))
            ge = starts[i] + clean
            if nxt is not None:
                ge = min(ge, nxt)
            ends.append(max(starts[i] + 6, ge))
        elif nxt is not None:
            ends.append(max(starts[i] + 6, nxt))
        else:
            ends.append(starts[i] + max(6, round(raw_dur / 6) * 6))

    out: list[dict] = []
    for i, n in enumerate(melody):
        out.append(
            {
                "start": step_to_time(starts[i] + anchor_step, beat_times, TPB),
                "end": step_to_time(ends[i] + anchor_step, beat_times, TPB),
                "pitch": n["pitch"],
                "amplitude": n["amplitude"],
            }
        )
    return out, tuplet_beats


def main() -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from beat_grid import synthetic_beat_times
    from key_detection import detect_key, parse_key
    from musicxml_writer import write_musicxml
    from transcribe_monophonic import melody_to_midi, skyline_melody

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("midi", type=Path)
    parser.add_argument("--out-musicxml", type=Path, required=True)
    parser.add_argument("--out-mid", type=Path, default=None, help="MIDI re-exportado (compasso/andamento/armadura corretos)")
    parser.add_argument("--time-signature", type=str, default=None, help='Ex.: "4/4". Se omitido, usa o do MIDI (ou 4/4).')
    parser.add_argument("--bpm", type=float, default=None, help="Sobrepõe o andamento do MIDI (afeta a GRADE de quantização).")
    parser.add_argument("--score-bpm", type=float, default=None, help="Sobrepõe SÓ a marca de metrônomo escrita na partitura, sem mexer na grade. Ex.: --score-bpm 82.")
    parser.add_argument("--key", type=str, default=None, help='Ex.: "Ebm". Se omitido, detecta.')
    parser.add_argument("--anacrusis-notes", type=int, default=0)
    parser.add_argument("--downbeat-notes", type=str, default=None, help='"i,j[,tempos]" - duas notas que são tempos fortes + quantos tempos entre elas.')
    parser.add_argument("--monophonic", action="store_true", help="Reduz a uma linha só (ataque mais recente vence) - use se o MIDI tiver acordes/vozes.")
    parser.add_argument("--square", action="store_true", help="Desliga o ritmo livre (volta a forçar subdivisão por batida).")
    parser.add_argument("--drop-leading", type=int, default=0, help="Descarta as N primeiras notas (nota-fantasma/anacruse que o autor diz não existir).")
    parser.add_argument("--no-snap", action="store_true", help="Não encaixa ataques na grade notacional (colcheia/tercina) antes de escrever.")
    parser.add_argument("--local-tempo", action="store_true", help="Segue rubato largo (re-ajusta a grade por janela). Ligar quando o andamento varia muito (barroco); desligado, assume andamento macro estável.")
    parser.add_argument("--title", type=str, default=None, help="Título da obra na partitura.")
    parser.add_argument("--composer", type=str, default=None, help="Autoria (compositor) na partitura.")
    parser.add_argument("--part-name", type=str, default="Melodia", help='Nome do instrumento/parte (ex.: "Flauta transversal").')
    parser.add_argument("--register-fix", action="store_true", help="Corrige TRECHO inteiro deslocado de oitava (erro do Suno de gerar meia peça uma oitava abaixo). Opt-in - agressivo demais pra ligar sempre (mexe em saltos melódicos reais).")
    parser.add_argument("--triplet-feel", action="store_true", help="Escreve a peça inteira em tercinas (3 notas por tempo) - encaixa cada tempo na grade {0,8,16}/24 avos.")
    args = parser.parse_args()

    data = read_midi_notes(args.midi)
    melody = data["notes"]
    print(f"MIDI: {len(melody)} notas, {data['tempo_bpm']:.1f} BPM, compasso {data['time_signature'] or '(nenhum)'}")

    if args.drop_leading > 0:
        dropped = melody[: args.drop_leading]
        melody = melody[args.drop_leading :]
        t0 = melody[0]["start"]
        melody = [{**n, "start": n["start"] - t0, "end": n["end"] - t0} for n in melody]
        print(f"  descartadas {len(dropped)} nota(s) inicial(is); melodia re-ancorada em t=0")

    if args.monophonic:
        # skyline_melody espera tuplas (start,end,pitch,amp,...)
        melody = skyline_melody([(n["start"], n["end"], n["pitch"], n["amplitude"]) for n in melody])
        print(f"  reduzido a linha melódica: {len(melody)} notas")

    if args.register_fix:
        from octave_fix import normalize_register

        rf = normalize_register(melody)
        if rf["shifted_runs"]:
            melody = rf["melody"]
            print(f"  registro: {len(rf['shifted_runs'])} trecho(s) re-encaixado(s) de oitava ({len(rf['corrections'])} notas)")

    ts = args.time_signature or (f"{data['time_signature'][0]}/{data['time_signature'][1]}" if data["time_signature"] else "4/4")
    beats_per_measure, beat_unit = (int(x) for x in ts.split("/"))

    bpm = args.bpm or data["tempo_bpm"]
    if args.downbeat_notes:
        parts = [int(x) for x in args.downbeat_notes.split(",")]
        i0, i1 = parts[0], parts[1]
        beats_between = parts[2] if len(parts) > 2 else beats_per_measure
        span = melody[min(i1, len(melody) - 1)]["start"] - melody[min(i0, len(melody) - 1)]["start"]
        if span > 0:
            bpm = beats_between * 60.0 / span
        anchor = melody[min(i0, len(melody) - 1)]["start"]
    elif args.anacrusis_notes > 0:
        anchor = melody[min(args.anacrusis_notes, len(melody) - 1)]["start"]
    else:
        anchor = melody[0]["start"]

    duration = max(n["end"] for n in melody)
    beat_times = synthetic_beat_times(bpm, duration)

    tuplet_beats: set[int] = set()
    if not args.no_snap and not args.square:
        before = len(melody)
        melody, tuplet_beats = snap_to_musical_grid(
            melody, beat_times, anchor, local_tempo=args.local_tempo, triplet_feel=args.triplet_feel
        )
        anchor = melody[0]["start"] if anchor <= melody[0]["start"] + 1e-6 else anchor
        tinfo = f", {len(tuplet_beats)} batida(s) em quiáltera" if tuplet_beats else ""
        print(f"  ataques encaixados na grade notacional: {before} notas{tinfo}")

    key_info = parse_key(args.key) if args.key else detect_key(melody)
    kf = key_info["fifths"] if key_info else 0
    km = key_info["mode"] if key_info else "major"
    print(f"  andamento {bpm:.1f} BPM | compasso {ts} | tom {key_info['name'] if key_info else '(dó maior)'} | âncora t={anchor:.3f}s")

    write_musicxml(
        melody,
        beat_times=beat_times,
        path=str(args.out_musicxml),
        beats_per_measure=beats_per_measure,
        beat_unit=beat_unit,
        downbeat_time=anchor,
        display_bpm=args.score_bpm or bpm,
        key_fifths=kf,
        key_mode=km,
        free_rhythm=not args.square,
        work_title=args.title,
        composer=args.composer,
        part_name=args.part_name,
        tuplet_beats=tuplet_beats,
    )
    print(f"  MusicXML -> {args.out_musicxml}")

    if args.out_mid:
        melody_to_midi(melody, bpm=bpm, beats_per_measure=beats_per_measure, beat_unit=beat_unit, key=key_info).write(str(args.out_mid))
        print(f"  MIDI     -> {args.out_mid}")


if __name__ == "__main__":
    main()
