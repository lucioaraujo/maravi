"""Grade de tempo baseada nas batidas REAIS detectadas no áudio, em vez
de um único BPM constante extrapolado pra peça inteira.

Motivação (2026-08-20, `MARAVI_CONCEITO.md` seção 7.1): com um BPM
fixo, qualquer variação real de andamento (comum mesmo em áudio gerado/
performático) desalinha a grade aos poucos - medido um desvio real de
~327ms (mais de 2 passos de semicolcheia) entre a abertura da música e
um "recomeço" temático 16 compassos depois. `librosa.beat.beat_track`
já devolve os TIMESTAMPS de cada batida individual, não só a média -
usar isso como referência (com interpolação linear entre batidas
vizinhas) segue o andamento real em vez de assumir constância perfeita.
Mesmo princípio já usado pro andamento variável do ANTITOTEM
(`MidiCapture::TempoEvent`, docs/PESQUISA_MIDI_E_PARTITURA.md seção
3.7) - lá vinha de captura direta do sequenciador; aqui vem de detecção
de áudio.
"""
from __future__ import annotations

import bisect
from pathlib import Path


def estimate_beat_times(audio_path: Path) -> list[float]:
    """Timestamps reais (segundos) de cada batida detectada, na
    resolução do TEMPO/BEAT (não subdividido ainda - a subdivisão em
    colcheia/semicolcheia é feita depois por `time_to_step`)."""
    import librosa

    y, sr = librosa.load(str(audio_path), sr=None)
    _, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    if len(beat_times) < 2:
        raise ValueError("librosa não conseguiu detectar batidas suficientes neste áudio - forneça --bpm manualmente")
    return beat_times


def synthetic_beat_times(bpm: float, duration_seconds: float) -> list[float]:
    """Grade de batidas perfeitamente constante, pro caso de o usuário
    fornecer um BPM manual e preferir constância a seguir variação real
    detectada (`--bpm` na CLI)."""
    beat_seconds = 60.0 / bpm
    count = int(duration_seconds / beat_seconds) + 4  # margem
    return [i * beat_seconds for i in range(count)]


def average_bpm(beat_times: list[float]) -> float:
    """Levanta erro (em vez de devolver um número sem sentido) quando as
    batidas detectadas estão longe demais umas das outras pra formar um
    andamento plausível - achado real 2026-08-20 testando gravação de
    microfone: um trecho com poucas batidas detectadas e bem espaçadas
    (ex.: só 2 batidas nos extremos de um áudio de 30s) produz uma
    média de ~2 BPM. `pretty_midi`/`mido` representam andamento como
    microssegundos por semínima num campo de 24 bits (máx. 16.777.215
    µs) - abaixo de ~3,6 BPM isso estoura o campo e quebra a escrita do
    `.mid` com um erro interno do `mido`, sem mensagem clara pro
    usuário. Faixa de 20 a 400 BPM cobre qualquer andamento musical
    real com folga; fora dela é sinal de detecção de batida ruim, não
    de música genuinamente muito lenta/rápida."""
    if len(beat_times) < 2:
        return 120.0
    bpm = 60.0 / ((beat_times[-1] - beat_times[0]) / (len(beat_times) - 1))
    if not (20.0 <= bpm <= 400.0):
        raise ValueError(
            "andamento detectado é implausível (batidas detectadas longe demais umas das outras) - "
            "forneça um BPM manualmente"
        )
    return bpm


def time_to_step(t: float, beat_times: list[float], steps_per_beat: int) -> float:
    """Posição fracionária de `t` na grade (unidade = 1/steps_per_beat
    de um tempo/beat), interpolando linearmente dentro do intervalo
    entre duas batidas reais vizinhas. Fora do intervalo conhecido
    (antes da 1a batida ou depois da última), extrapola usando a
    duração do intervalo mais próximo - sem isso, notas no comecinho ou
    no finalzinho do áudio (antes/depois de onde o beat tracker
    conseguiu ancorar) não teriam grade nenhuma pra cair."""
    n = len(beat_times)
    if t <= beat_times[0]:
        i = 0
    elif t >= beat_times[-1]:
        i = n - 2
    else:
        i = bisect.bisect_right(beat_times, t) - 1
        i = max(0, min(i, n - 2))
    beat_duration = beat_times[i + 1] - beat_times[i]
    fraction = (t - beat_times[i]) / beat_duration
    return (i + fraction) * steps_per_beat


def step_to_time(step: float, beat_times: list[float], steps_per_beat: int) -> float:
    n = len(beat_times)
    beat_position = step / steps_per_beat
    i = int(beat_position)
    i = max(0, min(i, n - 2))
    fraction = beat_position - i
    beat_duration = beat_times[i + 1] - beat_times[i]
    return beat_times[i] + fraction * beat_duration


def local_grid_seconds(t: float, beat_times: list[float], steps_per_beat: int) -> float:
    """Duração (segundos) de UM passo de grade perto de `t` - usada
    como limiar local pra fusão/absorção em `quantize_and_simplify`,
    já que a grade não é mais constante ao longo da peça."""
    n = len(beat_times)
    if t <= beat_times[0]:
        i = 0
    elif t >= beat_times[-1]:
        i = n - 2
    else:
        i = bisect.bisect_right(beat_times, t) - 1
        i = max(0, min(i, n - 2))
    return (beat_times[i + 1] - beat_times[i]) / steps_per_beat


