import os
import requests
import urllib3
from dotenv import load_dotenv

load_dotenv()

NAS_URL = os.environ.get("NAS_URL")
NAS_ID = os.environ.get("NAS_ID")
NAS_PW = os.environ.get("NAS_PW")

# SSL 경고 숨기기
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def https_login_test():
    print("=== 시놀로지 NAS 로그인 테스트 (HTTPS 전용 규격) ===")
    print(f"접속 주소: {NAS_URL}")
    print(f"접속 계정: {NAS_ID}")
    print("-" * 40)

    # requests.Session을 쓰면 로그인 세션(쿠키)이 내부적으로 유지되어 보안 차단을 우회하기 쉽습니다.
    session = requests.Session()

    # [Step 1] DSM 7.3+ 규격으로 직접 로그인 시도 (POST 방식)
    print("[시도] entry.cgi 규격으로 로그인 요청 중...")
    login_payload = {
        "api": "SYNO.API.Auth",
        "version": "6",
        "method": "login",
        "account": NAS_ID,
        "passwd": NAS_PW,
        "session": "FileStation",
        "format": "sid"
    }

    try:
        resp = session.post(
            f"{NAS_URL}/webapi/entry.cgi",
            data=login_payload,
            verify=False,
            timeout=10
        )
        print(f"-> 응답 코드: {resp.status_code}")
        print(f"-> 응답 내용: {resp.text}")
        
        data = resp.json()
        if data.get("success"):
            print("\n🎉 [성공] HTTPS를 통해 로그인에 성공했습니다! SID 발급 완료.")
            print(f"발급된 SID: {data['data']['sid']}")
            return
    except Exception as e:
        print(f"⚠️ entry.cgi 통신 중 예외 발생: {e}")

    # [Step 2] 구버전 API 경로로 롤백 적용 (혹시 모를 대안)
    print("\n" + "-"*40)
    print("[대안 시도] 구버전 auth.cgi 규격으로 로그인 요청 중...")
    try:
        resp = session.post(
            f"{NAS_URL}/webapi/auth.cgi",
            data={
                "api": "SYNO.API.Auth",
                "version": "3",
                "method": "login",
                "account": NAS_ID,
                "passwd": NAS_PW,
                "session": "FileStation",
                "format": "sid"
            },
            verify=False,
            timeout=10
        )
        print(f"-> 응답 코드: {resp.status_code}")
        print(f"-> 응답 내용: {resp.text}")
        
        data = resp.json()
        if data.get("success"):
            print("\n🎉 [성공] auth.cgi 경로로 로그인에 성공했습니다!")
            return
            
    except Exception as e:
        print(f"⚠️ auth.cgi 통신 중 예외 발생: {e}")

if __name__ == "__main__":
    https_login_test()
    print(repr(NAS_PW), len(NAS_PW))  # '비번\n' 이나 '"비번"' 같은 오염 탐지


# import os
# import time
# import requests
# import urllib3
# from dotenv import load_dotenv

# # .env 파일 로드
# load_dotenv()

# SLACK_TOKEN = os.environ["WEEKLY_BACKUP_BOT_TOKEN"]
# ALERT_CHANNEL_ID = os.environ["ALERT_CHANNEL_ID"]
# SLACK_HEADERS = {"Authorization": f"Bearer {SLACK_TOKEN}"}

# NAS_URL = os.environ["NAS_URL"]
# NAS_ID = os.environ["NAS_ID"]
# NAS_PW = os.environ["NAS_PW"]
# NAS_UPLOAD_PATH = os.environ["NAS_UPLOAD_PATH"]

# LOCAL_TEMP_DIR = "./tmp_slack_files"
# STATE_FILE = "./last_successful_ts.txt"

