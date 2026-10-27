#!/usr/bin/env python3
"""Transcreve um áudio (Basic Pitch) e reduz o resultado a uma única
linha melódica monofônica.

Motivação (2026-08-20, docs/MARAVI_CONCEITO.md): o stem testado
("Woodwinds", ParMePerdre) não é uma linha solo - tem mais de uma
voz/instrumento soando ao mesmo tempo, o que o Basic Pitch capta como
notas simultâneas. Tentar afinar onset_threshold/frame_threshold pra
eliminar "ruído" também cortava notas rápidas reais (choro tem
passagens rápidas e ornamentadas - ver RESULTADO.md do primeiro
teste). A solução correta é separar as duas responsabilidades: deixar
a detecção sensível o bastante pra capturar tudo, e resolver a escolha
de UMA nota por instante como um passo de pós-processamento explícito
(autor: "gostaria que fosse uníssono" - "quero extrair uma linha única
deste stem").

**Trocado de "skyline" (mais aguda vence) pra "ataque mais recente
vence"** (2026-08-20) - achado real testando com o autor: no compasso
3, uma nota real de F4 (confirmada por DOIS detectores independentes -
o próprio Basic Pitch, amplitude 0.69, e `librosa.pyin` rodado direto
no áudio, probabilidade até 0.98) começa enquanto um G4 anterior ainda
estava soando (cauda/harmonia). O skyline antigo descartava o F4 por
ser mais grave - "mais aguda vence" pressupõe que a melodia sempre fica
por cima de qualquer harmonia, o que é falso aqui. Autor: "no momento a
nota não é o mais importante, e sim que as notas estejam nos lugares
certos nos compassos" - um NOVO ataque quase sempre significa "a
melodia se moveu pra cá", seja ele mais agudo ou mais grave que o que
estava soando; a cauda de uma nota anterior é ruído de sobreposição,
não conteúdo melódico novo. Mais simples que o skyline antigo também -
nunca precisa decidir "ficou mascarada por inteiro", só corta a
anterior no instante em que a nova começa."""
from __future__ import annotations

import argparse
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")


def skyline_melody(note_events: list[tuple]) -> list[dict]:
    """Reduz uma lista de notas (possivelmente sobrepostas) a uma única
    linha monofônica, priorizando o ATAQUE MAIS RECENTE (não o pitch
    mais agudo - ver o comentário do módulo). `note_events` é o formato
    devolvido por `basic_pitch.inference.predict`: (start, end, pitch,
    amplitude, pitch_bends). Retorna uma lista de dicts já ordenada e
    sem sobreposição. Nome mantido (`skyline_melody`) por compatibi-
    lidade com o resto do pipeline, mesmo não sendo mais skyline de
    verdade."""
    notes = sorted(note_events, key=lambda n: n[0])
    melody: list[dict] = []
    for start, end, pitch, amplitude, *_ in notes:
        if melody:
            last = melody[-1]
            # QUASE-SIMULTÂNEAS (< 45 ms entre ataques): não é sequência,
            # é a mesma nota dobrada/duplicada (o Suno costuma dobrar em
            # oitava; num instrumento monofônico como a flauta isso é uma
            # nota só). Fica a MAIS AGUDA e a outra some - sem isso, um
            # dó6+dó5 tocados juntos viravam "dó6 semicolcheia, dó5
            # semicolcheia" e a linha ficava em ziguezague de oitava
            # (autor, "Delicate" c.21: "o segundo tempo... me soa estranho").
            if start - last["start"] < 0.045:
                if pitch > last["pitch"]:
                    last["pitch"] = pitch
                    last["end"] = max(last["end"], end)
                    last["amplitude"] = amplitude
                continue
            if start < last["end"]:
                # Uma nota nova começou enquanto a anterior ainda soava -
                # ela sempre vence, seja qual for o pitch. A anterior é
                # cortada no instante em que a nova começa.
                last["end"] = start
                if last["end"] <= last["start"]:
                    melody.pop()
        if end > start:
            melody.append({"start": start, "end": end, "pitch": pitch, "amplitude": amplitude})
    return merge_fragmented_repeats(melody)


