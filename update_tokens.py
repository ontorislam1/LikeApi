import requests
import json
import time

UIDPASS_FILE = "uidpass.json"
TOKEN_FILE = "token_bd.json"
API_URL = "https://ff-jwt-gen-api.lovable.app/api/public/token"

def read_uidpass():
    with open(UIDPASS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def fetch_token(uid, password):
    url = f"{API_URL}?uid={uid}&password={password}"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()

        if data.get("success") is True:
            token = data.get("token", "").strip()
            if token:
                print(f"  ✅ UID {uid} → Token মিলেছে (region: {data.get('region', '?')})")
                return token
            else:
                print(f"  ⚠️  UID {uid} → success=true কিন্তু token খালি")
                return None
        else:
            error_msg = data.get("error", "Unknown error")
            print(f"  ❌ UID {uid} → Failed: {error_msg}")
            return None

    except requests.exceptions.Timeout:
        print(f"  ⏱️  UID {uid} → Timeout!")
        return None
    except Exception as e:
        print(f"  💥 UID {uid} → Error: {e}")
        return None

def update_token_file(token_list):
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(token_list, f, ensure_ascii=False, indent=4)

def main():
    print("=" * 50)
    print("  🔄 JWT Token Updater শুরু হচ্ছে...")
    print("=" * 50)

    uidpass_list = read_uidpass()
    print(f"\n📋 মোট {len(uidpass_list)} টি UID পাওয়া গেছে\n")

    new_tokens = []
    for i, item in enumerate(uidpass_list, 1):
        uid = item.get("uid", "")
        password = item.get("password", "")
        print(f"[{i}/{len(uidpass_list)}] UID: {uid} চেক করা হচ্ছে...")

        token = fetch_token(uid, password)
        if token:
            new_tokens.append({"token": token})

        # API rate limit এড়াতে সামান্য delay
        time.sleep(0.5)

    print("\n" + "=" * 50)
    if new_tokens:
        update_token_file(new_tokens)
        print(f"✅ সফলভাবে {len(new_tokens)}/{len(uidpass_list)} টি token আপডেট হয়েছে!")
        print(f"📁 সেভ হয়েছে: {TOKEN_FILE}")
    else:
        print("❌ কোনো token আপডেট হয়নি!")
    print("=" * 50)

if __name__ == "__main__":
    main()
