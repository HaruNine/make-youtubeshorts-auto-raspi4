# 라즈베리파이4B+ 기반 영상 자동화 시스템 구축기

## 개요

저사양 임베디드 환경에서 대용량 영상 자동화 파이프라인을 구축하기 위해 라즈베리파이4B+ 8GB 모델과 라즈비안 64bit OS, 500GB HDD, Docker 및 Docker Compose를 활용하여 실전 영상 생성/처리/업로드 시스템을 설계하고 운영한 경험을 공유합니다.

---

## 하드웨어 및 OS 환경

- **보드:** Raspberry Pi 4B+ 8GB RAM
- **저장장치:** 500GB 외장 HDD (USB 3.0)
- **운영체제:** Raspberry Pi OS 64bit (라즈비안)
- **네트워크:** 유선 LAN, 1Gbps
- **전원:** 정품 어댑터, UPS 백업

### 하드웨어 선정 이유
- 저전력, 저소음, 24/7 무중단 운영 가능
- USB 3.0 지원으로 대용량 영상 입출력에 유리
- 8GB RAM으로 멀티프로세스 및 캐싱에 충분

---

## 소프트웨어 스택 및 라이브러리

### 컨테이너 오케스트레이션
- **Docker**: 서비스 격리, 배포 자동화, 환경 일관성 확보
- **Docker Compose**: 멀티 컨테이너 관리, 볼륨/네트워크/환경변수 통합 관리

### Python 기반 영상 처리
- **Python 3.11** (slim-bookworm 베이스)
- **MoviePy 2.2.1**: 영상 합성, 자막, 오디오 믹싱, 자동화 파이프라인의 핵심
- **requests**: 외부 API 및 영상 다운로드
- **assemblyai**: AI 기반 음성 인식 및 자막 생성
- **termcolor**: CLI 상태 출력
- **python-dotenv**: 환경변수 관리
- **matplotlib**: 영상 처리 중 임시 시각화
- **srt_equalizer**: 자막 싱크 보정
- **flask, flask-cors**: REST API 서버(확장성 고려)
- **oauth2client, google-api-python-client**: 유튜브 업로드 자동화
- **pydub, playsound**: 오디오 처리

### 기타
- **ffmpeg**: MoviePy 내부에서 활용, 영상/오디오 인코딩
- **ImageMagick**: 텍스트/자막 렌더링, Pillow와 연동
- **fontconfig**: 한글/영문 폰트 지원

---

## 시스템 구조 및 폴더 구성

```
/codes/mkshorts
├── Backend/           # 파이썬 백엔드 소스
├── temp/              # 임시 영상/오디오/자막 파일
├── uptemp/            # 최종 완성 영상 (업로드 대기)
├── log/               # 실행/에러 로그
├── fonts/             # 커스텀 폰트(TTF)
├── Songs/             # 배경음악 ZIP 및 추출 파일
├── subtitles/         # 생성된 SRT 자막
├── docker-compose.yml # 컨테이너 오케스트레이션
├── Dockerfile         # 베이스 이미지 및 의존성
└── requirements.txt   # 파이썬 패키지 목록
```

- **임시/최종 파일 분리**: temp/와 uptemp/로 작업 중간 산출물과 최종 결과를 분리하여 안정성 및 관리 용이성 확보
- **볼륨 마운트**: Docker Compose에서 각 폴더를 호스트와 공유, 장애 복구 및 데이터 백업 용이

---

## 주요 기능 및 자동화 파이프라인

1. **스크립트/자막 자동 생성**
    - OpenAI, AssemblyAI API 연동으로 영상 스크립트 및 자막 자동 생성
    - TTS(텍스트-음성 변환)로 오디오 파일 생성
2. **영상 클립 검색 및 다운로드**
    - Pexels API 등에서 키워드 기반 영상 검색/다운로드
    - requests로 병렬 다운로드, 임시폴더 저장
3. **영상 합성 및 편집**
    - MoviePy로 클립 자르기, 크롭, 리사이즈, 오디오/자막 합성
    - 배경음악 믹싱, 볼륨 조절, 자막 스타일링(폰트, 색상, 배경)
4. **최종 영상 렌더링 및 업로드**
    - 완성본을 uptemp/에 저장, 유튜브 API로 자동 업로드
    - 업로드 후 temp/ 정리 및 리소스 해제
5. **로깅 및 예외 처리**
    - 모든 주요 이벤트/에러를 /app/log/alog.log에 기록
    - MoviePy 내부 ffmpeg 로그까지 통합 관리

---

## 개발 및 운영 중 주요 이슈와 해결 경험

### 1. 저사양 환경에서의 성능 최적화
- **문제:** 라즈베리파이의 CPU/GPU 한계로 인코딩 속도 저하, OOM(메모리 부족) 빈번
- **해결:**
    - MoviePy의 threads 옵션을 1~2로 제한, 병렬 처리 최소화
    - 임시파일 주기적 정리, gc.collect() 및 malloc_trim(0)으로 메모리 회수
    - ffmpeg 인코딩 파라미터 조정(저비트레이트, 하드웨어 가속 옵션)