def merge_fragmented_repeats(melody: list[dict], max_gap_seconds: float = 0.03, max_fragment_seconds: float = 0.09) -> list[dict]:
    """Funde duas notas ADJACENTES do MESMO pitch só quando a lacuna
    entre elas é ínfima (ruído de detecção de onset, não silêncio real)
    E pelo menos uma das duas é curta demais pra ser uma nota própria -
    sinal de que o Basic Pitch fragmentou UMA nota real em dois pedaços
    (achado real, 2026-08-20: D#4 dividido em 70ms + 163ms com só 11ms
    de lacuna entre eles). Deliberadamente mais estrito que a fusão por
    mesmo pitch que existia antes (removida - destruía repetições de
    nota reais, como a anacruse de choro com quatro semicolcheias D6
    genuínas, cada uma já ~128-163ms, bem acima do piso de fragmento
    aqui). Os limiares (30ms de lacuna, 90ms de fragmento) são
    arbitrários, nunca calibrados por escuta - só o suficiente pra picos
    de detecção sub-passo de grade, longe de qualquer nota real com
    duração própria."""
    merged: list[dict] = []
    for note in melody:
        if merged:
            last = merged[-1]
            gap = note["start"] - last["end"]
            is_fragment = (last["end"] - last["start"]) < max_fragment_seconds or (note["end"] - note["start"]) < max_fragment_seconds
            if note["pitch"] == last["pitch"] and gap < max_gap_seconds and is_fragment:
                last["end"] = note["end"]
                continue
        merged.append(dict(note))
    return merged


def join_contiguous_same_pitch(melody: list[dict], max_gap_seconds: float = 0.02) -> list[dict]:
    """Modo opt-in para solo ligado: uma altura sem pausa é uma nota só.

    Deve ser usado somente quando o músico confirmar ausência de ataques
    repetidos na mesma altura. Não serve como padrão: uma sequência de
    notas realmente rearticuladas pode ter o mesmo pitch e nenhum silêncio.
    Preserva início, fim, altura e ordem das mudanças de nota; não inventa
    ataques e não funde alturas diferentes.
    """
    result: list[dict] = []
    for note in melody:
        if result and note["pitch"] == result[-1]["pitch"]:
            gap = note["start"] - result[-1]["end"]
            if -1e-6 <= gap <= max_gap_seconds:
                result[-1]["end"] = max(result[-1]["end"], note["end"])
                result[-1]["amplitude"] = max(result[-1].get("amplitude", 0.8), note.get("amplitude", 0.8))
                continue
        result.append(dict(note))
    return result


def correct_isolated_octave_spikes(melody: list[dict]) -> tuple[list[dict], int]:
    """Correção conservadora, opt-in, de harmônicos breves em solo de flauta.

    Só uma nota curta, sem pausa ao redor, muito acima das duas vizinhas e
    cuja transposição por uma ou duas oitavas explica o contorno é candidata.
    Não filtra brilho, vibrato ou notas agudas sustentadas; esses aspectos
    pertencem à execução e não devem se transformar em notas fictícias.
    """
    result = [dict(note) for note in melody]
    corrected = 0
    for i in range(1, len(melody) - 1):
        previous, note, following = melody[i - 1:i + 2]
        pitch = int(note["pitch"])
        if (pitch < 78 or note["end"] - note["start"] > 0.25
                or note["start"] - previous["end"] > 0.12
                or following["start"] - note["end"] > 0.12
                or pitch - previous["pitch"] < 7
                or pitch - following["pitch"] < 7):
            continue
        original_distance = abs(pitch - previous["pitch"]) + abs(pitch - following["pitch"])
        candidates = [
            candidate for candidate in (pitch - 12, pitch - 24)
            if candidate >= 59  # si3 de flauta com pe em si e uma nota valida
            and min(abs(candidate - previous["pitch"]), abs(candidate - following["pitch"])) <= 2
            and max(abs(candidate - previous["pitch"]), abs(candidate - following["pitch"])) <= 12
            and original_distance - (
                abs(candidate - previous["pitch"]) + abs(candidate - following["pitch"])
            ) >= 12
        ]
        if candidates:
            result[i]["pitch"] = min(
                candidates,
                key=lambda candidate: abs(candidate - previous["pitch"])
                + abs(candidate - following["pitch"]),
            )
            corrected += 1
    return result, corrected


class NoNotesInRangeError(ValueError):
    """Nenhuma nota detectada cabe no registro escolhido pelo músico."""


def filter_below_pitch(melody: list[dict], minimum_pitch: int) -> tuple[list[dict], int]:
    """Descarta candidatas abaixo do limite, sem transpor nem inventar notas.

    Em áudio misto isto limpa a pauta, mas não recupera a flauta que possa
    estar simultânea a um instrumento grave escolhido pelo skyline.
    """
    kept = [note for note in melody if int(note["pitch"]) >= minimum_pitch]
    return kept, len(melody) - len(kept)


