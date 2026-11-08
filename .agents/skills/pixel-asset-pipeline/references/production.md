# 2D 에셋 제작 계약

아래 예시는 로컬 실행 흐름이다. JSON 블록을 해당 예시의 `--request` 파일로 저장하고, PNG·프로필·기존 번들 경로를 준비한다. JSON 내부의 상대 경로는 요청 파일을 기준으로, 명령행의 상대 경로는 작업 폴더를 기준으로 해석한다. 제작 명령은 새 출력 폴더에 게시하고 stdout 한 줄의 JSON에 파일 목록을 반환한다. 입력 오류는 종료 코드 2로 보고한다.

## build · 정적 캐릭터·아이콘·아이템

```json
{"schema_version":1,"kind":"character","prompt":"이끼색 후드와 장화를 갖춘 숲 정찰병","profile":"style.json","size":48}
```

```sh
pixel-asset build --request build.json --draft source.png --out scout
```

투명한 로컬 초안 PNG와 공유 프로필을 사용한다. 프로필에도 schema_version 1을 넣고 palette, style, view, outline을 지정할 수 있다. 개별 요청의 값이 우선한다. 프로필이 없으면 profile 필드를 생략한다. character 기본값은 48px/16색, icon은 24px/12색, item은 32px/24색이다. max_colors로 상한을 줄일 수 있다. 독립 생성은 --draft 대신 --codex를 명시한다. 성공 결과는 asset.png, preview.png, metadata.json, validation.json, draft.png이다.

## validate · 기존 정적 PNG 검사

```sh
pixel-asset validate --request build.json scout/asset.png
```

위 build 요청을 재사용한다. 출력 파일을 쓰지 않고 검사 결과 JSON을 stdout으로 반환한다. 규격을 만족하면 종료 코드 0, 완성 PNG가 검사에서 탈락하면 1, 잘못된 입력이나 실행 오류이면 2다.

## variant · 기준 캐릭터의 장비 교체

```json
{"schema_version":1,"base":"scout/asset.png","base_metadata":"scout/metadata.json","equipment":"gear/staff.png","anchor":[36,31],"offset":[-3,-28],"allowed_region":[35,2,46,44],"allowed_occlusion":[[35,29,38,34]]}
```

```sh
pixel-asset variant --request variant.json --out variant-out
```

장비 PNG의 좌상단은 anchor + offset이다. 모든 좌표는 원본 좌상단 픽셀 기준이며 사각형의 오른쪽과 아래끝은 제외한다. allowed_region은 장비를 그릴 수 있는 영역, allowed_occlusion은 기존 불투명 몸을 가려도 되는 영역이다. 장비는 기준 캐릭터에서 실제 사용한 색과 이진 알파를 쓴다. 발과 투명 여백을 유지하며 다시 크롭하거나 확대하지 않는다. 장비 필드를 모두 생략하면 기준형을 내보낸다. 결과는 asset.png, preview.png, metadata.json, validation.json이다.

## compare · 별도 제작한 세트의 시각 비교

```json
{"schema_version":1,"name":"Woodland","assets":[{"id":"scout","label":"Scout","bundle":"scout","reference":{"path":"art/scout.png","provenance":"existing woodland atlas"}},{"id":"acorn","label":"Acorn","bundle":"acorn"}]}
```

```sh
pixel-asset compare --request compare.json --out compare-out
```

정적 build 번들 2~12개를 비교한다. 생성된 PNG를 재검증하고 원본·결과 해시와 선언된 출처를 manifest.json에 적는다. 참조 이미지는 같은 native 크기의 로컬 PNG다. contact-sheet.png에서 같은 피벗으로 1×와 4×를 본다. 서로 다른 원본 해시는 호출 횟수나 외형의 일관성을 보증하지 않으므로 실제 생성 기록과 함께 해석한다.

## sheet · 동작 프레임 묶음

```json
{"schema_version":1,"frames":[{"path":"step-a.png","duration_ms":130},{"path":"step-b.png","duration_ms":110}],"pivot_px_from_top_left":[24,46],"loop":true}
```

```sh
pixel-asset sheet --request sheet.json --out sheet-out
```

같은 크기·같은 격자의 실제 포즈 PNG를 순서대로 준비한다. 팔·다리가 움직여도 몸을 프레임마다 새로 맞추지 않는다. 1~64장의 픽셀을 그대로 수평 시트에 넣고 각 프레임을 다시 잘라 내용이 일치하는지 확인한다. sheet.png와 sheet.json의 rect·duration_ms·pivot·loop가 엔진용 계약이다. preview.gif는 미리보기로서 GIF 시간 단위로 반올림한다. 매우 긴 동일 자세는 GIF 지연 한도까지 보인다.

