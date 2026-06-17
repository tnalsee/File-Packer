# 🚀 File Packer: Automatic Backup Pipeline

Python과 Synology NAS 작업 스케줄러를 활용하여 슬랙(Slack) 채널의 파일들을 주기적으로 NAS로 안전하게 자동 백업하는 파이프라인입니다.

매주 토요일 새벽, 365일 구동되는 NAS 서버 자체에서 백그라운드로 실행되는 자동화 백업을 구현합니다.

---

## 📌 주요 기능
- **공개/비공개 채널 통합 조회**: 봇이 참여하고 있는 모든 공개 및 비공개 채널의 파일을 누락 없이 수집합니다.
- **타임스탬프 기반 증분 백업**: `last_successful_ts.txt` 파일을 통해 마지막 백업 성공 시점을 기록하여, 이미 백업된 파일은 건너뛰고 신규 파일만 효율적으로 수집합니다.
- **안전한 예외 처리 및 슬랙 알림**: 백업 과정 중 오류나 부분 실패 발생 시, 지정된 알림 채널로 즉시 Slack 알림을 전송하며 데이터 유실 방지를 위해 성공 상태 갱신을 보류합니다.
- **독립형 서버 최적화**: 로컬 PC 환경에 의존하지 않고 NAS 내부 리소스(내장 Python)만으로 주기적 작업을 완벽하게 수행합니다.

---

## ⚙️ 시스템 요구사항 및 환경
- **OS**: Synology DSM (Linux 환경)
- **Language**: Python 3.8+
- **의존성 라이브러리**:
```text
  certifi==2026.5.20
  charset-normalizer==3.4.7
  idna==3.18
  python-dotenv==1.2.2
  requests==2.34.2
  urllib3==2.7.0
```
---

## 🛠️ 환경 변수 설정 (.env)
프로젝트 소스 폴더 내에 `.env` 파일을 생성하고 아래의 실제 환경 변수 명칭에 맞게 정보를 입력합니다.
```
FILE_PACKER_TOKEN=<xoxb-your-slack-bot-token>
ALERT_CHANNEL_ID=<C0XXXXXXXXX>
NAS_URL=http://<your-nas-ip>:<port>
NAS_ID=<your-nas-username>
NAS_PW=<your-nas-password>
NAS_UPLOAD_PATH=</NAS-directory-name>
```

---

## Synology NAS 작업 스케줄러 등록 가이드

### 1. 파일 업로드 (File Station)
- NAS 내부에 소스코드 전용 폴더(`__file_packer`)를 생성합니다. (경로: /volume1/Slack/__file_packer)
- 해당 폴더에 `synology_script.py`, `.env`, `requirements.txt` 파일을 업로드합니다.
- (선택 사항) 로컬 테스트 시 생성된 `last_successful_ts.txt` 파일이 있다면 함께 업로드하여 기존 백업 시점을 NAS 스크립트와 동기화할 수 있습니다.

### 2. 제어판 스케줄러 등록
**※ 관리자 계정 로그인 필요**
1. Synology 제어판(Control Panel) ➡️ 작업 스케줄러(Task Scheduler)로 이동합니다. 
2. [생성] ➡️ [예약된 작업] ➡️ [사용자 정의 스크립트]를 클릭합니다.
3. 각 탭을 다음과 같이 설정합니다.
  - 일반 탭:
    - 작업 이름: Slack_File_Packer
    - 사용자: root (최고 권한 지정으로 파일 쓰기 및 폴더 생성 권한 에러 방지)
  - 트리거 탭:
    - 매주 토요일 새벽 1시 실행
  - 작업 설정 탭 (사용자 정의 스크립트): 아래 명령어를 그대로 입력하고 저장합니다.
    ```Bash
      # 1. 소스코드가 모여있는 __file_packer 폴더로 이동
      cd /volume1/Slack/__file_packer

      # 2. 파이썬 라이브러리 최신 상태로 설치 및 유지
      python3 -m pip install -r requirements.txt --quiet

      # 3. 백업 스크립트 실행
      python3 script.py
      ```

---

## 📂 프로젝트 구조 (Directory Structure)
실제 백업 파일이 저장되는 공간과 소스코드가 구동되는 환경을 격리하여 관리 편의성을 극대화한 구조입니다.
```text
📁 volume1 (Synology Storage)
  └── 📁 Slack (실제 백업본 전용 상위 폴더)
        ├── 📁 **__file_packer** (★ 소스코드 및 구동 환경 격리 폴더)
        │     ├── 📄 script.py               # 백업 파이프라인 메인 스크립트
        │     ├── 📄 requirements.txt        # 의존성 라이브러리 목록
        │     ├── 📄 .env                    # 환경 변수 정의 파일 (Git 커밋 배제)
        │     ├── 📄 last_successful_ts.txt  # 마지막 백업 성공 일시 기록 파일 (상태 관리용)
        │     └── 📁 tmp_slack_files         # 백업 진행 시 생성되는 임시 다운로드 폴더
        │
        ├── 📁 daily-meeting (실제 슬랙 채널별 백업 폴더들...)
        ├── 📁 materials
        └── 📁 notice
```

---

### ⚠️ 상태 관리 파일 (last_successful_ts.txt) 안내
- 이 파일은 마지막으로 백업에 성공한 기준 시점(타임스탬프)을 기록하여 증분 백업을 가능하게 합니다.
- 로컬에서 테스트 성공 후 생성된 파일을 NAS의 __file_packer 폴더에 함께 업로드하면, NAS에서 첫 구동 시 중복 작업 없이 로컬 성공 시점 이후의 신규 파일만 수집합니다.
- 만약 해당 파일 없이 스크립트를 처음 구동하면, 코드가 자동으로 최근 7일 전을 기점으로 파일 수집을 시작하며 실행 종료 후 파일이 자동으로 새로 생성됩니다.