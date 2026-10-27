const assert = require('node:assert/strict');
const path = require('node:path');

class Element {
  constructor(value = '') {
    this.value = value;
    this.textContent = '';
    this.handlers = new Map();
    this.attributes = new Map();
  }
  addEventListener(type, fn) { this.handlers.set(type, fn); }
  dispatchEvent(event) { this.handlers.get(event.type)?.(event); }
  setAttribute(name, value) { this.attributes.set(name, value); }
}

const elements = Object.fromEntries([
  ['metro-bpm', '100'], ['metro-pulse', '1'], ['metro-meter', '4'],
  ['metro-volume', '0.08'], ['metro-start', ''], ['metro-use', ''],
  ['metro-status', ''], ['bpm', ''], ['metro-minus', ''], ['metro-plus', ''],
].map(([id, value]) => [id, new Element(value)]));
elements['ui-strings-data'] = new Element();
elements['ui-strings-data'].textContent = JSON.stringify({
  metro_label: '{bpm} BPM · {beats} pulsos', metro_stopped: 'parado',
  metro_playing: 'tocando', metro_applied: '{label} · aplicado',
  metro_outside: 'fora da faixa', listen_pulses: 'Ouvir pulsos',
  stop_pulses: 'Parar pulsos',
});
const document = {
  hidden: false,
  handlers: new Map(),
  getElementById(id) { return elements[id]; },
  addEventListener(type, fn) { this.handlers.set(type, fn); },
  dispatchEvent(event) { this.handlers.get(event.type)?.(event); },
};

const clicks = [];
let intervalCleared = false;
let intervalCallback = null;
let delayedResume = null;
const audioParam = {
  setValueAtTime() {}, exponentialRampToValueAtTime() {}, setTargetAtTime() {},
};
class FakeContext {
  constructor() { this.currentTime = 1; this.destination = {}; this.closed = false; FakeContext.last = this; }
  resume() { return delayedResume || Promise.resolve(); }
  close() { this.closed = true; return Promise.resolve(); }
  createGain() { return { gain: { ...audioParam }, connect() {}, disconnect() {} }; }
  createOscillator() {
    const click = { frequency: null, at: null };
    return {
      frequency: { ...audioParam, setValueAtTime(value) { click.frequency = value; } },
      connect() {}, disconnect() {},
      start(at) { click.at = at; clicks.push(click); }, stop() {},
    };
  }
}

global.Event = class Event { constructor(type) { this.type = type; } };
global.window = {
  document,
  AudioContext: FakeContext,
  setInterval(fn) { intervalCallback = fn; return 1; },
  clearInterval() { intervalCleared = true; intervalCallback = null; },
  addEventListener() {},
};

const { audibleBpm } = require(path.join(__dirname, '..', 'webapp', 'static', 'metronome.js'));
assert.equal(audibleBpm(100, 0.5), 50);
assert.equal(audibleBpm(100, 2), 200);
assert.equal(audibleBpm(400, 1), null);

async function main() {
  elements['metro-pulse'].value = '2';
  elements['metro-pulse'].dispatchEvent(new Event('input'));
  assert.equal(elements['bpm'].value, '');  // ouvir não fixa a transcrição
  elements['metro-use'].dispatchEvent(new Event('click'));
  assert.equal(elements['bpm'].value, '200.0');
  elements['metro-plus'].dispatchEvent({ type: 'click', shiftKey: false });
  assert.equal(elements['metro-bpm'].value, 101);
  elements['metro-bpm'].value = 240;
  elements['metro-use'].dispatchEvent(new Event('click'));
  assert.equal(elements['bpm'].value, '200.0');  // 480 BPM é só para escuta
  elements['metro-bpm'].value = 101;
  elements['metro-start'].dispatchEvent(new Event('click'));
  await new Promise(setImmediate);
  assert.equal(elements['metro-start'].attributes.get('aria-pressed'), 'true');
  assert.equal(clicks.length, 1);
  assert.equal(clicks[0].frequency, 1180); // primeiro pulso acentuado
  FakeContext.last.currentTime = 1.27;
  intervalCallback();
  assert.equal(clicks[1].frequency, 820); // próximo pulso sem acento

  // Ao trocar de um andamento lento para rápido, não esperar pelo
  // intervalo antigo de dois segundos antes de ouvir o novo pulso.
  elements['metro-pulse'].value = '1';
  elements['metro-bpm'].value = 30;
  elements['metro-bpm'].dispatchEvent(new Event('input'));
  FakeContext.last.currentTime = 1.38;
  intervalCallback();
  const beforeChange = clicks.length;
  elements['metro-bpm'].value = 120;
  elements['metro-bpm'].dispatchEvent(new Event('input'));
  FakeContext.last.currentTime = 1.50;
  intervalCallback();
  assert.equal(clicks.length, beforeChange + 1);
  assert.equal(clicks.at(-1).frequency, 1180);
  assert.ok(clicks.at(-1).at < 1.60);
  assert.ok(clicks.at(-1).at - clicks.at(-2).at >= 0.119);

  document.dispatchEvent(new Event('maravi:stop-metronome'));
  assert.equal(elements['metro-start'].attributes.get('aria-pressed'), 'false');
  assert.ok(intervalCleared);
  assert.equal(FakeContext.last.closed, true);

  // Interromper enquanto AudioContext.resume() ainda não concluiu não pode
  // reativar o clique nem deixar um timer órfão após a resolução tardia.
  let finishResume;
  delayedResume = new Promise((resolve) => { finishResume = resolve; });
  elements['metro-start'].dispatchEvent(new Event('click'));
  const pendingContext = FakeContext.last;
  assert.equal(elements['metro-start'].disabled, true);
  document.dispatchEvent(new Event('maravi:stop-metronome'));
  assert.equal(elements['metro-start'].disabled, false);
  finishResume();
  await new Promise(setImmediate);
  assert.equal(pendingContext.closed, true);
  assert.equal(intervalCallback, null);
  assert.equal(elements['metro-start'].attributes.get('aria-pressed'), 'false');
  console.log('Metrônomo: pulso/acento, mudança de BPM, aplicação explícita e parada durante início OK');
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
