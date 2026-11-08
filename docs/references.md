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
