#!/usr/bin/env python3
"""Servidor web local do Maravi - arrastar um áudio, preencher alguns
metadados opcionais, receber o `.mid`/`.musicxml`.

Motivação (2026-08-20, ver `MARAVI_CONCEITO.md`): pedido do autor por
uma "parte funcional" (arrastar arquivo + campos de metadado), depois
de eu esclarecer que um Artifact do claude.ai não consegue RODAR o
pipeline (Basic Pitch/ONNX/librosa) - só uma página local de verdade
(este servidor) consegue. Recomendação registrada e aceita: web local
primeiro, empacotamento (.deb/multiplataforma) só depois que o núcleo
estiver mais maduro (ver `MARAVI_TAREFAS.md`, Marco 4).

Uso: `.venv/bin/python webapp/app.py`, depois abrir
http://127.0.0.1:5001 no navegador. Processamento é síncrono (um
usuário local, sem necessidade de fila/websocket) - a resposta demora
o tempo real da inferência (alguns segundos por arquivo)."""
from __future__ import annotations

import json
import hmac
import math
import os
import re
import secrets
import subprocess
import shutil
import sys
import tempfile
import threading
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from flask import Flask, abort, jsonify, render_template, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge
from score_preview import render_score_preview
from instrument_labels import SCORE_INSTRUMENTS
from i18n import LANGUAGES, display_key_name, frontend_text, normalized_language, result_label, translate
from score_omr import (MAX_SCORE_BYTES, SCORE_EXTENSIONS, ScoreInputError, ScoreToolError,
                       available_tools, prepare_score_source, recognize_score, save_score_input)
from version import VERSION

VOICE_REGISTER_MINIMUMS = {"low": 48, "medium": 55, "high": 60}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200MB - áudio bruto, não precisa mais que isso
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


def default_export_directory(home: Path | None = None) -> str:
    """Suggest an existing personal folder; never create it or write to it here."""
    personal = Path.home() if home is None else home
    documents = personal / "Documents"
    return str(documents if documents.is_dir() else personal)


def use_solo_onset_filter(instrument_choice: str, source_isolated: bool) -> bool:
    """Opt in only for a declared solo voice, never infer singing from the mic."""
    return instrument_choice == "voice" and source_isolated


@app.context_processor
def release_identity():
    lang = normalized_language(request.args.get("lang"))
    return {"maravi_version": VERSION,
            "suggested_export_directory": default_export_directory(),
            "lang": lang, "languages": LANGUAGES,
            "t": lambda key, **values: translate(lang, key, **values),
            "result_label": lambda value: result_label(lang, value),
            "result_options": lambda values: ", ".join(result_label(lang, value) for value in values),
            "display_key": lambda value: display_key_name(lang, value),
            "frontend_text": frontend_text(lang)}


def preview_process_command(audio_path: Path, channel: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--analyze-preview", str(audio_path), "--channel", channel]
    script = Path(__file__).resolve().parent.parent / "tools" / "analyze_audio_preview.py"
    return [sys.executable, "-B", str(script), str(audio_path), "--channel", channel]


@app.after_request
def no_stale_interface(response):
    """F5 deve buscar a interface atual, não um HTML/JS/CSS em cache."""
    if response.mimetype == "text/html" or request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    return response

# Extensões confirmadas (libsndfile via `soundfile`, verificado
# 2026-08-20: MP3/WAV/FLAC/OGG/AIFF decodificam nativamente neste
# ambiente). Nada além disso é aceito no formulário - evita prometer
# suporte a um formato nunca testado.
VALID_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".aif", ".aiff"}

# Extensões que só chegam vindas da gravação pelo próprio microfone no
# navegador (`static/app.js`, MediaRecorder) - nunca oferecidas no
# <input accept> do upload de arquivo comum. Firefox grava ogg/opus
# (decodifica direto, já coberto por VALID_EXTENSIONS); Chrome/Edge só
# oferecem webm/opus, cujo CONTAINER `libsndfile` não reconhece -
# confirmado 2026-08-20 com um arquivo sintético (mesmo codec Opus,
# container .ogg funciona, container .webm dá "Format not
# recognised"). Por isso toda gravação de mic passa por
# `convert_to_wav()` antes do pipeline, independente do container.
MIC_RECORDING_EXTENSIONS = {".webm", ".ogg"}
CHANNEL_CHOICES = {"mix", "left", "right"}
MAX_CHANNEL_SECONDS = 180
MAX_PREVIEW_BYTES = 50 * 1024 * 1024

