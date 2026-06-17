import os
import time
import requests
from dotenv import load_dotenv
import urllib3
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

SLACK_TOKEN = os.environ["FILE_PACKER_TOKEN"]
ALERT_CHANNEL_ID = os.environ["ALERT_CHANNEL_ID"]
SLACK_HEADERS = {"Authorization": f"Bearer {SLACK_TOKEN}"}

NAS_URL = os.environ["NAS_URL"]
NAS_ID = os.environ["NAS_ID"]
NAS_PW = os.environ["NAS_PW"]
NAS_UPLOAD_PATH = os.environ["NAS_UPLOAD_PATH"]

# 🔁 수정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_TEMP_DIR = os.path.join(BASE_DIR, "tmp_slack_files")
STATE_FILE = os.path.join(BASE_DIR, "last_successful_ts.txt")


# ── Slack 알림 ───────────────────────────────────────────
def send_alert(message):
    try:
        resp = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers=SLACK_HEADERS,
            json={"channel": ALERT_CHANNEL_ID, "text": message},
        )
        if not resp.json().get("ok"):
            print(f"알림 전송 실패: {resp.json().get('error')}")
    except Exception as e:
        print(f"알림 전송 중 예외 발생: {e}")


# ── 상태 관리 ─────────────────────────────────────────────
def get_last_successful_ts():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                date_str = f.read().strip()
                # 표준 날짜 문자열을 읽어서 구조화된 시간 객체로 변경 후, 타임스탬프(float)로 변환
                struct_time = time.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                return time.mktime(struct_time)
        except Exception as e:
            print(f"[디버그] 타임스탬프 읽기 실패: {e}")
            pass
    # 기록이 없거나 에러 시 기본값 7일 전 타임스탬프 반환
    return time.time() - (7 * 86400)


def save_current_ts(current_ts):
    with open(STATE_FILE, "w") as f:
        # float 타임스탬프를 로컬 시간 기준의 표준 날짜 문자열로 변환하여 저장
        date_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(current_ts))
        f.write(date_str)



# ── Slack 채널 목록 조회 ──────────────────────────────────
def get_all_channels():
    """워크스페이스에서 봇이 참여하고 있는 채널 목록만 조회 (공개/비공개 모두 포함)"""
    channels = []
    cursor = None

    while True:
        # types에 private_channel을 추가합니다.
        params = {
            "limit": 200, 
            "exclude_archived": "true",
            "types": "public_channel,private_channel" 
        }
        if cursor:
            params["cursor"] = cursor

        resp = requests.get(
            "https://slack.com/api/conversations.list",
            headers=SLACK_HEADERS,
            params=params,
        )
        data = resp.json()

        if not data.get("ok"):
            raise Exception(f"채널 목록 조회 실패: {data.get('error')}")

        # 봇이 멤버로 들어가 있는 채널만 결과에 담습니다.
        for channel in data.get("channels", []):
            if channel.get("is_member", False):
                channels.append(channel)

        metadata = data.get("response_metadata", {})
        cursor = metadata.get("next_cursor")
        if not cursor:
            break

    return channels


# ── Slack 파일 추출 ───────────────────────────────────────
def get_channel_files(channel_id, oldest_ts=0):
    files_list = []
    cursor = None

    while True:
        params = {"channel": channel_id, "oldest": oldest_ts, "limit": 200}
        if cursor:
            params["cursor"] = cursor

        resp = requests.get(
            "https://slack.com/api/conversations.history",
            headers=SLACK_HEADERS,
            params=params,
        )
        data = resp.json()

        if not data.get("ok"):
            raise Exception(f"Slack API Error: {data.get('error')}")
        
        # 🔍 [디버깅 코드 추가] API가 실제로 메시지를 몇 개나 가져왔는지 출력
        print(f"   -> [디버그] 가져온 순수 메시지 개수: {len(data.get('messages', []))}")
        
        for msg in data.get("messages", []):
            if "files" in msg:
                files_list.extend(msg["files"])

        metadata = data.get("response_metadata", {})
        cursor = metadata.get("next_cursor")
        if not cursor:
            break

    return files_list


