# Agent Sprite Forge, pixelfx, 로컬 2D 제작기의 경계

확인일: 2026-11-08. Agent Sprite Forge의 기본 브랜치 `main`은 GitHub API 트리에서 `6b3da5c444363378e20f3fce130ebecc22f343dd`로 고정해 확인했다. pixelfx 기본 브랜치는 `a84159688af3ca37a4be05a0d422b94451b2e24`였다. 아래 소스 링크는 이 커밋을 가리킨다. 이는 현재 도구의 동작·출력 계약을 읽은 결과이며, 두 저장소를 설치하거나 현재 워크스페이스에서 실행한 결과는 아니다.

## 먼저 결론

- ASF의 기본 여섯 액션은 `idle`, `walk`, `run`, `attack`, `jump`, `hurt`다. 승인된 캐릭터 정지화면 하나를 기준으로 액션마다 **이미지→동영상 클립 하나씩** 만든 뒤, 클립을 로컬에서 키잉·발 위치 맞춤·루프/타이밍 처리·픽셀 마감·패키징한다. 영상 생성 단계만 생성 API나 사용자 로컬 이미지→동영상 도구가 필요하다.
- pixelfx는 ASF의 캐릭터 액션 영상 생성기를 대신하지 않는다. ASF에는 pixelfx의 **이펙트 전용 연결기**가 이미 있다. 이펙트 프레임을 별도 생성하고 출처와 크레딧을 붙인다. 공격 캐릭터는 자체 애니메이션으로 그리고 pixelfx가 제공하는 타격·히트스톱 타이밍을 참고해 호스트에서 맞출 수 있다.
- 현재 설치된 로컬 Pixel Asset Pipeline 0.2.1의 `sheet`는 준비된 동일 크기 PNG 포즈를 무손실 시트로 포장한다. 여섯 액션을 한 원화에서 생성하거나, 임의 PNG를 관절 리그로 바꾸지는 않는다. `effect`는 자체 코드로 그린 `pickup`/`flame` 두 프리셋이다.
- 외부 영상 생성 없이 코드만으로 애니메이션을 원하면 ASF의 `codeart2d`처럼 새 SVG 리그와 키프레임을 직접 그리는 경로가 있다. 이는 승인 PNG를 변형해 같은 얼굴·복장으로 보존하는 방법이 아니다. 결과를 새 코드 그림으로 명시해야 한다.

## ASF의 여섯 액션: 생성은 외부 가능, 처리·검수는 로컬

