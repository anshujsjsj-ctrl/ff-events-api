import gzip
import requests
import urllib3
from flask import Flask, jsonify, request
from flask_cors import CORS
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import blackboxprotobuf

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
app.json.sort_keys = False
CORS(app)

AeSkEy = b'Yg&tc%DEuh6%Zc^8'
AeSiV = b'6oyZDr22E3ychjM%'
RELEASE_VERSION = "OB55"

REGIONS = {
    "IND": {
        "name": "India",
        "server": "https://client.ind.freefiremobile.com/",
        "lang": "en-in",
    },
    "ME": {
        "name": "Middle East",
        "server": "https://clientbp.ggpolarbear.com/",
        "lang": "en-me",
    },
    "BD": {
        "name": "Bangladesh",
        "server": "https://clientbp.ggpolarbear.com/",
        "lang": "en-bd",
    },
    "PK": {
        "name": "Pakistan",
        "server": "https://clientbp.ggpolarbear.com/",
        "lang": "en-pk",
    },
    "BR": {
        "name": "Brazil",
        "server": "https://client.us.freefiremobile.com/",
        "lang": "pt-br",
    },
    "ID": {
        "name": "Indonesia",
        "server": "https://clientbp.ggpolarbear.com/",
        "lang": "id-id",
    },
    "TH": {
        "name": "Thailand",
        "server": "https://clientbp.ggpolarbear.com/",
        "lang": "th-th",
    },
}


def enc(d):
  return AES.new(AeSkEy, AES.MODE_CBC, AeSiV).encrypt(pad(d, 16))


def dec(d):
  try:
    return unpad(AES.new(AeSkEy, AES.MODE_CBC, AeSiV).decrypt(d), 16)
  except Exception:
    return d


def smart_encode(payload_dict):
  typedef = {}
  for key, value in payload_dict.items():
    if isinstance(value, int):
      typedef[str(key)] = {"type": "int", "name": ""}
    elif isinstance(value, str):
      typedef[str(key)] = {"type": "bytes", "name": ""}
    elif isinstance(value, dict):
      _, inner_typedef = blackboxprotobuf.decode_message(
          blackboxprotobuf.encode_message(value, {})
      )
      typedef[str(key)] = {
          "type": "message",
          "message_typedef": inner_typedef,
          "name": "",
      }
    else:
      typedef[str(key)] = {"type": "int", "name": ""}
  return blackboxprotobuf.encode_message(payload_dict, typedef)


def decode_bytes(val):
  if isinstance(val, bytes):
    try:
      return val.decode("utf-8")
    except UnicodeDecodeError:
      return val.hex()
  return val


@app.route("/")
def api_documentation():
  docs = {
      "status": "Online",
      "endpoints": {
          "region_events": {
              "url": "/events?region={region_code}&jwt={access_token}",
              "method": "GET",
              "description": (
                  "Fetch and parse clean event details from server response."
              ),
          }
      },
      "available_regions": {k: v["name"] for k, v in REGIONS.items()},
      "example_usage": "/events?region=IND&jwt=your_access_token_here",
  }
  return jsonify(docs)


@app.route("/events")
def get_splash_events():
  query = request.args.get("region", "IND").strip().upper()
  jwt_token = request.args.get("jwt", "").strip()

  if not jwt_token:
    return jsonify({
        "error": (
            "Missing 'jwt' query parameter. Usage:"
            " /events?region=IND&jwt=YOUR_TOKEN"
        )
    }), 400

  target_region = None
  for code, data in REGIONS.items():
    if query == code or query == data["name"].upper():
      target_region = code
      break

  if not target_region:
    return jsonify({
        "error": (
            f"Region '{query}' not found. Available regions:"
            f" {', '.join(REGIONS.keys())}"
        )
    }), 404

  r_data = REGIONS[target_region]

  game_headers = {
      "User-Agent": (
          "UnityPlayer/2018.4.12f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)"
      ),
      "Accept": "*/*",
      "Accept-Encoding": "deflate, gzip",
      "X-Ga-Sv": "1789534056",
      "Authorization": f"Bearer {jwt_token}",
      "X-Ga": "v1 1",
      "Releaseversion": f"{RELEASE_VERSION}",
      "Content-Type": "application/octet-stream",
      "X-Unity-Version": "2018.4.12f1",
      "PlAy_VeR": "1.132.1",
      "Ob_VeR": f"{RELEASE_VERSION}",
      "LoGiN_UrL": "https://loginbp.ppmainecoonghj.com/",
  }

  url = f"{r_data['server'].rstrip('/')}/LoginGetSplash"
  payload_dict = {"1": r_data["lang"], "2": 1}

  try:
    session = requests.Session()

    binary_payload = smart_encode(payload_dict)
    encrypted_req = enc(binary_payload)

    r = session.post(
        url, headers=game_headers, data=encrypted_req, timeout=10, verify=False
    )

    decrypted = dec(r.content)

    if decrypted.startswith(b"\x1f\x8b"):
      decrypted = gzip.decompress(decrypted)

    decoded_dict, _ = blackboxprotobuf.decode_message(decrypted)

    extracted_events = []
    detected_region = target_region

    if "2" in decoded_dict and "1" in decoded_dict["2"]:
      raw_events = decoded_dict["2"]["1"]

      if isinstance(raw_events, dict):
        raw_events = [raw_events]
      
      VERSION = RELEASE_VERSION

      for ev in raw_events:
        if "1" in ev:
          detected_region = decode_bytes(ev["1"])

        clean_event = {
            "event_id": decode_bytes(ev.get("3", 0)),
            "event_name": decode_bytes(ev.get("4", "")),
            "start_timestamp": decode_bytes(ev.get("6", 0)),
            "redirect_url": decode_bytes(ev.get("12", "")),
            "Release_Version": VERSION,
            "image_url": decode_bytes(ev.get("14", "")),
        }
        extracted_events.append(clean_event)

    response_data = {
        "region": detected_region,
        "total_events": len(extracted_events),
        "events": extracted_events,
    }

    return jsonify(response_data)

  except Exception as e:
    return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
  app.run(host="0.0.0.0", port=5000)
