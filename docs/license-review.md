# 기업 사용·배포 라이선스 확인 기록

확인일: 2026-11-08. 사용자 요청에 따라 현재 확인 깊이에서 조사를 종료했다. 이 문서는 확인 자료와 후속 조치이며, 포괄적인 권리 보증이나 법률 의견은 아니다.

## 배포 범위

`scripts/package-plugin.py`의 허용 목록은 다음과 같다.

- `.codex-plugin/plugin.json`
- `.agents/plugins/marketplace.json`
- `.agents/skills/pixel-asset-pipeline/`
- `pyproject.toml`
- `src/pixel_asset_pipeline/` (`__pycache__`, `*.pyc` 제외)

따라서 이 스크립트의 현재 설계에서는 `.venv`, Pillow 휠·바이너리, Python, Node, Codex CLI, `examples`, 테스트, 빌드 결과물을 복사하지 않는다. `pyproject.toml`의 setuptools 패키지 검색 범위는 `src`이며 런타임 의존성은 `Pillow>=10,<13`, 빌드 의존성은 `setuptools>=68`이다. 선언된 버전 범위는 설치 버전을 고정하지 않는다. 플러그인 스테이징과 Python wheel/sdist는 다른 산출물이므로 별도로 확인해야 한다.

0.1 설치 묶음은 9개 파일이었다. 0.2 로컬 설치 묶음에는 자체 제작 모듈과 요청 규격 문서가 추가되어 허용 목록이 16개 파일이다. Codex 네이티브 생성을 호출하는 provider.py는 자체 구현이다. 생성할 때는 기존 ChatGPT 인증을 사용하고, 로컬 초안 처리에는 네트워크와 인증이 필요하지 않다. 외부 참고 스킬이나 별도 업체 서비스 클라이언트를 포함하지 않는다.

## 로컬에서 직접 확인한 의존성

| 대상 | 확인 결과 | 배포 시 처리 |
| --- | --- | --- |
| Pillow | `.venv` 설치 버전 **12.3.0**, METADATA `License-Expression: MIT-CMU`, `License-File: LICENSE` | 현재 플러그인에는 미포함. 휠을 함께 배포하면 휠의 전체 고지와 각 구성 요소 조건을 보존·검토 |
| Pillow 휠 | `cp313-cp313-macosx_11_0_arm64`, installer `uv`, generator setuptools 82.0.1 / delocate 0.13.0 | 다른 OS/휠은 내장 구성과 고지를 다시 확인 |
| Python | 로컬 실행기 3.13.3 | 실행기 자체를 묶을 때 해당 배포본의 PSF 및 제3자 고지 검토 |
| Node | 로컬 v26.7.0 | 예제 도구용 외부 실행기. 묶어 배포할 때 그 배포본 고지 검토 |
| Codex CLI | 로컬 `codex-cli 0.165.0` | 네이티브 생성 모드에서만 호출하는 외부 실행기. 바이너리를 동봉하지 않음 |
| setuptools | 빌드 선언 존재, 해당 `.venv` 설치 METADATA는 없음 | 실제 빌드 환경·최종 wheel/sdist를 별도 검사 |

Pillow 고지 파일은 `.venv/lib/python3.13/site-packages/pillow-12.3.0.dist-info/licenses/LICENSE`이다. 확인 당시 SHA-256:

`dda12a98c1979cf3d94df1cff45d27a4cb3f04a60c76f76902ac54cac03ec0ce`

이 파일에는 Pillow 외에 AOM, BROTLI, BZIP2, DAV1D, FREETYPE2, HARFBUZZ, LCMS2, LIBAVIF, LIBJPEG, LIBLZMA, LIBPNG, LIBTIFF, LIBWEBP, LIBYUV, OPENJPEG, RAQM, TCL_TK, XAU, XCB, XDMCP, ZLIB, ZSTD 고지가 있다. 이는 **고지에 있는 목록**이며 모든 항목이 이 휠에 개별 동적 라이브러리로 탑재되었다는 뜻은 아니다. 실제 `PIL/.dylibs`에는 FreeType, HarfBuzz, libavif, Brotli, libjpeg, lcms2, liblzma, OpenJPEG, libpng, libtiff, WebP, Xau, XCB, zlib-ng 등의 바이너리가 있었다.

