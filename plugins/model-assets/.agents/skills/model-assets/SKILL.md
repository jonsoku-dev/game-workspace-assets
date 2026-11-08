---
name: model-assets
description: 게임용 3D 소품을 Blender에서 제작하거나 선택한 로컬 .blend의 정적 메시를 GLB로 납품한다. 크기, 축, 재질, Webstage 예산, Three.js 로딩을 검사하고 필요할 때 WebGL 미리보기를 연다.
---

요청에 소품 이름, 실제 높이 또는 승인된 로컬 모델, 씬에서의 용도를 기록한다. 설치된 이 스킬 파일에서 네 디렉터리 위가 제작기 루트다. 아래 명령의 MODEL_ROOT에는 그 절대 경로를 쓴다.

1. 등불을 모델링할 때는 프로젝트에 아래처럼 요청을 저장한다. 다른 소품은 로컬 Blender에서 메시를 만들고 적용할 수정자를 정리한 뒤, 내보낼 메시만 선택한 상태로 저장한다. 요청의 preset과 height_m을 제거하고 source_blend에 요청 파일을 기준으로 한 상대경로를 넣는다. 소스는 자신이 제작했거나 신뢰하는 정적 .blend를 사용한다.

   ```json
   {"schema_version":1,"name":"Camp lantern","preset":"lantern","height_m":0.30}
   ```

2. Blender, Node, Webstage CLI가 있는 환경에서 실행한다. three/node_modules가 없으면 이 설치본의 three 디렉터리에서 `npm ci --offline --ignore-scripts --no-audit --no-fund`로 잠금 파일의 의존성을 준비한다. 오프라인 캐시가 비었으면 부족한 패키지를 알려 준다.

   ```sh
   python3 "$MODEL_ROOT/tools/build.py" --request lantern.json --out generated/lantern-v1
   ```

3. stdout에서 status가 ready인지 확인하고 files의 상대 파일명을 결과 폴더에서 읽는다. source는 편집 원본, raw는 Blender 내보내기, model은 게임용 컴파일 GLB다. metadata에서 Blender 재임포트의 삼각형·재질·경계 검사를, receipt에서 hero 예산 통과를, validation에서 Three가 실제 읽은 메시와 축 변환 후 크기를 확인한다. 출력은 새 폴더여야 한다. 수정할 때는 새 경로로 다시 제작한다.
4. 외관 확인이 필요하면 `python3 "$MODEL_ROOT/tools/serve.py" generated/lantern-v1 --port 8765`를 실행하고 로컬 URL을 연다. 모델이 실제로 보이는지, 재질과 바닥·손잡이 비율이 맞는지 확인한다. Node 로딩 결과와 브라우저에서 관찰한 결과를 각각 기록한다.

지원 입력은 미터 단위의 정적 메시와 단색 PBR 또는 아래 계약의 packed Base Color 재질이다. 납품할 게임의 씬 배치와 플레이 동작은 호스트 스튜디오에서 정한다.

### 모델링과 외관 검수

- 제작 전 게임에서 보일 크기와 각도를 정하고, 레퍼런스에서 실제로 보이는 부품·비율·접합부를 적는다. 첨부 자료가 제작 방법을 설명하는 문서라면 그 문서를 대상 소품의 정면 설계도로 간주하지 않는다. 보이지 않는 형상은 제작자가 결정한 부분으로 기록한다.
- 대표 소품 하나를 큰 덩어리로 먼저 만든다. 정면·측면·사선의 실루엣과 게임 표시 크기에서 손잡이와 몸통 사이의 빈 공간, 받침과 기능 부품의 구분을 확인한다. 윤곽이 틀리면 메시의 비례를 고친다.
- 역할이 다른 재질을 나눈다. 예를 들어 랜턴은 도장된 금속, 황동 철물, 투과하는 유리, 발광하는 불꽃이다. 구부린 금속과 말아 만든 테두리, 유리 두께, 걸쇠와 손잡이의 회전축은 실제 단면과 접합으로 표현한다. Base Color 도장·표식은 아래 packed 이미지 계약으로 만든다. 노멀·러프니스 텍스처와 베이크는 지원 범위를 먼저 밝힌다.
- 새 버전을 검토할 때 이전 버전과 같은 높이·카메라·조명에 놓는다. 원본 미리보기와 컴파일된 GLB를 각각 보고 옆·뒤에서 부품이 관통하거나 사라지지 않는지, 작은 크기에서도 내부 광원이 읽히는지 기록한다. 기술 검증, 작성자의 시각 검토, 사용자의 승인 상태를 각각 구분한다.
- 스튜디오를 통한 생성은 단계·출력·검증을 해당 프로젝트의 SSOT 그래프에 자동으로 기록한다. 독립 제작 또는 외관 검토라면 `game-studio`의 `graph.py record`로 실제 사용한 요청·비교 대상·산출물을 연결한다.

`files.review`는 정면·측면·후면을 384px와 128px 프레임으로 렌더한 검수 시트다. 모델이 프레임을 전부 채우지 않으므로 프레임 해상도와 화면에서 보이는 물체 높이는 다르다. 시트 생성 자체는 외형 승인이 아니다.

### 3D 불티

등불 주위의 3D 효과는 `{"schema_version":1,"name":"Lantern embers","preset":"embers","seed":23}` 요청으로 만든다. 같은 제작 명령이 실제 발광 메시와 컴파일된 GLB, `files.effect`의 3축 궤적 레시피를 함께 납품한다. 레시피는 미터·+Y 축·초 단위다. 스튜디오의 `parent` 배치로 등불 통풍구에 연결하고, 여러 시점에서 커지는 불티·옆 방향 움직임·모델과의 가림을 본다. 과거 픽셀 효과의 판정 기준은 2D 스프라이트 요청에 적용한다.

### Packed Base Color 텍스처

- 로컬 .blend 안에 PNG/JPEG 이미지를 Pack하고 저장한다. 크기는 각 변 1–2048px, 색공간은 sRGB다. 이미지를 외부 경로에서 런타임에 읽거나 네트워크로 가져오지 않는다.
- 명시적인 UV Map 노드의 이름을 모든 재질 사용 메시의 UV 레이어와 맞춘다. `UV Map → Image Texture(Vector)`, `Image Texture(Color) → Principled(Base Color)`만 연결한다. 이미지 설정은 Linear와 Repeat다. 다른 PBR 값은 상수로 유지한다. 노멀·러프니스 맵, 알파 연결, 임의 노드 그래프, 리그·애니메이션은 거부된다.
- Node 검증은 로컬 Blender로 이미지를 실제 RGBA로 디코딩하고 Three GLTFLoader로 기본 씬을 읽는다. validation의 decoded_textures에 크기·실제 색상 수·SHA-256이 있어야 한다. texture_comparison에서 원본과 컴파일 GLB의 픽셀·sRGB 재질 색·UV/월드 좌표 샘플 집합이 같아야 한다. 좌표는 0.0001 단위 반올림으로 비교하며 텍스처 메시를 단순화하는 컴파일은 보수적으로 거부될 수 있다.
- 브라우저에서도 컴파일 결과를 열어 실제 이미지 디코딩, 패널의 엠블럼 방향과 UV 이음새, 128px 게임 표시 크기를 확인한다. 디코딩이나 예산 통과를 외관 승인으로 보고하지 않는다.

```json
{"schema_version":1,"name":"Workshop rescue crate","source_blend":"rescue-crate.blend"}
```
