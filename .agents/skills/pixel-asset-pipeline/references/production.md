# 로컬 제작 계약

아래 명령은 모두 `pixel-asset 명령 --request 요청.json --out 새폴더` 형태이며 네트워크와 API 키 없이 실행한다. 요청에 `"schema_version": 1`을 넣고 입력 파일은 요청 파일 기준 상대 경로로 지정한다. 성공 시 stdout 한 줄의 JSON에서 `files`를 읽는다. 입력 오류는 stderr와 종료 코드 2로 보고하고 새 번들은 게시하지 않는다.

## variant · 기준 캐릭터의 장비 교체

```json
{"schema_version":1,"base":"scout/asset.png","base_metadata":"scout/metadata.json","equipment":"gear/staff.png","anchor":[36,31],"offset":[-3,-28],"allowed_region":[35,2,46,44],"allowed_occlusion":[[35,29,38,34]]}
```

장비 PNG의 좌상단은 anchor + offset이다. 모든 좌표는 원본 좌상단 픽셀 기준이며 사각형의 오른쪽과 아래끝은 제외한다. allowed_region은 장비를 그릴 수 있는 영역, allowed_occlusion은 기존 불투명 몸을 가려도 되는 영역이다. 장비는 기준 캐릭터에서 실제 사용한 색과 이진 알파를 쓴다. 발과 투명 여백을 유지하며 다시 크롭하거나 확대하지 않는다. 장비 필드를 모두 생략하면 기준형을 내보낸다. 결과는 asset.png, preview.png, metadata.json, validation.json이다.

## compare · 별도 제작한 세트의 시각 비교

```json
{"schema_version":1,"name":"Woodland","assets":[{"id":"scout","label":"Scout","bundle":"scout","reference":{"path":"art/scout.png","provenance":"existing woodland atlas"}},{"id":"acorn","label":"Acorn","bundle":"acorn"}]}
```

정적 build 번들 2~12개를 비교한다. 생성된 PNG를 재검증하고 원본·결과 해시와 선언된 출처를 manifest.json에 적는다. 참조 이미지는 같은 native 크기의 로컬 PNG다. contact-sheet.png에서 같은 피벗으로 1×와 4×를 본다. 서로 다른 원본 해시는 호출 횟수나 외형의 일관성을 보증하지 않으므로 실제 생성 기록과 함께 해석한다.

## sheet · 동작 프레임 묶음

```json
{"schema_version":1,"frames":[{"path":"step-a.png","duration_ms":130},{"path":"step-b.png","duration_ms":110}],"pivot_px_from_top_left":[24,46],"loop":true}
```

같은 크기·같은 격자의 실제 포즈 PNG를 순서대로 준비한다. 팔·다리가 움직여도 몸을 프레임마다 새로 맞추지 않는다. 1~64장의 픽셀을 그대로 수평 시트에 넣고 각 프레임을 다시 잘라 내용이 일치하는지 확인한다. sheet.png와 sheet.json의 rect·duration_ms·pivot·loop가 엔진용 계약이다. preview.gif는 미리보기로서 GIF 시간 단위로 반올림한다. 매우 긴 동일 자세는 GIF 지연 한도까지 보인다.

## tile · 불투명 지형 반복

```json
{"schema_version":1,"source":"grass.png","size":32,"palette":["#425e3a","#52723e","#668344"],"max_colors":3}
```

정사각형 원본 크기, 완전한 불투명도, 지정 팔레트와 최대 12색을 검사한다. 타일 외곽까지 그대로 보존하고 가로·세로 반복 경계의 색 변화량을 내부와 비교한다. tile.png, repeat.png(3×3 반복의 정수배 미리보기), metadata.json, validation.json을 반환한다. 자연스러운 패턴·서로 다른 타일 연결은 사람이 반복 보기에서 확인한다.

## effect · 1회 반짝임과 반복 불꽃

```json
{"schema_version":1,"preset":"pickup","size":32,"palette":["#64754b","#e5ad57","#fff1d0"],"seed":17}
```

`pickup`은 10프레임 × 60ms이며 마지막 프레임은 투명하다. `flame`은 12프레임 × 80ms의 반복 불꽃이다. size는 16~64px, 팔레트는 바깥색에서 중심색 순서로 서로 다른 3~8색이다. 시드와 입력이 같으면 같은 소스 픽셀을 만든다. 효과는 중심 원점과 프레임 전체 격자를 유지한다. 한 픽셀짜리 불티와 빈 종료 프레임을 보존한다. 출력은 sheet.png, sheet.json, preview.gif, effect.json이다.
