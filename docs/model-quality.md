# 등불 모델의 외형 기준

첫 모델을 실제 브라우저에서 보니 앞면의 주황색 사각형이 몸통에 붙은 판처럼 읽혔다. 청록 몸통이 뒤를 완전히 가려 옆에서 내부 광원을 볼 수 없었다. 손잡이와 금속 띠는 보였지만 기능이 다른 부분의 외형과 재질 차이가 작았다. Blender 왕복과 Three 렌더 검사는 이 문제를 발견하지 못한다.

## 레퍼런스에서 가져온 제작 방식

| 자료 | 원문의 방법 | 등불에 적용한 판단 |
| --- | --- | --- |
| [첨부 create-game-assets](https://github.com/gamedev-skills/awesome-gamedev-agent-skills/blob/19d93f97c9c1ea0f8b306e77aa81e0d3e352d3e9/skills/disciplines/create-game-assets/SKILL.md) | 게임 카메라·표시 크기와 재질 역할을 먼저 정한다. 대표 에셋 하나를 실제 배경에서 검토한 뒤 같은 계열을 만든다. | 실루엣 안에서 연료통, 유리실, 윗뚜껑, 손잡이를 구분할 수 있어야 한다. |
| [로컬 blender-image-to-3d](/Users/jongseoklee/.codex/skills/blender-image-to-3d/SKILL.md) | 참조 시점·실측 비례·추정한 면을 분리한다. 블록아웃과 형태 단계에서 정면·측면·사선을 비교하고 게임 크기에서도 읽는다. 직교 레퍼런스가 있으면 실루엣 정렬·비례를 측정한다. | 첨부 화면은 등불의 도면이 아니므로 이번 30cm 비례와 곡면은 새로 설계했다. 참조 실루엣 일치율은 산출하지 않았다. |
| [Blender Bevel](https://docs.blender.org/manual/en/latest/modeling/modifiers/generate/bevel.html) · 로컬 Frameforge modeling/review | 면 사이 모서리의 실제 너비와 세그먼트를 제어한다. Frameforge는 형상을 먼저 확인한 후 여러 각도에서 조명과 표면을 검토한다. | 윤곽이 달라지는 부분은 회전 단면과 굽은 관으로 만들고, 얇은 테두리가 빛을 받도록 한다. |
| [Khronos 허리케인 램프](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/GlassHurricaneCandleHolder) · [glTF PBR 예제](https://github.khronos.org/glTF-Tutorials/gltfTutorial/gltfTutorial_014_AdvancedMaterial.html) | 유리 샘플은 투과와 체적 감쇠를 구분하고 여러 엔진에서 비교한다. PBR 예제는 반사 거칠기·금속성·발광이 서로 다른 역할을 보여 준다. | 유리벽 안에 버너와 불꽃을 두고, 도장 금속과 황동의 반사가 조명 방향에 따라 구별되는지 검사한다. 실제 Three 렌더에서 내부가 가려지면 소스 재질·두께·조명을 다시 본다. |

스프라이트 제작, 픽셀로 출력하는 골격·IK, Godot/Bevy의 엔진 조명과 배치를 별도 범위로 둔 이유와 원본 라이선스는 [3D 레퍼런스](model-references.md)에 있다. 참조 모델·텍스처·폰트는 복사하지 않았다. Khronos의 유리 샘플은 Wayfair 모델·텍스처에 CC BY 4.0을 명시한다.
