"use strict";
(() => {
  const data = JSON.parse(document.querySelector('#player-data').textContent);
  const config = data.config;
  const text = config.text;
  const canvas = document.querySelector('canvas');
  const status = document.querySelector('#status');
  const pause = document.querySelector('#pause');
  const replay = document.querySelector('#replay');
  const decode = value => Uint8Array.from(atob(value), char => char.charCodeAt(0));
  const runtime = document.createElement('script');
  runtime.textContent = new TextDecoder().decode(decode(data.runtime));
  document.head.append(runtime);
  rive.RuntimeLoader.setWasmBinary(decode(data.wasm).buffer);
  rive.RuntimeLoader.setWasmUrl(`data:application/wasm;base64,${data.wasm}`);
  rive.RuntimeLoader.setWasmFallbackUrl(`data:application/wasm;base64,${data.fallback}`);
  rive.RuntimeLoader.setWasmThreadsUrl(null);
  document.querySelector('#download').href = `data:application/octet-stream;base64,${data.riv}`;
  let input;
  let selected = 0;
  let playback = 'loading';
  let elapsed = 0;
  let started = 0;
  let ticker;
  const buttons = config.states.map((state, index) => {
    const button = document.createElement('button');
    button.textContent = state.label;
    button.disabled = true;
    button.dataset.action = String(index);
    button.setAttribute('aria-pressed', String(index === selected));
    button.addEventListener('click', () => restart(index));
    document.querySelector('#actions').append(button);
    return button;
  });
  function update() {
    const state = config.states[selected];
    status.textContent = `${state.label} · ${text[playback]}`;
    canvas.setAttribute('aria-label', `${config.title} · ${state.label}`);
    pause.textContent = playback === 'playing' ? text.pause : text.resume;
    pause.disabled = playback === 'complete';
    buttons.forEach((button, index) => button.setAttribute('aria-pressed', String(index === selected)));
  }
  function fail() {
    cancelAnimationFrame(ticker);
    playback = 'error';
    status.textContent = text.error;
    document.querySelectorAll('button').forEach(button => { button.disabled = true; });
    if (player) player.pause();
  }
  function connect() {
    input = player.stateMachineInputs(config.state_machine).find(item => item.name === config.number_input);
    if (!input || input.type !== rive.StateMachineInputType.Number) {
      fail();
      return false;
    }
    input.value = config.states[selected].value;
    return true;
  }
  function resize() {
    const available = canvas.parentElement.clientWidth;
    const scale = Math.max(1, Math.floor(Math.min(available, 640) / config.size[0]));
    // shortcut: canvases wider than the viewport scroll at 1x to preserve native pixels.
    canvas.style.width = `${config.size[0] * scale}px`;
    canvas.style.height = `${config.size[1] * scale}px`;
  }
  function tick(now) {
    const state = config.states[selected];
    if (playback !== 'playing' || state.loop) return;
    if (elapsed + now - started >= state.duration_ms) {
      player.pause(config.state_machine);
      playback = 'complete';
      update();
      return;
    }
    ticker = requestAnimationFrame(tick);
  }
  function play() {
    playback = 'playing';
    started = performance.now();
    player.play(config.state_machine);
    ticker = requestAnimationFrame(tick);
    update();
  }
  function restart(index) {
    cancelAnimationFrame(ticker);
    selected = index;
    elapsed = 0;
    player.reset({artboard: config.artboard, stateMachines: config.state_machine, autoplay: false});
    if (connect()) play();
  }
  let player;
  try {
    player = new rive.Rive({
      buffer: decode(data.riv).buffer,
      canvas,
      artboard: config.artboard,
      stateMachines: config.state_machine,
      autoplay: false,
      enableRiveAssetCDN: false,
      layout: new rive.Layout({fit: rive.Fit.Contain, alignment: rive.Alignment.Center}),
      onLoad() {
        if (!connect()) return;
        [canvas.width, canvas.height] = config.size;
        player.resizeToCanvas();
        resize();
        document.querySelectorAll('button').forEach(button => { button.disabled = false; });
        if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
          playback = 'paused';
          update();
        } else play();
      },
      onLoadError: fail,
    });
  } catch (error) { fail(); }
  pause.addEventListener('click', () => {
    if (playback === 'playing') {
      elapsed += performance.now() - started;
      cancelAnimationFrame(ticker);
      player.pause(config.state_machine);
      playback = 'paused';
      update();
    } else if (playback === 'paused') play();
  });
  replay.addEventListener('click', () => restart(selected));
  new ResizeObserver(resize).observe(canvas.parentElement);
  window.addEventListener('pagehide', () => {
    cancelAnimationFrame(ticker);
    if (player) player.cleanup();
  }, {once: true});
})();