def detect_beat_divisions(
    melody: list[dict],
    beat_times: list[float],
    candidates: tuple[int, ...] = (1, 2, 3, 4, 6, 8),
    complexity_bias: float = 0.015,
) -> list[int]:
    """Escolhe, PRA CADA BATIDA, em quantas partes iguais ela
    genuinamente se divide (1=nenhuma, 2=colcheia, 3=tercina,
    4=semicolcheia, 6=sextina, 8=fusa) - em vez de uma única subdivisão
    fixa pra peça inteira.

    Motivação (2026-08-20, autor, depois de ver a maioria da notação
    virar tercina num MIDI gerado): "talvez seja a minha fala em
    forçar a partitura em semicolcheia que tenha gerado imprecisões
    [...] não precisa forçar, depende da música, no chorinho se usa
    tercinas também, colcheias, etc [...] essa estratégia de definir
    compasso por compasso é boa (ou a cada dois ou quatro), pois vai
    evitar erros escalonados." Diagnóstico confirmado: uma grade
    binária ÚNICA (semicolcheia = 4 passos/tempo) é estruturalmente
    incapaz de representar tercina (3 no espaço de 2 não é potência de
    dois) - qualquer trecho realmente tocado em tercina era distorcido
    pra caber na grade errada, e o MuseScore (mais esperto ao
    reimportar o `.mid`) provavelmente "sentia" essa distorção e
    tentava corrigir de volta pra tercina sozinho - o erro nascia aqui,
    não lá.

    Pra cada batida, testa cada candidato D: gera D pontos igualmente
    espaçados dentro da batida, mede o erro médio entre cada nota REAL
    (não quantizada ainda) que começa dentro dela e o ponto de grade
    mais próximo. Crucial: o erro é medido em RELAÇÃO ao espaçamento da
    própria grade (`erro / (duração_da_batida/D)`), não em segundos
    absolutos - uma grade mais fina SEMPRE parece caber melhor em
    segundos absolutos, simplesmente por ter mais pontos candidatos
    (mais chance de sobra um perto), mesmo sem ser um ajuste musical
    real (bug real encontrado testando: com uma penalidade em segundos
    absolutos, um erro pequeno-mas-genuíno de tercina perdia pra uma
    fusa/D=8 que só "cabia melhor" por acaso estatístico). Medir em
    unidades de "passos de grade" corrige isso - só depois disso é que
    faz sentido uma pequena preferência (`complexity_bias`) por D mais
    simples quando dois candidatos ajustam quase igual. Batidas sem
    nenhuma nota dentro ficam com o padrão (4, semicolcheia) - não há
    dado pra decidir, e 4 é o meio-termo mais comum.
    """
    # Ordem de preferência quando o ajuste empata (D mais "natural"
    # primeiro) - usada só como desempate via `complexity_bias`, nunca
    # domina um ajuste genuinamente melhor de outro candidato.
    simplicity_rank = {1: 0, 2: 1, 4: 2, 3: 3, 8: 4, 6: 5}

    divisions: list[int] = []
    for i in range(len(beat_times) - 1):
        b0, b1 = beat_times[i], beat_times[i + 1]
        beat_duration = b1 - b0
        notes_in_beat = [n for n in melody if b0 <= n["start"] < b1]
        if not notes_in_beat:
            divisions.append(4)
            continue
        best_d, best_score = 4, float("inf")
        for d in candidates:
            grid_spacing = beat_duration / d
            grid_points = [b0 + k * grid_spacing for k in range(d)]
            total_error = sum(min(abs(n["start"] - gp) for gp in grid_points) for n in notes_in_beat)
            relative_error = (total_error / len(notes_in_beat)) / grid_spacing
            score = relative_error + complexity_bias * simplicity_rank.get(d, 9)
            if score < best_score:
                best_score, best_d = score, d
        divisions.append(best_d)
    return divisions


def make_snap(beat_times: list[float], steps_per_beat: int, anchor_time: float):
    """Devolve uma função `snap(t) -> float` que arredonda `t` pro
    ponto de grade mais próximo, com step 0 ancorado em `anchor_time`
    (o tempo forte/downbeat real, não necessariamente uma batida
    detectada pelo `librosa` - a ancoragem em `anchor_time` continua
    sendo o que garante que `quantize_and_simplify` e `write_musicxml`
    concordem sobre onde cada compasso começa, ver seção 7.1 de
    `MARAVI_CONCEITO.md`)."""
    anchor_step = time_to_step(anchor_time, beat_times, steps_per_beat)

    def snap(t: float) -> float:
        raw_step = time_to_step(t, beat_times, steps_per_beat) - anchor_step
        rounded_step = round(raw_step) + anchor_step
        return step_to_time(rounded_step, beat_times, steps_per_beat)

    return snap


