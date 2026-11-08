# Model Assets

게임용 정적 소품을 Blender에서 편집 가능한 원본과 GLB로 만들고, Webstage hero 예산과 Three.js 로딩을 확인한다. Blender 내보내기와 재임포트 사이에 메시 수·삼각형·재질·미터 단위 경계가 일치해야 납품한다. 브라우저 검수 페이지에서는 컴파일된 GLB를 WebGL로 직접 그린다.

## 로컬 설치

필요한 프로그램은 Python 3, Blender, Node와 npm, Webstage CLI이다. macOS 또는 Linux에서 새 디렉터리로 패키징한다. Python 실행 파일, Blender, Webstage, Three.js 소스는 설치 묶음에 들어가지 않는다.

```sh
python3 package.py "$HOME/.local/share/codex-local-plugins/model-assets/0.3.0"
codex plugin marketplace add "$HOME/.local/share/codex-local-plugins/model-assets/0.3.0"
codex plugin add model-assets@model-assets
codex plugin list --marketplace model-assets --json
MODEL_ROOT="${CODEX_HOME:-$HOME/.codex}/plugins/cache/model-assets/model-assets/0.3.0"
npm ci --prefix "$MODEL_ROOT/three" --offline --ignore-scripts --no-audit --no-fund
```

Three.js 0.187.0의 npm 캐시가 있는 환경에서 실행한다. 새 캐시를 생성하거나 설치본을 교체하면 잠금 파일에서 의존성을 다시 준비한다.

Codex에서는 `$model-assets`로 요청한다. 입력·산출물·로컬 뷰어 실행 예시는 [모델 제작 스킬](.agents/skills/model-assets/SKILL.md)에 있다. [레퍼런스와 고지](../../docs/model-references.md)는 도구 사용과 배포 파일의 범위를 기록한다.

0.1.x에서 갱신할 때는 새 0.3.0 폴더를 먼저 준비한다. 기존 등록을 `codex plugin marketplace remove model-assets`로 교체한 뒤 위의 marketplace add와 plugin add를 실행한다. 이전에 만든 모델 번들은 각각 생성 당시의 리비전으로 남는다.

## 3D 불티

`{"schema_version":1,"name":"Lantern embers","preset":"embers","seed":23}`는 Blender에서 발광하는 입체 불티 메시를 만들고 동일한 GLB 검사를 거친다. `files.model`은 컴파일된 메시이며 `files.effect`는 결정적 3축 궤적·회전·수명·주기를 담은 로컬 재생 데이터다. 스튜디오에서 등불을 부모로 지정해 통풍구에 붙이면 메시가 등불과 같은 깊이 버퍼를 사용한다. 게임 엔진에 재사용할 때는 GLB 인스턴스에 레시피를 적용한다.

## Packed textured static props

`source_blend` accepts self-contained PNG/JPEG base color textures up to 2048px per edge. Pack each image in Blender, use sRGB and connect an explicitly named UV Map → Image Texture Color → Principled Base Color. Use Linear interpolation and Repeat extension. All selected meshes using the material need that finite UV map. Other PBR inputs remain constant values; procedural graphs, normal/roughness texture maps, external files, rigs and animation are rejected. Inputs must be trusted local files; Blender runs offline with script auto-execution disabled.

The Node inspector uses the already-required local Blender PNG/JPEG decoder and actual Three.js GLTFLoader DataTextures, without placeholder image shims. A textured build compares decoded RGBA hashes, sRGB material colors, and UV/world-position sample sets (rounded to 0.0001) between raw and compiled default scenes. A compiler change that simplifies textured vertices can fail this conservative fidelity gate. The browser viewer independently decodes embedded images through its normal image loader and renders the compiled artifact. Neither check grants artistic approval.

The repository example `../../examples/model-production/` contains an original workshop rescue crate, its deterministic Blender recipe, packed editable source, texture and reference render. Rebuild it with the commands in its README. Installed plugins do not include those example assets.
