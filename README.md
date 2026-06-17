# 🚀 Slack-to-NAS Automatic Backup Pipeline

Windows 작업 스케줄러와 Python을 활용하여 슬랙(Slack) 채널의 파일들을 주기적으로 Synology NAS로 안전하게 자동 백업하는 파이프라인입니다. 

매주 토요일 새벽, 컴퓨터가 잠금 화면이거나 절전 모드인 상태에서도 자동으로 시스템을 깨워 백업을 수행하며, 주말에 PC가 완전히 꺼져 있더라도 월요일 부팅 시 누락된 작업을 찾아 즉시 보완 실행하도록 설계되었습니다.

---

## 📌 주요 기능
- **공개/비공개 채널 통합 조회**: 봇이 참여하고 있는 모든 공개 및 비공개 채널의 파일을 누락 없이 수집합니다.
- **타임스탬프 기반 증분 백업**: `last_successful_ts.txt` 파일을 통해 마지막 백업 성공 시점을 기록하여, 이미 백업된 파일은 건너뛰고 신규 파일만 효율적으로 수집합니다[cite: 2].
- **안전한 예외 처리 및 슬랙 알림**: 백업 과정 중 오류나 부분 실패 발생 시, 지정된 알림 채널로 즉시 Slack 알림을 전송하며 데이터 유실 방지를 위해 성공 상태 갱신을 보류합니다[cite: 2].
- **윈도우 전원 관리 최적화**: 
  - `SYSTEM` 계정 구동으로 윈도우 잠금(`Win + L`) 상태에서도 백그라운드 실행
  - 절전 모드(Sleep Mode) 자동 해제 및 백업 완료 후 자동 안정화
  - 예약 시간 오프라인 시, 재부팅 후 즉시 예약 작업 보완 실행 (Missed Task Recovery)

---

## ⚙️ 시스템 요구사항 및 환경
- **OS**: Windows 10 / 11 (데스크톱 및 노트북)
- **Language**: Python 3.8+
- **의존성 라이브러리**:
```text
  certifi==2026.5.20
  charset-normalizer==3.4.7
  idna==3.18
  python-dotenv==1.2.2
  requests==2.34.2
  urllib3==2.7.0

---

## 🛠️ 설치 및 설정 방법 (Installation)
**1. 저장소 클론 및 패키지 설치**
```Bash
# 저장소 클론
git clone [https://github.com/YOUR_GITHUB_ID/slack-backup-to-NAS.git](https://github.com/YOUR_GITHUB_ID/slack-backup-to-NAS.git)
cd slack-backup-to-NAS

# 가상환경 생성 및 활성화
python -m venv venv
./venv/Scripts/activate

# 필수 라이브러리 설치
pip install -r requirements.txt
```
**2. 환경 변수 설정 (.env)**
프로젝트 루트 디렉토리에 .env 파일을 생성하고 아래의 실제 환경 변수 명칭에 맞게 정보를 입력합니다.
```
WEEKLY_BACKUP_BOT_TOKEN=<xoxb-your-slack-bot-token>
ALERT_CHANNEL_ID=<C0XXXXXXXXX>
NAS_URL=http://<your-nas-ip>:<port>
NAS_ID=<your-nas-username>
NAS_PW=<your-nas-password>
NAS_UPLOAD_PATH=</NAS-directory-name>
```

---

## ⏰ Windows 작업 스케줄러 등록 가이드
주말 및 부재중에도 100% 자동화를 구현하기 위한 윈도우 작업 스케줄러(Task Scheduler) 핵심 세팅 값입니다.

**1. 일반 (General) 탭**
- 사용자 또는 그룹 변경: SYSTEM 입력 후 Enter (암호 입력 없이 로그인 미실행 상태에서 구동 가능)
- 가장 높은 수준의 권한으로 실행 ☑️

**2. 트리거 (Triggers) 탭**
- 작업 시작: 예약 상태
- 설정: 매주 ➡️ 토요일 선택 (원하는 실행 시간 지정)
- 고급설정: 사용 ☑️

**3. 동작 (Actions) 탭**
- 동작: 프로그램 시작
- 프로그램/스크립트: 가상환경 내 Python 경로 입력 (예: `C:\Users\Username\slack-backup-to-NAS\venv\Scripts\python.exe`)
- 인수 추가(옵션): 실행할 스크립트 파일명 입력 (예: `script.py`)
- 시작 위치(옵션): 프로젝트 폴더 경로 입력 (예: `C:\Users\Username\slack-backup-to-NAS`)

**4. 조건 (Conditions) 탭**
- 전원 항목:
  - 컴퓨터의 AC 전원이 켜져 있는 경우에만 작업 시작 ➡️ 체크 해제 ❌ (노트북 환경 고려)
  - 이 작업을 실행하기 위해 컴퓨터의 절전 모드 해제 ☑️ (새벽에 자동 깨우기)

**5. 설정 (Settings) 탭**
- 요청 시 작업이 실행되도록 허용 ☑️
- 예약된 시작 시간을 놓친 경우 가능한 한 빨리 작업 시작 ☑️ (주말에 PC가 꺼져 있어도 월요일 부팅 시 즉시 백업 실행)
- 다음 시간 이상 작업이 실행되면 중지: 1시간으로 설정 (무한 루프 방지 안전장치)
- 요청할 때 실행 중인 작업이 끝나지 않으면 강제로 작업 중지 ☑️
- 작업이 이미 실행 중이면 다음 규칙 적용: 새 인스턴스 실행 안 함 (중복 실행 방지)

---

## 📂 프로젝트 구조 (Directory Structure)
```text
/slack-backup-to-NAS
├── venv/                  # 파이썬 가상환경 폴더
├── tmp_slack_files/       # 백업 진행 시 생성되는 로컬 임시 다운로드 폴더 (업로드 후 자동 삭제)
├── script.py              # 백업 파이프라인 메인 스크립트 코드
├── last_successful_ts.txt # 마지막 백업 성공 일시가 기록되는 상태 관리 파일
├── login_test.py          # NAS 로그인 확인용 디버깅 코드
├── .env                   # 환경 변수 정의 파일 (Git 배제)
├── .gitignore             # Git 추적 제외 설정 (.env, venv/, txt 등 포함)
└── README.md              # 프로젝트 안내서 (현재 파일)
```

---

### ⚠️ 주의사항 (Notice for Laptop Users)
노트북 환경에서 주말 자동 백업을 신뢰성 있게 유지하려면 금요일 퇴근 전 아래 사항을 반드시 확인하세요.

1. **AC 전원 어댑터 연결**: 배터리 모드에서는 윈도우가 시스템 보호를 위해 스케줄러의 절전 해제 명령을 거부할 수 있습니다.
2. **노트북 덮개 개방**: 덮개를 닫으면 시스템이 하이브리드 절전 또는 최대 절전 모드로 진입하여 스케줄러가 깨우지 못할 수 있습니다.
3. **잠금 화면 유지**: 화면은 자동으로 꺼지도록 전원 설정을 해두되, Win + L로 잠금 화면 상태를 유지하고 퇴근하는 것이 가장 안정적입니다.