## tile · 불투명 지형 반복

```json
{"schema_version":1,"source":"grass.png","size":32,"palette":["#425e3a","#52723e","#668344"],"max_colors":3}
```

```sh
pixel-asset tile --request tile.json --out tile-out
```

정사각형 원본 크기, 완전한 불투명도, 지정 팔레트와 최대 12색을 검사한다. 타일 외곽까지 그대로 보존하고 가로·세로 반복 경계의 색 변화량을 내부와 비교한다. tile.png, repeat.png(3×3 반복의 정수배 미리보기), metadata.json, validation.json을 반환한다. 자연스러운 패턴·서로 다른 타일 연결은 사람이 반복 보기에서 확인한다.

## effect · 1회 반짝임과 반복 불꽃

```json
{"schema_version":1,"preset":"pickup","size":32,"palette":["#64754b","#e5ad57","#fff1d0"],"seed":17}
```

```sh
pixel-asset effect --request effect.json --out effect-out
```

`pickup`은 10프레임 × 60ms이며 마지막 프레임은 투명하다. `flame`은 12프레임 × 80ms의 반복 불꽃이다. size는 16~64px, 팔레트는 바깥색에서 중심색 순서로 서로 다른 3~8색이다. 시드와 입력이 같으면 같은 소스 픽셀을 만든다. 효과는 중심 원점과 프레임 전체 격자를 유지한다. 한 픽셀짜리 불티와 빈 종료 프레임을 보존한다. 출력은 sheet.png, sheet.json, preview.gif, effect.json이다.

## action-set · 캐릭터 6동작과 접촉 효과

```json
{
  "schema_version": 1,
  "cell_size": [
    48,
    48
  ],
  "pivot_px_from_top_left": [
    24,
    46
  ],
  "actions": {
    "idle": {
      "loop": true,
      "frames": [
        {
          "path": "idle-1.png",
          "duration_ms": 80
        },
        {
          "path": "idle-2.png",
          "duration_ms": 120
        }
      ]
    },
    "walk": {
      "loop": true,
      "frames": [
        {
          "path": "walk-1.png",
          "duration_ms": 80
        },
        {
          "path": "walk-2.png",
          "duration_ms": 120
        }
      ]
    },
    "run": {
      "loop": true,
      "frames": [
        {
          "path": "run-1.png",
          "duration_ms": 80
        },
        {
          "path": "run-2.png",
          "duration_ms": 120
        }
      ]
    },
    "attack": {
      "loop": false,
      "frames": [
        {
          "path": "attack-1.png",
          "duration_ms": 80
        },
        {
          "path": "attack-2.png",
          "duration_ms": 120
        }
      ]
    },
    "jump": {
      "loop": false,
      "frames": [
        {
          "path": "jump-1.png",
          "duration_ms": 80
        },
        {
          "path": "jump-2.png",
          "duration_ms": 120
        }
      ]
    },
    "hurt": {
      "loop": false,
      "frames": [
        {
          "path": "hurt-1.png",
          "duration_ms": 80
        },
        {
          "path": "hurt-2.png",
          "duration_ms": 120
        }
      ]
    }
  },
  "events": []
}
```

```sh
pixel-asset action-set --request actions.json --out scout-actions
```

동작별로 그린 로컬 PNG를 요청 폴더 안에 준비한다. 캐릭터 셀과 발 피벗은 여섯 동작에 공통이다. 처음 세 동작은 반복하고 공격·점프·피격은 한 번 재생한다. `events`에 다음과 같은 객체를 넣으면 접촉 프레임부터 별도 pixelfx 시트를 재생한다. frame은 0부터 세며 시작 시각은 앞선 캐릭터 프레임 시간의 합이다. at_px와 effect_anchor_px는 각각 캐릭터 셀과 효과 프레임의 좌상단 기준이다. 지정한 효과 접점과 pixelfx가 기록한 원래 바닥 피벗은 각각 유지한다.

```json
{"action":"attack","frame":1,"sheet":"fx/hit.png","metadata":"fx/hit.json","license":"fx/LICENSE","notice":"fx/NOTICE.md","at_px":[46,25],"effect_anchor_px":[44,44]}
```

캐릭터 아틀라스, 액션별 프레임·시간·이벤트 메타데이터, 합성 재생 미리보기와 효과 고지는 stdout의 상대 파일 목록으로 전달된다. 프레임 저작과 게임 판정은 호출자가 맡는다.

