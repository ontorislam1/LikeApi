from flask import Flask, request, jsonify
import asyncio
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import binascii
import aiohttp
import requests
import json
import like_pb2
import uid_generator_pb2
import visit_count_pb2
from google.protobuf.message import DecodeError
from collections import OrderedDict

app = Flask(__name__)

# ✅ Valid API keys
VALID_API_KEYS = {
    "HALIMA"  
}

# 🔢 Like limit tracking
daily_limit = 1000
used_count = 0


def load_tokens(region):
    try:
        if region == "IND":
            with open("token_ind.json", "r") as f:
                tokens = json.load(f)
        elif region in {"BR", "US", "SAC", "NA"}:
            with open("token_br.json", "r") as f:
                tokens = json.load(f)
        else:
            with open("token_bd.json", "r") as f:
                tokens = json.load(f)
        return tokens
    except Exception as e:
        app.logger.error(f"Error loading tokens for region {region}: {e}")
        return None


def encrypt_message(plaintext):
    try:
        key = b'Yg&tc%DEuh6%Zc^8'
        iv = b'6oyZDr22E3ychjM%'
        cipher = AES.new(key, AES.MODE_CBC, iv)
        padded_message = pad(plaintext, AES.block_size)
        encrypted_message = cipher.encrypt(padded_message)
        return binascii.hexlify(encrypted_message).decode('utf-8')
    except Exception as e:
        app.logger.error(f"Error encrypting message: {e}")
        return None


def create_protobuf_message(user_id, region):
    try:
        message = like_pb2.like()
        message.uid = int(user_id)
        message.region = region
        return message.SerializeToString()
    except Exception as e:
        app.logger.error(f"Error creating protobuf message: {e}")
        return None


async def send_request(encrypted_uid, token, url, session):
    try:
        edata = bytes.fromhex(encrypted_uid)
        headers = {
            "User-Agent": "UnityPlayer/2022.3.47f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Expect": "100-continue",
            "X-Unity-Version": "2022.3.47f1",
            "X-GA": "v1 1",
            "ReleaseVersion": "OB55"
        }
        async with session.post(url, data=edata, headers=headers) as response:
            return await response.text()
    except Exception as e:
        app.logger.error(f"Exception in send_request: {e}")
        return None


async def send_multiple_requests(uid, region, url, amount=None, concurrency=50):
    try:
        protobuf_message = create_protobuf_message(uid, region)
        if protobuf_message is None:
            return None
        encrypted_uid = encrypt_message(protobuf_message)
        if encrypted_uid is None:
            return None
        tokens = load_tokens(region)
        if not tokens:
            return None

        # Use each unique token only once per run to avoid BR_ACCOUNT_DAILY_LIKE_PROFILE_LIMIT errors
        unique_tokens = []
        seen = set()
        for item in tokens:
            token = item.get("token") if isinstance(item, dict) else None
            if not token or token in seen:
                continue
            seen.add(token)
            unique_tokens.append(token)

        if amount is not None:
            try:
                unique_tokens = unique_tokens[:max(0, min(int(amount), len(unique_tokens)))]
            except (ValueError, TypeError):
                pass

        semaphore = asyncio.Semaphore(max(1, int(concurrency)))

        async def bounded_send(token, session):
            async with semaphore:
                return await send_request(encrypted_uid, token, url, session)

        async with aiohttp.ClientSession() as session:
            tasks = [bounded_send(token, session) for token in unique_tokens]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        return results
    except Exception as e:
        app.logger.error(f"Exception in send_multiple_requests: {e}")
        return None


def create_protobuf(uid):
    try:
        message = uid_generator_pb2.uid_generator()
        message.saturn_ = int(uid)
        message.garena = 1
        return message.SerializeToString()
    except Exception as e:
        app.logger.error(f"Error creating uid protobuf: {e}")
        return None


def enc(uid):
    protobuf_data = create_protobuf(uid)
    if protobuf_data is None:
        return None
    return encrypt_message(protobuf_data)