# # 자체 서명 인증서(verify=False) 사용 시 터미널에 경고 창 무더기로 뜨는 것 방지
# urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# # ── Slack 알림 ───────────────────────────────────────────
# def send_alert(message):
#     """파이프라인 실패 시 슬랙으로 알림 전송"""
#     try:
#         resp = requests.post(
#             "https://slack.com/api/chat.postMessage",
#             headers=SLACK_HEADERS,
#             json={"channel": ALERT_CHANNEL_ID, "text": message},
#             timeout=10
#         )
#         if not resp.json().get("ok"):
#             print(f"알림 전송 실패: {resp.json().get('error')}")
#     except Exception as e:
#         print(f"알림 전송 중 예외 발생: {e}")


# # ── 상태 관리 ─────────────────────────────────────────────
# def get_last_successful_ts():
#     """마지막으로 성공했던 타임스탬프를 파일에서 읽어옴"""
#     if os.path.exists(STATE_FILE):
#         try:
#             with open(STATE_FILE, "r") as f:
#                 return float(f.read().strip())
#         except ValueError:
#             pass
#     return time.time() - (7 * 86400)


# def save_current_ts(current_ts):
#     """성공 시 현재 타임스탬프를 파일에 기록"""
#     with open(STATE_FILE, "w") as f:
#         f.write(str(current_ts))


# # ── Slack 파일 추출 ───────────────────────────────────────
# def get_channel_files(channel_id, oldest_ts=0):
#     """채널 메시지 중 파일이 첨부된 것만 추출"""
#     files_list = []
#     cursor = None

#     while True:
#         params = {"channel": channel_id, "oldest": oldest_ts, "limit": 200}
#         if cursor:
#             params["cursor"] = cursor

#         resp = requests.get(
#             "https://slack.com/api/conversations.history",
#             headers=SLACK_HEADERS,
#             params=params,
#             timeout=15
#         )
#         data = resp.json()

#         if not data.get("ok"):
#             raise Exception(f"Slack API Error: {data.get('error')}")

#         for msg in data.get("messages", []):
#             if "files" in msg:
#                 files_list.extend(msg["files"])

#         metadata = data.get("response_metadata", {})
#         cursor = metadata.get("next_cursor")
#         if not cursor:
#             break

#     return files_list


# def download_file_to_temp(file_info, temp_dir):
#     """Slack 파일을 로컬 임시 폴더에 다운로드"""
#     url = file_info.get("url_private_download") or file_info.get("url_private")
#     if not url:
#         return None

#     file_id = file_info.get("id", "unknown")
#     filename = f"{file_id}_{file_info.get('name', file_id)}"
#     save_path = os.path.join(temp_dir, filename)

#     resp = requests.get(url, headers=SLACK_HEADERS, stream=True, timeout=30)
#     resp.raise_for_status()

#     content_type = resp.headers.get("Content-Type", "")
#     if "text/html" in content_type:
#         raise Exception(f"인증 오류 추정 (HTML 반환): {file_id}")

#     with open(save_path, "wb") as f:
#         for chunk in resp.iter_content(chunk_size=8192):
#             if chunk:
#                 f.write(chunk)

#     return save_path, filename


# # ── Synology NAS 업로드 ───────────────────────────────────
# def nas_login():
#     """Synology API 로그인 → sid 반환 (DSM 7.x 필수 보안 규격 반영)"""
#     print(f"NAS 로그인 시도 중... 주소: {NAS_URL}")
    
#     # 💡 핵심 수정: params= 대신 data= 로 변경하여 POST 바디 전송으로 규격 맞춤
#     # 💡 무한 멈춤 방지를 위해 timeout=10 추가
#     resp = requests.post(
#         f"{NAS_URL}/webapi/entry.cgi",
#         data={
#             "api": "SYNO.API.Auth",
#             "version": "6",
#             "method": "login",
#             "account": NAS_ID,
#             "passwd": NAS_PW,
#             "session": "FileStation",
#             "format": "sid",
#         },
#         verify=False,
#         timeout=10
#     )
    
#     print(f"NAS 응답 상태 코드: {resp.status_code}")
#     print(f"NAS 응답 내용: {resp.text}")
    
#     data = resp.json()
#     if not data.get("success"):
#         raise Exception(f"NAS 로그인 실패 상세: {data.get('error')}")
#     return data["data"]["sid"]


