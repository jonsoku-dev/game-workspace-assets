---
name: pixel-asset-pipeline
description: 게임에 사용할 2D 픽셀 스프라이트·장비 변형·걷기 시트·반복 지형 타일·수집 반짝임과 불꽃을 제작하고, 팔레트와 피벗을 검증해 재사용 가능한 에셋으로 내보낸다.
---

게임의 2D 아트 제작 레이어를 맡는다. 결과물은 게임 호스트가 읽는 PNG, 프레임·피벗 메타데이터와 미리보기다. 씬은 실제 사용 크기에서 아트를 검토할 때 사용한다.

1. 공통 아트 프로필, 원본 픽셀 크기, 색, 시점, 발 기준점과 필요한 산출물을 확인한다.
2. 캐릭터·아이콘·아이템 한 장은 `build`를 쓴다. 요청 필드는 `schema_version: 1`, `kind`, `prompt`이고 선택 필드는 `size`, `max_colors`, `profile`, `palette`, `style`, `view`, `outline`이다. 상대 프로필 경로는 요청 파일 기준이다. character 기본값은 48px/16색, icon은 24px/12색, item은 32px/24색이다. 기존 원본은 `--draft`로 로컬 처리한다. 새 이미지 생성에는 `--codex`를 명시하고 Codex 내장 기능만 사용한다. 사용자가 전송 대상으로 선택한 PNG만 `--style-reference`로 붙인다. API 키, 외부 업체 업로드, 다른 제공자로의 자동 전환을 추가하지 않는다.
3. **같은 몸의 장비 교체**는 `variant`, **독립 제작 세트의 1×/4× 비교**는 `compare`, **실제 포즈를 시트로 묶기**는 `sheet`, **불투명 지형 반복 검사**는 `tile`, **절차적 픽셀 효과 제작**은 `effect`를 사용한다. 이 다섯 경로의 입력 예시와 출력은 [로컬 제작 계약](references/production.md)을 확인한다.
4. 설치된 `pixel-asset`을 사용한다. PATH에 없으면 이 SKILL.md에서 상위 네 디렉터리의 플러그인 루트를 찾아, Python 3.10 이상과 Pillow 10~12가 준비된 환경에서 `PYTHONPATH="$PLUGIN_ROOT/src" "$PYTHON" -m pixel_asset_pipeline.cli`로 호출한다. 작업 중 라이브러리를 내려받지 않는다.

```sh
pixel-asset build --request request.json --draft draft.png --out sprite-v1
pixel-asset validate --request request.json sprite-v1/asset.png
pixel-asset effect --request pickup.json --out pickup-v1
```

5. 새 출력 경로를 사용한다. 성공하면 stdout의 `files`를 기준으로 결과를 반환한다. 기술 검사와 시각 판단을 분리한다. 정적 아트는 실제 크기에서 얼굴·장비·실루엣을, 걷기는 접지와 마지막→첫 프레임을, 타일은 3×3 반복을, 효과는 한 번 재생 후 소멸과 연속 루프를 각각 본다. 스타일에서 벗어난 항목만 수정하고 비교판에서 다시 확인한다.