### 2. 폰트/자막 한글 깨짐
- **문제:** Pillow, ImageMagick에서 한글 폰트 미인식
- **해결:**
    - /app/fonts/에 NotoSansKR 등 한글 지원 TTF 추가
    - Dockerfile에 fontconfig, ttf-* 패키지 설치
    - MoviePy TextClip에 font 경로 직접 지정

### 3. 경로 및 볼륨 마운트 이슈
- **문제:** 컨테이너 내부/외부 경로 불일치로 파일 접근 오류
- **해결:**
    - pathlib, os.path.abspath로 모든 경로 절대경로화
    - docker-compose.yml에서 호스트-컨테이너 경로 일치 보장

### 4. 대용량 파일 처리 및 장애 복구
- **문제:** HDD I/O 병목, 파일 손상 시 재처리 필요
- **해결:**
    - 임시파일/완성본 분리, 장애 발생 시 uptemp/에서 재업로드 가능
    - 로그/에러 발생 시 자동 알림(추후 슬랙/메일 연동 예정)

### 5. API Rate Limit 및 인증 관리
- **문제:** 외부 API(예: OpenAI, Pexels) 호출 제한, 인증키 노출 위험
- **해결:**
    - .env 파일로 모든 API 키 관리, gitignore로 보안 유지
    - 실패 시 재시도 로직, 백오프(backoff) 적용

---

## 성능 및 운영 결과

- **실제 1회 영상 생성 소요:** 약 54초~1분 10초 (영상 길이/효과/자막 복잡도에 따라 상이)
    - 예시: 14:28:49 작업 시작 → 14:29:46~50 자막/오디오 완료 → 14:29:50~14:53:10 렌더링 및 후처리
    - 실제 파이프라인 전체(스크립트 생성, TTS, 영상 다운로드, 합성, 자막, 렌더링, 업로드) 기준
- **동시 작업:** threads=1~2로 제한, 안정성 우선
- **장애 복구:** uptemp/에 완성본이 남아있어, 업로드 실패 시 재시도 용이
- **운영 기간:** 24/7 무중단 2개월 이상, HDD/SD카드 wear leveling 고려하여 주기적 백업

---

## 느낀점 및 확장성

- 저사양 환경에서도 Docker, Python, MoviePy 등 오픈소스 생태계를 적극 활용하면 충분히 실전 자동화 시스템을 구축할 수 있음을 경험
- 컨테이너 기반 설계로 추후 AWS, GCP 등 클라우드 이전도 용이
- REST API, 웹 프론트엔드, 슬랙/메일 알림 등 다양한 확장 가능성 확보
- 오픈소스/자동화/경량화에 관심 있는 개발자에게 강력 추천

---

## 사용한 주요 라이브러리/도구 목록

- Python 3.11
- MoviePy 2.2.1
- requests, assemblyai, termcolor, python-dotenv, matplotlib, srt_equalizer, flask, flask-cors, oauth2client, google-api-python-client, pydub, playsound
- ffmpeg, ImageMagick, fontconfig
- Docker, Docker Compose
- Raspberry Pi OS 64bit

---

## 참고 및 추가 자료

- [MoviePy 공식 문서](https://zulko.github.io/moviepy/)
- [Docker 공식 문서](https://docs.docker.com/)
- [Raspberry Pi 공식](https://www.raspberrypi.com/)
- [파이썬 pathlib 활용법](https://switowski.com/blog/pathlib/)

## 도커 및 코드 실행 방법

### 1. Docker 이미지 빌드 및 컨테이너 실행

- 프로젝트 루트(예: `/codes/mkshorts`)에서 아래 명령어를 실행합니다.
- **빌드 캐시를 사용하지 않고** 항상 최신 상태로 이미지를 생성하려면 `--no-cache` 옵션을 사용합니다.

```bash
docker compose build --no-cache && docker compose up -d
```

- `docker compose build --no-cache`  
  : 모든 레이어를 새로 빌드하여 의존성/환경 변경 사항을 반영합니다.  
  (참고: [CloudBees Docker Build Without Cache](https://www.cloudbees.com/blog/docker-build-without-cache), [Docker 공식 문서](https://docs.docker.com/reference/cli/docker/compose/up/))
- `docker compose up -d`  
  : 컨테이너를 백그라운드(detached) 모드로 실행합니다.

### 2. 컨테이너 내부에서 파이썬 코드 실행

- 컨테이너가 정상적으로 실행 중이라면, 아래 명령어로 직접 파이썬 메인 스크립트를 실행할 수 있습니다.

```bash
docker exec -it mkshorts python3 Backend/main.py
```

- `docker exec -it mkshorts ...`  
  : 실행 중인 `mkshorts` 컨테이너 내부에서 명령을 실행합니다.
- `python3 Backend/main.py`  
  : 영상 자동화 파이프라인 전체를 1회 실행합니다.

### 3. 기타 참고 사항

- 로그 및 결과 파일은 호스트의 `log/`, `uptemp/` 등에서 바로 확인할 수 있습니다.
- 환경 변수(.env) 및 볼륨 마운트가 올바르게 설정되어 있어야 정상 동작합니다.
- 컨테이너 재시작/재빌드 시에도 데이터(완성본, 로그 등)는 유지됩니다.

---

</rewritten_file> 