Pillow 자체 MIT-CMU는 상업 사용을 배제하지 않으며 저작권·허가문 보존과 이름의 광고 사용 제한을 둔다. 휠을 재배포할 때는 Pillow 라이선스 하나만 표시하지 말고 전체 내장 고지를 함께 검토한다. 예를 들어 포함된 FreeType 고지는 FTL/GPL 선택지와 FTL의 문서 크레딧 조건을 설명한다. 이 검토에서 프로젝트에 새 라이선스를 임의로 선택하지 않았다. [Pillow 12.3.0 LICENSE](https://github.com/python-pillow/Pillow/blob/12.3.0/LICENSE), [Pillow 공식 설명](https://pillow.readthedocs.io/en/stable/about.html).

## 참고 저장소와 복사 여부

소스에서 제3자 저장소 파일·폰트·스크린샷 에셋을 의도적으로 가져와 배포하는 경로는 확인하지 못했다. 전체 upstream과의 파일 유사도 비교는 수행하지 않았으므로 비침해를 증명한 것은 아니다. 화면에 등장한 저장소는 참고 링크이며 배포 의존성이 아니다.

| 참고 저장소 | 현재 확인 수준 |
| --- | --- |
| [awesome-gamedev-agent-skills](https://github.com/gamedev-skills/awesome-gamedev-agent-skills) | [LICENSE](https://github.com/gamedev-skills/awesome-gamedev-agent-skills/blob/main/LICENSE)와 [NOTICE](https://github.com/gamedev-skills/awesome-gamedev-agent-skills/blob/main/NOTICE)에서 Apache-2.0과 저자 고지를 확인 |
| [Claude-Code-Game-Studios](https://github.com/Donchitos/Claude-Code-Game-Studios) | [MIT 고지](https://github.com/Donchitos/Claude-Code-Game-Studios/blob/main/LICENSE)를 확인 |
| [sprite-gen](https://github.com/aldegad/sprite-gen) | [Apache-2.0](https://github.com/aldegad/sprite-gen/blob/main/LICENSE)과 MIT 유래 코드·외부 구성 요소 관련 [NOTICE](https://github.com/aldegad/sprite-gen/blob/main/NOTICE)를 확인 |
| [Game-Dev-Agentic-Skills](https://github.com/thedivergentai/Game-Dev-Agentic-Skills) | 공식 [LICENSE](https://github.com/thedivergentai/Game-Dev-Agentic-Skills/blob/main/LICENSE)의 LGPLv3를 확인 |

향후 실제 파일을 가져올 경우 가져오는 **정확한 커밋**과 파일별 LICENSE/NOTICE를 먼저 기록한다. Apache 계열은 해당 라이선스·NOTICE·수정 표시 조건을, MIT 계열은 저작권·허가문 보존을, LGPL 계열은 실제 사용·수정·결합·배포 방식에 따른 조건을 원문 기준으로 검토한다. 확인한 대상은 main의 고지이며 커밋별·파일별 권리 실사는 수행하지 않았다.

0.2의 `patch-gg/pixelfx`는 설계 레퍼런스로 기록했다. MIT 적용 범위, 추가 저자와 갤러리 폰트의 예외는 [레퍼런스 표](references.md)에 링크했다. 이펙트 프레임과 렌더러는 이 프로젝트에서 작성했다. 외부 VFX 코드·폰트·새 라이브러리를 설치용 폴더에 동봉하지 않는다.

## 생성 이미지와 서비스 계약

woodland 아틀라스는 Codex 내장 이미지 도구로 생성했다. 독립 CLI 정찰병은 코드로 만든 배치 가이드를 사용했다. 스타일 참조 예제에는 생성한 아틀라스에서 추출한 정찰병을 추가했다. 사용자의 첨부 스크린샷은 입력하거나 패키지에 동봉하지 않았다. 예제는 배포 허용 목록 밖이다. 이미지의 원본성·독점성·제3자 IP 비침해는 별도로 검증하지 않았다. 결정적 축소가 원본의 권리 상태를 바꾸지는 않는다.

Codex 공개 **소프트웨어**의 Apache-2.0 라이선스와 OpenAI **서비스** 계약은 별개이다. 소프트웨어 라이선스가 구독·서비스 권한이나 이미지 권리를 대신 부여하지 않는다. [Codex LICENSE](https://github.com/openai/codex/blob/main/LICENSE)는 확인 시점의 main이므로 설치 0.165.0 배포본 전체 고지와의 일치까지 확인한 것은 아니다.

OpenAI 개인용 이용약관은 법이 허용하는 범위에서 OpenAI와 사용자 사이의 출력 권리 이전, 입력 권리 확보 책임, 비독점적 출력 가능성을 명시한다. 이는 제3자 권리 보증이 아니다. Business/Enterprise에는 Services Agreement가 적용되며 고객 콘텐츠를 명시적 동의 없이 서비스 개발·개선에 사용하지 않는 조항이 있다. 실제 회사 계약·워크스페이스·데이터 설정은 확인하지 않았다. [개인용 약관](https://openai.com/policies/terms-of-use/), [Services Agreement §4](https://openai.com/policies/services-agreement/), [Codex 데이터 설정 안내](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan).

## 남은 실무 확인

- 패키지 확인 결과는 [검증 기록](verification.md)에 있다.
- 배포 담당자: 자체 코드·문서의 권리자와 허용할 공유 범위를 정하고 필요 시 자체 배포 라이선스 명시. 이 문서는 그 선택을 대신하지 않음.
- 회사 담당자: 향후 별도 AI 생성 작업을 사용할 때 실제 계약 주체·플랜·워크스페이스·입력 자료 권리·데이터 설정 확인. 이미지 권리·상표·캐릭터 유사성 검토는 생성 서비스 사용 여부와 별도로 수행.
- 라이브러리나 참고 저장소를 실제 동봉하는 변경 시: 정확한 버전/커밋, 전체 고지, 실제 산출물 목록으로 이 기록 갱신.

## 0.3.2 action-set

플러그인 허용 목록에는 자체 Python 모듈 `src/pixel_asset_pipeline/action_set.py` 하나가 추가됐다. pixelfx 코드·폰트·의존성은 설치 묶음에 넣지 않는다. 사용자가 지정한 로컬 pixelfx 시트·JSON과 LICENSE·NOTICE는 해당 액션 결과에 포함하고 출처 해시와 크레딧을 기록한다. 예제의 실제 타격 시트는 [고지와 출처](../../examples/scout-actions/README.md)를 따른다. 레퍼런스에 사용한 Agent Sprite Forge의 라이선스와 공급자 경로는 [조사 기록](sprite-forge.md)에 있다.