ASF [`README.md`](https://github.com/0x0funky/agent-sprite-forge/blob/6b3da5c444363378e20f3fce130ebecc22f343dd/README.md)와 [`video2dsprite/SKILL.md`](https://github.com/0x0funky/agent-sprite-forge/blob/6b3da5c444363378e20f3fce130ebecc22f343dd/skills/video2dsprite/SKILL.md)가 각각 액션을 계획하고 생성하는 경로를 설명한다. `sprite_set.py plan`의 기본은 여섯 액션이며, 각 클립의 시작은 마스터 정지화면으로 고정하고 액션별 캔버스·동작 프롬프트·검사 조건을 만든다. 필요하면 승인된 마스터를 다른 방향의 보기(view)로 추가할 수 있다.

| 단계 | 어디서 일어나는지 | 하는 일·제한 |
| --- | --- | --- |
| 마스터 정지화면 | 이미지 생성 도구/API 또는 사용자가 제공 | 캐릭터 모습·방향·스타일·피벗의 승인 기준. 여섯 액션을 한 장의 그림에서 잘라내는 접근이 아니다. ASF `master.json`은 패딩된 PNG와 해시를 고정한다. |
| 액션 클립 생성 | 외부 이미지→동영상 모델/CLI, 또는 사용자가 만든 클립 | 마스터와 프롬프트로 각 액션별 클립을 만든다. README/API 경로에는 xAI Grok Imagine, BytePlus Seedance, fal.ai를 비롯한 업체 경로가 기재되어 있고, 로컬 경로는 Grok 이미지→동영상 도구/CLI다. 실제 사용 가능 모델·계정·가격·약관은 별도로 확인해야 한다. 이 조사에서는 키를 읽거나 요청을 보내지 않았다. |
| 키잉·검사·정합 | ASF의 결정적 Python 도구 | 소프트 매트 키잉, 프레임별 크기·얼굴/정체성·방향·배경·여분 물체·화면 가장자리·동작 검사, 마스터에 대한 프레임 등록, 발 고정 등을 한다. 검사 실패 시 최대 3회 생성 시도와 수정 문구를 계획할 수 있다. 검사 숫자만으로 외형 승인하지 않고 시트도 눈으로 봐야 한다. |
| 루프·일회성 액션 처리 | ASF의 로컬 도구 | `idle/walk/run`은 후보 루프를 선택하고, `attack/jump/hurt`는 움직임 지점에 이벤트를 두고 게임 재생 길이로 리타이밍한다. 흔히 쓰는 기본 계획값은 공격 0.7초, 점프 0.9초, 피격 0.5초이며 액션별로 계획 파일에서 수정 가능하다. |
| 마감·내보내기 | ASF의 로컬 도구 | HD 또는 pixel 마감, 마스터 색 잠금, PNG 프레임/아틀라스 및 WebM·packed video 등 포맷을 검증한다. README는 편집기 임포트가 모두 검증됐다고 주장하지 않는다. 실제 타깃 게임/편집기에서 확인은 별도다. |

**유료·외부 라우트의 권한을 이 설명에서 추정하지 않는다.** 로컬 계정, API 키, 제공자 약관, 생성 대상 권리, 업로드 허용 범위는 작업 전에 실제 환경에 맞춰 확인할 일이다. 사용자가 제공한 클립을 처리하는 경로도 문서화되어 있다.

참고 링크: [`sprite_set.py`의 여섯 액션 기본값](https://github.com/0x0funky/agent-sprite-forge/blob/6b3da5c444363378e20f3fce130ebecc22f343dd/skills/video2dsprite/scripts/sprite_set.py), [액션별 프롬프트·QC·타이밍 설명](https://github.com/0x0funky/agent-sprite-forge/blob/6b3da5c444363378e20f3fce130ebecc22f343dd/skills/video2dsprite/references/sprite-set.md), [미디어 라우팅 도구](https://github.com/0x0funky/agent-sprite-forge/blob/6b3da5c444363378e20f3fce130ebecc22f343dd/skills/generate2dmedia/scripts/route_media.py), [서드파티 고지](https://github.com/0x0funky/agent-sprite-forge/blob/6b3da5c444363378e20f3fce130ebecc22f343dd/THIRD_PARTY_NOTICES.md).

## pixelfx와 연결할 수 있는 것

ASF는 [`fx_pixelfx.py`](https://github.com/0x0funky/agent-sprite-forge/blob/6b3da5c444363378e20f3fce130ebecc22f343dd/skills/generate2dsprite/scripts/fx_pixelfx.py) 및 `generate2dsprite/SKILL.md`에서 hibit 게임용 이펙트 경로를 제공한다. 체크아웃이 있으면 `check`는 경로를 판별하고, `list`는 효과 카탈로그를 읽으며, `render`는 선택 효과를 투명 프레임으로 내보낸다. 렌더 명령의 형식은 다음과 같다.

```sh
python "<generate2dsprite>/scripts/fx_pixelfx.py" check --pixelfx <pixelfx-checkout>
python "<generate2dsprite>/scripts/fx_pixelfx.py" list slash --pixelfx <pixelfx-checkout>
python "<generate2dsprite>/scripts/fx_pixelfx.py" render --pixelfx <pixelfx-checkout> \
  --id melee/sword-slash --ramp '#242033,#8f4978,#f4bb74' \
  --snap <palette.json> --output-dir <new-output>
```

연결기는 upstream의 `node tools/render.mjs <effect> --sheet --no-actor --bg none`을 호출하고, 시트 메타데이터를 따라 투명 PNG 프레임을 분리한다. 새 출력 폴더에 `frames/`, Aseprite 형식 `sheet.png`/`sheet.json`, `preview.gif`, 출처 정보가 담긴 `fx.json`, 원본 라이선스와 고지 전문을 담은 `CREDITS.txt`를 쓴다. 팔레트 ramp와 `--snap`을 적용할 수 있고, 기본 알파는 0/255로 자른다. 흐릿한 광선은 밝은 배경에서 어두운 잔상처럼 보일 수 있어 `--alpha keep`은 어두운 배경이나 additive 합성에만 사용하라고 구현 주석이 경고한다.

이 경로에는 pixelfx 체크아웃과 Node.js 18 이상이 필요하며, upstream 스크립트는 npm 패키지 설치가 필요 없다고 안내한다. `node tools/render.mjs fire/torch --sheet`는 원본 시트와 JSON을, `node tools/check.mjs fire/torch`는 캔버스 바깥 그리기·루프 경계·비결정 난수·그리기 시간 등을 검사하는 공식 명령이다. 다만 이 작업 환경에는 pixelfx 체크아웃이 없고 사용자가 설치하지 말라고 했으므로, 여기서 위 명령의 실제 실행 성공이나 새 `CREDITS.txt` 생성을 주장하지 않는다. 이는 고정 커밋의 [`README`](https://github.com/patch-gg/pixelfx/blob/a84159688af3ca37a4be05a0d422b94451b2e24/README.md), [`SKILL.md`](https://github.com/patch-gg/pixelfx/blob/a84159688af3ca37a4be05a0d422b94451b2e24/skills/pixelfx/SKILL.md), [`render.mjs`](https://github.com/patch-gg/pixelfx/blob/a84159688af3ca37a4be05a0d422b94451b2e24/tools/render.mjs), [`check.mjs`](https://github.com/patch-gg/pixelfx/blob/a84159688af3ca37a4be05a0d422b94451b2e24/tools/check.mjs), 그리고 ASF의 브리지 소스가 문서화하는 계약이다.

pixelfx에는 캐릭터 공격을 동작시키는 `act` 데이터와 스켈레톤/IK가 있지만, 기본 시각 인물은 픽셀로 그리는 내장 대역 캐릭터다. `skeleton(pose)`는 관절 좌표를 계산하고 포즈의 각 픽셀이 기준 몸 픽셀을 추적한다. 결과물은 픽셀 애니메이션과 PNG 스프라이트 시트이지 GLB가 아니다. ASF 브리지는 내장 배우를 빼고 효과만 렌더한다. 게임 고유 캐릭터를 쓰려면 자신의 공격 애니메이션을 별도로 재생하고, `act`/시트 메타데이터의 `windup`, `hits`, `freeze` 타이밍에 맞춰 게임을 멈추거나 반응시키는 것은 호스트가 맡는다. 따라서 **pixelfx는 여섯 캐릭터 액션의 원화 유지·생성 경로가 아니며, FX 보강 경로**다.

## 우리 Pixel Asset Pipeline 0.2.1과의 차이

실제 설치본의 CLI 도움말은 `build`, `variant`, `compare`, `sheet`, `tile`, `effect`, `validate`를 보여준다. 요청 중심의 해당 명령은 다음 용도다.

| 설치된 명령 | 실제 수행 범위 | 액션 세트와의 관계 |
| --- | --- | --- |
| `sheet --request <json> --out <new>` | 요청에서 1~64개의 RGBA 프레임 PNG 경로, 프레임별 `duration_ms`, 공통 `pivot_px_from_top_left`, loop 값을 읽는다. 프레임은 크기가 같아야 하고 픽셀을 변경하지 않고 가로 시트로 붙인 다음 다시 잘라 바이트 동일성을 검사한다. PNG·JSON 계약·GIF 미리보기를 반환한다. | 프레임이 이미 있어야 한다. 마스터 PNG에서 포즈를 생성·예측·움직이게 하지 않으며 한 번의 요청은 한 시퀀스 시트다. 같은 계약을 여섯 액션별로 호출해 각각 묶을 수 있지만 이는 포장 자동화일 뿐 여섯 동작을 만드는 기능이 아니다. pixelfx가 만든 PNG를 프레임별로 먼저 추출하면 포장할 수 있지만, 직접 upstream 메타데이터를 읽거나 ASF의 출처/크레딧 파일을 생성하는 연결은 없다. |
| `effect --request <json> --out <new>` | 현재 preset은 코드로 그리는 `pickup` 10프레임(60ms/프레임, 끝 프레임 투명)과 반복 `flame` 12프레임(80ms/프레임)이다. 지정 팔레트·시드로 로컬 생성한다. | 픽셀 이펙트 예시이며 캐릭터 신체 애니메이션이나 pixelfx 카탈로그 연동은 아니다. |
| `build --draft <png>` / `validate` / `variant` | 각각 정적 PNG 제작 초안 정리, 정적 PNG 검사, 승인 몸체에 장비 PNG 붙이기를 한다. 로컬 초안 흐름은 이미지 업로드가 없다. | 동영상에서 프레임을 키잉·정합·타이밍하는 파이프라인이 아니다. 현재 0.2.1에는 video CLI 또는 pixelfx 브리지 명령이 없다. |

워크스페이스의 기존 걷기 예시는 [`assets/examples/production/walk/author_frames.py`](../examples/production/walk/author_frames.py)가 만든 네 PNG를 [`request.json`](../examples/production/walk/request.json)으로 묶어 [`sheet` 결과](../examples/production/walk/result/sheet.png)와 미리보기를 둔다. 브라우저 게임 예제는 실제 4프레임 걷기 시트를 재생한다. 이는 수작업 코드로 만든 프레임을 포장·검수하는 증거이지, ASF처럼 승인 원화에서 연속 동영상을 생성한 증거는 아니다. 계약과 출력 경계는 [로컬 `sheet.py`](../src/pixel_asset_pipeline/sheet.py), [0.2 제작 계약](asset-production-plan.md), [README](../README.md)에 있다.

## 코드 아트로 할 수 있는 것과 PNG에서 할 수 없는 것

ASF의 [`codeart2d` 스킬](https://github.com/0x0funky/agent-sprite-forge/blob/6b3da5c444363378e20f3fce130ebecc22f343dd/skills/codeart2d/SKILL.md)은 사용자 요청 또는 이미지·영상 라우트가 없을 때만 쓰는 명시적 대체 경로다. [`rig-animation.md`](https://github.com/0x0funky/agent-sprite-forge/blob/6b3da5c444363378e20f3fce130ebecc22f343dd/skills/codeart2d/references/rig-animation.md)에 따르면 작은 캐릭터(가시 높이 약 48px 이하)를 위해 사람이 휴대용 SVG rig(본·관절·도형·피벗)와 `rig_anim.v1` 키프레임/2본 IK 사양을 직접 작성하고 스크립트가 프레임·루프·접지 검사·클립을 렌더한다. idle/walk 등 여러 클립을 새 코드 그림으로 만들 수 있지만 문서 자체가 puppet 같은 절단 인형 인상과 단순한 캐릭터에 맞는다고 제한한다.

승인된 PNG를 이 도구에 넣으면 자동으로 본·스킨 가중치를 추출하거나 원본 얼굴·의상 픽셀을 보존하는 기능은 확인되지 않았다. portable SVG rig는 `<image>`를 거부한다. 따라서 기존 PNG를 “시각 참고”로 삼아 사람이 비슷한 SVG/PixelSpec 그림을 다시 그릴 수는 있지만, 이 결과는 그 PNG의 변형·재사용이 아니라 별도로 코딩한 아트다. 실루엣·얼굴·옷 디테일을 동일하게 유지한다고 약속할 수 없고 결과는 code-drawn으로 공개한다. 승인 그림의 정체성을 그대로 지켜야 한다면 프레임을 직접 그려 `sheet`로 묶거나, 마스터 기준 image-to-video 경로가 필요하다.

## 최소 로컬 경로와 채택 선택지

1. **승인된 그림을 유지하고 간단히 납품:** 사용자/아티스트가 액션별 투명 PNG 프레임을 준비한다. 로컬 `sheet` 요청은 각 액션마다 프레임 순서·시간·피벗·loop를 선언해 시트로 묶을 수 있다. 여섯 액션의 각 프레임은 별도로 저작해야 하며, 이 단계에는 생성이나 관절 보간이 없다.
2. **완전 로컬, 별도 코드 캐릭터:** 사용자가 code-art를 선택한 경우에만 새 SVG rig와 여섯 동작 키프레임을 직접 정의하고 로컬 렌더한다. 작은 단순 캐릭터용이며 승인 PNG와 시각적으로 같다고 보장하지 않는다. 현재 우리 0.2.1에는 ASF `rig_animate.py`에 해당하는 rig 제작기가 없다.
3. **pixelfx 연동:** 히트/마법/수집 같은 단독 FX가 필요하면 선택형 pixelfx 외부 체크아웃 브리지를 추가하는 것이 맞다. ASF의 `fx_pixelfx.py`가 구체적 선례다. 설치하지 않고 현재 API로 바로 쓸 수는 없고, 도입 시 효과 코드의 출처·커밋·`CREDITS.txt` 전달을 구현해야 한다. 이 경로는 여섯 인물 액션을 대체하지 않는다.
4. **ASF에 가까운 동일 캐릭터 여섯 동작:** 별도 image-to-video 라우트(또는 사용자가 제공한 여섯 클립)와 키잉·정합·프레임 QC·루프/리타이밍·마감·내보내기 층이 필요하다. 영상 생성은 연결된 API/도구가 허가·설정된 경우만 선택할 수 있다. 현재 Pixel Asset Pipeline 0.2.1은 이 기능을 구현하지 않았다.

따라서 현재 제작기에 추가할 수 있는 가장 작은 충실한 기능은 **이미 준비된 `action_id`별 PNG 프레임 목록을 받아 각 동작 시트를 만들고 하나의 manifest로 묶는 것**이다. 원본 approved PNG에서 프레임을 만들도록 요구하면 새 영상 생성기 또는 새 코드 rig가 필요하므로 범위가 달라진다.

## 소스 코드·출력 고지

- Agent Sprite Forge 코드·문서는 저장소 [MIT LICENSE](https://github.com/0x0funky/agent-sprite-forge/blob/6b3da5c444363378e20f3fce130ebecc22f343dd/LICENSE)를 따른다. upstream `THIRD_PARTY_NOTICES.md`는 저장소에 pixelfx 구현 코드를 복사하지 않고 별도 사용자의 pixelfx 체크아웃을 호출한다고 밝힌다.
- pixelfx 자체 라이선스는 [`LICENSE`](https://github.com/patch-gg/pixelfx/blob/a84159688af3ca37a4be05a0d422b94451b2e24/LICENSE)의 MIT다. [`NOTICE.md`](https://github.com/patch-gg/pixelfx/blob/a84159688af3ca37a4be05a0d422b94451b2e24/NOTICE.md)는 `src/core/sim.js`와 해당 표시가 있는 효과의 Sprite Fusion/Hugo Duprez 유래 코드, `src/core/act.js`의 Hollow Crown/rehan-remade 유래 액팅 방식을 따로 알린다. 갤러리의 [Patch Pixel 폰트 고지](https://github.com/patch-gg/pixelfx/blob/a84159688af3ca37a4be05a0d422b94451b2e24/gallery/fonts/NOTICE.md)는 이 MIT 적용 대상이 아니며 ASF 브리지도 그 폰트를 사용하지 않는다.
- ASF 브리지로 뽑은 pixelfx 효과는 브리지의 `CREDITS.txt`와 `fx.json`을 프레임과 함께 유지하고 게임 크레딧에 pixelfx를 표시하라고 `THIRD_PARTY_NOTICES.md`가 지시한다. 순수 pixelfx upstream renderer는 자체 시트와 JSON을 만들며, 이 별도 크레딧 번들은 **ASF 브리지의 출력**이다.
- 코드 라이선스는 생성 이미지/영상 제공자의 이용조건을 대체하지 않는다. 참조 PNG의 저작권·사용 허가, 영상 제공자의 계약, 결과물의 제3자 IP 유사성은 별도로 확인해야 한다. 본 조사는 파일을 설치·복사하거나 이미지/영상을 외부 제공자에게 전송하지 않았다.

## 설치본 검증

위 0.2.1 비교는 기능 추가 전 기준이다. 이번 로컬 구현은 Pixel Asset Pipeline 0.3.2의 `action-set`이다. [입력과 출처](../../examples/scout-actions/README.md), [프레임 복원 검사](../../examples/scout-actions/evidence/atlas-check.json), [브라우저 재생 측정](../../examples/scout-actions/evidence/final-browser.json)에서 확인할 수 있다. 공식 pixelfx의 로컬 렌더러로 생성한 효과를 사용했고, Agent Sprite Forge 영상 생성 서비스·코드·쇼케이스 에셋은 사용하지 않았다.
