/* Metrônomo local de escuta. Não grava áudio nem altera BPM da transcrição
   até o músico acionar explicitamente "Usar pulso ouvido". */
(function (root) {
  "use strict";

  function audibleBpm(baseBpm, pulseFactor) {
    const base = Number(baseBpm);
    const factor = Number(pulseFactor);
    if (!Number.isFinite(base) || base < 30 || base > 240 ||
        ![0.5, 1, 2].includes(factor)) return null;
    return base * factor;
  }

  // Permite testar os cálculos sem abrir áudio ou navegador.
  if (typeof module !== "undefined" && module.exports) module.exports = { audibleBpm };
  if (!root.document) return;

  const doc = root.document;
  const uiText = JSON.parse(doc.getElementById("ui-strings-data")?.textContent || "{}");
  const tr = (key, values = {}) => {
    const phrase = uiText[key];
    if (typeof phrase !== "string") throw new Error(`Missing UI text: ${key}`);
    return phrase.replace(/\{([a-z]+)\}/g, (_match, name) => String(values[name] ?? ""));
  };
  const bpm = doc.getElementById("metro-bpm");
  const pulse = doc.getElementById("metro-pulse");
  const meter = doc.getElementById("metro-meter");
  const volume = doc.getElementById("metro-volume");
  const startButton = doc.getElementById("metro-start");
  const useButton = doc.getElementById("metro-use");
  const status = doc.getElementById("metro-status");
  const transcriptionBpm = doc.getElementById("bpm");
  if (!bpm || !pulse || !meter || !volume || !startButton || !useButton || !status || !transcriptionBpm) return;

  let context = null;
  let output = null;
  let timer = null;
  let nextClickTime = 0;
  let lastScheduledClickTime = -Infinity;
  let pulseIndex = 0;
  let startGeneration = 0;

  function label() {
    const heard = audibleBpm(bpm.value, pulse.value);
    if (heard === null) return tr("metro_bad_base");
    return tr("metro_label", { bpm: heard.toFixed(1), beats: meter.value });
  }

  function updateStatus(message) {
    status.textContent = message || `${label()} · ${tr(context ? "metro_playing" : "metro_stopped")}`;
  }

  function stop() {
    startGeneration += 1;
    if (timer !== null) root.clearInterval(timer);
    timer = null;
    if (output && context) output.gain.setValueAtTime(0, context.currentTime);
    if (context) context.close().catch(() => {});
    context = null;
    output = null;
    pulseIndex = 0;
    lastScheduledClickTime = -Infinity;
    startButton.disabled = false;
    startButton.textContent = tr("listen_pulses");
    startButton.setAttribute("aria-pressed", "false");
    updateStatus();
  }

  function scheduleClick(at, accented) {
    const oscillator = context.createOscillator();
    const envelope = context.createGain();
    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(accented ? 1180 : 820, at);
    envelope.gain.setValueAtTime(0.0001, at);
    envelope.gain.exponentialRampToValueAtTime(accented ? 0.6 : 0.35, at + 0.002);
    envelope.gain.exponentialRampToValueAtTime(0.0001, at + 0.065);
    oscillator.connect(envelope);
    envelope.connect(output);
    oscillator.start(at);
    oscillator.stop(at + 0.07);
    lastScheduledClickTime = at;
    oscillator.onended = () => { oscillator.disconnect(); envelope.disconnect(); };
  }

  function schedule() {
    if (!context) return;
    const heard = audibleBpm(bpm.value, pulse.value);
    if (heard === null) { stop(); updateStatus(tr("metro_invalid")); return; }
    const now = context.currentTime;
    // Após suspensão do navegador, abandona cliques atrasados; não dispara
    // um lote de pulsos acumulados ao voltar à aba.
    if (nextClickTime < now - 0.1) nextClickTime = now + 0.03;
    const beatsPerGroup = Number(meter.value);
    let scheduled = 0;
    while (nextClickTime < now + 0.09 && scheduled < 4) {
      scheduleClick(nextClickTime, pulseIndex === 0);
      pulseIndex = (pulseIndex + 1) % beatsPerGroup;
      nextClickTime += 60 / heard;
      scheduled += 1;
    }
  }

  async function start() {
    const heard = audibleBpm(bpm.value, pulse.value);
    if (heard === null) { updateStatus(tr("metro_base_range")); return; }
    const AudioContextClass = root.AudioContext || root.webkitAudioContext;
    if (!AudioContextClass) { updateStatus(tr("metro_unavailable")); return; }
    startButton.disabled = true;
    const generation = ++startGeneration;
    try {
      const newContext = new AudioContextClass();
      context = newContext;
      await newContext.resume();
      // Gravação, envio ou saída da página podem parar o metrônomo
      // enquanto o navegador ainda aguarda a ativação do áudio.
      if (generation !== startGeneration || context !== newContext) return;
      output = context.createGain();
      output.gain.value = Number(volume.value);
      output.connect(context.destination);
      pulseIndex = 0;
      lastScheduledClickTime = -Infinity;
      nextClickTime = context.currentTime + 0.04;
      schedule();
      timer = root.setInterval(schedule, 25);
      startButton.textContent = tr("stop_pulses");
      startButton.setAttribute("aria-pressed", "true");
      updateStatus();
    } catch (_error) {
      if (generation === startGeneration) {
        stop();
        updateStatus(tr("metro_start_failed"));
      }
    } finally {
      if (generation === startGeneration) startButton.disabled = false;
    }
  }

  function tempoChanged() {
    if (context) {
      // O próximo pulso ainda não agendado segue o novo andamento, sem
      // esperar até dois segundos pelo intervalo antigo de 30 BPM.
      // Um clique já entregue ao Web Audio não pode ser cancelado aqui;
      // evite que o novo pulso fique colado nele.
      nextClickTime = Math.max(context.currentTime + 0.12,
                               lastScheduledClickTime + 0.12);
      pulseIndex = 0;
    }
    updateStatus();
  }

  startButton.addEventListener("click", () => { if (context) stop(); else start(); });
  doc.getElementById("metro-minus").addEventListener("click", (event) => {
    bpm.value = Math.max(30, Math.min(240, (Number(bpm.value) || 100) - (event.shiftKey ? 5 : 1)));
    tempoChanged();
  });
  doc.getElementById("metro-plus").addEventListener("click", (event) => {
    bpm.value = Math.max(30, Math.min(240, (Number(bpm.value) || 100) + (event.shiftKey ? 5 : 1)));
    tempoChanged();
  });
  [bpm, pulse, meter].forEach((control) => control.addEventListener("input", () => {
    if (control === meter) { pulseIndex = 0; updateStatus(); }
    else tempoChanged();
  }));
  volume.addEventListener("input", () => {
    if (output && context) output.gain.setTargetAtTime(Number(volume.value), context.currentTime, 0.01);
  });
  useButton.addEventListener("click", () => {
    const heard = audibleBpm(bpm.value, pulse.value);
    if (heard === null) { updateStatus(tr("metro_apply_first")); return; }
    if (heard < 20 || heard > 400) {
      updateStatus(tr("metro_outside"));
      return;
    }
    transcriptionBpm.value = heard.toFixed(1);
    transcriptionBpm.dispatchEvent(new Event("input"));
    updateStatus(tr("metro_applied", { label: label() }));
  });
  doc.addEventListener("maravi:stop-metronome", stop);
  doc.addEventListener("visibilitychange", () => { if (doc.hidden) stop(); });
  root.addEventListener("pagehide", stop);
  updateStatus();
})(typeof window !== "undefined" ? window : globalThis);
