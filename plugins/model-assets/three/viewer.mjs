import { THREE, loadModel, validateReceipt } from './loader.mjs';

const report = document.querySelector('#report');
const canvas = document.querySelector('#view');
window.__MODEL_INSPECTION__ = { passed: false, state: 'loading' };
try {
  const [modelResponse, receiptResponse] = await Promise.all([fetch('/model.web.glb'), fetch('/model.web.glb.webstage.json')]);
  if (!modelResponse.ok || !receiptResponse.ok) throw new Error('Unable to fetch model or receipt');
  const buffer = await modelResponse.arrayBuffer();
  const receipt = await receiptResponse.json();
  validateReceipt(receipt, buffer.byteLength);
  const { gltf, metrics } = await loadModel(buffer, { textures: true });
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
  renderer.setSize(960, 640, false);
  renderer.setPixelRatio(1);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#111827');
  scene.add(new THREE.HemisphereLight(0xffffff, 0x657080, 2.5));
  const light = new THREE.DirectionalLight(0xffffff, 3);
  light.position.set(3, 5, 4);
  scene.add(light);
  const pivot = new THREE.Group();
  const bounds = new THREE.Box3().setFromObject(gltf.scene, true);
  const sphere = bounds.getBoundingSphere(new THREE.Sphere());
  gltf.scene.position.sub(sphere.center);
  pivot.add(gltf.scene);
  scene.add(pivot);
  const camera = new THREE.PerspectiveCamera(38, 960 / 640, sphere.radius / 100, sphere.radius * 100);
  camera.position.set(1, 0.7, 1.3).normalize().multiplyScalar(sphere.radius / Math.sin(THREE.MathUtils.degToRad(19)) * 1.15);
  camera.lookAt(0, 0, 0);
  const gl = renderer.getContext();
  function draw() {
    // Compare the model frame to the same renderer's empty background frame.
    pivot.visible = false;
    renderer.render(scene, camera);
    const empty = new Uint8Array(960 * 640 * 4);
    gl.readPixels(0, 0, 960, 640, gl.RGBA, gl.UNSIGNED_BYTE, empty);
    pivot.visible = true;
    renderer.render(scene, camera);
    const pixels = new Uint8Array(empty.length);
    gl.readPixels(0, 0, 960, 640, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
    let nonBackground = 0;
    for (let i = 0; i < pixels.length; i += 4) {
      if (pixels[i] !== empty[i] || pixels[i + 1] !== empty[i + 1] || pixels[i + 2] !== empty[i + 2]) nonBackground++;
    }
    const result = { ...metrics, state: 'complete', passed: renderer.info.render.triangles > 0 && nonBackground > 0,
      drawn_triangles: renderer.info.render.triangles, non_background_pixels: nonBackground,
      canvas: { width: 960, height: 640 }, backend: 'WebGL', webgl_version: gl.getParameter(gl.VERSION),
      renderer: gl.getParameter(gl.RENDERER) };
    if (!result.passed) throw new Error('WebGL produced no visible triangles');
    window.__MODEL_INSPECTION__ = result;
    report.textContent = JSON.stringify(result, null, 2);
  }
  draw();
  const rotate = document.querySelector('#rotate');
  rotate.disabled = false;
  rotate.onclick = () => { pivot.rotation.y += Math.PI / 4; draw(); };
} catch (error) {
  window.__MODEL_INSPECTION__ = { passed: false, state: 'error', error: error.message };
  report.textContent = JSON.stringify(window.__MODEL_INSPECTION__, null, 2);
  console.error(error);
}
