# 0.1.0 검증 기록

0.2.0의 최신 결과는 [제작 계획·검증 기록](asset-production-plan.md)에 있다.

2026-11-08 macOS arm64에서 Python 3.13.3, Pillow 12.3.0, Node 26.7.0, Codex CLI 0.165.0으로 확인했다.

| 대상 | 실행 및 관찰 |
| --- | --- |
| 단위·계약 테스트 | `.venv/bin/python -W error -m unittest discover -s tests` 29개 통과. 팔레트·알파·기준선·외곽선, 잘못된 요청·원본·생성 실패, 출력 보존, 스타일 PNG 메타데이터 제거, 모의 호스트의 오류 거부를 포함한다. |
| 아틀라스 재가공 | Codex 내장 이미지 도구로 만든 [원본 한 장](../examples/woodland/atlas.png)에서 캐릭터·아이콘·아이템 각 3개를 추출했다. 9개 PNG가 각각 10개 규격 검사를 통과했다. 빌드 두 번의 PNG 9개·미리보기·검증 JSON이 바이트 단위로 동일했다. [결과 JSON](../examples/woodland/results.json) |
| CLI 네이티브 생성 | `pixel-asset build --codex`로 배치 가이드를 첨부하여 [첫 정찰병](../examples/codex-scout/preview.png)을 생성했다. 같은 요청에 기존 정찰병 PNG를 `--style-reference`로 지정하여 [두 번째 정찰병](../examples/codex-scout-styled/preview.png)을 생성했다. 양쪽 모두 초안부터 최종 번들까지 CLI 한 번으로 완료했다. [두 번째 검증 결과](../examples/codex-scout-styled/validation.json) |
| 시각 검토 | 확대 시트에서 9개 실루엣을 구분할 수 있다. 올빼미의 지도와 가방의 작은 버클은 원본보다 단순해졌다. 독립 생성한 두 정찰병 모두 48×48·16색을 충족했지만 첫 그림의 몸통은 길고, 스타일 예시를 넣은 두 번째 그림은 머리와 후드가 더 크게 읽힌다. 이 비교는 해당 샘플에 한정한다. |
| 설치 | 최종 ZIP을 풀어 임시 CODEX_HOME의 로컬 마켓플레이스에 설치했다. `codex plugin list`에서 installed/enabled를, app-server `skills/list`에서 `pixel-asset-pipeline:pixel-asset-pipeline` 활성화를 확인했다. |
| 로컬 경로의 네트워크 격리 | macOS sandbox-exec의 `deny network*`에서 소켓 연결 대조군이 EPERM으로 실패했다. 같은 정책에서 실제 Node 모의 호스트가 새 게임 폴더에 정찰병을 가져왔고 원본과 PNG 바이트가 일치했다. 피벗은 [24, 46], 필터는 nearest였다. 별도 실행에서 설치 캐시의 Python 소스도 네트워크 차단 상태로 같은 PNG를 생성했다. |
| 배포 묶음 | ZIP 무결성 검사와 9개 파일의 소스 대조를 통과했다. 두 manifest, SKILL.md, pyproject.toml, Python 파일 5개만 들어 있다. 외부 스킬, 라이브러리 바이너리, 예시 아트, API 키가 들어갈 설정 파일을 포함하지 않는다. ZIP SHA-256은 `e1f56b1c0bd8f8a07afc2837d90c0e704cd586b51751b870583bd51e11779bbc`이다. |

Codex 이미지 생성은 네트워크를 쓰는 허용된 경로이다. 네트워크 차단 증거는 로컬 초안 처리와 게임 에셋 가져오기에 해당한다. 네이티브 세션 전체의 패킷 캡처, 실제 앱 제작 플러그인·게임 엔진의 임포트, Dot 런타임, 게임 속 시각 승인은 이번 검증 범위에 포함하지 않았다.

## 브라우저 씬 후속 검증

2026-11-08에 [이끼숲 순찰길](../examples/forest-scene/index.html)을 로컬 HTTP로 실행했다. 씬은 검증용 소비자이며 플러그인의 배포 목록 밖에 있다. 배경은 예제 전용으로 Codex 내장 이미지 도구에서 생성해 논리 해상도 352×176으로 맞췄다. 캐릭터는 `codex-scout-styled/asset.png`와 피벗 메타데이터, 수집물은 woodland의 PNG 원본을 사용한다.

- 데스크톱 브라우저에서 오른쪽 방향키를 눌러 수집 가방이 0 → 1 → 2 → 3으로 바뀌는 것을 관찰했다. 오른쪽 끝 x=328에서 왼쪽 끝 x=24까지 돌아오는 동안 수집 수는 3을 유지했다. 다시 시작하면 x=48, 수집 수 0으로 돌아왔다. 이 흐름에서 브라우저 콘솔 및 페이지 오류는 없었다.
- 정찰병 원본 48×48, 피벗 (24, 46), 씬의 바닥선 y=150을 확인했다. 정지 자세에서 불투명 픽셀 908개가 원본과 일치했다. 오른쪽 걷기의 두 자세를 포함한 312개 관측 프레임에서 매번 한쪽 부츠의 원본 색이 y=149에 남았고 y=150·151 두 행은 배경과 일치했다. 이는 캔버스 픽셀 비교이며 실제 엔진의 충돌 판정 측정은 아니다.
- 1280px 브라우저에서 맞춤 2×(704×352)와 원본 1×(352×176), 390px 뷰포트에서 1×와 발 위치 검사 패널을 확인했다. 320px 뷰포트에서는 캔버스를 가로로 스크롤할 수 있고 페이지 자체에는 가로 넘침이 없었다. 모바일 크기는 데스크톱 브라우저에서 확인했다.
- `node --test examples/forest-scene/game.test.mjs`는 5개, Python 회귀 테스트는 29개 통과했다. Node 테스트는 모의 Canvas의 동작을 검증한다. 실제 플레이는 [영상](../examples/forest-scene/evidence/play.mp4)과 [검사 화면](../examples/forest-scene/evidence/foot-inspection.png)에 남겼다.
