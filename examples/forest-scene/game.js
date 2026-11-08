(() => {
  'use strict';

  const scene = document.querySelector('#scene');
  const detail = document.querySelector('#detail');
  const context = scene.getContext('2d');
  const zoom = detail.getContext('2d');
  const inspect = document.querySelector('#inspect');
  const status = document.querySelector('#status');
  const count = document.querySelector('#count');
  const position = document.querySelector('#position');
  const buttons = [...document.querySelectorAll('button[data-direction]')];
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const baseline = 150;
  const loot = [
    { id: 'acorn', name: '도토리', size: 24, x: 120 },
    { id: 'feather', name: '깃털', size: 32, x: 208 },
    { id: 'compass', name: '나침반', size: 32, x: 300 },
  ];
  const keys = new Set();
  const pointers = new Map();
  let x = 48;
  let facing = 1;
  let walkTime = 0;
  let walking = false;
  let walk;
  let pickup;
  const effects = [];
  let lastTime;
  let scout;
  let background;
  let pivot;
  let ready = false;

  scene.width = 352;
  scene.height = 176;
  detail.width = 240;
  detail.height = 240;
  scene.dataset.ready = 'false';
  context.imageSmoothingEnabled = false;
  zoom.imageSmoothingEnabled = false;

  function sync() {
    const collected = loot.filter(item => item.collected).length;
    if (count.textContent !== `${collected} / 3`) count.textContent = `${collected} / 3`;
    position.textContent = `(${Math.round(x)}, ${baseline})`;
    Object.assign(scene.dataset, {
      x: String(Math.round(x)), y: String(baseline), count: String(collected),
      inspection: String(inspect.checked), facing: facing === 1 ? 'right' : 'left',
    });
    for (const item of loot) {
      document.querySelector(`[data-loot="${item.id}"]`).dataset.collected = String(Boolean(item.collected));
    }
  }

  function clearInput() {
    keys.clear();
    pointers.clear();
    for (const button of buttons) button.dataset.pressed = 'false';
  }

  function image(path, width, height) {
    return new Promise((resolve, reject) => {
      const asset = new Image();
      asset.onload = () => (!width || asset.naturalWidth === width && asset.naturalHeight === height)
        ? resolve(asset) : reject(new Error(`잘못된 이미지 크기: ${path}`));
      asset.onerror = () => reject(new Error(`이미지를 불러오지 못했습니다: ${path}`));
      asset.src = path;
    });
  }

  async function sheet(path, loop) {
    const [metadata, asset] = await Promise.all([
      fetch(`${path}/sheet.json`).then(response => {
        if (!response.ok) throw new Error(`시트 정보를 불러오지 못했습니다: ${path}`);
        return response.json();
      }),
      image(`${path}/sheet.png`),
    ]);
    const pivot = metadata.pivot_px_from_top_left;
    if (metadata.schema_version !== 1 || metadata.loop !== loop ||
        !Array.isArray(pivot) || pivot.length !== 2 || !pivot.every(Number.isInteger) ||
        !Array.isArray(metadata.frames) || !metadata.frames.length ||
        !metadata.frames.every(frame => {
          const rect = frame.rect;
          return rect && [rect.x, rect.y, rect.w, rect.h].every(Number.isInteger) &&
            rect.x >= 0 && rect.y >= 0 && rect.w > 0 && rect.h > 0 &&
            rect.x + rect.w <= asset.naturalWidth && rect.y + rect.h <= asset.naturalHeight &&
            pivot[0] >= 0 && pivot[0] <= rect.w && pivot[1] >= 0 && pivot[1] <= rect.h &&
            Number.isFinite(frame.duration_ms) && frame.duration_ms > 0;
        })) throw new Error(`시트 프레임 또는 피벗 규격을 확인해 주세요: ${path}`);
    return { ...metadata, image: asset, duration: metadata.frames.reduce((sum, frame) => sum + frame.duration_ms, 0) };
  }

  function frameAt(animation, elapsed) {
    let remaining = animation.loop ? elapsed % animation.duration : elapsed;
    for (let index = 0; index < animation.frames.length; index++) {
      remaining -= animation.frames[index].duration_ms;
      if (remaining < 0) return index;
    }
    return animation.frames.length - 1;
  }

  function inspection() {
    const offset = 24;
    const scale = 4;
    zoom.clearRect(0, 0, detail.width, detail.height);
    zoom.fillStyle = '#252b2b';
    zoom.fillRect(0, 0, detail.width, detail.height);
    for (let row = 0; row < 48; row++) {
      for (let column = 0; column < 48; column++) {
        zoom.fillStyle = (row + column) % 2 ? '#424a45' : '#343d38';
        zoom.fillRect(offset + column * scale, offset + row * scale, scale, scale);
      }
    }
    zoom.drawImage(scout, offset, offset, 192, 192);
    zoom.strokeStyle = '#a3ad8955';
    zoom.lineWidth = 1;
    zoom.beginPath();
    for (let pixel = 0; pixel <= 48; pixel++) {
      const value = offset + pixel * scale + 0.5;
      zoom.moveTo(value, offset); zoom.lineTo(value, offset + 192);
      zoom.moveTo(offset, value); zoom.lineTo(offset + 192, value);
    }
    zoom.stroke();
    const px = offset + pivot[0] * scale;
    const py = offset + pivot[1] * scale;
    zoom.fillStyle = '#efbd68';
    zoom.fillRect(offset, py, 192, 1);
    zoom.fillRect(px - 6, py - 1, 13, 3);
    zoom.fillRect(px - 1, py - 6, 3, 13);
  }

  function draw(moving) {
    const walkFrame = moving && !reducedMotion.matches ? frameAt(walk, walkTime) : -1;
    scene.dataset.pose = walkFrame >= 0 ? `walk-${walkFrame}` : 'idle';
    scene.dataset.effects = String(effects.length);
    scene.dataset.effectFrame = effects.length ? String(frameAt(pickup, effects[0].elapsed)) : '';
    context.clearRect(0, 0, 352, 176);
    context.drawImage(background, 0, 0);
    for (const item of loot) {
      if (!item.collected) context.drawImage(item.image, item.x - item.size / 2, baseline - item.size);
    }
    const playerX = Math.round(x);
    const animationPivot = walkFrame >= 0 ? walk.pivot_px_from_top_left : pivot;
    const top = baseline - animationPivot[1];
    context.save();
    context.translate(playerX, top);
    context.scale(facing, 1);
    const left = -animationPivot[0];
    if (walkFrame >= 0) {
      const { x, y, w, h } = walk.frames[walkFrame].rect;
      context.drawImage(walk.image, x, y, w, h, left, 0, w, h);
    } else {
      context.drawImage(scout, left, 0);
    }
    context.restore();
    for (const effect of effects) {
      const { x, y, w, h } = pickup.frames[frameAt(pickup, effect.elapsed)].rect;
      const [px, py] = pickup.pivot_px_from_top_left;
      context.drawImage(pickup.image, x, y, w, h, effect.x - px, effect.y - py, w, h);
    }
    if (inspect.checked) {
      context.strokeStyle = '#f6eed6a0';
      context.lineWidth = 1;
      const spriteLeft = playerX - (facing === 1 ? pivot[0] : 48 - pivot[0]);
      context.strokeRect(spriteLeft + 0.5, top + 0.5, 48, 48);
      context.fillStyle = '#274b45';
      context.fillRect(0, baseline, 352, 1);
      context.fillRect(playerX - 1, baseline - 4, 3, 9);
      context.fillStyle = '#fff1bf';
      context.fillRect(playerX - 3, baseline, 7, 1);
      context.fillRect(playerX, baseline - 3, 1, 7);
    }
  }

  function advance(direction, distance, elapsed = 0) {
    const previous = x;
    facing = direction;
    const leftEdge = direction === 1 ? pivot[0] : 48 - pivot[0];
    x = Math.max(leftEdge, Math.min(352 - (48 - leftEdge), x + direction * distance));
    const moved = x !== previous;
    walkTime = moved && walking ? walkTime + elapsed : 0;
    walking = moved;
    for (const item of loot) {
      if (!item.collected && Math.abs(x - item.x) <= 15) {
        item.collected = true;
        effects.push({ x: item.x, y: baseline - item.size / 2, elapsed: 0 });
        status.textContent = loot.every(entry => entry.collected)
          ? '순찰 완료! 세 가지 물건을 모두 찾았어요.' : `${item.name} 수집 완료.`;
      }
    }
    sync();
    draw(moved);
  }

  function frame(time) {
    const elapsed = lastTime === undefined ? 0 : Math.min((time - lastTime) / 1000, 0.05);
    lastTime = time;
    if (ready) {
      const left = keys.has('arrowleft') || keys.has('a') || [...pointers.values()].includes('left');
      const right = keys.has('arrowright') || keys.has('d') || [...pointers.values()].includes('right');
      const direction = Number(right) - Number(left);
      const hadEffects = effects.length > 0;
      for (let index = effects.length - 1; index >= 0; index--) {
        effects[index].elapsed += elapsed * 1000;
        if (effects[index].elapsed >= pickup.duration) effects.splice(index, 1);
      }
      if (direction) advance(direction, elapsed * 54, elapsed * 1000);
      else {
        walking = false;
        walkTime = 0;
        if (scene.dataset.pose !== 'idle' || hadEffects) draw(false);
      }
    }
    requestAnimationFrame(frame);
  }

  function movementKey(event) {
    if (event.code === 'KeyA') return 'a';
    if (event.code === 'KeyD') return 'd';
    return event.key.toLowerCase();
  }

  window.addEventListener('keydown', event => {
    const key = movementKey(event);
    if (!['arrowleft', 'arrowright', 'a', 'd'].includes(key) || event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.target?.matches('textarea, select, [contenteditable="true"], input:not([type="checkbox"]):not([type="radio"])')) return;
    event.preventDefault();
    keys.add(key);
  });
  window.addEventListener('keyup', event => keys.delete(movementKey(event)));
  window.addEventListener('blur', clearInput);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { clearInput(); lastTime = undefined; }
  });
  for (const button of buttons) {
    button.addEventListener('pointerdown', event => {
      if (!ready || event.button !== 0) return;
      button.focus({ preventScroll: true });
      button.setPointerCapture(event.pointerId);
      pointers.set(event.pointerId, button.dataset.direction);
      advance(button.dataset.direction === 'left' ? -1 : 1, 3);
      button.dataset.pressed = 'true';
    });
    const release = event => {
      pointers.delete(event.pointerId);
      button.dataset.pressed = 'false';
    };
    button.addEventListener('pointerup', release);
    button.addEventListener('pointercancel', release);
    button.addEventListener('lostpointercapture', release);
    button.addEventListener('keydown', event => {
      if (event.key === ' ' || event.key === 'Enter') {
        event.preventDefault();
        keys.add(button.dataset.direction === 'left' ? 'arrowleft' : 'arrowright');
        button.dataset.pressed = 'true';
      }
    });
    button.addEventListener('keyup', event => {
      if (event.key === ' ' || event.key === 'Enter') clearInput();
    });
    button.addEventListener('blur', clearInput);
  }
  inspect.addEventListener('change', () => {
    sync();
    if (ready) { inspection(); draw(false); }
  });
  document.querySelector('#reset').addEventListener('click', () => {
    clearInput();
    x = 48; facing = 1; walkTime = 0; walking = false;
    effects.length = 0;
    for (const item of loot) item.collected = false;
    sync();
    if (ready) {
      status.textContent = '다시 출발해요. 숲속 보물 세 가지를 찾아보세요.';
      draw(false);
    }
  });

  sync();
  Promise.all([
    fetch('../codex-scout-styled/metadata.json').then(response => {
      if (!response.ok) throw new Error('캐릭터 정보를 불러오지 못했습니다.');
      return response.json();
    }),
    image('../codex-scout-styled/asset.png', 48, 48),
    image('./background.png', 352, 176),
    sheet('../production/walk/result', true),
    sheet('../production/effects/pickup/result', false),
    ...loot.map(item => image(`../woodland/sprites/${item.id}.png`, item.size, item.size)),
  ]).then(([metadata, character, scenery, walkSheet, pickupSheet, ...items]) => {
    pivot = metadata.import?.pivot_px_from_top_left;
    if (metadata.import?.filter !== 'nearest' || !Array.isArray(pivot) || pivot.length !== 2 ||
        !pivot.every(value => Number.isInteger(value) && value >= 0 && value <= 48)) {
      throw new Error('캐릭터 피벗 또는 필터 규격을 확인해 주세요.');
    }
    scout = character; background = scenery;
    walk = walkSheet; pickup = pickupSheet;
    const pivotLabel = document.querySelector('#pivot');
    const sizeLabel = document.querySelector('#native-size');
    if (pivotLabel) pivotLabel.textContent = `(${pivot[0]}, ${pivot[1]})`;
    if (sizeLabel) sizeLabel.textContent = `${scout.naturalWidth} × ${scout.naturalHeight} px`;
    loot.forEach((item, index) => { item.image = items[index]; });
    ready = true;
    scene.dataset.ready = 'true';
    inspection(); draw(false);
    status.textContent = '준비됐어요. 방향키 또는 A, D로 숲을 걸어보세요.';
  }).catch(error => {
    clearInput();
    scene.dataset.error = 'true';
    status.textContent = `${error.message} 로컬 서버에서 페이지를 다시 열어 주세요.`;
  });
  requestAnimationFrame(frame);
})();
