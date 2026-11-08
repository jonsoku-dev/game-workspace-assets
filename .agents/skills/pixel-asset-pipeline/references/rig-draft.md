# rig-draft · 제한된 중립 정면 인물의 검토용 6부위 제안

이 명령은 이미 1×인 스프라이트의 실루엣을 분석해 편집 가능한 마스크와 관절 초안을 만든다. 보이는 픽셀만 정확히 나누며 새로운 그림이나 가려진 몸을 만들지 않는다. 부드러운 원본은 먼저 snap으로 정리하고 결과를 검토한다.

```json
{"schema_version":1,"source":"relaxed-sprite.png"}
```

```sh
pixel-asset rig-draft --request rig-draft.json --out rig-draft-out
```

입력은 요청 폴더 안의 로컬 정적 PNG다. 각 축 16~128px, 이진 알파, 투명 여백이 필요하다. 정면 중립 자세에서 전체 몸이 하나로 연결돼 있고, 팔 둘이 몸통과 떨어져 보이는 연속 3개 이상의 행과 다리 둘이 분리된 마지막 3개 이상의 행을 요구한다. 머리·목·연결된 어깨·허리의 행 구조와 좌우 실루엣의 유사도도 검사한다. 이 조건을 벗어난 측면, 포개진 팔·다리, 무기·떨어진 이펙트, 비대칭 행동 자세나 모호한 분리는 거부한다. 이런 입력은 일반 motion의 명시적 리그로 직접 저작한다.

목의 잘록한 지점이 모호하면 사람이 확인한 `guides`를 추가할 수 있다. `neck_y`, `shoulder_y`, `hip_y`는 각각 원본 좌상단 기준 정수 행이며 선택적이다. 어깨 가이드는 관측된 연결 어깨 밴드 안, 엉덩이 가이드는 팔 밴드 아래와 실제 다리 분리 행 사이여야 한다. 가이드가 분리되지 않은 팔다리를 자동으로 만들어 주지는 않는다.

```json
{"schema_version":1,"source":"relaxed-sprite.png","guides":{"neck_y":22,"shoulder_y":25,"hip_y":42}}
```

출력은 다음과 같다.

- 캡처한 입력 바이트 그대로의 `master.png`와 정확한 가시 픽셀 중립 복원 `neutral.png`.
- torso, head, arm_left, arm_right, leg_left, leg_right의 6개 이진 grayscale 마스크. 각 원본 불투명 픽셀은 정확히 한 부위에 속한다.
- `joint-preview.png`: 원본 1×, 최근접 확대 관절 번호, 색으로 구분한 마스크 배정. 좌우는 그림의 좌우이며 해부학적 좌우를 인증하지 않는다.
- `rig-draft.request.json`: 출력 폴더의 원본·마스크를 참조하는 실제 motion 입력. **항상 approved:false다.**
- `inspection.json`: 캡처한 원본·요청 해시, 실루엣 범위와 대칭 지표, 관측된 팔·다리 분리, 제공/제안 가이드, 부위별 픽셀 수와 마스크 해시, 정확한 배정·중립 복원 검사.

먼저 관절 시트와 각 마스크에서 머리/목 경계, 어깨, 팔의 몸통 픽셀 오배정, 허벅지·발을 확인한다. 마스크와 관절은 motion의 일반 입력이므로 직접 수정 가능하다. 마스크가 바뀌면 중복·누락을 포함한 motion 검사를 다시 받아야 한다. 사용자 또는 지정된 검토자가 새 원본과 제안을 명시적으로 확인한 뒤에만 출력 요청의 approved를 true로 변경하고 실행한다.

```sh
pixel-asset motion --request rig-draft-out/rig-draft.request.json --out reviewed-motion
pixel-asset action-set --request reviewed-motion/action-set.request.json --out reviewed-actions
```

수정하지 않은 출력 요청에 위 motion 명령을 실행하면 승인이 없다는 오류가 난다. `inspection`의 `visual_review`와 `anatomical_review`는 required이고 아트 승인은 unverified다. 6개의 관측 기반 컷아웃 제안이며 17뼈·해부학 자동 인식·자동 승인을 주장하지 않는다. 행 분리와 대칭이 맞아도 시각적으로 적절한 리그라는 보장은 없다.

요청은 1 MiB, 원본 파일은 16 MiB, 디코드는 128²픽셀 상한이다. 원본을 캡처한 바이트로 디코드·해시하므로 해시와 분석한 그림이 일치한다. 원본을 변경하지 않고 공통 비덮어쓰기 게시 경로를 사용한다.