각 캐릭터 동작에는 최대 64프레임, 이벤트 하나의 pixelfx 시트에는 최대 256프레임을 쓴다. 루프의 끝을 지나는 효과는 다음 접촉까지 이어지며, 같은 이벤트가 다시 시작되면 최신 접촉에서 재생을 시작한다. GIF는 한 번의 동작과 그 효과의 꼬리를 보여 준다. 미리보기의 픽셀·시간 예산을 넘는 극단적인 입력은 CLI가 오류를 반환한다. 정확한 프레임 시간은 JSON에서 읽는다.

## motion · 승인된 원본의 로컬 관절 동작 제작

```json
{
  "schema_version": 1,
  "approved": true,
  "master": "motion-master.png",
  "pivot_px_from_top_left": [
    24,
    41
  ],
  "rig": {
    "parts": [
      {
        "id": "body",
        "role": "torso",
        "parent": null,
        "anchor_px": [
          24,
          24
        ],
        "rect": [
          21,
          18,
          7,
          13
        ]
      },
      {
        "id": "head",
        "role": "head",
        "parent": "body",
        "anchor_px": [
          24,
          18
        ],
        "rect": [
          20,
          11,
          9,
          7
        ]
      },
      {
        "id": "left",
        "role": "arm_left",
        "parent": "body",
        "anchor_px": [
          20,
          20
        ],
        "rect": [
          17,
          20,
          4,
          11
        ]
      },
      {
        "id": "right",
        "role": "arm_right",
        "parent": "body",
        "anchor_px": [
          28,
          20
        ],
        "rect": [
          28,
          20,
          4,
          11
        ]
      },
      {
        "id": "legl",
        "role": "leg_left",
        "parent": null,
        "anchor_px": [
          23,
          31
        ],
        "rect": [
          21,
          31,
          3,
          10
        ]
      },
      {
        "id": "legr",
        "role": "leg_right",
        "parent": null,
        "anchor_px": [
          26,
          31
        ],
        "rect": [
          25,
          31,
          3,
          10
        ]
      }
    ]
  }
}
```

```sh
pixel-asset motion --request motion.json --out motion-out
```

이 예시는 48×48 투명 PNG `motion-master.png`에 여섯 rect의 불투명 직사각형만 그린 자가 제작 대조군을 사용한다. rect는 `[x,y,width,height]`이며 몸·머리·왼팔·오른팔·왼다리·오른다리를 각각 독립 색으로 칠한다. 실제 캐릭터에서는 승인된 원본과 해부학에 맞게 리그를 작성한다. `approved:true`는 호출자가 원본 사용을 승인했다는 선언이며, 출력 아트의 자동 승인이 아니다.

원본은 4~128px, 이진 알파이며 투명·불투명 픽셀이 모두 있어야 한다. 모든 불투명 픽셀을 2~24개 부위에 정확히 한 번 배정한다. `rect` 대신 같은 크기의 0/255 grayscale PNG `mask`를 쓸 수 있다. 부모는 자식보다 앞에 선언하고 `anchor_px`는 원본 좌상단 기준 관절이다. 부위 순서가 합성 순서다. `role`은 torso, head, arm_left, arm_right, leg_left, leg_right, weapon, accessory 중 하나이며 팔이나 다리가 적어도 하나 필요하다. 가려진 픽셀이나 새로운 신체를 추론하지 않는다. 관절 틈이나 가림 문제가 생기면 원본 저작 단계에서 명시적으로 보완한 뒤 새 승인 원본으로 재시작한다.

기본 동작은 idle·walk·run·attack·jump·hurt다. 네이티브 격자에서 역방향 최근접 샘플링하며 원본 팔레트와 이진 알파를 보존한다. `neutral.png`는 투명 RGB를 0으로 정규화한 원본과 정확히 일치해야 한다. 프레임 PNG와 `action-set.request.json`, `inspection.json`을 반환한다. 다음 명령으로 엔진용 아틀라스와 동작별 GIF를 만든다.

```sh
pixel-asset action-set --request motion-out/action-set.request.json --out motion-actions
```

검수는 `motion-actions`의 원속도 GIF와 원본 1× 포즈에서 한다. inspection의 `clipped_part_pixels`, `unique_poses`, `duplicate_frames`, `unmarked_adjacent_duplicates`, `loop_seam_changed_pixels`, `contact_error_px`를 함께 읽는다. 접촉값은 측정한 관절/랜드마크와 목표의 차이이며 발을 고정하는 역운동학이 아니다. 잘림이 있어도 번들은 게시되지만 `passed:false`와 `needs-clipping-review`이므로 채택 전에 수정한다. `visual_review`와 `artistic_acceptance`는 자동으로 승인되지 않는다.