def quantize_and_simplify(melody: list[dict], beat_times: list[float], grid_division: int = 2, anchor_time: float = 0.0) -> list[dict]:
    """Quantiza pra uma grade musical explícita (padrão: colcheia,
    `grid_division=2` = 1/2 tempo/beat), usando a mesma função
    compartilhada com `write_musicxml`
    (`beat_grid.quantize_melody_to_steps` - ver o comentário lá pro
    racional completo e o histórico de bugs que motivou unificar as
    duas quantizações numa só).

    Estado real (20 ago. 2026): isto NÃO é mais a simplificação
    "estilo Real Book" que o nome sugere - só a fusão por mesmo pitch
    (removida, destruía repetições de nota reais) e a absorção de notas
    mais curtas que 1 passo de grade (agora built-in na quantização
    compartilhada, nunca sobra nota sub-passo) existiam antes; nenhuma
    delas era uma simplificação musicalmente informada de verdade. O
    critério de importância real (nota em tempo forte/valor mais longo
    = estrutural; nota curta fora do tempo = ornamento) continua em
    aberto - ver `MARAVI_CONCEITO.md`, seção 7, "Limite conceitual
    encontrado, ainda não resolvido".

    `beat_times`: timestamps reais de cada batida (`beat_grid.
    estimate_beat_times`, ou uma grade sintética constante via
    `beat_grid.synthetic_beat_times` quando o usuário fornece `--bpm`
    manualmente).
    """
    from beat_grid import quantize_melody_to_steps, step_to_time, time_to_step

    anchor_step = time_to_step(anchor_time, beat_times, grid_division)
    quantized_steps = quantize_melody_to_steps(melody, beat_times, grid_division, anchor_time)
    result: list[dict] = []
    for start_step, end_step, pitch, amplitude in quantized_steps:
        start = step_to_time(start_step + anchor_step, beat_times, grid_division)
        end = step_to_time(end_step + anchor_step, beat_times, grid_division)
        result.append({"start": start, "end": end, "pitch": pitch, "amplitude": amplitude})
    return result


