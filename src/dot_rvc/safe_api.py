"""Small ASGI boundary for the local, pre-provisioned RVC service profile."""
import json
import math
from urllib.parse import parse_qs


def validate_setting(key, value):
    """Reject unknown operations before upstream can persist or apply them."""
    value = str(value)
    choices = {
        "modelSlotIndex": {"0"}, "gpu": {"0", "-1"}, "f0Detector": {"rmvpe"},
        "indexRatio": {"0", "0.0"}, "serverMonitorDeviceId": {"-1"},
        "serverAudioSampleRate": {"48000"}, "enableServerAudio": {"0", "1"},
        "serverAudioStated": {"0", "1"}, "passThrough": {"true", "false"},
    }
    if key in choices:
        if value not in choices[key]:
            raise ValueError("Setting value is outside this service profile")
        return
    ranges = {"tran": (-24, 24), "dstId": (0, 108), "serverInputDeviceId": (0, 10000),
              "serverOutputDeviceId": (0, 10000), "serverReadChunkSize": (16, 512)}
    if key in ranges:
        number = int(value)
        if str(number) != value or not ranges[key][0] <= number <= ranges[key][1]:
            raise ValueError("Invalid integer setting")
        return
    floats = {"serverInputAudioGain": (0, 2), "serverOutputAudioGain": (0, 1),
              "silentThreshold": (0, 1)}
    if key in floats:
        number = float(value)
        if not math.isfinite(number) or not floats[key][0] <= number <= floats[key][1]:
            raise ValueError("Invalid finite setting")
        return
    raise ValueError("Setting is disabled in this service profile")


class SafeAPI:
    """No browser audio, upload, export, merge, arbitrary model or static files.

    This is a local profile, not an authentication scheme for Internet exposure.
    """
    def __init__(self, app, status):
        self.app, self.status = app, status

    async def reply(self, send, code, content):
        body = json.dumps(content).encode("utf-8")
        await send({"type": "http.response.start", "status": code,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
            return await send({"type": "websocket.close", "code": 1008})
        if scope["type"] != "http":
            return
        headers = dict(scope.get("headers", []))
        origin = headers.get(b"origin")
        if origin is not None and origin not in (b"http://127.0.0.1:18888", b"http://localhost:18888"):
            return await self.reply(send, 403, {"error": "origin_not_allowed"})
        method, path = scope["method"], scope["path"]
        if method == "GET" and path == "/safe_status":
            return await self.reply(send, 200, self.status)
        if method == "GET" and path in ("/info", "/performance"):
            return await self.app(scope, receive, send)
        if method != "POST" or path != "/update_settings":
            return await self.reply(send, 403, {"error": "operation_disabled_in_safe_profile"})
        if headers.get(b"content-type", b"").split(b";", 1)[0] != b"application/x-www-form-urlencoded":
            return await self.reply(send, 415, {"error": "expected_urlencoded_settings"})
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > 1024:
                return await self.reply(send, 413, {"error": "settings_request_too_large"})
            if not message.get("more_body"):
                break
        try:
            form = parse_qs(body.decode("ascii"), strict_parsing=True, max_num_fields=2)
            if set(form) != {"key", "val"} or any(len(values) != 1 for values in form.values()):
                raise ValueError("Expected one key and value")
            validate_setting(form["key"][0], form["val"][0])
        except (ValueError, UnicodeError):
            return await self.reply(send, 400, {"error": "setting_rejected"})
        delivered = False
        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()
        return await self.app(scope, replay, send)