문제가 있는 동작만 요청의 `actions`에 덮어쓴다. 예를 들어 attack의 접촉을 조정하려면 기존 요청에 아래 필드를 추가하고 `--out motion-repair` 같은 새 경로에 `motion`을 재실행한다. 다른 다섯 동작의 기본 제작은 유지된다.

```json
{"actions":{"attack":{"frames":[{"duration_ms":100,"parts":{"left":{"angle_deg":-45}}},{"duration_ms":180,"parts":{"left":{"angle_deg":90}}},{"duration_ms":100,"parts":{"left":{"angle_deg":90}},"hold":true}]}}}
```

```sh
pixel-asset motion --request motion.json --out motion-repair
pixel-asset action-set --request motion-repair/action-set.request.json --out motion-repair-actions
```

각 동작은 2~32프레임이며 각 프레임은 `duration_ms`, 선택적 `parts`(부위별 `angle_deg` ±180°, `offset_px` 각 축 ±32), `root_offset_px` 각 축 ±32, `contacts`, `hold`를 받는다. `contact_px`를 부위에 지정하면 그 원본 랜드마크를 측정하고, 생략하면 관절을 측정한다. 예를 들어 부위 `legl`에 `contact_px:[23,40]`, 프레임에 `contacts:{"legl":[23,40]}`을 선언하면 발 목표 오차를 기록한다. 동작 시간 합은 120000ms 이하이며 프레임·연산 예산도 검사한다.

동일 자세를 오래 유지하려면 보통 한 프레임의 시간을 늘린다. 별도 정지 프레임이 필요하면 `hold:true`로 의도를 표시한다. 표시해도 중복 픽셀과 unique pose 수는 그대로 측정하며, 모든 프레임이 동일한 동작과 서로 같은 포즈 시퀀스의 동작은 거부한다. 역할 기반 기본 포즈는 해부학별 시각 검수가 필요한 시작점이다. 실제 게임 판정과 엔진 통합은 호스트 책임이다.

## snap · 확대 원화를 네이티브 픽셀 격자로 변환

```json
{"schema_version":1,"source":"soft.png","crop":[0,0,160,160],"grid_size":[40,40],"max_colors":16,"alpha_cutoff":128}
```

```sh
pixel-asset snap --request snap.json --out snapped
```

결과의 `asset.png`를 1×에서 확인한다. 승인한 그림을 리그에 사용할 때는 `motion` 요청의 master와 부위 좌표를 새 격자에 맞춘다. [샘플링 방식과 한계](snap.md)

## effect-clip · 기존 GIF 재편집

```json
{"schema_version":1,"source":"spell.gif","license":"spell-license.txt","notice":"spell-notice.txt","actor_cell_size":[40,40],"effect_size":[16,16],"pivot_px_from_top_left":[8,8],"background":{"mode":"preserve"},"phases":{"charge":[{"frame":0,"duration_ms":120}],"travel":[{"frame":1,"duration_ms":80}],"impact":[{"frame":2,"duration_ms":100}]}}
```

```sh
pixel-asset effect-clip --request clip.json --out spell
```

세 단계의 원본 인덱스와 길이를 정한다. 결과 시트·메타데이터·원본의 라이선스와 고지를 `action-set`의 접촉 이벤트에 연결한다. 선택 프레임이 이동을 표현하며, 게임의 투사체 물리·충돌은 해당 엔진이 소유한다. [배경 처리·프레임 합성 규칙](effect-clip.md)

## rig-draft · 정면 인물 리그 초안

```json
{"schema_version":1,"source":"relaxed-sprite.png"}
```

```sh
pixel-asset rig-draft --request rig.json --out joints
```

정면에서 팔·몸·다리 사이의 투명한 틈이 보이는 단일 원화를 사용한다. 초안의 마스크·부모·관절을 그림과 맞춰 확인하고 승인 후 motion 요청에 사용한다. [입력 가이드와 지원 자세](rig-draft.md)

## rive · 상태 머신으로 동작을 선택하는 캐릭터 파일

```json
{"schema_version":1,"size":[48,48],"actions":{"idle":{"loop":true,"frames":[{"path":"idle-1.png","duration_ms":160}]},"wave":{"loop":true,"frames":[{"path":"walk-1.png","duration_ms":120},{"path":"walk-2.png","duration_ms":120}]}}}
```

```sh
pixel-asset rive --request rive-poses.json --out rive-out
```

