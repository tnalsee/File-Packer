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
LOCAL_TEMP_DIR = "./tmp_slack_files"
STATE_FILE = "./last_successful_ts.txt"
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# LOCAL_TEMP_DIR = os.path.join(BASE_DIR, "tmp_slack_files")
# STATE_FILE = os.path.join(BASE_DIR, "last_successful_ts.txt")


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
# 🌟 첫 실행 시 제한 없이 모든 파일을 가져오기 위해 기본값을 0으로 설정합니다.
DEFAULT_OLDEST_TS = 0

#DEFAULT_OLDEST_TS = time.time() - (7 * 86400)  # 기본값: 7일 전

def get_state() -> dict:
    """
    JSON 상태 파일을 읽어 채널별 마지막 성공 타임스탬프를 반환.
    포맷: { "channel_name": float_timestamp, ... }
    """
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:  # 파일이 비어있는 경우
                    return {}
                
                raw_data = json.load(f)
                clean_state = {}
                for channel_name, data in raw_data.items():
                    if isinstance(data, dict) and "ts" in data:
                        clean_state[channel_name] = data["ts"]
                    elif isinstance(data, (int, float)): # 혹시 모를 예외 대비
                        clean_state[channel_name] = float(data)
                return clean_state
        except Exception as e:
            print(f"[디버그] 상태 파일 읽기 실패 (첫 실행으로 간주): {e}")
    return {}

# save_state 호출 시 채널 고유 ID 기반으로 저장 (채널이름 변경상황 대비)
def save_state(state: dict, channel_names_map: dict):
    """
    채널별로 타임스탬프를 json으로 저장. 가독성을 위해 _readable 키도 함께 기록.
    state 포맷: { "channel_id": float_timestamp } 
    channel_names_map 포맷: { "channel_id": "channel_name" }
    """
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
    """채널 ID로 마지막 성공 timestamp 조회. 없으면 기본값(7일 전) 반환."""
    return state.get(channel_id, DEFAULT_OLDEST_TS)


# ── Slack 채널 목록 조회 ──────────────────────────────────
def get_all_channels():
    # 워크스페이스에서 봇이 참여하고 있는 채널 목록만 조회 (공개/비공개 모두 포함)
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


# ── Slack 파일 추출 (채널에서 파일 읽고, temp 폴더에 임시 저장) ────────────────────
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
    
    """
    # ── 🌟 파일명 안전화 로직 추가 ──────────────────────────────────────
    raw_filename = file_info.get('name', file_id)
    
    # 1. 파일명에서 확장자와 본문 이름을 분리합니다.
    name_part, ext_part = os.path.splitext(raw_filename)
    
    # 2. 알파벳, 한글, 숫자, 하이픈(-), 언더바(_)를 제외한 모든 특수문자와 공백을 언더바(_)로 치환합니다.
    #    (경로 구분자인 / 나 \ 도 여기서 모두 제거됩니다.)
    clean_name = re.sub(r'[^a-zA-Z0-9ㄱ-ㅎㅏ-ㅣ가-힣\-_]', '_', name_part)
    
    # 3. 확장자도 혹시 모를 특수문자를 제거합니다 (.txt -> .txt)
    clean_ext = re.sub(r'[^a-zA-Z0-9\.]', '', ext_part)
    
    # 4. 최종 안전한 파일명 조립
    filename = f"{clean_name}{clean_ext}"
    
    # 만약 정규식 처리로 이름이 완전히 비어버린 경우를 대비한 방어 코드
    if not clean_name or filename.startswith('.'):
        filename = f"file_{file_id}{clean_ext if clean_ext else '.bin'}"
    # ──────────────────────────────────────────────────────────────────
    """
    
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


# ── Synology NAS 로그인/로그아웃 ───────────────────────────────────
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


# ── Synology NAS 업로드 ───────────────────────────────────
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
    current_run_state = state.copy()  # 성공한 채널만 부분 갱신하기 위한 복사본
    
    # 🌟 스크립트가 시작된 시점을 기록 (이 시점 이후의 파일은 다음 실행 때 트리거됨)
    current_run_ts = time.time()
    failed_files = []

    try:
        channels = get_all_channels()
        print(f"발견된 채널 수: {len(channels)}")

        # 채널 ID -> 채널 이름 매핑 테이블 구축
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

        # 4. 상태 저장 및 알림 처리 (일부 성공한 채널이라도 기록을 남기기 위해 무조건 저장)
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