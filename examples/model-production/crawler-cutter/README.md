# METALCUT 절삭기 · 파라메트릭 조립 예시

METALCUT 2D 팩의 분해식 절삭기를 `schema_version: 2` 조립 소품으로 다시 만든 예시다. 청회색 강철 본체·트랙, 탈착하는 주황 법랑 외장과 반원 가드, 구리 플라이휠·축 캡, 회전 톱날, 발광 램프로 구성된다.

```sh
python3 ../../../plugins/model-assets/tools/build.py --request request.json --out /tmp/crawler-cutter
```

- `review.png`: 네 방향·위·128px 게임 크기·분해도(외장 들림, 가드 탈착)·톱날 회전과 외장 열림 표본.
- `preview.png`: 3/4 정면 768px.
- `build-summary.json`: 실제 빌드 결과. 1.422×0.46×0.511m, LOD0 4044 / LOD1 1988 / LOD2 1062 삼각형, 1024px 공유 아틀라스, `blade_spin`·`shell_open`·`guard_detach` 애니메이션, 컴파일 뒤 별도 노드로 남는 움직이는 부품, 부품별 텍셀 밀도와 접합 거리.

2D 원화에서 "가드 볼트가 허공에 떠 있다"고 지적된 문제는 이 경로에서 `floating-part` 게이트로 막힌다. 처음 요청에서 톱날이 암을 관통하고 트랙이 공중에 뜨던 배치는 브래킷과 상대 좌표로 고쳤다. 1800rpm 회전은 30fps에서 프레임마다 정확히 한 바퀴라 멈춰 보였기 때문에 요청 단계에서 거부되며, 예시는 240rpm이다.

블록아웃 이상의 세부(트랙 링크, 볼트, 게이지)는 아직 없다. 측정 통과와 검수 시트는 외형 승인이 아니며 `artistic_acceptance`는 pending이다.
