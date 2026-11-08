import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const source = await readFile(new URL('./game.js', import.meta.url), 'utf8');

async function game({ invalidMetadata = false, failedImage = false, reduced = false, invalidSheet = false, failedSheet = false } = {}) {
  const drawings = [];
  const context = new Proxy({}, { get: (_, name) => (...args) => drawings.push([name, ...args]) });
  class Element {
    dataset = {};
    checked = false;
    textContent = '';
    events = new Map();
    getContext() { return context; }
    addEventListener(type, callback) {
      this.events.set(type, [...(this.events.get(type) ?? []), callback]);
    }
    emit(type, values = {}) {
      const event = { target: this, preventDefault() {}, ...values };
      for (const callback of this.events.get(type) ?? []) callback(event);
    }
    matches() { return false; }
    setPointerCapture() {}
    focus() {}
  }
  const elements = new Map();
  const element = selector => {
    if (!elements.has(selector)) elements.set(selector, new Element());
    return elements.get(selector);
  };
  const buttons = ['left', 'right'].map(direction => {
    const button = new Element(); button.dataset.direction = direction; return button;
  });
  const window = new Element();
  const document = new Element();
  document.querySelector = element;
  document.querySelectorAll = () => buttons;
  let scheduled;
  let time = 0;
  class Image {
    set src(value) {
      this.path = value;
      this.naturalWidth = value.includes('/walk/') ? 144 : value.includes('/pickup/') ? 128 : value.includes('background') ? 352 : value.includes('asset') ? 48 : value.includes('acorn') ? 24 : 32;
      this.naturalHeight = value.includes('/walk/') ? 48 : value.includes('/pickup/') ? 32 : value.includes('background') ? 176 : this.naturalWidth;
      queueMicrotask(() => failedImage ? this.onerror() : this.onload());
    }
  }
  vm.runInNewContext(source, {
    document, window, Image,
    matchMedia: () => ({ matches: reduced }),
    fetch: async path => ({ ok: !(failedSheet && path.includes('sheet.json')), json: async () => {
      if (path.includes('sheet.json')) {
        const walk = path.includes('/walk/');
        const size = walk ? 48 : 32;
        return {
          schema_version: 1, loop: walk, pivot_px_from_top_left: walk ? [24, 46] : [16, 16],
          frames: (walk ? [100, 200, 150] : [50, 100, 150, 200]).map((duration_ms, index) => ({
            rect: { x: index * size, y: 0, w: invalidSheet ? 9999 : size, h: size }, duration_ms,
          })),
        };
      }
      return { import: { filter: invalidMetadata ? 'linear' : 'nearest', pivot_px_from_top_left: [24, 46] } };
    } }),
    requestAnimationFrame: callback => { scheduled = callback; },
  });
  await new Promise(resolve => setImmediate(resolve));
  const tick = (frames = 1) => {
    for (let frame = 0; frame < frames; frame++) { time += 50; scheduled(time); }
  };
  tick();
  return { element, buttons, window, tick, drawings };
}

test('native asset loading, movement, unique collection, clamps, and replay', async () => {
  const { element, window, tick } = await game();
  const scene = element('#scene');
  assert.equal(scene.dataset.ready, 'true');
  assert.equal(element('#pivot').textContent, '(24, 46)');
  assert.equal(element('#native-size').textContent, '48 × 48 px');
  assert.equal(scene.dataset.y, '150');
  window.emit('keydown', { key: 'd' });
  tick(35);
  assert.equal(scene.dataset.count, '1');
  assert.equal(element('[data-loot="acorn"]').dataset.collected, 'true');
  tick(100);
  assert.equal(scene.dataset.x, '328');
  assert.equal(scene.dataset.count, '3');
  assert.match(element('#status').textContent, /모두/);
  window.emit('keydown', { key: 'a' });
  window.emit('keyup', { key: 'd' });
  tick(140);
  assert.equal(scene.dataset.x, '24');
  assert.equal(scene.dataset.facing, 'left');
  assert.equal(scene.dataset.count, '3');
  element('#reset').emit('click');
  tick();
  assert.equal(scene.dataset.x, '48');
  assert.equal(scene.dataset.count, '0');
  assert.equal(scene.dataset.pose, 'idle');
});

