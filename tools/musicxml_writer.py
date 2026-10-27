"""Escreve uma melodia monofônica (lista de notas com start/end/pitch)
como MusicXML real, com figuras de nota/compassos/ligaduras - mesma
arquitetura já provada em `ANTITOTEM/src/app/Main.cpp`
(`writeMusicXmlCaptureToFile`, ver `ANTITOTEM/docs/
PESQUISA_REPRESENTACAO_MUSICAL_RASGO.md`), portada pra Python aqui
porque o MARAVI é um pipeline Python (`basic-pitch`), não C++/JUCE.

Novidade em relação à versão do ANTITOTEM: suporte a **anacruse**
(compasso incompleto no início, quando a música começa antes do 1º
tempo forte de verdade).

Novidade 2026-08-20: **subdivisão local por batida, com tercina de
verdade** (autor, depois de ver a maioria da notação de um MIDI virar
tercina: "talvez seja a minha fala em forçar a partitura em
semicolcheia que tenha gerado imprecisões [...] não precisa forçar,
depende da música [...] essa estratégia de definir compasso por
compasso é boa [...] pois vai evitar erros escalonados" - confirmado:
"pode e deve implementar pois o objetivo é que funcione para todo tipo
de melodia, com todas as divisões e subdivisões possíveis, e todas as
fórmulas de compasso também"). A grade de quantização em si agora é
SEMPRE fina o bastante (24 passos por tempo - `TICKS_PER_BEAT`,
divisível por 1/2/3/4/6/8, então nunca distorce nem binário nem
tercina/sextina) - o que muda POR BATIDA é só a escrita: uma batida
com `beat_grid.detect_beat_divisions()` = 2/4/8 é escrita em figuras
binárias normais; = 3/6 vira um grupo de tercina/sextina de verdade
(`<time-modification>`/`<tuplet>`), sem forçar nada, decidido batida a
batida a partir dos ataques reais detectados nela.
"""
from __future__ import annotations

import bisect
from xml.sax.saxutils import escape

TICKS_PER_BEAT = 24
TUPLET_RATIO = {3: (3, 2), 6: (6, 4)}  # divisão local -> (actual-notes, normal-notes)


# Grafia dos acidentes por sustenido ou por bemol. A escolha não muda
# NENHUMA altura - muda só como a mesma altura é escrita, e isso é
# legibilidade pura: em fá maior a nota 10 é si bemol, não lá sustenido;
# em mi maior a nota 3 é ré sustenido, não mi bemol. Antes de 2026-08-31
# havia só a tabela de sustenidos, fixa (ver `key_detection.py`).
SHARP_STEPS = ("C", "C", "D", "D", "E", "F", "F", "G", "G", "A", "A", "B")
SHARP_ALTERS = (0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0)
FLAT_STEPS = ("C", "D", "D", "E", "E", "F", "G", "G", "A", "A", "B", "B")
FLAT_ALTERS = (0, -1, 0, -1, 0, 0, -1, 0, -1, 0, -1, 0)


def midi_note_to_xml_pitch(midi_note: int, key_fifths: int = 0) -> tuple[str, int, int]:
    """`key_fifths` é a armadura (negativo = bemóis). Armadura com bemol
    grafa os acidentes como bemol; com sustenido (ou dó maior/lá menor,
    fifths=0) grafa como sustenido - a convenção usual. Chamar sem o
    argumento mantém exatamente o comportamento antigo."""
    # As duas tabelas usam só grafias dentro da mesma oitava numérica
    # (nunca "Cb"/"B#", que cruzariam a fronteira de oitava), então a
    # oitava sai direto da altura absoluta nos dois casos.
    steps, alters = (FLAT_STEPS, FLAT_ALTERS) if key_fifths < 0 else (SHARP_STEPS, SHARP_ALTERS)
    pitch_class = midi_note % 12
    octave = midi_note // 12 - 1
    return steps[pitch_class], alters[pitch_class], octave