# Diretório de trabalho pras tomadas processadas nesta sessão do
# servidor - cada job é uma pasta própria, nunca sobrescreve outra.
JOBS_DIR = Path(tempfile.gettempdir()) / "maravi_webapp_jobs"
JOBS_DIR.mkdir(exist_ok=True)
EXPORT_TOKEN = secrets.token_urlsafe(32)  # impede gravações disparadas por outra página local
OMR_SLOT = threading.BoundedSemaphore(1)  # nunca iniciar dois reconhecimentos pesados juntos
AUDIO_SLOT = threading.BoundedSemaphore(1)  # análise prévia e transcrição não rodam juntas


def discard_failed_job(job_dir: Path) -> None:
    """Remove apenas a cópia temporária de um job novo que falhou.

    O arquivo escolhido pelo usuário, fora de JOBS_DIR, nunca é tocado.
    """
    if job_dir.parent != JOBS_DIR or len(job_dir.name) != 12:
        raise ValueError("Caminho de job inválido para limpeza")
    if any(c not in "0123456789abcdef" for c in job_dir.name):
        raise ValueError("Identificador de job inválido para limpeza")
    shutil.rmtree(job_dir)


@app.errorhandler(RequestEntityTooLarge)
def upload_too_large(_error):
    if request.path == "/analisar-audio":
        return jsonify(error="A pré-análise aceita arquivos de até 50 MB."), 413
    limit_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    return render_template(
        "erro.html", mensagem=f"Arquivo grande demais para esta instalação (limite: {limit_mb} MB).",
        mode="score" if request.path == "/reconhecer-partitura" else "audio",
    ), 413

# Sugestões de estilo por gênero (2026-08-20, autor: "os arquivos do
# suno passam pelo mesmo processo [...] a diferença talvez é que
# possamos utilizar os prompts [...] pra ajudar a configurar o Maravi
# pra gerar partituras mais próximas do estilo de escrita adotado
# segundo o que a música pede"). Deliberadamente pequeno e só
# PREENCHE campos vazios no formulário via JS (`static/app.js`) - nunca
# decide por conta própria, sempre editável antes de enviar.
#
# `grid_division` foi removido (2026-08-20): a subdivisão rítmica agora
# é detectada automaticamente compasso a compasso (`beat_grid.
# detect_beat_divisions`) em vez de forçada globalmente - ver
# `MARAVI_CONCEITO.md` seção 7.5. Só a fórmula de compasso continua
# sendo sugestão de gênero.
GENRE_SUGGESTIONS = {
    "chorinho": {"time_signature": "2/4"},
    "choro": {"time_signature": "2/4"},
    "samba": {"time_signature": "2/4"},
    "valsa": {"time_signature": "3/4"},
    "jazz": {"time_signature": "4/4"},
    "bossa nova": {"time_signature": "4/4"},
}


def convert_to_wav(src_path: Path, dst_path: Path) -> None:
    """Converte a gravação do microfone (webm/opus ou ogg/opus,
    dependendo do navegador) pra WAV via ffmpeg, sempre - não só pro
    caso webm. `librosa.load()` (usado pelo pipeline inteiro, Basic
    Pitch incluído) parou de ter fallback pra `audioread`/ffmpeg nesta
    versão (1.0.0) - só decodifica formatos que o `soundfile`/
    `libsndfile` reconhece direto. ffmpeg confirmado presente neste
    ambiente (ver `MARAVI_CONCEITO.md`)."""
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-y", "-i", str(src_path), "-ar", "44100", "-ac", "1", str(dst_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Falha ao converter a gravação do microfone (ffmpeg): {result.stderr[-500:]}")