# def nas_logout(sid):
#     """Synology API 로그아웃"""
#     try:
#         requests.post(
#             f"{NAS_URL}/webapi/entry.cgi",
#             data={
#                 "api": "SYNO.API.Auth",
#                 "version": "6",
#                 "method": "logout",
#                 "session": "FileStation",
#                 "_sid": sid,
#             },
#             verify=False,
#             timeout=5
#         )
#     except:
#         pass


# def upload_to_nas(local_path, filename, sid):
#     """로컬 임시 파일을 NAS에 업로드"""
#     with open(local_path, "rb") as f:
#         # 업로드 API 역시 params가 아닌 정확한 규격으로 매칭
#         resp = requests.post(
#             f"{NAS_URL}/webapi/entry.cgi",
#             params={
#                 "api": "SYNO.FileStation.Upload",
#                 "version": "2",
#                 "method": "upload",
#                 "_sid": sid,
#             },
#             data={
#                 "path": NAS_UPLOAD_PATH,
#                 "create_parents": "true",
#                 "overwrite": "true",
#             },
#             files={"file": (filename, f)},
#             verify=False,
#             timeout=60  # 파일 업로드는 용량 고려하여 60초 타임아웃 지정
#         )
#     data = resp.json()
#     if not data.get("success"):
#         raise Exception(f"NAS 업로드 실패: {filename}, 에러: {data.get('error')}")


# # ── 메인 ─────────────────────────────────────────────────
# if __name__ == "__main__":
#     CHANNEL_ID = "C0BALFG2D6E"
#     os.makedirs(LOCAL_TEMP_DIR, exist_ok=True)

#     oldest_ts = get_last_successful_ts()
#     current_run_ts = time.time()
#     failed_files = []

#     try:
#         print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 파이프라인 작동 시작")
#         print(f"{oldest_ts} 이후의 새 파일을 가져옵니다...")
#         files = get_channel_files(CHANNEL_ID, oldest_ts=oldest_ts)
#         print(f"발견된 파일 수: {len(files)}")

#         if len(files) == 0:
#             print("백업할 새로운 파일이 없습니다. 프로그램을 종료합니다.")
#             save_current_ts(current_run_ts)
#             exit(0)

#         sid = nas_login()
#         print("NAS 로그인 성공!")

#         try:
#             for f in files:
#                 file_id = f.get("id", "unknown")
#                 local_path = None
#                 try:
#                     result = download_file_to_temp(f, LOCAL_TEMP_DIR)
#                     if result is None:
#                         print(f"건너뜀 (다운로드 URL 없음): {file_id}")
#                         continue

#                     local_path, filename = result
#                     upload_to_nas(local_path, filename, sid)
#                     print(f"업로드 완료: {filename}")

#                 except Exception as file_err:
#                     print(f"파일 처리 실패: {file_id}, 사유: {file_err}")
#                     failed_files.append((file_id, str(file_err)))

#                 finally:
#                     if local_path and os.path.exists(local_path):
#                         os.remove(local_path)

#         finally:
#             nas_logout(sid)
#             print("NAS 로그아웃 완료")

#         if failed_files:
#             fail_summary = "\n".join([f"- {fid}: {err}" for fid, err in failed_files])
#             send_alert(
#                 f"⚠️ Slack→NAS 파이프라인 부분 실패\n"
#                 f"성공: {len(files) - len(failed_files)}건 / 실패: {len(failed_files)}건\n"
#                 f"{fail_summary}\n"
#                 f"상태값 미갱신 → 다음 실행에서 재시도"
#             )
#             print(f"부분 실패 (상태 유지됨): {[f[0] for f in failed_files]}")
#         else:
#             save_current_ts(current_run_ts)
#             print("🎉 파이프라인 대성공: 상태 갱신 완료")

#     except Exception as e:
#         send_alert(f"🚨 Slack→NAS 파이프라인 치명적 실패\n사유: {e}\n상태값 미갱신")
#         print(f"치명적 실패 (상태 유지됨): {e}")