# Figuras "limpas" em ticks (TICKS_PER_BEAT = 24 por semínima), da maior
# pra menor. `(ticks, <type>, pontos, tuplet_ratio_ou_None)`. É a base do
# modo "ritmo livre": em vez de forçar TODA a batida numa subdivisão só
# (o que deixa a música "quadrada" - autor, 2026-08-31), cada nota é
# grafada pela figura que a duração REAL dela pede, e o que sobra é
# ligado.
#
# Prefere figuras binárias. Resíduos de 1/2/4/8/16 ticks na grade de
# 24 ticks/semínima só podem ser escritos exatamente como quiálteras;
# usá-las é melhor que declarar uma figura incompatível com <duration>.
# A escolha rítmica principal continua sendo feita por batida.
_CLEAN_FIGURES = [
    (96, "whole", 0, None),
    (72, "half", 1, None),
    (48, "half", 0, None),
    (36, "quarter", 1, None),
    (24, "quarter", 0, None),
    (18, "eighth", 1, None),
    (16, "quarter", 0, (3, 2)),
    (12, "eighth", 0, None),
    (9, "16th", 1, None),
    (8, "eighth", 0, (3, 2)),
    (6, "16th", 0, None),
    (4, "16th", 0, (3, 2)),
    (3, "32nd", 0, None),
    (2, "32nd", 0, (3, 2)),
    (1, "64th", 0, (3, 2)),
]

# Tabela alternativa, usada só nas batidas marcadas como quiáltera.
_TUPLET_FIGURES = [
    (24, "quarter", 0, None),
    (18, "eighth", 1, None),
    (16, "quarter", 0, (3, 2)),   # semínima de tercina de semínimas
    (12, "eighth", 0, None),
    (9, "16th", 1, None),
    (8, "eighth", 0, (3, 2)),     # colcheia de tercina
    (6, "16th", 0, None),
    (4, "16th", 0, (3, 2)),       # semicolcheia de sextina
    (3, "32nd", 0, None),
    (2, "32nd", 0, (3, 2)),
    (1, "64th", 0, (3, 2)),
]


def figure_for_ticks(cap: int, allow_tuplets: bool = False) -> tuple[int, str, int, tuple | None]:
    """A maior figura limpa que cabe em `cap` ticks. Devolve
    `(ticks, type, pontos, tuplet)`. `allow_tuplets` só quando a batida
    foi marcada como quiáltera."""
    for ticks, ntype, dots, tup in (_TUPLET_FIGURES if allow_tuplets else _CLEAN_FIGURES):
        if ticks <= cap:
            return ticks, ntype, dots, tup
    return 1, "64th", 0, (3, 2)


def readable_phrase_steps(
    notes: list[tuple[int, int, int]],
) -> list[tuple[int, int, int]]:
    """Simplifica só a escrita: preserva ordem, alturas e quantidade de notas.

    Uma pausa de pelo menos uma semicolcheia separa células. Dentro de cada
    célula, tenta primeiro a grade de semicolcheias; uma célula que contém
    notas rápidas demais usa fusas. Se nem esta grade preserva os ataques,
    mantém os passos originais daquela célula, sem apagar ornamentos.
    Nenhuma transformação aqui modifica o MIDI/performance de referência.
    """
    if not notes:
        return []

    phrases: list[list[tuple[int, int, int]]] = []
    for note in notes:
        if not phrases or note[0] - phrases[-1][-1][1] >= 6:
            phrases.append([note])
        else:
            phrases[-1].append(note)

    result: list[tuple[int, int, int]] = []
    for phrase in phrases:
        for grid in (6, 3):
            adjusted = [
                (round(start / grid) * grid, round(end / grid) * grid, pitch)
                for start, end, pitch in phrase
            ]
            previous_end = result[-1][1] if result else None
            # Não apagar uma anacruse curta ao arredondar seu começo
            # negativo para o tempo forte zero.
            valid = not (phrase[0][0] < 0 <= adjusted[0][0])
            for start, end, _ in adjusted:
                if end <= start or (previous_end is not None and start < previous_end):
                    valid = False
                    break
                previous_end = end
            if valid:
                result.extend(adjusted)
                break
        else:
            # Uma célula com ataque mais rápido que fusa não cabe numa
            # notação simples sem perder notas. Retém a escrita detalhada.
            result.extend(phrase)
    return result