def melody_to_midi(
    melody: list[dict],
    program: int = 0,
    bpm: float | None = None,
    beats_per_measure: int = 4,
    beat_unit: int = 4,
    key: dict | None = None,
) -> "pretty_midi.PrettyMIDI":
    """`bpm`/`beats_per_measure`/`beat_unit` são opcionais - sem eles, o
    `pretty_midi` (e por consequência qualquer software de notação que
    abrir o arquivo, ex.: MuseScore) assume 120 BPM e 4/4 por padrão,
    mesmo quando a melodia foi pensada/quantizada pra outro compasso
    (achado real, 2026-08-20, autor: "o arquivo musicxml entendeu 2/4,
    o midi abriu no musescore como 4/4" - o `.musicxml` já escrevia
    isso certo via `musicxml_writer.write_musicxml`, o `.mid` nunca
    escrevia nada).

    `key` (`tools/key_detection.py`) escreve também a ARMADURA no `.mid`
    - mesma classe de omissão do compasso/andamento acima: sem isso o
    MuseScore importa o MIDI sempre em dó maior, e uma peça em fá vira
    uma parede de bemóis de cortesia."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm if bpm is not None else 120.0)
    pm.time_signature_changes.append(pretty_midi.TimeSignature(beats_per_measure, beat_unit, 0.0))
    if key is not None:
        # `pretty_midi` numera as tonalidades 0-11 = dó..si maior e
        # 12-23 = dó..si menor (não é o "fifths" do MusicXML).
        key_number = key["tonic_pc"] + (12 if key["mode"] == "minor" else 0)
        pm.key_signature_changes.append(pretty_midi.KeySignature(key_number, 0.0))
    instrument = pretty_midi.Instrument(program=program, name="melodia (skyline)")
    for note in melody:
        velocity = max(1, min(127, int(round(note["amplitude"] * 127))))
        instrument.notes.append(
            pretty_midi.Note(velocity=velocity, pitch=int(note["pitch"]), start=note["start"], end=note["end"])
        )
    pm.instruments.append(instrument)
    return pm


def run_pipeline(
    audio_path: Path,
    onset_threshold: float = 0.4,
    frame_threshold: float = 0.25,
    minimum_note_length: float = 58.0,
    bpm: float | None = None,
    time_signature: str = "4/4",
    anacrusis_notes: int = 0,
    key: str | None = None,
    tap_count: int | None = None,
    auto_downbeat: bool = False,
    align_repeats: bool = False,
    solo: bool = False,
    join_equal_pitch: bool = False,
    suppress_harmonic_spikes: bool = False,
    midi_program: int = 0,
    preserve_low_register_from: int | None = None,
    minimum_pitch: int | None = None,
    piano_two_staves: bool = False,
    force_division: int | None = None,
    downbeat_from_notes: tuple[int, int] | None = None,
) -> dict:
    """Núcleo do pipeline, reutilizável por `main()` (CLI) e pelo
    servidor web (`webapp/app.py`) - factorado 2026-08-20 pra nunca
    duplicar a lógica de transcrição em dois lugares (mesma lição desta
    sessão inteira: duas implementações do mesmo passo sempre acabam
    divergindo - ver `MARAVI_CONCEITO.md` seção 7.3). Devolve um dict
    com a melodia já quantizada, o `.mid` já pronto
    (`pretty_midi.PrettyMIDI`, em memória) e os dados que
    `write_musicxml()` precisa - quem chama decide COMO materializar
    (escrever arquivo, mandar em resposta HTTP, etc.).

    Sem parâmetro de "nível de detalhe" forçado (`grid_division`
    existia antes, removido 2026-08-20) - autor, depois de ver a
    maioria da notação de um MIDI virar tercina por causa de uma grade
    binária única forçada: "não precisa forçar, depende da música
    [...] pode e deve implementar [detecção por batida] pois o
    objetivo é que funcione para todo tipo de melodia, com todas as
    divisões e subdivisões possíveis." A subdivisão (colcheia,
    semicolcheia, tercina, sextina...) agora é decidida SOZINHA, batida
    a batida, por `beat_grid.detect_beat_divisions()` - ver o
    comentário lá pro racional completo."""
    from basic_pitch.inference import predict
    from beat_grid import average_bpm, detect_beat_divisions, estimate_beat_times, synthetic_beat_times
    from key_detection import detect_key, parse_key
    from musicxml_writer import TICKS_PER_BEAT

    beats_per_measure, beat_unit = (int(x) for x in time_signature.split("/"))

    _, midi_data_raw, note_events = predict(
        str(audio_path),
        onset_threshold=onset_threshold,
        frame_threshold=frame_threshold,
        minimum_note_length=minimum_note_length,
    )
    piano_notes = None
    if piano_two_staves:
        from piano_score import piano_notes_from_events

        piano_notes = piano_notes_from_events(note_events)
        if not piano_notes:
            raise NoNotesInRangeError("Nenhuma nota de piano foi detectada no áudio.")
    raw_note_count = len(note_events)
    excluded_low_notes = 0
    if minimum_pitch is not None and preserve_low_register_from is None:
        # Filtra ANTES de reduzir a mistura a uma voz: uma nota grave do
        # acompanhamento não deve cortar uma candidata de flauta simultânea,
        # nem ser elevada pela correção estatística de oitava.
        note_events = [event for event in note_events if int(event[2]) >= minimum_pitch]
        excluded_low_notes = raw_note_count - len(note_events)
    melody = skyline_melody(note_events)
    if minimum_pitch is not None and not melody:
        raise NoNotesInRangeError(
            "Nenhuma nota detectada ficou no registro escolhido. "
            "Confira o instrumento e o áudio; o limite de registro não isola a fonte."
        )

    # Correção de erros de oitava do Basic Pitch (subharmônico detectado
    # como fundamental). Só a etapa de FAIXA - puxa pra dentro da faixa
    # robusta da própria peça as notas grosseiramente fora dela. Medido
    # contra a referência do autor do "Le Magicien Baroque" (flauta solo,
    # faixa real MIDI 61-88): o Basic Pitch devolvia 25-92, a etapa de
    # faixa traz pra ~60-90. No ParMePerdre (aprovado pelo autor) não
    # muda nada. Ver `tools/octave_fix.py`.
    from octave_fix import fix_octave_errors

    _oct = fix_octave_errors(melody, preserve_low_register_from=preserve_low_register_from)
    melody = _oct["melody"]
    octave_corrections = _oct["corrections"]

    if minimum_pitch is not None:
        melody, dropped_after_octave_fix = filter_below_pitch(melody, minimum_pitch)
        excluded_low_notes += dropped_after_octave_fix
        if not melody:
            raise NoNotesInRangeError(
                "Nenhuma nota detectada ficou no registro escolhido. "
                "Confira o instrumento e o áudio; o limite de registro não isola a fonte."
            )

    # `--solo`: material monofônico de verdade (flauta, voz). Descarta
    # notas do Basic Pitch que não coincidem com um ataque real detectado
    # no áudio - reduz a fragmentação que faz a subdivisão sair fina
    # demais. NÃO usar em stem multi-voz (ParMePerdre): apagaria nota
    # real. Ver `tools/onset_filter.py`.
    onset_filtered = 0
    if solo:
        from onset_filter import filter_to_real_onsets

        _of = filter_to_real_onsets(melody, audio_path)
        melody = _of["melody"]
        onset_filtered = _of["dropped"]

    # Contagem batida pelo músico no início do próprio take (ideia do
    # autor, ver `tools/tap_tempo.py`). Vem ANTES de tudo porque muda
    # duas coisas de uma vez: o andamento e o instante zero da melodia -
    # as batidas em si são descartadas, senão virariam notas.
    tap_info = None
    if tap_count:
        from tap_tempo import detect_tap_tempo, trim_melody_before

        tap_info = detect_tap_tempo(audio_path, tap_count=tap_count)
        melody = trim_melody_before(melody, tap_info["melody_start_seconds"])
        if piano_notes is not None:
            piano_notes = trim_melody_before(piano_notes, tap_info["melody_start_seconds"])
            if not piano_notes:
                raise NoNotesInRangeError("Depois da contagem não sobrou nenhuma nota de piano.")
        if not melody:
            raise ValueError(
                "Depois de descartar a contagem não sobrou nenhuma nota - "
                "a gravação tem só as batidas, ou a melodia não foi detectada."
            )
        bpm = tap_info["bpm"]

    if downbeat_from_notes is not None and bpm is None:
        # O autor aponta duas notas e quantos TEMPOS há entre elas (por
        # padrão, um compasso inteiro). Deriva o andamento disso, sem
        # confiar no beat tracker. Ex.: `--downbeat-notes "1,7,2"` = da
        # nota 1 à nota 7 vão 2 tempos (meio compasso de 4/4).
        i0, i1 = downbeat_from_notes[0], downbeat_from_notes[1]
        beats_between = downbeat_from_notes[2] if len(downbeat_from_notes) > 2 else beats_per_measure
        i0 = max(0, min(i0, len(melody) - 1)); i1 = max(i0 + 1, min(i1, len(melody) - 1))
        span = melody[i1]["start"] - melody[i0]["start"]
        if span > 0 and beats_between > 0:
            bpm = beats_between * 60.0 / span

    if bpm is not None:
        duration = max(n["end"] for n in melody)
        beat_times = synthetic_beat_times(bpm, duration)
        bpm_source = "batido" if tap_info else ("estrutura do autor" if downbeat_from_notes else "forcado")
    else:
        beat_times = estimate_beat_times(audio_path)
        bpm_source = "detectado"

    # Re-ajuste da grade pelas repetições da própria música (opt-in, ver
    # `tools/grid_align.py` e `MARAVI_CONCEITO.md` 12.4). Sempre calculado
    # pra reportar o efeito, mas só SUBSTITUI a grade quando pedido -
    # muda toda a escrita rítmica.
    from grid_align import align_grid_to_repeats

    # Só MEDE - não substitui a grade. A troca de grade está implementada
    # em `grid_align.py` e valida bem o objetivo direto (coerência de
    # repetição), mas a integração com `write_musicxml` infla a contagem
    # de compassos (154 esperados viram 338) por uma interação com a
    # subdivisão por batida - bug pré-existente do escritor, exposto
    # pela grade mais uniforme. Ver `MARAVI_CONCEITO.md` 12.4. O
    # parâmetro `align_repeats` fica reservado pra quando isso for
    # resolvido; hoje é no-op.
    align_info = align_grid_to_repeats(beat_times, melody, beats_per_measure)
    grid_aligned = False

    # Estimativa do tempo forte - sempre calculada (é barata e usa só
    # dados que já estão aqui), mas **consultiva**: nunca sobrepõe a
    # contagem batida nem o `--anacrusis-notes` do autor. Ver
    # `tools/downbeat.py` pro método e pro resultado negativo medido em
    # material sincopado.
    from downbeat import detect_downbeat_phase

    downbeat_info = detect_downbeat_phase(melody, beat_times, beats_per_measure)

    if tap_info:
        # Com contagem, o primeiro tempo forte é conhecido por
        # construção: a melodia foi reancorada no zero, que É a batida
        # seguinte à contagem. Não precisa contar notas de anacruse.
        downbeat_time = 0.0
        downbeat_source = "contagem"
    elif grid_aligned:
        # O alinhamento por repetição fixou a origem métrica - usar
        # `--anacrusis-notes` aqui brigaria com ela (grade e âncora de
        # quantização em referências diferentes descarrilam a contagem
        # de compassos).
        downbeat_time = align_info["downbeat_time"]
        downbeat_source = "alinhamento"
    elif downbeat_from_notes is not None:
        downbeat_time = melody[max(0, min(downbeat_from_notes[0], len(melody) - 1))]["start"]
        downbeat_source = "estrutura do autor"
    elif anacrusis_notes > 0:
        anacrusis_index = min(anacrusis_notes, len(melody) - 1)
        downbeat_time = melody[anacrusis_index]["start"]
        downbeat_source = "informado"
    elif auto_downbeat and downbeat_info is not None:
        downbeat_time = downbeat_info["downbeat_time"]
        downbeat_source = "estimado"
    else:
        downbeat_time = melody[0]["start"]
        downbeat_source = "primeira nota"

    # Grade de quantização SEMPRE fina (TICKS_PER_BEAT, hoje 24 - divide
    # exato por 1/2/3/4/6/8). A figura de nota é decidida depois, batida
    # a batida (ou por `--force-division`).
    simplified = quantize_and_simplify(melody, beat_times=beat_times, grid_division=TICKS_PER_BEAT, anchor_time=downbeat_time)
    harmonic_spikes_corrected = 0
    if suppress_harmonic_spikes:
        simplified, harmonic_spikes_corrected = correct_isolated_octave_spikes(simplified)
    joined_equal_pitch_count = 0
    if join_equal_pitch:
        before_join = len(simplified)
        simplified = join_contiguous_same_pitch(simplified)
        joined_equal_pitch_count = before_join - len(simplified)
    display_bpm = average_bpm(beat_times)
    piano_midi = None
    if piano_notes is not None:
        from piano_score import piano_to_midi

        piano_midi = piano_to_midi(piano_notes, display_bpm, beats_per_measure, beat_unit)

    # Tom: o que o usuário informar vence a estimativa, mesma regra do
    # `bpm` acima. Detectado sobre a melodia COMPLETA (não a
    # simplificada) - a simplificação pode fundir notas curtas, e o
    # perfil tonal fica mais fiel com todo o material real.
    key_info = parse_key(key) if key else None
    key_source = "informado" if key_info else "detectado"
    if key_info is None:
        key_info = detect_key(melody)
        if key_info is None:
            key_source = "indisponivel"

    midi = melody_to_midi(
        simplified,
        program=midi_program,
        bpm=display_bpm,
        beats_per_measure=beats_per_measure,
        beat_unit=beat_unit,
        key=key_info,
    )
    if force_division:
        # O autor sabe a figura ("essa peça é em colcheia") - força a
        # subdivisão em vez de deixar `detect_beat_divisions` escolher.
        # Mesma regra do `--bpm`/`--key`: informação do autor vence
        # estimativa. Reintroduz, de forma controlada, o `--grid-division`
        # que foi removido em 2026-08-20 (seção 7.5) - lá o problema era
        # FORÇAR global sem o autor pedir; aqui é o autor pedindo.
        beat_divisions = [force_division] * (len(beat_times) - 1)
    else:
        beat_divisions = detect_beat_divisions(melody, beat_times)

    return {
        "tap_info": tap_info,
        "octave_corrections": octave_corrections,
        "onset_filtered": onset_filtered,
        "align_info": align_info,
        "downbeat_info": downbeat_info,
        "downbeat_source": downbeat_source,
        "key": key_info,
        "key_source": key_source,
        "key_fifths": key_info["fifths"] if key_info else 0,
        "key_mode": key_info["mode"] if key_info else "major",
        "raw_note_count": raw_note_count,
        "melody_note_count": len(melody),
        "excluded_low_notes": excluded_low_notes,
        "simplified_note_count": len(simplified),
        "joined_equal_pitch_count": joined_equal_pitch_count,
        "harmonic_spikes_corrected": harmonic_spikes_corrected,
        "beat_count": len(beat_times),
        "display_bpm": display_bpm,
        "bpm_source": bpm_source,
        "beats_per_measure": beats_per_measure,
        "beat_unit": beat_unit,
        "beat_times": beat_times,
        "beat_divisions": beat_divisions,
        "downbeat_time": downbeat_time,
        "simplified_melody": simplified,
        "full_melody": melody,
        "midi": midi,
        "piano_notes": piano_notes,
        "piano_midi": piano_midi,
        "midi_data_raw": midi_data_raw,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path, help="Arquivo de áudio de entrada")
    parser.add_argument("--out-raw", type=Path, default=None, help="MIDI com a transcrição bruta (todas as notas)")
    parser.add_argument("--out-melody", type=Path, default=None, help="MIDI com a linha melódica (skyline, sem simplificar)")
    parser.add_argument("--out-simplified", type=Path, required=True, help="MIDI com a melodia simplificada (estilo lead sheet)")
    parser.add_argument("--onset-threshold", type=float, default=0.4)
    parser.add_argument("--frame-threshold", type=float, default=0.25)
    parser.add_argument("--minimum-note-length", type=float, default=58.0, help="ms")
    parser.add_argument("--bpm", type=float, default=None, help="Andamento CONSTANTE forçado; se omitido, segue as batidas reais detectadas por librosa.beat.beat_track (recomendado - acompanha variação real de andamento)")
    parser.add_argument("--out-musicxml", type=Path, default=None, help="MusicXML com a melodia simplificada (estilo lead sheet, pode perder notas)")
    parser.add_argument("--out-musicxml-full", type=Path, default=None, help="MusicXML direto da linha skyline (sem fundir/absorver notas) - mais próximo do MIDI completo")
    parser.add_argument("--time-signature", type=str, default="4/4", help='Fórmula de compasso, ex.: "2/4"')
    parser.add_argument("--anacrusis-notes", type=int, default=0, help="Quantas das primeiras notas formam anacruse/levada antes do 1o tempo forte")
    parser.add_argument("--key", type=str, default=None, help='Tom/armadura FORÇADO, ex.: "F", "Fá", "Bbm", "Lá menor"; se omitido, detecta pelo perfil tonal Krumhansl-Schmuckler')
    parser.add_argument("--force-division", type=int, default=None, choices=[1,2,3,4,6,8], help="Força a subdivisão de TODA batida (2=colcheia, 3=tercina, 4=semicolcheia...) em vez da detecção automática. Use quando souber a figura da peça.")
    parser.add_argument("--downbeat-notes", type=str, default=None, help="Índices (base 0) de duas notas + opcionalmente quantos TEMPOS há entre elas. \"1,7\" = compasso inteiro; \"1,7,2\" = 2 tempos entre elas. Andamento e anacruse saem daí, sem beat tracker.")
    parser.add_argument("--solo", action="store_true", help="Material monofônico real (flauta/voz): descarta notas do Basic Pitch sem ataque real correspondente. NÃO usar em stem multi-voz.")
    parser.add_argument("--join-equal-pitch", action="store_true", help="Solo ligado sem ataques repetidos na mesma altura: une notas contíguas do mesmo pitch após a quantização. Não usar quando há rearticulação real.")
    parser.add_argument("--suppress-harmonic-spikes", action="store_true", help="Corrige somente picos breves de oitava com vizinhos concordantes; não altera agudos sustentados.")
    parser.add_argument("--midi-program", type=int, default=0, metavar="0..127", help="Timbre General MIDI de reprodução (0=piano genérico, 73=flauta). Não identifica nem separa o instrumento da gravação.")
    parser.add_argument("--phrase-downbeats", action="store_true", help="MusicXML editorial: reentradas após respiração clara tendem ao primeiro tempo, com fermata em sustentações antes de pausa longa. MIDI intacto.")
    parser.add_argument("--align-repeats", action="store_true", help="(RESERVADO - hoje no-op) Re-ajuste da grade por repetições. Implementado em grid_align.py e medido sempre, mas a troca de grade está desligada até resolver a inflação de compassos no escritor de MusicXML - ver MARAVI_CONCEITO.md 12.4.")
    parser.add_argument("--auto-downbeat", action="store_true", help="USA a estimativa automática de tempo forte em vez da 1a nota. Consultivo por padrão (só é impresso) - ver tools/downbeat.py: falha em material muito sincopado, e a margem impressa avisa quando está em dúvida")
    parser.add_argument("--tap-count", type=int, default=None, help="Nº de batidas de contagem no INÍCIO do próprio áudio (ex.: 4). O andamento vem delas, as batidas são descartadas e a melodia é reancorada no primeiro tempo forte - dispensa --bpm e --anacrusis-notes")
    args = parser.parse_args()
    if not 0 <= args.midi_program <= 127:
        parser.error("--midi-program deve estar entre 0 e 127")

    print(f"Transcrevendo {args.audio} ...")
    result = run_pipeline(
        args.audio,
        onset_threshold=args.onset_threshold,
        frame_threshold=args.frame_threshold,
        minimum_note_length=args.minimum_note_length,
        bpm=args.bpm,
        time_signature=args.time_signature,
        anacrusis_notes=args.anacrusis_notes,
        key=args.key,
        tap_count=args.tap_count,
        auto_downbeat=args.auto_downbeat,
        align_repeats=args.align_repeats,
        solo=args.solo,
        join_equal_pitch=args.join_equal_pitch,
        suppress_harmonic_spikes=args.suppress_harmonic_spikes,
        midi_program=args.midi_program,
        force_division=args.force_division,
        downbeat_from_notes=tuple(int(x) for x in args.downbeat_notes.split(",")) if args.downbeat_notes else None,
    )
    print(f"Notas brutas detectadas: {result['raw_note_count']}")
    if args.out_raw:
        result["midi_data_raw"].write(str(args.out_raw))
        print(f"Bruto salvo em: {args.out_raw}")

    if result["octave_corrections"]:
        print(f"Correções de oitava (faixa): {len(result['octave_corrections'])} nota(s)")
    if result["onset_filtered"]:
        print(f"Filtro solo: {result['onset_filtered']} nota(s) sem ataque real descartadas")
    print(f"Notas na linha melódica: {result['melody_note_count']}")
    if args.out_melody:
        melody_to_midi(result["full_melody"]).write(str(args.out_melody))
        print(f"Melodia (sem simplificar) salva em: {args.out_melody}")

    if result["tap_info"]:
        ti = result["tap_info"]
        print(
            f"Contagem batida: {ti['tap_count_detected']} batida(s) lidas, {ti['bpm']:.1f} BPM "
            f"(regularidade {ti['spread'] * 100:.0f}%); melodia começa em {ti['melody_start_seconds']:.2f}s - contagem descartada"
        )
    print(f"Grade de andamento ({result['bpm_source']}): {result['beat_count']} batidas, média {result['display_bpm']:.1f} BPM")
    if result["key"]:
        k = result["key"]
        detalhe = ""
        if k["confidence"] is not None:
            detalhe = f" (correlação {k['confidence']:.2f}, margem {k['margin']:.2f} sobre {k['runner_up']})"
        print(f"Tom ({result['key_source']}): {k['name']}, armadura {k['fifths']:+d}{detalhe}")
    else:
        print("Tom: indisponível (material insuficiente) - armadura fica em dó maior")
    print(f"Subdivisão local por batida (auto): {result['beat_divisions']}")
    ai = result["align_info"]
    if ai:
        estado = "APLICADO" if (result["bpm_source"].endswith("alinhado")) else ("disponível" if ai["applied"] else "não aplicável")
        det = ""
        if ai["applied"]:
            det = f" | coerência de repetição {ai['before']*100:.0f}% -> {ai['after']*100:.0f}%"
        print(f"Alinhamento por repetição ({estado}): {ai['reason']}{det}")
    if result["downbeat_info"]:
        di = result["downbeat_info"]
        confianca = "confiante" if di["margin"] > 0.10 else ("fraca" if di["margin"] > 0.03 else "AMBÍGUA - não confie")
        print(
            f"Tempo forte (usando: {result['downbeat_source']}) | estimativa automática: fase {di['phase']}, "
            f"anacruse ~{di['anacrusis_notes']} nota(s), margem {di['margin']:.3f} ({confianca})"
        )
    print(f"Notas após simplificação: {result['simplified_note_count']}")
    if result["harmonic_spikes_corrected"]:
        print(f"Picos breves de oitava corrigidos: {result['harmonic_spikes_corrected']}")
    result["midi"].write(str(args.out_simplified))
    print(f"Melodia simplificada salva em: {args.out_simplified} ({result['beats_per_measure']}/{result['beat_unit']}, andamento médio {result['display_bpm']:.1f} BPM)")

    if args.out_musicxml:
        from musicxml_writer import write_musicxml

        write_musicxml(
            result["simplified_melody"],
            beat_times=result["beat_times"],
            path=str(args.out_musicxml),
            beats_per_measure=result["beats_per_measure"],
            beat_unit=result["beat_unit"],
            downbeat_time=result["downbeat_time"],
            display_bpm=result["display_bpm"],
            beat_divisions=result["beat_divisions"],
            key_fifths=result["key_fifths"],
            key_mode=result["key_mode"],
            readable_notation=args.phrase_downbeats,
            phrase_downbeats=args.phrase_downbeats,
        )
        print(f"MusicXML ({result['beats_per_measure']}/{result['beat_unit']}, anacruse={args.anacrusis_notes} notas) salvo em: {args.out_musicxml}")

    if args.out_musicxml_full:
        # Direto da linha skyline (SEM passar por quantize_and_simplify)
        # - autor, 2026-08-20: "consegue deixar o musicxml com a
        # notação mais próxima do midi (assim evitamos falta de
        # notas)". write_musicxml() sozinha já nunca DESCARTA nota (só
        # aperta o quanto precisar quando duas ficam quantizadas muito
        # perto - ver o comentário de `items` em musicxml_writer.py) -
        # é a fusão/absorção de quantize_and_simplify que reduz
        # contagem, então pular essa etapa preserva tudo que a linha
        # skyline detectou, ao custo de mais figuras curtas (32avos,
        # etc.) do que a versão simplificada.
        from musicxml_writer import write_musicxml

        write_musicxml(
            result["full_melody"],
            beat_times=result["beat_times"],
            path=str(args.out_musicxml_full),
            beats_per_measure=result["beats_per_measure"],
            beat_unit=result["beat_unit"],
            downbeat_time=result["downbeat_time"],
            display_bpm=result["display_bpm"],
            beat_divisions=result["beat_divisions"],
            key_fifths=result["key_fifths"],
            key_mode=result["key_mode"],
        )
        print(f"MusicXML completo (sem simplificar, {result['melody_note_count']} notas) salvo em: {args.out_musicxml_full}")


if __name__ == "__main__":
    main()
