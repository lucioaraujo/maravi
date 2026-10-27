"""Corrige erros de oitava do Basic Pitch por continuidade melódica.

Autor, 2026-08-31, testando a flauta barroca solo ("Le Magicien
Baroque"): a saída tinha notas em MIDI 25 (dó#0) numa peça de flauta,
uma oitava - às vezes duas - abaixo de qualquer nota que o instrumento
toca. Confirmado contra `librosa.pyin` (confiável em material
monofônico): faixa real MIDI 55-87, o Basic Pitch devolveu 25-92.

## Por que acontece

Modelos de transcrição neural confundem a FUNDAMENTAL com um
SUBHARMÔNICO (metade da frequência) ou com um harmônico (o dobro),
especialmente em timbres ricos ou com reverb. O resultado é uma nota
certa em NOME (mesma classe de altura) mas errada em OITAVA. Não é ruído
que dá pra cortar por limiar - a "nota" tem energia real, só na oitava
errada.

## Como este módulo decide

Puramente por CONTINUIDADE / faixa, sem tocar no áudio de novo. Duas
etapas, da mais segura pra menos:

**A. Faixa robusta da própria peça.** Percentis 8 e 92 das alturas
(descarta os 8% mais extremos de cada lado, que é justamente onde os
erros de subharmônico/harmônico se concentram). Uma nota mais de
`range_slack` semitons ABAIXO do percentil 8 - ou acima do 92 - quase
certamente é oitava errada: uma flauta não desce 3 oitavas por uma nota
e sobe de volta. Desloca por ±12/±24/±36 pra trazer pra dentro da
faixa. Verificado contra a referência do autor do "Le Magicien
Baroque": faixa real MIDI 61-88; o Basic Pitch devolveu 25-92, com um
punhado de notas em MIDI 25.

**B. Continuidade local.** Depois de A, uma nota ainda a mais de
`max_leap` semitons da mediana das vizinhas é candidata a oitava; só
corrige se um deslocamento a trouxer pra dentro de `max_leap`. Mais
conservador que A - saltos melódicos reais grandes existem, então essa
etapa só age quando o deslocamento resolve de forma limpa.

Nunca muda a classe de altura, nunca a posição no tempo. Só oitava.
"""
from __future__ import annotations


def _percentil(valores: list[int], p: float) -> float:
    s = sorted(valores)
    if not s:
        return 0.0
    k = (len(s) - 1) * p
    lo = int(k)
    frac = k - lo
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + frac * (s[hi] - s[lo])