def extract_stereo_channel(src_path: Path, dst_path: Path, channel: str) -> None:
    """Extrai L/R sem alterar o original; não declara isolamento instrumental.

    O limite de duração impede que um MP3 pequeno expanda para um WAV enorme
    no volume temporário. A primeira trilha de áudio é a mesma usada pelo
    decodificador normal; entradas mono ou sem duração verificável falham.
    """
    if channel not in {"left", "right"}:
        raise ValueError("Escolha de canal inválida.")
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=channels,duration:format=duration", "-of", "json", str(src_path)],
        capture_output=True, text=True, timeout=15,
    )
    if probe.returncode != 0:
        raise ValueError("Não foi possível examinar os canais deste áudio.")
    try:
        metadata = json.loads(probe.stdout)
        stream = metadata["streams"][0]
        channels = int(stream["channels"])
        duration = float(stream.get("duration") or metadata["format"]["duration"])
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ValueError("O áudio não informa canais e duração suficientes para escolher um canal.") from exc
    if channels != 2:
        raise ValueError("A escolha de canal exige uma gravação estéreo de dois canais.")
    if not math.isfinite(duration) or duration <= 0 or duration > MAX_CHANNEL_SECONDS:
        raise ValueError("Para escolher um canal, use um áudio de até 3 minutos.")
    index = 0 if channel == "left" else 1
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(src_path), "-map", "0:a:0",
         "-af", f"pan=mono|c0=c{index}", "-ar", "44100", "-acodec", "pcm_s16le",
         "-t", str(MAX_CHANNEL_SECONDS), "-y", str(dst_path)],
        capture_output=True, text=True, timeout=MAX_CHANNEL_SECONDS + 60,
    )
    if result.returncode != 0 or not dst_path.is_file():
        raise ValueError(f"Não foi possível extrair o canal escolhido: {result.stderr[-300:]}")


@app.get("/")
def index():
    return render_template(
        "index.html",
        valid_extensions=sorted(VALID_EXTENSIONS),
        genre_suggestions=GENRE_SUGGESTIONS,
    )


@app.get("/ajuda")
def ajuda():
    lang = normalized_language(request.args.get("lang"))
    return render_template("ajuda.html", lang=lang, languages=LANGUAGES,
                           t=lambda key: translate(lang, key),
                           help_sections=("audio", "instrument", "cues", "process",
                                          "score", "review", "privacy"))


@app.get("/partitura")
def partitura():
    audiveris, musescore = available_tools()
    return render_template(
        "partitura.html", formats=sorted(SCORE_EXTENSIONS),
        audiveris_available=bool(audiveris and Path(audiveris).is_file()),
        musescore_available=bool(musescore),
    )