def make_request(encrypt, region, token):
    try:
        if region == "IND":
            url = "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
        elif region in {"BR", "US", "SAC", "NA"}:
            url = "https://client.us.freefiremobile.com/GetPlayerPersonalShow"
        else:
            url = "https://clientbp.ggpolarbear.com/GetPlayerPersonalShow"
        edata = bytes.fromhex(encrypt)
        headers = {
            "User-Agent": "UnityPlayer/2022.3.47f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Expect": "100-continue",
            "X-Unity-Version": "2022.3.47f1",
            "X-GA": "v1 1",
            "ReleaseVersion": "OB55"
        }
        response = requests.post(url, data=edata, headers=headers, verify=False, timeout=20)
        if response.status_code != 200:
            app.logger.error(f"GetPlayerPersonalShow failed: HTTP {response.status_code}, body={response.text[:200]}")
            return None
        binary = response.content
        decoded = visit_count_pb2.Info()
        decoded.ParseFromString(binary)
        return decoded
    except DecodeError as e:
        app.logger.error(f"DecodeError: {e}")
        return None
    except Exception as e:
        app.logger.error(f"Error in make_request: {e}")
        return None


@app.route('/like', methods=['GET'])
def handle_requests():
    global used_count  # ✅ fix added

    # ✅ API key check
    api_key = request.args.get("key")
    if api_key not in VALID_API_KEYS:
        result = OrderedDict([
            ("error", "Invalid or missing API key"),
            ("status", 3)
        ])
        return app.response_class(
            response=json.dumps(result, separators=(',', ':')),
            status=401,
            mimetype='application/json'
        )

    uid = request.args.get("uid")
    region = request.args.get("region", "").upper()
    if not uid or not region:
        return {"error": "UID and region are required"}, 400

    try:
        def process_request():
            global used_count  # ✅ fix added again (for nested function)

            tokens = load_tokens(region)
            if not tokens:
                raise Exception("Failed to load tokens.")
            encrypted_uid = enc(uid)
            if encrypted_uid is None:
                raise Exception("Encryption of UID failed.")
            
            before = None
            token_used = None
            for item in tokens[:15]:
                t = item.get('token') if isinstance(item, dict) else None
                if not t:
                    continue
                before = make_request(encrypted_uid, region, t)
                if before is not None:
                    token_used = t
                    break
            
            if before is None:
                raise Exception("Failed to get initial info from player profile.")
            before_like = before.AccountInfo.Likes

            if region == "IND":
                url = "https://client.ind.freefiremobile.com/LikeProfile"
            elif region in {"BR", "US", "SAC", "NA"}:
                url = "https://client.us.freefiremobile.com/LikeProfile"
            else:
                url = "https://clientbp.ggpolarbear.com/LikeProfile"

            amount_param = request.args.get("amount", "all").strip().lower()
            amount = int(amount_param) if amount_param.isdigit() else None

            asyncio.run(send_multiple_requests(uid, region, url, amount=amount))

            after = make_request(encrypted_uid, region, token_used)
            if after is None:
                raise Exception("Failed to get final info.")
            after_like = after.AccountInfo.Likes
            like_given = after_like - before_like
            status = 1 if like_given > 0 else 2

            # ✅ Count only when successful (status == 1)
            if status == 1:
                used_count += 1

            remaining = max(daily_limit - used_count, 0)

            result = OrderedDict([
                ("LikesGivenByAPI", like_given),
                ("LikesafterCommand", after_like),
                ("LikesbeforeCommand", before_like),
                ("PlayerNickname", after.AccountInfo.PlayerNickname),
                ("Level", after.AccountInfo.Levels),
                ("Region", after.AccountInfo.PlayerRegion),
                ("UID", after.AccountInfo.UID),
                ("status", status),
                ("daily_limit", daily_limit),
                ("used", used_count),
                ("remaining", remaining)
            ])

            return app.response_class(
                response=json.dumps(result, separators=(',', ':')),
                status=200,
                mimetype='application/json'
            )

        return process_request()

    except Exception as e:
        app.logger.error(f"Error: {e}")
        return {"error": str(e)}, 500


# 🆕 /remain endpoint
@app.route('/remain', methods=['GET'])
def remain_info():
    global used_count  # ✅ fix added

    remaining = max(daily_limit - used_count, 0)
    data = {
        "daily_limit": daily_limit,
        "remaining": remaining,
        "used": used_count,
        "reset_info": "4:00 AM IST"
    }
    return jsonify(data)


if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