예시의 두 번째 동작에는 명령 검사용 기존 두 프레임을 넣었다. 실제 캐릭터는 원하는 동작의 원본 포즈를 지정한다. 한 장짜리 캐릭터 원화에서는 먼저 아래 순서로 준비한다. `motion` 출력의 `action-set.request.json`도 그대로 사용할 수 있다. 하나의 캐릭터를 같은 크기의 투명 PNG에 배치한다. 손·발·효과를 따로 움직이는 라이브 본은 내보내지 않는다.

`character.riv` 하나에 이미지와 모든 타임라인을 포함한다. 아트보드는 `Character`, 상태 머신은 `Character Actions`, Number 입력은 `action`이다. 입력값은 JSON에서 선언한 동작 순서대로 0부터 붙는다. `rive.json`에 각 값·동작명·길이·원본 프레임 지문을 기록한다. `loop:false`는 선택을 바꿀 때까지 마지막 포즈를 유지한다. `rive.Rive`로 파일을 열고 `stateMachineInputs("Character Actions")`에서 `action`의 값을 바꿔 실제 캔버스에서 확인한다.


캐릭터 몸이 연결되어야 할 때는 `motion` 입력에서 `single_body:true`를 지정한다. 별도 동작은 `extra_actions`에 `{"wave":{"loop":true,"frames":[…]}}` 형태로 넣는다. `frames`는 기존과 같은 관절별 회전·이동·재생 길이 배열이다. `motion`은 기존 여섯 동작을 위한 `action-set.request.json`도 계속 생성한다. 추가 동작까지 포함한 `rive-poses.json`과 기술 검사 결과를 확인한 뒤 다음과 같이 파일을 내보낸다.

```sh
pixel-asset motion --request art/motion.request.json --out builds/motion
pixel-asset rive --request builds/motion/rive-poses.json --out builds/rive
```

중립에서는 붙은 팔이 회전 중 떨어지면 해당 프레임의 `inspection.json`에서 분리된 픽셀의 면적과 위치를 본다. 필요하면 부위의 `joint_underlap`에 연결할 부모·자식 좌표 `parent_px`, `child_px`, 연결 폭의 반경 `radius_px`, 원화의 색 샘플 좌표 `source_px`와 선택 사항인 가장자리 색 `edge_px`를 둔다. 원화의 투명 영역과 팔레트를 유지하면서 소매와 관절이 겹치도록 조정하는 방식이다. 걷기와 달리기는 지지발과 들어 올린 발이 서로 뒤바뀌는지, 인사와 환호는 팔꿈치·어깨가 이어지는지 실제 재생 크기에서 검토한다.

## character · 개별 포즈에서 Rive 파일과 오프라인 재생 화면 만들기

```json
{"schema_version":1,"frames":"courier-cels.json","reference":"relaxed-sprite.png","actions":["wave","idle"],"title":"달빛 정류장","language":"ko"}
```

```sh
pixel-asset character --request courier-character.json --out courier-player
```

`frames`는 아래처럼 이미 그려 둔 완성 포즈의 목록이다. PNG 경로는 이 목록 파일이 있는 폴더 기준이다. `courier-cels.json`의 예시 값은 다음과 같다.

```json
{"schema_version":1,"size":[48,48],"actions":{"idle":{"loop":true,"frames":[{"path":"idle-1.png","duration_ms":180}]},"wave":{"loop":true,"frames":[{"path":"walk-1.png","duration_ms":100},{"path":"walk-2.png","duration_ms":120}]}}}
```

문서 실행 검사에는 기존 작은 테스트 이미지를 사용한다. 실제 캐릭터에는 손과 얼굴이 보이게 작화한 인사 포즈를 넣는다. 같은 그림을 한 박자 더 보여 주려면 해당 프레임의 시간을 늘리고, 순서를 바꾸거나 다른 PNG로 교체해 새 출력 폴더로 다시 실행한다. `reference`는 선택한 기준 원화를 기록한다. 요청의 `actions` 순서가 버튼과 상태 입력 순서다. `player.html` 한 파일에 공식 Rive 런타임·캐릭터를 포함해 브라우저로 열 수 있다. `character.riv`는 게임에 전달할 파일이다. `language`는 ko 또는 ja를 지원한다.

이미 관절·동작이 승인된 저작 요청이면 `frames` 대신 `motion_request`를 지정한다. 분리된 정면 인물에서 자동 리그의 동작 초안을 **명시적으로 원할 때만** `source`를 선택한다. 지원 자세 밖이거나 연결·잘림 검사에 실패하면 `needs_review`와 이유를 확인하고 원화에 맞는 리그나 개별 작화로 전환한다. 자동 초안으로 미술 승인을 대신하지 않는다.
