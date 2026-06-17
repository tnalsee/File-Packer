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
