(function () {
  const uiText = JSON.parse(document.getElementById("ui-strings-data")?.textContent || "{}");
  const tr = (key, values = {}) => {
    const phrase = uiText[key];
    if (typeof phrase !== "string") throw new Error(`Missing UI text: ${key}`);
    return phrase.replace(/\{([a-z]+)\}/g, (_match, name) => String(values[name] ?? ""));
  };
  const dropzone = document.getElementById("dropzone");
  const input = document.getElementById("audio-input");
  const filenameEl = document.getElementById("filename");
  const dropzoneText = document.getElementById("dropzone-text");
  const audioPreview = document.getElementById("mic-preview");
  const audioPreviewArea = document.getElementById("audio-preview-area");
  const analyzeAudio = document.getElementById("analyze-audio");
  const analysisResult = document.getElementById("audio-analysis-result");
  const analysisReport = document.getElementById("audio-analysis-report");
  const useAnalysisBpm = document.getElementById("use-analysis-bpm");
  const useAnalysisKey = document.getElementById("use-analysis-key");
  const audioChannel = document.getElementById("audio_channel");
  const instrumentSelect = document.getElementById("score_instrument");
  const voiceRegisterField = document.getElementById("voice-register-field");
  const voiceRegisterSelect = document.getElementById("voice_register");
  if (instrumentSelect && voiceRegisterField && voiceRegisterSelect) {
    const syncVoiceRegister = () => {
      const visible = instrumentSelect.value === "voice";
      voiceRegisterField.hidden = !visible;
      voiceRegisterSelect.disabled = !visible;
    };
    instrumentSelect.addEventListener("change", syncVoiceRegister);
    syncVoiceRegister();
  }
  const submitButton = document.getElementById("submit-btn");
  const transcriptionForm = document.getElementById("form");
  let previewUrl = null;
  let analysisRequest = 0;
  let analysisReviewed = false;

  function clearAnalysis() {
    analysisRequest += 1;
    analysisReviewed = false;
    analysisResult.hidden = true;
    useAnalysisBpm.hidden = true;
    useAnalysisKey.hidden = true;
    useAnalysisBpm.onclick = null;
    useAnalysisKey.onclick = null;
  }

  function showFile(file) {
    if (!file) return;
    clearAnalysis();
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(file);
    audioPreview.src = previewUrl;
    audioPreviewArea.hidden = false;
    filenameEl.textContent = file.name;
    filenameEl.hidden = false;
    dropzoneText.textContent = tr("file_selected");
  }

  // O <label for="audio-input"> já abre o seletor ao clicar. Chamar
  // input.click() aqui duplicava a ativação nativa em alguns navegadores.
  dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); }
  });
  input.addEventListener("change", () => showFile(input.files[0]));
  audioChannel.addEventListener("change", clearAnalysis);
  window.addEventListener("pagehide", () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  });

  ["dragenter", "dragover"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.add("dragover"); })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.remove("dragover"); })
  );
  dropzone.addEventListener("drop", (e) => {
    const file = e.dataTransfer?.files?.[0];
    if (!file) {
      dropzoneText.textContent = tr("no_file");
      return;
    }
    const allowed = input.accept.split(",").map((ext) => ext.trim().toLowerCase());
    const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (!allowed.includes(extension)) {
      dropzoneText.textContent = tr("bad_format");
      return;
    }
    try {
      // Alguns navegadores expõem uma FileList transitória no evento drop.
      // Uma nova DataTransfer mantém exatamente o arquivo escolhido.
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
    } catch (error) {
      try { input.files = e.dataTransfer.files; } catch (_ignored) { /* mensagem abaixo */ }
    }
    if (!input.files?.length || input.files[0].name !== file.name) {
      dropzoneText.textContent = tr("drop_failed");
      return;
    }
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });

  async function runAnalysis(beforeTranscription = false) {
    const file = input.files[0];
    if (!file) {
      analysisResult.hidden = false;
      analysisReport.textContent = tr("choose_audio");
      return;
    }
    clearAnalysis();
    const thisRequest = analysisRequest;
    analysisResult.hidden = false;
    analysisReport.textContent = tr("analyzing");
    analyzeAudio.disabled = true;
    submitButton.disabled = true;
    const data = new FormData();
    data.append("audio", file);
    data.append("audio_channel", audioChannel.value);
    data.append("source", document.getElementById("source-field").value);
    try {
      const lang = document.documentElement?.lang?.split("-")[0] || "pt";
      const response = await fetch(`/analisar-audio?lang=${encodeURIComponent(lang)}`, { method: "POST", body: data });
      const report = await response.json();
      if (thisRequest !== analysisRequest) return;
      if (!response.ok) throw new Error(report.error || tr("analysis_failed"));
      const channel = tr(`channel_${report.selected_channel === "mix" ? "mix" :
        report.selected_channel === "left" ? "left" : "right"}`);
      const bpm = report.bpm === null ? tr("no_pulse") :
        tr("pulse_candidate", { bpm: report.bpm });
      const pulseCaution = report.tempo_regularity !== null && report.tempo_regularity > 0.25 ?
        tr("pulse_irregular") : report.bpm !== null ? tr("pulse_check") : "";
      const key = report.key_name === null ? tr("no_key") :
        tr("key_candidate", { key: report.key_name }) + (report.key_ambiguous ?
          ` (${tr("key_ambiguous")}${report.key_runner_up ? tr("key_alternative", { key: report.key_runner_up }) : ""})` : "");
      analysisReport.textContent = tr("analysis_summary", {
        duration: report.duration_seconds, channels: report.channels,
        sample: report.sample_seconds, channel, bpm, caution: pulseCaution, key
      }) + (beforeTranscription ? tr("review_submit") : "");
      if (report.bpm !== null) {
        useAnalysisBpm.hidden = false;
        useAnalysisBpm.onclick = () => {
          document.getElementById("bpm").value = report.bpm;
        };
      }
      if (report.key_name !== null && !report.key_ambiguous) {
        useAnalysisKey.hidden = false;
        useAnalysisKey.onclick = () => {
          document.getElementById("key").value = report.key_name;
        };
      }
    } catch (error) {
      if (thisRequest === analysisRequest) {
        analysisReport.textContent = (error.message || tr("analysis_failed")) +
          (beforeTranscription ? tr("review_after_error") : "");
      }
    } finally {
      if (thisRequest === analysisRequest) {
        analysisReviewed = true;
        if (beforeTranscription) analysisResult.scrollIntoView({ behavior: "smooth", block: "center" });
      }
      analyzeAudio.disabled = false;
      submitButton.disabled = false;
    }
  }

  analyzeAudio.addEventListener("click", () => runAnalysis());

  transcriptionForm.addEventListener("submit", (event) => {
    if (analyzeAudio.disabled) {
      event.preventDefault();
      return;
    }
    const needsSuggestion = !document.getElementById("bpm").value.trim() ||
      !document.getElementById("key").value.trim();
    if (input.files[0] && needsSuggestion && !analysisReviewed) {
      event.preventDefault();
      runAnalysis(true);
    }
  });

  // Sugestao de estilo por genero (2026-08-20) - so preenche campos
  // que o autor deixou vazios, nunca sobrescreve o que ja foi digitado.
  // Dados vem de um <script type="application/json"> no HTML (nao dá
  // pra usar Jinja aqui - app.js e servido como arquivo estatico puro).
  const genreDataEl = document.getElementById("genre-suggestions-data");
  const genreSuggestions = genreDataEl ? JSON.parse(genreDataEl.textContent) : {};
  const genreInput = document.getElementById("genre");
  const timeSigInput = document.getElementById("time_signature");

  genreInput.addEventListener("change", () => {
    const key = genreInput.value.trim().toLowerCase();
    const suggestion = genreSuggestions[key];
    if (!suggestion) return;
    if (!timeSigInput.value || timeSigInput.value === "4/4") timeSigInput.value = suggestion.time_signature;
  });

  // Gravação pelo microfone (2026-08-20, autor: "ligar o mic e gravar
  // um audio na hora com o mic (uma melodia), registrar e
  // transcrever"). MediaRecorder grava no formato que o navegador
  // oferecer (Firefox: ogg/opus, decodifica direto via soundfile;
  // Chrome/Edge: só webm/opus - o CONTAINER webm não é reconhecido por
  // libsndfile mesmo sendo o mesmo codec Opus que funciona dentro de
  // um .ogg, confirmado testando os dois - por isso toda gravação de
  // mic passa por conversão via ffmpeg no servidor antes do pipeline,
  // ver `webapp/app.py`). O blob gravado é injetado no MESMO campo de
  // arquivo do formulário via `DataTransfer` - o resto do fluxo de
  // envio (preview, submit) não muda.
  const micBtn = document.getElementById("mic-btn");
  const micStatus = document.getElementById("mic-status");
  const sourceField = document.getElementById("source-field");
  const micDeviceSelect = document.getElementById("mic-device-select");
  const micMeter = document.getElementById("mic-meter");
  const micMeterFill = document.getElementById("mic-meter-fill");

  if (micBtn) {
    let mediaRecorder = null;
    let recordedChunks = [];
    let stream = null;
    let recording = false;
    let startedAt = 0;
    let timerId = null;
    let audioCtx = null;
    let meterRafId = null;

    // Medidor de nível ao vivo (2026-08-20) - achado real testando com
    // uma interface de áudio USB: sem um jeito de VER o sinal chegando
    // durante a gravação, um áudio mudo só é percebido depois, ao
    // tentar ouvir a prévia. `AnalyserNode` lê o stream bruto (NUNCA
    // conectado a `audioCtx.destination` - conectar geraria eco/
    // realimentação pelos alto-falantes) e atualiza uma barra em
    // tempo real via RMS por frame.
    function startMeter(mediaStream) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const source = audioCtx.createMediaStreamSource(mediaStream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);
      const data = new Uint8Array(analyser.fftSize);
      micMeter.hidden = false;
      const tick = () => {
        analyser.getByteTimeDomainData(data);
        let sumSquares = 0;
        for (let i = 0; i < data.length; i++) {
          const v = (data[i] - 128) / 128;
          sumSquares += v * v;
        }
        const rms = Math.sqrt(sumSquares / data.length);
        const pct = Math.min(100, rms * 300); // escala visual, nao calibrada
        micMeterFill.style.width = `${pct}%`;
        micMeterFill.classList.toggle("clipping", pct > 85);
        meterRafId = requestAnimationFrame(tick);
      };
      tick();
    }

    function stopMeter() {
      if (meterRafId) cancelAnimationFrame(meterRafId);
      meterRafId = null;
      if (audioCtx) { audioCtx.close(); audioCtx = null; }
      micMeter.hidden = true;
      micMeterFill.style.width = "0%";
    }

    // Se o autor trocar por um arquivo de verdade depois de já ter
    // gravado, o formulário volta a tratar como upload comum.
    const clearMicSource = () => { sourceField.value = ""; };
    input.addEventListener("change", clearMicSource);

    const formatElapsed = (ms) => {
      const s = Math.floor(ms / 1000);
      return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    };

    // Descoberta de dispositivo (2026-08-20) - achado real: com uma
    // interface de áudio USB conectada (AudioBox), a gravação saía
    // digitalmente muda mesmo com o hardware confirmado funcionando
    // (o mesmo microfone gravou normalmente no Audacity). O navegador
    // pode abrir um dispositivo de entrada diferente do padrão do
    // sistema (rótulo do dispositivo só fica disponível DEPOIS da
    // primeira concessão de permissão - por isso o <select> começa
    // escondido e só aparece depois da 1ª gravação). Deixa o autor
    // escolher explicitamente em vez de confiar no "padrão" do
    // navegador.
    async function refreshDeviceList(activeDeviceId) {
      if (!navigator.mediaDevices.enumerateDevices) return;
      const devices = await navigator.mediaDevices.enumerateDevices();
      const inputs = devices.filter((d) => d.kind === "audioinput");
      if (inputs.length === 0) return;
      micDeviceSelect.innerHTML = "";
      inputs.forEach((d, i) => {
        const opt = document.createElement("option");
        opt.value = d.deviceId;
        opt.textContent = d.label || tr("audio_input", { number: i + 1 });
        micDeviceSelect.appendChild(opt);
      });
      if (activeDeviceId) micDeviceSelect.value = activeDeviceId;
      micDeviceSelect.hidden = false;
    }

    async function startRecording() {
      // Um clique audível entraria na tomada do microfone.
      document.dispatchEvent(new Event("maravi:stop-metronome"));
      audioPreview.pause();
      audioPreviewArea.hidden = true;
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        micStatus.textContent = tr("mic_unsupported");
        return;
      }
      const chosenDeviceId = micDeviceSelect.hidden ? null : micDeviceSelect.value;
      const constraints = { audio: chosenDeviceId ? { deviceId: { exact: chosenDeviceId } } : true };
      try {
        stream = await navigator.mediaDevices.getUserMedia(constraints);
      } catch (err) {
        micStatus.textContent = tr("mic_denied");
        return;
      }
      const activeLabel = stream.getAudioTracks()[0]?.label || tr("default_device");
      const activeDeviceId = stream.getAudioTracks()[0]?.getSettings().deviceId;
      refreshDeviceList(activeDeviceId);
      startMeter(stream);
      recordedChunks = [];
      const preferredType = ["audio/ogg;codecs=opus", "audio/webm;codecs=opus", "audio/webm"]
        .find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported(t));
      mediaRecorder = preferredType ? new MediaRecorder(stream, { mimeType: preferredType }) : new MediaRecorder(stream);
      mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) recordedChunks.push(e.data); };
      mediaRecorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        stopMeter();
        clearInterval(timerId);
        const mimeType = mediaRecorder.mimeType || "audio/webm";
        const ext = mimeType.includes("ogg") ? "ogg" : "webm";
        const blob = new Blob(recordedChunks, { type: mimeType });
        const file = new File([blob], `gravacao_mic.${ext}`, { type: mimeType });
        const dt = new DataTransfer();
        dt.items.add(file);
        input.files = dt.files;
        audioChannel.value = "mix"; // a gravação de mic não expõe lados estéreo
        sourceField.value = "mic";
        showFile(file);
        micStatus.textContent = tr("mic_recorded", { time: formatElapsed(Date.now() - startedAt) });
      };
      mediaRecorder.start();
      recording = true;
      startedAt = Date.now();
      micBtn.textContent = tr("stop_recording");
      micBtn.classList.add("recording");
      timerId = setInterval(() => {
        micStatus.textContent = tr("mic_recording", { device: activeLabel, time: formatElapsed(Date.now() - startedAt) });
      }, 250);
    }

    function stopRecording() {
      if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop();
      recording = false;
      micBtn.textContent = tr("mic_record");
      micBtn.classList.remove("recording");
    }

    micBtn.addEventListener("click", () => {
      if (!recording) startRecording(); else stopRecording();
    });
  }

  // ===== "Bater ritmo": define o BPM tocando no botão =====
  // Complementa a contagem gravada no próprio take (`tap_count` /
  // `tools/tap_tempo.py`), que só serve pra uma gravação NOVA - autor,
  // 2026-08-31: "isso só serve quando houver uma gravação, não para
  // audio já gravados". Aqui não há análise de áudio nenhuma: o
  // andamento vem dos cliques do próprio usuário, então funciona também
  // com um arquivo já pronto - é só bater junto enquanto escuta a
  // faixa. Preenche o mesmo campo `bpm` que já existia, sem caminho
  // novo no pipeline.
  const tapBtn = document.getElementById("tapBpm");
  const bpmInput = document.getElementById("bpm");
  const tapHint = document.getElementById("tapBpmHint");
  if (tapBtn && bpmInput) {
    let tapTimes = [];
    let resetTimer = null;
    const RESET_MS = 2500; // silêncio longo = recomeçar a contagem

    tapBtn.addEventListener("click", () => {
      const now = performance.now();
      clearTimeout(resetTimer);
      tapTimes.push(now);
      // Só os últimos 8 intervalos - o músico acerta o ritmo depois de
      // algumas batidas, e as primeiras costumam ser as mais tortas.
      if (tapTimes.length > 9) tapTimes = tapTimes.slice(-9);

      if (tapTimes.length >= 2) {
        const intervalos = [];
        for (let i = 1; i < tapTimes.length; i++) intervalos.push(tapTimes[i] - tapTimes[i - 1]);
        // Mediana, não média: uma batida atrasada não estraga o valor.
        const ordenados = [...intervalos].sort((a, b) => a - b);
        const meio = Math.floor(ordenados.length / 2);
        const mediana = ordenados.length % 2 ? ordenados[meio] : (ordenados[meio - 1] + ordenados[meio]) / 2;
        const bpm = 60000 / mediana;
        if (bpm >= 20 && bpm <= 400) {
          bpmInput.value = bpm.toFixed(1);
          const metroBpm = document.getElementById("metro-bpm");
          if (metroBpm && bpm >= 30 && bpm <= 240) {
            metroBpm.value = Math.round(bpm);
            metroBpm.dispatchEvent(new Event("input"));
          }
          tapHint.textContent = tr("tap_count", { count: intervalos.length + 1, bpm: bpm.toFixed(1) });
        } else {
          tapHint.textContent = tr("tap_outside");
        }
      } else {
        tapHint.textContent = tr("tap_continue");
      }

      tapBtn.classList.add("tapping");
      resetTimer = setTimeout(() => {
        tapTimes = [];
        tapBtn.classList.remove("tapping");
        if (bpmInput.value) tapHint.textContent = tr("tap_fixed", { bpm: bpmInput.value });
      }, RESET_MS);
    });
  }

  const form = document.getElementById("form");
  const submitBtn = document.getElementById("submit-btn");
  form.addEventListener("submit", (event) => {
    if (event.defaultPrevented) return; // pré-análise ainda não enviou a partitura
    document.dispatchEvent(new Event("maravi:stop-metronome"));
    submitBtn.disabled = true;
    submitBtn.textContent = tr("transcribing");
  });
})();