def align_clear_phrase_starts(
    notes: list[tuple[int, int, int]],
    steps_per_measure: int,
    min_gap_steps: int = TICKS_PER_BEAT,
    min_rest_steps: int = 6,
    max_shift_steps: int = 2 * TICKS_PER_BEAT,
) -> list[tuple[int, int, int]]:
    """Edição da pauta, não do MIDI: alinha reentradas após respiração clara.

    O silêncio entre células pode encolher ou crescer; duração, ordem e
    intervalos *dentro* de cada célula permanecem. Alinha apenas quando há
    pausa >= um tempo e uma barra próxima que deixa ao menos uma semicolcheia
    de respiração. Reentradas ambíguas ficam onde estão — nem toda frase
    começa no primeiro tempo. Não se usa para síncopes/ostinatos automáticos.
    """
    if not notes or steps_per_measure <= 0:
        return list(notes)
    result: list[tuple[int, int, int]] = []
    shift = 0
    for i, (start, end, pitch) in enumerate(notes):
        if i and start - notes[i - 1][1] >= min_gap_steps:
            proposed = start + shift
            previous_end = result[-1][1]
            lower = (proposed // steps_per_measure) * steps_per_measure
            candidates = (lower, lower + steps_per_measure)
            eligible = [
                bar for bar in candidates
                if bar >= previous_end + min_rest_steps
                and abs(bar - proposed) <= max_shift_steps
            ]
            if eligible:
                target = min(eligible, key=lambda bar: (abs(bar - proposed), bar))
                shift += target - proposed
        result.append((start + shift, end + shift, pitch))
    return result


def write_musicxml(
    melody: list[dict],
    beat_times: list[float],
    path: str,
    beats_per_measure: int = 2,
    beat_unit: int = 4,
    downbeat_time: float | None = None,
    part_name: str = "Melodia",
    instrument_name: str | None = None,
    midi_program: int | None = None,
    display_bpm: float | None = None,
    work_title: str | None = None,
    composer: str | None = None,
    beat_divisions: list[int] | None = None,
    key_fifths: int = 0,
    key_mode: str = "major",
    free_rhythm: bool = False,
    tuplet_beats: set[int] | None = None,
    readable_notation: bool = False,
    phrase_downbeats: bool = False,
) -> None:
    """`beat_times`: timestamps reais de cada batida. `downbeat_time`:
    instante real (segundos) do primeiro tempo forte de verdade -
    precisa ser a MESMA âncora usada por `quantize_and_simplify()`.
    `display_bpm`: só pro texto de andamento mostrado na partitura.
    `beat_divisions`: uma divisão local (1/2/3/4/6/8) por intervalo de
    `beat_times` (`beat_grid.detect_beat_divisions()`) - se omitido,
    usa semicolcheia (4) pra tudo, igual ao comportamento antes desta
    mudança.
    `key_fifths`/`key_mode`: armadura de clave (`tools/key_detection.py`).
    O padrão 0/"major" reproduz o comportamento anterior, quando a
    armadura era escrita fixa em dó maior. `readable_notation` é uma
    camada editorial apenas para o MusicXML: simplifica a grade por
    trechos separados por pausa, preservando alturas e quantidade de
    notas; não altera o MIDI gerado pelo pipeline."""
    if not melody:
        raise ValueError("melodia vazia - nada pra escrever")
    if beats_per_measure < 1 or beat_unit not in (1, 2, 4, 8, 16):
        raise ValueError("fórmula de compasso inválida")
    # Voz grave em clave de sol gera muitas linhas suplementares. A escolha
    # é apenas editorial: preserva as alturas reais e não transpõe o MIDI.
    voice_pitches = sorted(int(note["pitch"]) for note in melody) if instrument_name == "Voice" else []
    low_voice = bool(voice_pitches and voice_pitches[len(voice_pitches) // 2] < 57)
    clef_sign, clef_line = ("F", 4) if low_voice else ("G", 2)
    steps_per_measure = TICKS_PER_BEAT * beats_per_measure * 4 // beat_unit
    if downbeat_time is None:
        downbeat_time = melody[0]["start"]
    if display_bpm is None:
        from beat_grid import average_bpm

        display_bpm = average_bpm(beat_times)
    bpm = display_bpm

    from beat_grid import quantize_melody_to_steps, step_to_time, time_to_step

    # Grade de quantização SEMPRE fina o bastante (24/batida - divide
    # exato por 1,2,3,4,6,8, então nunca distorce nem binário nem
    # tercina) - a escrita real por batida é decidida abaixo, não aqui.
    quant_notes = [
        (start_step, end_step, pitch)
        for start_step, end_step, pitch, _amplitude in quantize_melody_to_steps(melody, beat_times, TICKS_PER_BEAT, downbeat_time)
    ]
    if readable_notation:
        quant_notes = readable_phrase_steps(quant_notes)

    if phrase_downbeats:
        quant_notes = align_clear_phrase_starts(
            quant_notes, steps_per_measure
        )

    # Preenche lacunas com silêncio - mesma responsabilidade de
    # MidiCapture::closeNote() na versão C++, aqui em steps discretos.
    items: list[tuple[bool, int, int, int]] = []  # (is_rest, steps, start_step, pitch)
    cursor = quant_notes[0][0]
    first_step = cursor
    for start_step, end_step, pitch in quant_notes:
        if start_step < cursor:
            start_step = cursor
        if end_step <= start_step:
            end_step = start_step + 1
        if start_step > cursor:
            items.append((True, start_step - cursor, cursor, 0))
        items.append((False, end_step - start_step, start_step, pitch))
        cursor = end_step
    last_step = cursor

    has_pickup = first_step < 0

    anchor_step = time_to_step(downbeat_time, beat_times, TICKS_PER_BEAT)

    def division_for_beat_block(block_start_step: int) -> int:
        """Divisão local (1/2/3/4/6/8) do bloco de batida que começa em
        `block_start_step` (relativo à âncora) - acha a batida REAL
        (`beat_times`) mais próxima do meio desse bloco e usa a divisão
        já calculada pra ela."""
        if not beat_divisions:
            return 4
        mid_step = block_start_step + TICKS_PER_BEAT / 2 + anchor_step
        t = step_to_time(mid_step, beat_times, TICKS_PER_BEAT)
        idx = bisect.bisect_right(beat_times, t) - 1
        idx = max(0, min(idx, len(beat_divisions) - 1))
        return beat_divisions[idx]

    xml_parts: list[str] = []
    xml_parts.append('<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n')
    xml_parts.append(
        '<!DOCTYPE score-partwise  PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
        '"http://www.musicxml.org/dtds/partwise.dtd">\n'
    )
    xml_parts.append('<score-partwise version="4.0">\n')
    if work_title:
        xml_parts.append(f"<work><work-title>{escape(work_title)}</work-title></work>\n")
    if composer:
        xml_parts.append(f'<identification><creator type="composer">{escape(composer)}</creator></identification>\n')
    xml_parts.append('<part-list>\n')
    score_part = [f'<score-part id="P1"><part-name>{escape(part_name)}</part-name>']
    if instrument_name:
        score_part.append(
            f'<score-instrument id="I1"><instrument-name>{escape(instrument_name)}</instrument-name>'
            '</score-instrument>'
        )
        if midi_program is not None:
            score_part.append(
                f'<midi-instrument id="I1"><midi-channel>1</midi-channel>'
                f'<midi-program>{midi_program}</midi-program></midi-instrument>'
            )
    score_part.append('</score-part>\n')
    xml_parts.append(''.join(score_part))
    xml_parts.append('</part-list>\n<part id="P1">\n')

    measure_number = 0 if has_pickup else 1
    # Bloco de batida ATUAL (múltiplo de TICKS_PER_BEAT relativo à
    # âncora) - começa no bloco que contém o primeiro step real (pode
    # ser um bloco parcial, se a anacruse não preencher a batida
    # inteira - mesmo espírito do compasso 0 parcial de antes, um nível
    # abaixo).
    current_beat_block_start = (first_step // TICKS_PER_BEAT) * TICKS_PER_BEAT
    steps_left_in_current_beat = TICKS_PER_BEAT - (first_step - current_beat_block_start)
    steps_left_in_current_measure = steps_per_measure - ((first_step % steps_per_measure) if has_pickup else 0) if has_pickup else steps_per_measure
    current_division = division_for_beat_block(current_beat_block_start)

    def open_measure_xml(number: int, first_of_all: bool) -> str:
        parts = [f'<measure number="{number}">\n']
        if first_of_all:
            parts.append(
                f"<attributes><divisions>{TICKS_PER_BEAT}</divisions>"
                f"<key><fifths>{key_fifths}</fifths><mode>{key_mode}</mode></key>"
                f"<time><beats>{beats_per_measure}</beats><beat-type>{beat_unit}</beat-type></time>"
                f"<clef><sign>{clef_sign}</sign><line>{clef_line}</line></clef></attributes>\n"
            )
            # Andamento arredondado pro inteiro na marca de metrônomo -
            # "82,8" na partitura não ajuda ninguém; o autor lê e toca
            # "82". O `<sound tempo>` (playback) mantém uma casa.
            parts.append(
                f'<direction placement="above"><direction-type><metronome><beat-unit>quarter</beat-unit>'
                f'<per-minute>{round(bpm)}</per-minute></metronome></direction-type>'
                f'<sound tempo="{bpm:.1f}"/></direction>\n'
            )
        return "".join(parts)

    xml_parts.append(open_measure_xml(measure_number, True))

    # Cursor ABSOLUTO em steps (relativo à âncora) - a posição real já
    # emitida. O bloco de batida e o que resta da batida são DERIVADOS
    # dele a cada iteração, nunca decrementados à mão: uma nota mais longa
    # que uma batida (mínima etc., via `on_strong`) deixava
    # `steps_left_in_current_beat` muito negativo e o `advance_beat_block`
    # só somava 24 - o `current_beat_block_start` ia perdendo o compasso e
    # a marcação de quiáltera (`tuplet_beats`) nunca casava (bug real,
    # "Delicate" c.13).
    abs_cursor = first_step
    tuplet_open = False  # se ha um bracket de tercina/sextina aberto no meio da batida atual

    for item_index, (is_rest, steps, _start_step, pitch) in enumerate(items):
        remaining = steps
        first_chunk = True
        phrase_fermata = (
            phrase_downbeats and not is_rest and steps >= 2 * TICKS_PER_BEAT
            and item_index + 1 < len(items) and items[item_index + 1][0]
            and items[item_index + 1][1] >= 3 * TICKS_PER_BEAT // 2
        )
        while remaining > 0:
            if steps_left_in_current_measure <= 0:
                xml_parts.append("</measure>\n")
                measure_number += 1
                steps_left_in_current_measure = steps_per_measure
                xml_parts.append(open_measure_xml(measure_number, False))
                tuplet_open = False

            current_beat_block_start = (abs_cursor // TICKS_PER_BEAT) * TICKS_PER_BEAT
            steps_left_in_current_beat = TICKS_PER_BEAT - (abs_cursor - current_beat_block_start)
            current_division = division_for_beat_block(current_beat_block_start)

            raw_cap = min(remaining, steps_left_in_current_beat, steps_left_in_current_measure)

            if free_rhythm or readable_notation:
                # Cada nota grafada pela figura que a DURAÇÃO real dela
                # pede - não force a batida numa subdivisão só. Deixa a
                # música respirar (autor, 2026-08-31: "a definição de
                # tempo de nota predominante tá deixando a música
                # quadrada").
                # Nota LONGA que começa na cabeça do compasso ou no meio
                # dele pode virar mínima/semibreve/mínima pontuada de
                # verdade - sem isso, uma nota sustentada por 4 tempos
                # sai como 4 semínimas ligadas (feio). Fora desses dois
                # pontos, mantém o corte na batida (a convenção não
                # deixa escrever mínima começando no tempo 2 ou 4).
                pos_in_measure = steps_per_measure - steps_left_in_current_measure
                on_strong = steps_left_in_current_beat == TICKS_PER_BEAT and (
                    pos_in_measure == 0 or pos_in_measure * 2 == steps_per_measure
                )
                in_tuplet_beat = bool(tuplet_beats) and current_beat_block_start in tuplet_beats
                fr_cap = min(remaining, steps_left_in_current_measure) if (on_strong and not in_tuplet_beat) else raw_cap
                chunk_ticks, note_type_fr, dots_fr, tup_fr = figure_for_ticks(fr_cap, allow_tuplets=in_tuplet_beat)
                dotted = dots_fr > 0
                is_tuplet = tup_fr is not None
                tuplet_ratio = tup_fr
                forced_type = note_type_fr
            else:
                unit_ticks = TICKS_PER_BEAT // current_division
                # Prefere cortar numa fronteira da subdivisão local desta
                # batida, MAS o pedaço nunca pode passar de `raw_cap` -
                # senão os contadores de batida/compasso são decrementados
                # a mais e os compassos fecham cedo (bug real de 12.6).
                cap = (raw_cap // unit_ticks) * unit_ticks
                if cap == 0:
                    cap = raw_cap
                chunk_ticks, forced_type, dots, tuplet_ratio = figure_for_ticks(
                    cap, allow_tuplets=current_division in TUPLET_RATIO
                )
                dotted = dots > 0
                is_tuplet = tuplet_ratio is not None

            is_last_chunk_of_item = (remaining - chunk_ticks <= 0)
            is_last_chunk_of_beat = (steps_left_in_current_beat - chunk_ticks <= 0)

            xml_parts.append("<note>\n")
            if is_rest:
                xml_parts.append("<rest/>\n")
            else:
                step_name, alter, octave = midi_note_to_xml_pitch(pitch, key_fifths)
                xml_parts.append(f"<pitch><step>{step_name}</step>")
                if alter:
                    xml_parts.append(f"<alter>{alter}</alter>")
                xml_parts.append(f"<octave>{octave}</octave></pitch>\n")
            xml_parts.append(f"<duration>{chunk_ticks}</duration>")
            # <tie> precede <voice>/<type> na ordem exigida pelo MusicXML.
            if not is_rest:
                if not first_chunk:
                    xml_parts.append('<tie type="stop"/>')
                if not is_last_chunk_of_item:
                    xml_parts.append('<tie type="start"/>')
            xml_parts.append(f"<voice>1</voice><type>{forced_type}</type>")
            if dotted:
                xml_parts.append("<dot/>")
            if is_tuplet and tuplet_ratio:
                actual, normal = tuplet_ratio
                xml_parts.append(
                    f"<time-modification><actual-notes>{actual}</actual-notes>"
                    f"<normal-notes>{normal}</normal-notes></time-modification>"
                )

            notations: list[str] = []
            if not is_rest:
                if not first_chunk:
                    notations.append('<tied type="stop"/>')
                if not is_last_chunk_of_item:
                    notations.append('<tied type="start"/>')
            if is_tuplet:
                if not tuplet_open:
                    notations.append('<tuplet type="start" number="1"/>')
                    tuplet_open = True
                if is_last_chunk_of_beat or is_last_chunk_of_item:
                    notations.append('<tuplet type="stop" number="1"/>')
                    tuplet_open = False
            if phrase_fermata and is_last_chunk_of_item:
                notations.append('<fermata type="upright"/>')
            if notations:
                xml_parts.append(f"<notations>{''.join(notations)}</notations>")
            xml_parts.append("</note>\n")

            abs_cursor += chunk_ticks
            steps_left_in_current_measure -= chunk_ticks
            remaining -= chunk_ticks
            first_chunk = False

    xml_parts.append("</measure>\n</part>\n</score-partwise>\n")

    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(xml_parts))
