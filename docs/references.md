# 게임 제작 레퍼런스

2026-11-08에 첨부된 두 화면에서 출발해 공식 저장소의 README, 스킬 설명, 라이선스 고지를 확인했다. 아래의 지원 기능은 해당 프로젝트의 설명이며, 여기서 각 프로젝트를 설치하거나 실행한 결과는 아니다. 참고 프로젝트는 런타임에 설치하지 않는다. 후속으로 첨부된 pixelfx 화면도 함께 검토했다.

| 레퍼런스 | 확인한 접근 | 이번 구현에 반영한 점 | 보류한 기능과 다시 볼 시점 |
| --- | --- | --- | --- |
| [awesome-gamedev-agent-skills](https://github.com/gamedev-skills/awesome-gamedev-agent-skills) · [create-game-assets](https://github.com/gamedev-skills/awesome-gamedev-agent-skills/blob/main/skills/disciplines/create-game-assets/SKILL.md) | 시각 기준을 정한 뒤 에셋군을 제작하고 실제 표시 크기와 엔진 내 결과를 점검한다. 엔진·장르·시스템용 스킬도 나뉜다. | 공유 스타일 파일, 픽셀 크기 검사, 원본과 확대본, 엔진이 읽을 기준점과 nearest 필터 정보를 만들었다. | 엔진별 프로젝트 생성, 저장 슬롯, 출시 절차는 상위 앱 제작 플러그인에 실제 담당 모듈이 생길 때 재검토한다. |
| [Claude Code Game Studios](https://github.com/Donchitos/Claude-Code-Game-Studios) · [technical-artist](https://github.com/Donchitos/Claude-Code-Game-Studios/blob/main/.claude/agents/technical-artist.md) | 아트 기준, 에셋 사양, 감사 역할을 분리한다. | 게임별 아트 기준은 프로필 소유자가 정하고, 제작기는 JSON으로 실제 측정값을 돌려준다. 시각 승인 상태는 별도로 다룬다. | 스튜디오 조직, 다중 에이전트 조율, 출시 게이트는 여러 제작 역할을 운영하게 될 때 검토한다. |
| [sprite-gen](https://github.com/aldegad/sprite-gen) · [SKILL.md v4.3.0](https://github.com/aldegad/sprite-gen/blob/main/SKILL.md) | 이미지 생성, 알파 정리, 상태별 프레임과 아틀라스, 비디오 루프, 엔진 내보내기를 다룬다. | 사용자가 생성과 로컬 이미지 입력을 선택한다. 정적 PNG의 기술 검증을 독립 실행할 수 있게 했다. | 애니메이션이 필요해지면 프레임마다 기준점·실루엣 유지, 루프 이음새, 프레임 시간 메타데이터를 먼저 검토한다. Grok·기타 업체 서버 호출, 영상 보간 모델 및 제공자 자동 전환은 제외했다. |
| [Game-Dev-Agentic-Skills](https://github.com/thedivergentai/Game-Dev-Agentic-Skills) · [변경 기록](https://github.com/thedivergentai/Game-Dev-Agentic-Skills/blob/main/CHANGELOG.md) | Godot·Bevy별 진입점과 필요한 도메인 스킬을 선택하는 구조다. | 게임 엔진 독립적인 PNG 계약을 두고 실제 소비 코드는 호스트가 맡는다. | Godot·Bevy 패키지, 장르 설계도, 엔진용 임포터는 실제 호스트 엔진과 버전이 정해지면 검토한다. |

| [patch-gg/pixelfx](https://github.com/patch-gg/pixelfx/tree/a84159688af3ca37a4be05a0d422b94451b2e24e) | 공식 문서에서 21개 분류의 효과·동작 244개, 로컬 절차적 프레임 렌더링, 팔레트 교체, 투명 시트와 프레임 좌표·시간·원점 내보내기를 확인했다. | 색·시드·원점·재생 시간을 분리하는 설계를 참고했다. 수집 반짝임과 반복 불꽃의 픽셀 및 프레임 코드는 자체 제작했다. | 캐릭터 연기·히트스톱·타격 반응은 게임 호스트에서 타이밍이 필요할 때 다시 본다. 코드를 실제 가져올 경우 [MIT 고지](https://github.com/patch-gg/pixelfx/blob/a84159688af3ca37a4be05a0d422b94451b2e24e/LICENSE)와 [추가 저자 고지](https://github.com/patch-gg/pixelfx/blob/a84159688af3ca37a4be05a0d422b94451b2e24e/NOTICE.md)를 검토한다. 갤러리의 [Patch Pixel 폰트](https://github.com/patch-gg/pixelfx/blob/a84159688af3ca37a4be05a0d422b94451b2e24e/gallery/fonts/NOTICE.md)는 MIT 적용 대상에서 제외되며 이 프로젝트에 포함하지 않았다. |

첫 번째 화면에서 함께 언급된 인벤토리·세이브·던전 생성은 게임 플레이 시스템에 해당한다. 프레임 애니메이션과 12색 반복 타일은 0.2에서 각각 sheet와 tile로 분리했다. 타일의 이음새와 특수 효과의 불티는 투명 단일 스프라이트와 다른 방식으로 검사한다. 출시와 스토어 업로드는 배포 레이어의 책임이다.

사용한 외부 구현은 이미지 생성 시의 Codex 내장 기능과 로컬 Pillow이다. 이 표의 저장소에서 스킬 본문, 코드, 에셋을 가져오지 않았다. 소스 라이선스와 고지 범위는 [검토 기록](license-review.md)에 남겼다.

## 0.2.1 이후의 제작 후보

첨부된 픽셀 제작 공식, 게임 개발 스킬 소개 두 장, pixelfx 소개 화면을 설치된 0.2.1과 다시 대조했다. 아래 항목은 검토 후보이며 현재 CLI에 추가된 명령은 아니다.

| 순서 | 남은 제작 작업 | 첫 검증물 |
| --- | --- | --- |
| 1 | **아틀라스 분리.** 현재 sheet는 개별 PNG를 시트로 묶는다. 반대 방향으로는 투명 원본 시트, 행·열, 이름을 받아 투명 여백을 찾고 애매한 경계만 사용자가 지정할 수 있게 한다. 서로 다른 소품의 상대 크기는 한 배율로 유지한다. [sprite-gen 시트 분리](https://github.com/aldegad/sprite-gen/blob/main/docs/sheet-slicing.md) | woodland 원본을 9개로 추출한다. 알파 128 이상 기준으로 원본 1254px의 단순 3등분선 y=418·836은 각각 전경 317·55픽셀을 지난다. 현재 예제의 y=459·798은 전경 0픽셀이다. 추출 사각형·이름을 기록하고 원위치에 붙여 가시 픽셀 손실을 검사한다. |
| 2 | **기준 캐릭터 한 장에서 대기 동작 제작.** 현재 걷기 포즈는 예제 전용 코드로 그린다. 먼저 고정할 얼굴·발과 움직일 몸통을 지정하는 짧은 호흡 루프를 독립 제작 경로로 검토한다. 공격 자세 생성은 별도의 미술 문제다. [sprite-gen 호흡 모드](https://github.com/aldegad/sprite-gen/blob/main/docs/breathing.md) | 승인 정찰병의 4포즈를 만들어 동일 팔레트·피벗·고정 영역의 픽셀 보존을 확인하고, 원속도에서 몸통이 자연스럽게 보이는지 검수한다. |
| 3 | **함께 연결되는 지형 세트.** 현재 tile은 한 타일의 자기 반복을 확인한다. 방향별 길 입구를 정의한 뒤 직선·모서리·끝·교차로를 한 세트로 제작한다. [지형 조합 제작 지침](https://github.com/gamedev-skills/awesome-gamedev-agent-skills/blob/main/skills/disciplines/create-game-assets/references/raster-pipeline.md) | 메모리에서 만든 32px 타일 두 개는 각각 통과했지만, 위아래로 붙이자 폭 8px의 길이 겹치는 픽셀은 0개였다. 방향별 연결 마스크를 서로 비교하고 실제 혼합 지도에서 길이 이어지는지 확인한다. |
| 4 | **캐릭터와 이펙트의 합성·타이밍.** 기존 pickup/flame의 납품 방식에 캐릭터 앞·뒤 레이어와 기준 프레임 정보를 추가하는 후보이다. [pixelfx의 합성과 acting](https://github.com/patch-gg/pixelfx/tree/a84159688af3ca37a4be05a0d422b94451b2e24e#acting) | 정찰병이 지팡이를 휘두르는 1회성 예시로 손 부착점, 뒤쪽 잔상, 앞쪽 타격광, 타격 프레임의 일치를 확인한다. 전투 판정과 피해 처리는 호스트에 둔다. |

후순위로는 승인된 스프라이트의 지정색만 바꾸는 [팔레트 변형](https://github.com/aldegad/sprite-gen/blob/main/docs/recolor.md), 인벤토리 창의 모서리를 보존하며 늘리는 [9-slice UI 아트와 스크롤 배경 레이어](https://github.com/gamedev-skills/awesome-gamedev-agent-skills/blob/main/skills/disciplines/create-game-assets/references/raster-pipeline.md)가 있다. 엔진이 정해지면 pixelfx의 Aseprite 스타일 JSON을 참고해 **한 엔진의 실제 임포트**부터 검증한다. 이 후보들은 로컬 PNG 처리와 기존 Codex 내장 생성 경로 안에서 검토할 수 있다.

3D 제작과 씬 통합을 위해 같은 원본 다섯 곳의 실제 파일, 로컬 Blender·Webstage·Frameforge 도구, 채택 여부와 라이선스를 [3D 레퍼런스 검토](model-references.md)에 기록한다.

[Agent Sprite Forge와 pixelfx](sprite-forge.md)에는 정지 마스터, 여섯 동작, 로컬 미디어 후처리와 pixelfx 연동을 조사한 결과를 기록했다. 이 저장소의 `action-set`은 로컬 프레임과 로컬 효과 시트를 입력으로 받는다.

## 프레임별 작화와 Rive

Polymation의 픽셀 캐릭터 문서는 카메라 쪽으로 향하는 팔다리의 단축과 윤곽 재작화를 설명한다. 가려진 신체나 포즈 변화가 큰 경우에는 기존 프레임을 flipbook으로 보존하는 경로도 있다. v0.7.0의 `character`는 완성 셀을 직접 입력받아 선택·재생하는 로컬 경로를 지원한다. 이 제품의 리깅·작화 코드는 복사하지 않았다. [픽셀 캐릭터](https://polymation.stunning.gg/docs/pixel-characters) · [이미지 리그](https://polymation.stunning.gg/docs/rig-from-picture) · [공개 체험](https://polymation.stunning.gg/try/)

플레이어에는 공식 `@rive-app/canvas` 2.49.4의 JS·WASM과 MIT 고지를 포함한다. 공급 패키지와 파일 지문은 설치 배포물에 보존한다. [런타임 소스](https://github.com/rive-app/rive-wasm) · [포함 파일의 출처와 SHA-256](../src/pixel_asset_pipeline/player/vendor/integrity.json)

## 행동별 피드백 제작

첨부한 @porsukgames의 전투 사례와 GDC 강연을 참고해, 이동·착지·수집·확인·거절·명중을 서로 다른 시점과 피벗에 연결했다. 효과의 픽셀과 소리는 이 프로젝트에서 생성한다. 외부 게시물의 이미지나 음원을 배포물에 넣지 않았다. [Jonasson과 Purho의 GDC 강연](https://gdcvault.com/play/1016487/Juice-It-or-Lose-It)