def quantize_melody_to_steps(
    melody: list[dict],
    beat_times: list[float],
    steps_per_beat: int,
    anchor_time: float,
) -> list[tuple[int, int, int, float]]:
    """Quantização ÚNICA, compartilhada por `quantize_and_simplify` e
    `write_musicxml` - antes as duas tinham implementações SEPARADAS e
    sutilmente diferentes, e essa duplicação foi a raiz de pelo menos
    três bugs reais nesta sessão (fusão em cascata, grades
    desalinhadas, nota esticada por arredondamento independente de
    início/fim - ver `MARAVI_CONCEITO.md`, seção 7). Devolve uma lista
    de `(start_step, end_step, pitch, amplitude)` relativa a
    `anchor_time` (step 0 = tempo forte/downbeat real), sem
    sobreposições nem lacunas espúrias.

    A nota-âncora (a que está exatamente em `anchor_time` - tipicamente
    o tempo forte real, a nota logo depois da anacruse) precisa cair
    EXATAMENTE no step 0, por definição (`fractional_step(anchor_time)
    == 0` sempre). Encadear a quantização numa única cadeia PRA FRENTE
    a partir da primeira nota da melodia não garante isso - erro de
    arredondamento acumulado entre a primeira nota e a âncora podia
    "empurrar" a âncora um passo pra fora do lugar (bug real,
    2026-08-20, autor: "não fez o anacruse correto" - a 4ª nota, que
    devia abrir o compasso 1, ficava presa no compasso 0/anacruse).
    Corrigido processando em DUAS cadeias a partir da âncora: uma pra
    FRENTE (âncora em diante, cursor monotônico normal) e uma pra TRÁS
    (da nota imediatamente antes da âncora até a primeira, com o mesmo
    raciocínio de duração-relativa-ao-início mas o CURSOR sendo o
    início da nota seguinte em vez do fim da anterior) - a âncora nunca
    depende de arredondamento acumulado de notas antes dela.

    Regra de duração, igual nas duas cadeias: arredondada em RELAÇÃO ao
    início/fim já decidido (`fractional_step(fim) - fractional_step
    (início)`), nunca início e fim absolutos arredondados
    independentemente - isso é o que esticava notas curtas (uma nota
    real de ~0.9 passo podia virar 2 passos inteiros: `round(a) -
    round(b) != round(a-b)` em geral). Lacunas espúrias (nota
    contígua na realidade, mas arredondamento deixando 1 passo de
    "pausa" fantasma) são fechadas comparando a lacuna REAL em
    segundos - só vira pausa de verdade se a lacuna bruta for de pelo
    menos meio passo de grade."""
    anchor_step = time_to_step(anchor_time, beat_times, steps_per_beat)

    def fractional_step(t: float) -> float:
        return time_to_step(t, beat_times, steps_per_beat) - anchor_step

    sorted_melody = sorted(melody, key=lambda n: n["start"])
    anchor_index = 0
    for i, note in enumerate(sorted_melody):
        if note["start"] >= anchor_time:
            anchor_index = i
            break
    else:
        anchor_index = len(sorted_melody)

    quantized: list[tuple[int, int, int, float] | None] = [None] * len(sorted_melody)

    # Cadeia pra FRENTE: da âncora (step 0 fixo) em diante.
    cursor: int | None = None
    previous_real_end: float | None = None
    for i in range(anchor_index, len(sorted_melody)):
        note = sorted_melody[i]
        start_frac = fractional_step(note["start"])
        start_step = 0 if i == anchor_index else round(start_frac)
        if cursor is not None:
            real_gap = note["start"] - previous_real_end
            grid_seconds = local_grid_seconds(note["start"], beat_times, steps_per_beat)
            if start_step <= cursor or real_gap < grid_seconds * 0.5:
                start_step = cursor
        duration_steps = max(1, round(fractional_step(note["end"]) - start_frac))
        end_step = start_step + duration_steps
        quantized[i] = (start_step, end_step, note["pitch"], note.get("amplitude", 0.8))
        cursor = end_step
        previous_real_end = note["end"]

    # Cadeia pra TRÁS: da nota logo antes da âncora até a primeira -
    # mesmo raciocínio espelhado (cursor = onde a PRÓXIMA nota já
    # começa, em vez de onde a anterior termina).
    cursor = 0  # a âncora sempre começa em 0 - a última nota de trás termina aqui
    next_real_start: float | None = anchor_time
    for i in range(anchor_index - 1, -1, -1):
        note = sorted_melody[i]
        end_frac = fractional_step(note["end"])
        end_step = round(end_frac)
        if cursor is not None:
            real_gap = next_real_start - note["end"]
            grid_seconds = local_grid_seconds(note["end"], beat_times, steps_per_beat)
            if end_step >= cursor or real_gap < grid_seconds * 0.5:
                end_step = cursor
        duration_steps = max(1, round(end_frac - fractional_step(note["start"])))
        start_step = end_step - duration_steps
        quantized[i] = (start_step, end_step, note["pitch"], note.get("amplitude", 0.8))
        cursor = start_step
        next_real_start = note["start"]

    return [q for q in quantized if q is not None]