def download_file_to_temp(file_info, temp_dir):
    url = file_info.get("url_private_download") or file_info.get("url_private")
    if not url:
        return None

    file_id = file_info.get("id", "unknown")
    filename = file_info.get('name', file_id)
    save_path = os.path.join(temp_dir, filename)

    resp = requests.get(url, headers=SLACK_HEADERS, stream=True)
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "")
    if "text/html" in content_type:
        raise Exception(f"인증 오류 추정 (HTML 반환): {file_id}")

    with open(save_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    return save_path, filename


# ── Synology NAS 업로드 ───────────────────────────────────
def nas_login():
    resp = requests.get(
        f"{NAS_URL}/webapi/entry.cgi",
        params={
            "api": "SYNO.API.Auth",
            "version": "7",
            "method": "login",
            "account": NAS_ID,
            "passwd": NAS_PW,
            "session": "FileStation",
            "format": "sid",
        },
        verify=False
    )
    print(f"NAS 응답 코드: {resp.status_code}")
    print(f"NAS 응답 내용: {resp.text}")

    data = resp.json()
    if not data.get("success"):
        raise Exception(f"NAS 로그인 실패: {data.get('error')}")
    return data["data"]["sid"]


def nas_logout(sid):
    requests.get(
        f"{NAS_URL}/webapi/entry.cgi",
        params={
            "api": "SYNO.API.Auth",
            "version": "7",
            "method": "logout",
            "session": "FileStation",
            "_sid": sid,
        },
        verify=False
    )


def upload_to_nas(local_path, filename, sid, channel_name):
    """로컬 임시 파일을 NAS 채널별 폴더에 업로드"""
    channel_path = f"{NAS_UPLOAD_PATH}/{channel_name}"  # 예: /Slack/daily-meeting

    with open(local_path, "rb") as f:
        resp = requests.post(
            f"{NAS_URL}/webapi/entry.cgi",
            params={
                "api": "SYNO.FileStation.Upload",
                "version": "2",
                "method": "upload",
                "_sid": sid,
            },
            data={
                "path": channel_path,
                "create_parents": "true",
                "overwrite": "true",
            },
            files={"file": (filename, f)},
            verify=False
        )
    data = resp.json()
    if not data.get("success"):
        raise Exception(f"NAS 업로드 실패: {filename}, 에러: {data.get('error')}")


# ── 메인 ─────────────────────────────────────────────────
if __name__ == "__main__":
    os.makedirs(LOCAL_TEMP_DIR, exist_ok=True)

    #oldest_ts = 0  # [첫 실행용] 0으로 강제 설정 (과거 데이터 강제 흡수)
    oldest_ts = get_last_successful_ts()
    
    current_run_ts = time.time()
    failed_files = []

    try:
        channels = get_all_channels()
        print(f"발견된 채널 수: {len(channels)}")

        sid = nas_login()
        print("NAS 로그인 성공")

        try:
            for channel in channels:
                channel_id = channel["id"]
                channel_name = channel["name"]
                print(f"\n[{channel_name}] 파일 조회 중...")

                files = get_channel_files(channel_id, oldest_ts=oldest_ts)
                print(f"[{channel_name}] 발견된 파일 수: {len(files)}")

                for f in files:
                    file_id = f.get("id", "unknown")
                    local_path = None
                    try:
                        result = download_file_to_temp(f, LOCAL_TEMP_DIR)
                        if result is None:
                            print(f"건너뜀 (다운로드 URL 없음): {file_id}")
                            continue

                        local_path, filename = result
                        upload_to_nas(local_path, filename, sid, channel_name)
                        print(f"업로드 완료: [{channel_name}] {filename}")

                    except Exception as file_err:
                        print(f"파일 처리 실패: [{channel_name}] {file_id}, 사유: {file_err}")
                        failed_files.append((file_id, channel_name, str(file_err)))

                    finally:
                        if local_path and os.path.exists(local_path):
                            os.remove(local_path)

        finally:
            nas_logout(sid)
            print("NAS 로그아웃 완료")

        if failed_files:
            fail_summary = "\n".join([f"- [{ch}] {fid}: {err}" for fid, ch, err in failed_files])
            send_alert(
                f"⚠️ Slack→NAS 파이프라인 부분 실패\n"
                f"실패: {len(failed_files)}건\n"
                f"{fail_summary}\n"
                f"상태값 미갱신 → 다음 실행에서 재시도"
            )
            print(f"부분 실패 (상태 유지됨): {failed_files}")
        else:
            save_current_ts(current_run_ts)
            print("파이프라인 성공: 상태 갱신 완료")

    except Exception as e:
        send_alert(f"🚨 Slack→NAS 파이프라인 치명적 실패\n사유: {e}\n상태값 미갱신")
        print(f"치명적 실패 (상태 유지됨): {e}")