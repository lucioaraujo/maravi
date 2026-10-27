// Contrato mínimo do formulário sem navegador ou processamento de áudio.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function element() {
  return {
    value: '', files: [], hidden: false, disabled: false, textContent: '',
    listeners: new Map(),
    classList: { add() {}, remove() {} },
    addEventListener(type, listener) {
      const callbacks = this.listeners.get(type) || [];
      callbacks.push(listener);
      this.listeners.set(type, callbacks);
    },
    dispatch(type, event = {}) {
      for (const callback of this.listeners.get(type) || []) callback(event);
      return event;
    },
    dispatchEvent(event) { return this.dispatch(event.type, event); },
    scrollIntoView() {},
  };
}

async function main() {
  const nodes = new Map();
  const get = (id) => {
    if (!nodes.has(id)) nodes.set(id, element());
    return nodes.get(id);
  };
  get('ui-strings-data').textContent = JSON.stringify({
    file_selected: 'Arquivo selecionado', bad_format: 'Formato não aceito',
    channel_mix: 'mistura', pulse_candidate: 'pulso {bpm} BPM',
    pulse_check: '', key_candidate: 'tom {key}', key_ambiguous: 'ambíguo',
    key_alternative: '; alternativa {key}',
    analysis_summary: '{duration}s {channels} {sample}s {channel} {bpm}{caution} {key}',
    review_submit: 'Transcrever novamente', analyzing: 'Analisando',
    transcribing: 'Transcrevendo',
  });
  get('audio-input').files = [{ name: 'ensaio.wav' }];
  get('audio-input').accept = '.mp3,.wav,.flac,.ogg,.aif,.aiff';
  get('audio_channel').value = 'mix';
  get('use-analysis-bpm').hidden = true;
  get('use-analysis-key').hidden = true;
  const report = {
    duration_seconds: 145.1, channels: 2, sample_seconds: 20,
    selected_channel: 'mix', bpm: 215.3, tempo_regularity: 0.06,
    key_name: 'Sol♯ menor', key_runner_up: 'Lá♭ maior', key_ambiguous: true,
  };
  let calls = 0;
  const requestUrls = [];
  const context = {
    document: {
      documentElement: { lang: 'pt-BR' },
      getElementById: (id) => id === 'genre-suggestions-data' ? null : get(id),
      dispatchEvent() {},
    },
    window: { addEventListener() {} },
    URL: { createObjectURL: () => 'blob:test', revokeObjectURL() {} },
    DataTransfer: class {
      constructor() {
        this.files = [];
        this.items = { add: (file) => this.files.push(file) };
      }
    },
    FormData: class { append() {} },
    Event: class { constructor(type) { this.type = type; } },
    fetch: async (url) => { calls += 1; requestUrls.push(url); return { ok: true, json: async () => report }; },
  };
  const script = fs.readFileSync(path.join(__dirname, '../webapp/static/app.js'), 'utf8');
  vm.runInNewContext(script, context, { filename: 'app.js' });

  const drop = (files) => get('dropzone').dispatch('drop', {
    dataTransfer: { files }, preventDefault() {},
  });
  drop([{ name: 'novo.mp3' }]);
  assert.equal(get('audio-input').files[0].name, 'novo.mp3');
  assert.equal(get('filename').textContent, 'novo.mp3');
  drop([{ name: 'invalido.txt' }]);
  assert.match(get('dropzone-text').textContent, /Formato não aceito/);
  assert.equal(get('audio-input').files[0].name, 'novo.mp3');

  const submit = () => {
    const event = { defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } };
    get('form').dispatch('submit', event);
    return event;
  };

  assert.equal(submit().defaultPrevented, true);
  await new Promise(setImmediate);
  assert.equal(calls, 1);
  assert.equal(requestUrls[0], '/analisar-audio?lang=pt');
  assert.equal(get('submit-btn').disabled, false);
  assert.equal(get('use-analysis-bpm').hidden, false);
  assert.equal(get('use-analysis-key').hidden, true);
  assert.match(get('audio-analysis-report').textContent, /ambíguo/);
  assert.match(get('audio-analysis-report').textContent, /Transcrever novamente/);

  report.key_ambiguous = false;
  context.document.documentElement.lang = 'fr';
  get('analyze-audio').dispatch('click');
  await new Promise(setImmediate);
  assert.equal(requestUrls[1], '/analisar-audio?lang=fr');
  assert.equal(get('use-analysis-key').hidden, false);
  get('use-analysis-key').onclick();
  assert.equal(get('key').value, 'Sol♯ menor');

  assert.equal(submit().defaultPrevented, false);
  assert.equal(calls, 2);
  assert.equal(get('submit-btn').disabled, true);
  assert.match(get('submit-btn').textContent, /Transcrevendo/);
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