@app.post("/analisar-audio")
def analisar_audio():
    """Prévia curta e revisável; não transcreve nem identifica instrumento."""
    def preview_error(key: str, status: int):
        return jsonify(error=translate(normalized_language(request.args.get("lang")), key)), status

    if request.content_length and request.content_length > MAX_PREVIEW_BYTES + 64 * 1024:
        return preview_error("preview_error_large", 413)
    file = request.files.get("audio")
    if file is None or not file.filename:
        return preview_error("preview_error_missing", 400)
    is_mic = request.form.get("source") == "mic"
    ext = Path(file.filename).suffix.lower()
    if ext not in (MIC_RECORDING_EXTENSIONS if is_mic else VALID_EXTENSIONS):
        return preview_error("preview_error_format", 400)
    channel = request.form.get("audio_channel", "mix")
    if channel not in CHANNEL_CHOICES or (is_mic and channel != "mix"):
        return preview_error("preview_error_channel", 400)
    if not AUDIO_SLOT.acquire(blocking=False):
        return preview_error("preview_error_busy", 503)
    try:
        with tempfile.TemporaryDirectory(prefix="analise_", dir=JOBS_DIR) as folder:
            audio_path = Path(folder) / f"entrada{ext}"
            size = 0
            with audio_path.open("xb") as output:
                while chunk := file.stream.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_PREVIEW_BYTES:
                        return preview_error("preview_error_large", 413)
                    output.write(chunk)
            if size == 0:
                return preview_error("preview_error_empty", 400)
            environment = os.environ.copy()
            environment.update(OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", NUMBA_NUM_THREADS="1")
            process = subprocess.run(
                preview_process_command(audio_path, channel),
                capture_output=True, text=True, timeout=55, env=environment,
            )
            if process.returncode != 0:
                app.logger.warning("Pré-análise falhou: %s", process.stderr[-500:])
                return preview_error("preview_error_failed", 422)
            return jsonify(json.loads(process.stdout))
    except (OSError, subprocess.TimeoutExpired, ValueError):
        app.logger.exception("Falha na pré-análise de áudio")
        return preview_error("preview_error_timeout", 503)
    finally:
        AUDIO_SLOT.release()


@app.post("/reconhecer-partitura")
def reconhecer_partitura():
    # Evita que um multipart enorme seja inteiramente analisado antes do
    # limite específico de partitura (o teto global de áudio é maior).
    if request.content_length and request.content_length > MAX_SCORE_BYTES + 64 * 1024:
        return render_template(
            "erro.html", mensagem="Partitura acima do limite de 20 MB.",
            message_key="error_score_too_large", mode="score"
        ), 413
    file = request.files.get("score")
    if file is None or not file.filename:
        return render_template("erro.html", mensagem="Nenhuma partitura enviada.",
                               message_key="error_no_score", mode="score"), 400
    page_field = request.form.get("pdf_page", "").strip()
    if page_field and not re.fullmatch(r"[1-9][0-9]{0,5}", page_field):
        return render_template("erro.html", mensagem="A página do PDF deve ser um número positivo.",
                               message_key="error_pdf_page", mode="score"), 400
    selected_page = int(page_field) if page_field else None
    if not OMR_SLOT.acquire(blocking=False):
        return render_template(
            "erro.html", mensagem="Já há uma partitura em processamento. Tente novamente ao terminar.",
            message_key="error_score_busy", mode="score",
        ), 503
    try:
        job_id = uuid.uuid4().hex[:12]
        job_dir = JOBS_DIR / job_id
        job_dir.mkdir(mode=0o700)
        try:
            original, metadata = save_score_input(file, job_dir, attribution={
                "score_author": request.form.get("score_author", ""),
                "source_reference": request.form.get("source_reference", ""),
                "rights_note": request.form.get("rights_note", ""),
            }, selected_page=selected_page)
            prepared = prepare_score_source(original, job_dir, metadata)
            result = recognize_score(prepared, job_dir)
            structure_review = result.get("structure_review") if isinstance(result, dict) else None
            if structure_review is not None:
                (job_dir / "revisao_estrutura.json").write_text(
                    json.dumps(structure_review, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        except ScoreInputError as exc:
            discard_failed_job(job_dir)
            return render_template("erro.html", mensagem=str(exc), diagnostic=str(exc),
                                   message_key="error_score_input", mode="score"), 400
        except ScoreToolError as exc:
            discard_failed_job(job_dir)
            return render_template("erro.html", mensagem=str(exc), diagnostic=str(exc),
                                   message_key="error_score_tool", mode="score"), 503
        except Exception:
            discard_failed_job(job_dir)
            app.logger.exception("Falha no reconhecimento de partitura")
            return render_template(
                "erro.html", mensagem="Falha inesperada ao reconhecer a partitura.",
                message_key="error_score_unexpected", mode="score"
            ), 500
        return render_template("resultado_partitura.html", job_id=job_id, metadata=metadata,
                               local_job_path=str(job_dir.resolve()), export_token=EXPORT_TOKEN,
                               structure_review=structure_review)
    finally:
        OMR_SLOT.release()


@app.post("/transcrever")
def transcrever():
    file = request.files.get("audio")
    if file is None or file.filename == "":
        return render_template("erro.html", mensagem="Nenhum arquivo de áudio enviado.",
                               message_key="error_no_audio"), 400

    is_mic_recording = request.form.get("source", "").strip() == "mic"
    audio_channel = request.form.get("audio_channel", "mix").strip()
    if audio_channel not in CHANNEL_CHOICES:
        return render_template("erro.html", mensagem="Escolha de canal inválida.",
                               message_key="error_channel_invalid"), 400
    if is_mic_recording and audio_channel != "mix":
        return render_template("erro.html", mensagem="A escolha de canal vale somente para arquivo estéreo enviado.",
                               message_key="error_channel_mic"), 400
    allowed_extensions = MIC_RECORDING_EXTENSIONS if is_mic_recording else VALID_EXTENSIONS

    ext = Path(file.filename).suffix.lower()
    if ext not in allowed_extensions:
        return render_template(
            "erro.html",
            mensagem=f'Tipo de arquivo "{ext or "(sem extensão)"}" não suportado. '
            f"Use um destes: {', '.join(sorted(allowed_extensions))}.",
        ), 400

    def opt_float(name):
        raw = request.form.get(name, "").strip()
        return float(raw) if raw else None

    def opt_int(name, default=0):
        raw = request.form.get(name, "").strip()
        return int(raw) if raw else default

    # Validar antes de criar o job: um campo inválido não deve deixar áudio
    # salvo em /tmp nem devolver a página 500 do Flask.
    try:
        bpm = opt_float("bpm")
        anacrusis_notes = opt_int("anacrusis_notes", default=0)
        tap_count = opt_int("tap_count", default=0) or None
        time_signature = request.form.get("time_signature", "").strip() or "4/4"
        parts = time_signature.split("/")
        if len(parts) != 2 or not all(part.isascii() and part.isdecimal() for part in parts):
            raise ValueError("Fórmula de compasso inválida; use, por exemplo, 4/4.")
        numerator, denominator = map(int, parts)
        if not 1 <= numerator <= 32 or denominator not in (1, 2, 4, 8, 16):
            raise ValueError("Fórmula de compasso fora da faixa aceita.")
        if bpm is not None and not 20 <= bpm <= 400:
            raise ValueError("BPM deve estar entre 20 e 400.")
        if not 0 <= anacrusis_notes <= 64:
            raise ValueError("Notas de anacruse devem estar entre 0 e 64.")
        if tap_count is not None and not 2 <= tap_count <= 16:
            raise ValueError("Contagem gravada deve estar entre 2 e 16.")
    except (ValueError, OverflowError) as exc:
        return render_template("erro.html", mensagem=f"Confira os campos numéricos: {exc}"), 400

    work_title = request.form.get("work_title", "").strip() or None
    composer = request.form.get("composer", "").strip() or None
    year = request.form.get("year", "").strip() or None
    genre = request.form.get("genre", "").strip() or None
    genre_prompt = request.form.get("genre_prompt", "").strip() or None
    score_style = request.form.get("score_style", "lead_sheet")
    key = request.form.get("key", "").strip() or None
    join_equal_pitch = request.form.get("join_equal_pitch") == "on"
    phrase_downbeats = request.form.get("phrase_downbeats") == "on"
    suppress_harmonic_spikes = request.form.get("suppress_harmonic_spikes") == "on"
    instrument_choice = request.form.get("score_instrument", "melody").strip()
    # Compatibilidade com um formulário antigo que nomeava flauta pelo
    # checkbox de fonte isolada. A interface nova usa dois campos distintos.
    legacy_flute = request.form.get("flute_only_source") == "on"
    if legacy_flute and "score_instrument" not in request.form:
        instrument_choice = "flute"
    if instrument_choice not in SCORE_INSTRUMENTS:
        return render_template("erro.html", mensagem="Instrumento da pauta inválido.",
                               message_key="error_instrument_invalid"), 400
    source_isolated = request.form.get("source_isolated") == "on" or legacy_flute
    voice_register = request.form.get("voice_register", "medium").strip()
    if voice_register not in VOICE_REGISTER_MINIMUMS:
        return render_template("erro.html", mensagem="Registro vocal inválido.",
                               message_key="error_voice_register_invalid"), 400
    part_name, instrument_name, midi_program, xml_midi_program = SCORE_INSTRUMENTS[instrument_choice]
    piano_ignored_options = []
    if instrument_choice == "piano_grand":
        piano_ignored_options = [
            label for enabled, label in (
                (join_equal_pitch, "Solo ligado"),
                (phrase_downbeats, "Escrita por frases"),
                (suppress_harmonic_spikes, "Picos de oitava"),
                (anacrusis_notes > 0, "Anacruse"),
            ) if enabled
        ]
        join_equal_pitch = phrase_downbeats = suppress_harmonic_spikes = False
        anacrusis_notes = 0

    job_id = uuid.uuid4().hex[:12]
    job_dir = JOBS_DIR / job_id
    # A pasta compartilhada de /tmp pode ser visível a outros usuários;
    # cada áudio/resultados ficam dentro de um job privado.
    job_dir.mkdir(mode=0o700)
    audio_path = job_dir / f"entrada{ext}"
    file.save(audio_path)

    if is_mic_recording:
        wav_path = job_dir / "entrada_convertida.wav"
        try:
            convert_to_wav(audio_path, wav_path)
        except Exception as exc:  # noqa: BLE001 - mostra o erro real pro autor
            discard_failed_job(job_dir)
            return render_template("erro.html", mensagem=str(exc)), 500
        audio_path = wav_path

    if audio_channel != "mix":
        selected_path = job_dir / f"entrada_canal_{audio_channel}.wav"
        try:
            extract_stereo_channel(audio_path, selected_path, audio_channel)
        except (ValueError, subprocess.TimeoutExpired, OSError) as exc:
            discard_failed_job(job_dir)
            return render_template("erro.html", mensagem=f"Não foi possível usar o canal: {exc}"), 400
        audio_path = selected_path

    pipeline_options = dict(
        bpm=bpm, time_signature=time_signature, anacrusis_notes=anacrusis_notes,
        key=key, tap_count=tap_count, join_equal_pitch=join_equal_pitch,
        suppress_harmonic_spikes=suppress_harmonic_spikes,
        solo=use_solo_onset_filter(instrument_choice, source_isolated),
        midi_program=midi_program,
        preserve_low_register_from=59 if source_isolated and instrument_choice == "flute" else None,
        minimum_pitch=(59 if instrument_choice == "flute" else
                       VOICE_REGISTER_MINIMUMS[voice_register] if instrument_choice == "voice" else None),
        piano_two_staves=instrument_choice == "piano_grand",
    )
    if not AUDIO_SLOT.acquire(blocking=False):
        discard_failed_job(job_dir)
        return render_template("erro.html", mensagem="Já há uma análise ou transcrição em andamento.",
                               message_key="error_audio_busy"), 503
    try:
        from transcribe_monophonic import NoNotesInRangeError, run_pipeline
        from musicxml_writer import write_musicxml

        try:
            result = run_pipeline(audio_path, **pipeline_options)
        except NoNotesInRangeError:
            raise  # o conversor de formato não resolveria ausência de notas no registro
        except Exception:
            if is_mic_recording or audio_channel != "mix":
                raise  # ja passou pelo ffmpeg; nunca substituir o canal escolhido pela mistura
            # Achado 2026-08-20 testando a gravação de mic com um clipe
            # real: um .ogg "suportado" (VALID_EXTENSIONS) ainda pode
            # travar o decodificador direto (`libsndfile`) quando o
            # arquivo carrega uma capa/arte embutida (o encoder original
            # muxou isso como uma trilha extra dentro do contêiner OGG,
            # algo que `libsndfile` não espera). Antes de desistir,
            # tenta de novo convertendo por ffmpeg - mesmo caminho já
            # usado pra gravação de microfone.
            wav_fallback = job_dir / "entrada_convertida.wav"
            convert_to_wav(audio_path, wav_fallback)
            result = run_pipeline(wav_fallback, **pipeline_options)

        # Escrita dos arquivos de saída DENTRO do mesmo try - achado
        # real 2026-08-20: um andamento implausível (batidas detectadas
        # longe demais umas das outras) fazia `pretty_midi`/`mido`
        # estourar o campo de 24 bits do tempo MIDI e quebrar aqui,
        # FORA do try original - o autor via "Internal Server Error"
        # cru do Flask em vez da página de erro normal do Maravi.
        # `beat_grid.average_bpm()` já filtra esse caso agora (levanta
        # `ValueError` com mensagem clara antes de chegar aqui), mas
        # qualquer outra falha de escrita também deve cair na mesma
        # página de erro, não vazar como erro interno cru.
        mid_path = job_dir / "resultado.mid"
        xml_path = job_dir / "resultado.musicxml"
        if instrument_choice == "piano_grand":
            from piano_score import write_piano_musicxml

            result["piano_midi"].write(str(mid_path))
            write_piano_musicxml(
                result["piano_notes"], beat_times=result["beat_times"],
                path=str(xml_path), beats_per_measure=result["beats_per_measure"],
                beat_unit=result["beat_unit"], downbeat_time=result["downbeat_time"],
                display_bpm=result["display_bpm"], key_fifths=result["key_fifths"],
                key_mode=result["key_mode"], work_title=work_title, composer=composer,
            )
        else:
            result["midi"].write(str(mid_path))
            write_musicxml(
                result["simplified_melody"],
                beat_times=result["beat_times"],
                path=str(xml_path),
                beats_per_measure=result["beats_per_measure"],
                beat_unit=result["beat_unit"],
                beat_divisions=result["beat_divisions"],
                downbeat_time=result["downbeat_time"],
                display_bpm=result["display_bpm"],
                work_title=work_title,
                composer=composer,
                key_fifths=result["key_fifths"],
                key_mode=result["key_mode"],
                readable_notation=True,
                phrase_downbeats=phrase_downbeats,
                part_name=part_name,
                instrument_name=instrument_name,
                midi_program=xml_midi_program,
            )
    except NoNotesInRangeError as exc:
        discard_failed_job(job_dir)
        return render_template("erro.html", mensagem=str(exc)), 422
    except Exception as exc:  # noqa: BLE001 - mostra o erro real pro autor, não esconde
        discard_failed_job(job_dir)
        return render_template("erro.html", mensagem=f"Falha ao transcrever: {exc}"), 500
    finally:
        AUDIO_SLOT.release()

    # A prévia é derivada do MusicXML já salvo; falhar aqui não deve impedir
    # o músico de baixar e revisar os arquivos originais no editor externo.
    preview_available = False
    try:
        # A prévia atual é monofônica e não interpreta <backup>/<staff>.
        preview_svg = None if instrument_choice == "piano_grand" else render_score_preview(xml_path)
        if preview_svg:
            (job_dir / "preview.svg").write_text(preview_svg, encoding="utf-8")
            preview_available = True
    except Exception:  # noqa: BLE001 - só a prévia é opcional, os arquivos continuam válidos
        app.logger.exception("Falha ao criar prévia do MusicXML")

    stats = {
        "raw_note_count": result["raw_note_count"],
        "melody_note_count": result["melody_note_count"],
        "excluded_low_notes": result.get("excluded_low_notes", 0),
        "simplified_note_count": (len(result["piano_notes"]) if instrument_choice == "piano_grand"
                                  else result["simplified_note_count"]),
        "joined_equal_pitch_count": result.get("joined_equal_pitch_count", 0),
        "join_equal_pitch": join_equal_pitch,
        "phrase_downbeats": phrase_downbeats,
        "suppress_harmonic_spikes": suppress_harmonic_spikes,
        "score_instrument": instrument_choice,
        "voice_register": voice_register if instrument_choice == "voice" else None,
        "voice_minimum_pitch": VOICE_REGISTER_MINIMUMS[voice_register] if instrument_choice == "voice" else None,
        "piano_ignored_options": piano_ignored_options,
        "piano_upper_count": (sum(note["pitch"] >= 60 for note in result["piano_notes"])
                              if instrument_choice == "piano_grand" else None),
        "piano_lower_count": (sum(note["pitch"] < 60 for note in result["piano_notes"])
                              if instrument_choice == "piano_grand" else None),
        "part_name": part_name,
        "source_isolated": source_isolated,
        "solo_onsets_applied": pipeline_options["solo"],
        "onset_filtered": result.get("onset_filtered", 0),
        "audio_channel": audio_channel,
        "local_job_path": str(job_dir.resolve()),
        "harmonic_spikes_corrected": result.get("harmonic_spikes_corrected", 0),
        "beat_count": result["beat_count"],
        "display_bpm": round(result["display_bpm"], 1),
        "bpm_source": result["bpm_source"],
        "time_signature": f"{result['beats_per_measure']}/{result['beat_unit']}",
        "key_name": result["key"]["name"] if result["key"] else None,
        "key_source": result["key_source"],
        "key_confidence": round(result["key"]["confidence"], 2) if result["key"] and result["key"]["confidence"] is not None else None,
        "key_runner_up": result["key"]["runner_up"] if result["key"] else None,
        "tap_bpm": round(result["tap_info"]["bpm"], 1) if result["tap_info"] else None,
        "tap_count_detected": result["tap_info"]["tap_count_detected"] if result["tap_info"] else None,
        "anacrusis_notes": anacrusis_notes,
        "work_title": work_title,
        "composer": composer,
        "year": year,
        "genre": genre,
        "genre_prompt": genre_prompt,
        "score_style": score_style,
        "original_filename": file.filename,
    }
    if instrument_choice == "piano_grand":
        stats["score_census"] = None  # a análise de duas pautas exige regras polifônicas próprias
    else:
        from score_census import census_melody, census_written_figures

        score_census = census_melody(
            result["simplified_melody"], result["beat_times"], instrument_choice,
            voice_minimum=stats["voice_minimum_pitch"],
        )
        try:
            written_census = census_written_figures(xml_path)
            score_census.update({key: value for key, value in written_census.items()
                                 if key != "warnings"})
            score_census["warnings"].extend(written_census["warnings"])
        except Exception:  # a revisão é auxiliar e não pode invalidar a partitura escrita
            app.logger.exception("Falha no censo das figuras do MusicXML")
            score_census.update({
                "written_symbol_count": None, "grace_symbol_count": None,
                "short_symbol_count": None, "short_symbol_percent": None,
                "very_short_symbol_count": None, "very_short_symbol_percent": None,
            })
        if not source_isolated:
            score_census["warnings"].insert(
                0, {"key": "census_source_unisolated"}
            )
        stats["score_census"] = score_census
    (job_dir / "stats.txt").write_text(repr(stats), encoding="utf-8")

    return render_template("resultado.html", job_id=job_id, stats=stats,
                           preview_available=preview_available, export_token=EXPORT_TOKEN)


def _valid_job_id(job_id: str) -> bool:
    return len(job_id) == 12 and all(c in "0123456789abcdef" for c in job_id)


@app.post("/exportar/<job_id>")
def exportar(job_id: str):
    """Copia o par MusicXML/MIDI para uma pasta local escolhida pelo músico.

    Nunca aceita uma requisição remota ou de outra página sem o token exibido
    no resultado; não substitui o job nem sobrescreve material preexistente.
    """
    from urllib.parse import urlsplit

    if not _valid_job_id(job_id):
        abort(404)
    if request.remote_addr not in {"127.0.0.1", "::1"} or urlsplit(request.host_url).hostname not in {
        "127.0.0.1", "localhost", "::1"
    }:
        abort(403)
    if not hmac.compare_digest(request.form.get("export_token", ""), EXPORT_TOKEN):
        abort(403)

    job_dir = JOBS_DIR / job_id
    sources = (job_dir / "resultado.musicxml", job_dir / "resultado.mid")
    if not all(source.is_file() for source in sources):
        abort(404)

    raw = request.form.get("destination", "").strip()
    def export_error(message: str, status: int):
        return render_template("exportado.html", diagnostic=message, job_id=job_id,
                               export_token=EXPORT_TOKEN, entered_directory=raw), status

    if not raw or len(raw) > 4096:
        return export_error("Informe uma pasta de destino existente.", 400)
    try:
        destination = Path(raw).expanduser()
        if not destination.is_absolute():
            raise ValueError("Informe o caminho completo da pasta, ou use ~/ para sua pasta pessoal.")
        destination = destination.resolve(strict=True)
        jobs_root = JOBS_DIR.resolve()
        if not destination.is_dir() or destination == jobs_root or jobs_root in destination.parents:
            raise ValueError("Escolha uma pasta existente fora dos arquivos temporários do Maravi.")
    except (OSError, RuntimeError, ValueError) as exc:
        return export_error(f"Pasta de destino inválida: {exc}", 400)

    saved_dir = destination / f"Maravi-{job_id}"
    created = []
    try:
        saved_dir.mkdir(mode=0o700)  # se já existir, não tocar nem sobrescrever
    except FileExistsError:
        return export_error("Esta subpasta Maravi já existe no destino. Nenhum arquivo foi substituído; escolha outra pasta.", 409)
    except OSError as exc:
        return export_error(f"Não foi possível criar a pasta de saída: {exc}", 500)
    try:
        for source in sources:
            output = saved_dir / source.name
            with source.open("rb") as input_file, output.open("xb") as output_file:
                created.append(output)
                shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
    except OSError as exc:
        for output in created:
            try:
                output.unlink(missing_ok=True)
            except OSError:
                app.logger.exception("Não foi possível limpar a cópia incompleta: %s", output)
        try:
            saved_dir.rmdir()  # só remove a pasta que esta requisição acabou de criar, se vazia
        except OSError:
            app.logger.exception("Cópia incompleta permanece em %s", saved_dir)
        return export_error(f"Não foi possível copiar os arquivos: {exc}. Confira {saved_dir} antes de tentar novamente.", 500)
    return render_template("exportado.html", saved_dir=str(saved_dir), job_id=job_id)


@app.get("/preview/<job_id>.svg")
def preview(job_id: str):
    if not _valid_job_id(job_id):
        abort(404)
    path = JOBS_DIR / job_id / "preview.svg"
    if not path.is_file():
        abort(404)
    response = send_file(path, mimetype="image/svg+xml")
    response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/download/<job_id>/<fmt>")
def download(job_id: str, fmt: str):
    if not _valid_job_id(job_id):
        abort(404)
    job_dir = JOBS_DIR / job_id
    if fmt == "mid":
        filename, download_name = "resultado.mid", "maravi.mid"
    elif fmt == "musicxml":
        filename, download_name = "resultado.musicxml", "maravi.musicxml"
    elif fmt == "review":
        filename, download_name = "revisao_estrutura.json", "maravi-revisao-estrutura.json"
    elif fmt in ("mxl", "omr"):
        candidates = sorted((job_dir / "audiveris").rglob(f"*.{fmt}"))
        if len(candidates) != 1:
            abort(404)
        return send_file(candidates[0], as_attachment=True, download_name=f"maravi.{fmt}")
    else:
        abort(404)
    path = job_dir / filename
    if not path.is_file():
        abort(404)
    return send_file(path, as_attachment=True, download_name=download_name)


if __name__ == "__main__":
    port = int(os.environ.get("MARAVI_PORT", "5001"))
    if not 1024 <= port <= 65535:
        raise ValueError("MARAVI_PORT deve estar entre 1024 e 65535.")
    print(f"Maravi - servidor local. Abra http://127.0.0.1:{port}/ no navegador.")
    app.run(host="127.0.0.1", port=port, debug=False,
            use_reloader=True, reloader_type="stat", reloader_interval=2)