test('pointer cancellation, blur, and inspector state', async () => {
  const { element, buttons, window, tick } = await game();
  buttons[1].emit('pointerdown', { button: 0, pointerId: 1 });
  tick(4);
  assert.ok(Number(element('#scene').dataset.x) > 48);
  buttons[1].emit('pointercancel', { pointerId: 1 });
  const stopped = element('#scene').dataset.x;
  tick(4);
  assert.equal(element('#scene').dataset.x, stopped);
  window.emit('keydown', { key: 'ArrowRight' });
  tick(4);
  window.emit('blur');
  const blurred = element('#scene').dataset.x;
  tick(4);
  assert.equal(element('#scene').dataset.x, blurred);
  element('#inspect').checked = true;
  element('#inspect').emit('change');
  assert.equal(element('#scene').dataset.inspection, 'true');
  assert.equal(element('#detail').width, 240);
});

test('reduced motion keeps the source pose while allowing movement', async () => {
  const { element, window, tick } = await game({ reduced: true });
  window.emit('keydown', { key: 'd' });
  tick(3);
  assert.ok(Number(element('#scene').dataset.x) > 48);
  assert.equal(element('#scene').dataset.pose, 'idle');
});

for (const options of [{ invalidMetadata: true }, { failedImage: true }, { invalidSheet: true }, { failedSheet: true }]) {
  test(`load failure is announced and never starts gameplay: ${JSON.stringify(options)}`, async () => {
    const { element, window, tick } = await game(options);
    assert.equal(element('#scene').dataset.ready, 'false');
    assert.equal(element('#scene').dataset.error, 'true');
    assert.match(element('#status').textContent, /로컬 서버/);
    window.emit('keydown', { key: 'd' }); tick(10);
    assert.equal(element('#scene').dataset.x, '48');
  });
}


test('walk uses complete sheet frames, metadata timing, contact start, mirroring, and idle source', async () => {
  const { element, window, tick, drawings } = await game();
  const scene = element('#scene');
  window.emit('keydown', { key: 'd' });
  tick();
  assert.equal(scene.dataset.pose, 'walk-0');
  tick();
  assert.equal(scene.dataset.pose, 'walk-0');
  tick();
  assert.equal(scene.dataset.pose, 'walk-1');
  tick(3);
  assert.equal(scene.dataset.pose, 'walk-1');
  tick();
  assert.equal(scene.dataset.pose, 'walk-2');
  tick(3);
  assert.equal(scene.dataset.pose, 'walk-0');
  const walkDraws = drawings.filter(([name, asset]) => name === 'drawImage' && asset?.path?.includes('/walk/'));
  assert.ok(walkDraws.some(draw => JSON.stringify(draw.slice(2)) === JSON.stringify([48, 0, 48, 48, -24, 0, 48, 48])));
  window.emit('keyup', { key: 'd' });
  tick();
  assert.equal(scene.dataset.pose, 'idle');
  window.emit('keydown', { key: 'a' });
  tick();
  assert.equal(scene.dataset.pose, 'walk-0');
  assert.equal(scene.dataset.y, '150');
  assert.ok(drawings.some(draw => draw[0] === 'scale' && draw[1] === -1 && draw[2] === 1));
  assert.ok(drawings.some(draw => draw[0] === 'translate' && draw[2] === 104));
  assert.ok(drawings.some(([name, asset, ...args]) => name === 'drawImage' && asset?.path?.endsWith('/asset.png') && args.length === 2));
});

test('pickup uses full rect and item center, continues while stopped, completes once, and reset clears it', async () => {
  const { element, window, tick, drawings } = await game();
  const scene = element('#scene');
  window.emit('keydown', { key: 'd' });
  tick(22);
  assert.equal(scene.dataset.effects, '1');
  assert.equal(scene.dataset.effectFrame, '0');
  assert.ok(drawings.some(([name, asset, ...args]) => name === 'drawImage' && asset?.path?.includes('/pickup/') &&
    JSON.stringify(args) === JSON.stringify([0, 0, 32, 32, 104, 122, 32, 32])));
  window.emit('keyup', { key: 'd' });
  const stopped = scene.dataset.x;
  tick();
  assert.equal(scene.dataset.x, stopped);
  assert.equal(scene.dataset.pose, 'idle');
  assert.equal(scene.dataset.effectFrame, '1');
  tick(2);
  assert.equal(scene.dataset.effectFrame, '2');
  tick(7);
  assert.equal(scene.dataset.effects, '0');
  assert.equal(scene.dataset.effectFrame, '');
  tick(10);
  assert.equal(scene.dataset.effects, '0');
  element('#reset').emit('click');
  window.emit('keydown', { key: 'd' });
  tick(22);
  assert.equal(scene.dataset.effects, '1');
  element('#reset').emit('click');
  assert.equal(scene.dataset.effects, '0');
  assert.equal(scene.dataset.count, '0');
});
