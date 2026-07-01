import os
import time
import requests
from dotenv import load_dotenv
import urllib3
import json
from datetime import datetime
import re

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



DEFAULT_OLDEST_TS = 0
#DEFAULT_OLDEST_TS = time.time() - (7 * 86400)  # 기본값: 7일 전

def get_state() -> dict:
    # # 💡 [임시 조치] 파일 오류를 우회하기 위해 6/18 성공 기록을 메모리에 강제로 주입합니다.
    # print("[디버그] 6/18 백업 기록을 성공적으로 로드했습니다.")
    # return {
    #     "C0B3CU08JDU": 1781763810.089997,
    #     "C0B3GRB0H7T": 1781763810.089997,
    #     "C0B5N9D9H63": 1781763810.089997,
    #     "C0BA7J11XS8": 1781763810.089997
    # }
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                
                # 💡 [보안 코드 1] 파일이 존재하지만 내용이 비어있는 경우 안전하게 빈 딕셔너리 반환
                if not content:
                    print("[디버그] 상태 파일이 비어있습니다. 새로 시작합니다.")
                    return {}
                
                raw_data = json.loads(content)
                clean_state = {}
                for channel_name, data in raw_data.items():
                    if isinstance(data, dict) and "ts" in data:
                        clean_state[channel_name] = data["ts"]
                    elif isinstance(data, (int, float)):
                        clean_state[channel_name] = float(data)
                return clean_state
                
        except json.JSONDecodeError as je:
            # 💡 [보안 코드 2] 파일 내용이 깨졌을 때(char 0 에러 등) 발생 시 초기화 후 안전하게 진행
            print(f"[경고] 상태 파일이 손상되었습니다(JSON 파싱 실패). 초기화 후 새로 생성합니다. 사유: {je}")
            return {}
        except Exception as e:
            print(f"[디버그] 상태 파일 읽기 중 알 수 없는 실패: {e}")
            return {}
            
    return {}


def save_state(state: dict, channel_names_map: dict):
    state_with_readable = {}
    for cid, ts in state.items():
        cname = channel_names_map.get(cid, "unknown")
        state_with_readable[cid] = {
            "channel_name": cname,
            "ts": ts,
            "ts_readable": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)),
        }
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state_with_readable, f, ensure_ascii=False, indent=2)


def get_channel_oldest_ts(state: dict, channel_id: str) -> float:
    return state.get(channel_id, DEFAULT_OLDEST_TS)


def get_all_channels():
    channels = []
    cursor = None

    while True:
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

        for channel in data.get("channels", []):
            if channel.get("is_member", False):
                channels.append(channel)

        metadata = data.get("response_metadata", {})
        cursor = metadata.get("next_cursor")
        if not cursor:
            break

    return channels


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

    # 1. 상태 및 맵 정보 초기화
    state = get_state()
    channel_names_map = {}
    current_run_state = state.copy()
    
    current_run_ts = time.time()
    failed_files = []

    try:
        channels = get_all_channels()
        print(f"발견된 채널 수: {len(channels)}")

        for ch in channels:
            channel_names_map[ch["id"]] = ch["name"]

        sid = nas_login()
        print("NAS 로그인 성공")

        try:
            for channel in channels:
                channel_id = channel["id"]
                channel_name = channel["name"]
                
                # 2. 채널별 기존 성공 타임스탬프 로드 (없으면 0 -> 전체조회)
                oldest_ts = get_channel_oldest_ts(state, channel_id)
                if oldest_ts == 0:
                    print(f"\n[{channel_name}] 🚀 첫 실행: 모든 과거 파일을 백업합니다.")
                else:
                    readable_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(oldest_ts))
                    print(f"\n[{channel_name}] 🔄 후속 실행: {readable_time} 이후의 파일을 조회합니다.")
                
                files = get_channel_files(channel_id, oldest_ts=oldest_ts)
                print(f"[{channel_name}] 발견된 신규 파일 수: {len(files)}")

                channel_success = True

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
                        channel_success = False  # 채널 내 파일 하나라도 실패 시 False

                    finally:
                        if local_path and os.path.exists(local_path):
                            os.remove(local_path)

                # 3. 채널 안의 모든 파일이 완벽히 성공했을 때만 해당 채널의 타임스탬프를 갱신
                if channel_success:
                    current_run_state[channel_id] = current_run_ts

        finally:
            nas_logout(sid)
            print("NAS 로그아웃 완료")

        # 4. 상태 저장 및 알림 처리
        save_state(current_run_state, channel_names_map)

        if failed_files:
            fail_summary = "\n".join([f"- [{ch}] {fid}: {err}" for fid, ch, err in failed_files])
            send_alert(
                f"⚠️ Slack→NAS 파이프라인 부분 실패\n"
                f"실패: {len(failed_files)}건\n"
                f"{fail_summary}\n"
                f"실패 채널은 다음 실행에서 재시도됩니다."
            )
            print(f"부분 실패 (해당 채널 상태 유지됨): {failed_files}")
        else:
            print("파이프라인 전체 성공: 상태 갱신 완료")

    except Exception as e:
        send_alert(f"🚨 Slack→NAS 파이프라인 치명적 실패\n사유: {e}\n상태값 미갱신")
        print(f"치명적 실패: {e}")