def _local_median(pitches: list[int], i: int, radius: int) -> float:
    lo = max(0, i - radius)
    hi = min(len(pitches), i + radius + 1)
    janela = sorted(pitches[lo:i] + pitches[i + 1 : hi])
    if not janela:
        return float(pitches[i])
    n = len(janela)
    return janela[n // 2] if n % 2 else (janela[n // 2 - 1] + janela[n // 2]) / 2


def fix_octave_errors(
    melody: list[dict],
    range_slack: int = 10,
    max_leap: int = 14,
    radius: int = 4,
    passes: int = 2,
    local_continuity: bool = False,
    preserve_low_register_from: int | None = None,
) -> dict:
    """Devolve `{melody, corrections, core_range}` - a melodia com
    oitavas corrigidas, a lista de `(indice, pitch_antigo, pitch_novo)`
    e a faixa robusta `(p8, p92)` usada.

    `range_slack`: folga (semitons) abaixo do p8 / acima do p92 antes de
    uma nota virar candidata a erro de oitava na etapa A (faixa).
    `local_continuity`: liga a etapa B (continuidade local). DESLIGADA
    por padrão - a etapa A (faixa) pega os erros grosseiros de
    subharmônico sem risco, mas a etapa B mexe em notas DENTRO da faixa
    da peça, o que num material com saltos melódicos reais grandes pode
    "corrigir" o que estava certo. Medido: no ParMePerdre (aprovado pelo
    autor) a etapa A não muda nada e a B mexeria em 14 notas de 1183 -
    sem confirmação de que pra melhor.
    `max_leap`/`radius`/`passes`: parâmetros da etapa B.
    `preserve_low_register_from`: numa fonte instrumental já isolada, não
    elevar notas iguais ou superiores ao grave confirmado do instrumento.
    Sem essa declaração, a correção permanece como antes. Não é separação
    de fontes nem prova de que a nota pertence ao instrumento.
    """
    pitches = [int(n["pitch"]) for n in melody]
    correcoes: list[tuple[int, int, int]] = []
    if len(pitches) < 8:
        return {"melody": [dict(n) for n in melody], "corrections": [], "core_range": None}

    p8 = _percentil(pitches, 0.08)
    p92 = _percentil(pitches, 0.92)
    piso = p8 - range_slack
    teto = p92 + range_slack

    # Etapa A: puxa notas muito fora da faixa robusta pra dentro dela.
    for i, pit in enumerate(pitches):
        if piso <= pit <= teto:
            continue
        if pit < piso and preserve_low_register_from is not None and pit >= preserve_low_register_from:
            continue
        alvo = min(max(pit, piso), teto)  # borda mais próxima da faixa
        melhor, melhor_d = pit, abs(pit - alvo)
        for shift in (-36, -24, -12, 12, 24, 36):
            cand = pit + shift
            d = abs(cand - min(max(cand, piso), teto))  # 0 se cair dentro
            if d < melhor_d or (d == 0 and melhor_d > 0):
                melhor, melhor_d = cand, d
        if melhor != pit:
            correcoes.append((i, pit, melhor))
            pitches[i] = melhor

    # Etapa B: continuidade local, mais conservadora - só se pedida.
    for _ in range(passes if local_continuity else 0):
        mudou = False
        for i in range(len(pitches)):
            mediana = _local_median(pitches, i, radius)
            if (preserve_low_register_from is not None
                    and preserve_low_register_from <= pitches[i] < mediana):
                continue
            desvio = abs(pitches[i] - mediana)
            if desvio <= max_leap:
                continue
            melhor, melhor_desvio = pitches[i], desvio
            for shift in (-24, -12, 12, 24):
                d = abs(pitches[i] + shift - mediana)
                if d < melhor_desvio:
                    melhor_desvio, melhor = d, pitches[i] + shift
            if melhor != pitches[i] and melhor_desvio <= max_leap:
                correcoes.append((i, pitches[i], melhor))
                pitches[i] = melhor
                mudou = True
        if not mudou:
            break

    corrigida = [dict(n) for n in melody]
    for i, p in enumerate(pitches):
        corrigida[i]["pitch"] = p
    return {"melody": corrigida, "corrections": correcoes, "core_range": (round(p8), round(p92))}


def _mediana(vals: list[float]) -> float:
    s = sorted(vals)
    n = len(s)
    if n == 0:
        return 0.0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def normalize_register(melody: list[dict], window: int = 16, min_run: int = 16, ref_frac: float = 0.33) -> dict:
    """Corrige um TRECHO INTEIRO deslocado de oitava - o erro do Suno de
    gerar a segunda metade da peça uma oitava (ou duas) abaixo do resto
    (autor, 2026-09-01, "ParMePerdre": "é uma flauta transversal que
    toca, está num registro muito grave... muitas notas que me soam
    estranho"). Medido: 0-70s com mediana dó#5-lá5, e de 70s até o fim
    despenca pra ré4-fá#4 e fica lá - metade da peça.

    Diferente de `fix_octave_errors`: aquele pega NOTAS soltas fora da
    faixa; este pega um BLOCO longo cuja mediana móvel está ~1 oitava
    fora da referência. A referência é a mediana do primeiro `ref_frac`
    da peça (o registro costuma se estabelecer no começo, antes de
    qualquer erro do gerador). Só corrige runs de pelo menos `min_run`
    notas - um trecho grave curto é música de verdade. Não toca em
    classe de altura nem em tempo, só oitava."""
    pitches = [int(n["pitch"]) for n in melody]
    if len(pitches) < max(min_run, 8):
        return {"melody": [dict(n) for n in melody], "corrections": [], "shifted_runs": []}

    ref = _mediana(pitches[: max(8, int(len(pitches) * ref_frac))])
    rm = [
        _mediana([float(p) for p in pitches[max(0, i - window) : i + window + 1]])
        for i in range(len(pitches))
    ]
    off = [round((rm[i] - ref) / 12) for i in range(len(pitches))]

    correcoes: list[tuple[int, int, int]] = []
    runs: list[tuple[int, int, int]] = []
    i = 0
    while i < len(pitches):
        if off[i] != 0:
            j = i
            while j < len(pitches) and off[j] == off[i]:
                j += 1
            if j - i >= min_run:
                shift = -12 * off[i]
                for k in range(i, j):
                    correcoes.append((k, pitches[k], pitches[k] + shift))
                    pitches[k] += shift
                runs.append((i, j, shift))
            i = j
        else:
            i += 1

    corrigida = [dict(n) for n in melody]
    for k, p in enumerate(pitches):
        corrigida[k]["pitch"] = p
    return {"melody": corrigida, "corrections": correcoes, "shifted_runs": runs}
