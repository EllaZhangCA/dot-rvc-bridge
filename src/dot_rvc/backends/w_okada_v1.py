import httpx

from ..errors import BridgeError


class WOkadaV1:
    name = "w-okada-v1"

    def __init__(self, url: str, transport=None):
        self.url = url
        self.transport = transport

    def _request(self, method: str, path: str, data=None) -> dict:
        try:
            with httpx.Client(
                base_url=self.url,
                timeout=httpx.Timeout(45.0 if method == "POST" else 5.0, connect=3.0),
                trust_env=False, follow_redirects=False, transport=self.transport,
            ) as client:
                response = client.request(method, path, data=data)
                response.raise_for_status()
                result = response.json()
        except httpx.TimeoutException as exc:
            detail = "更新可能已生效；请重新查询状态，不要盲目重试。" if method == "POST" else "引擎响应超时。"
            raise BridgeError("engine_timeout", detail) from exc
        except httpx.HTTPStatusError as exc:
            raise BridgeError("engine_http_error", f"引擎返回 HTTP {exc.response.status_code}。") from exc
        except httpx.RequestError as exc:
            detail = "更新结果未知，请查询引擎状态。" if method == "POST" else "无法连接本地引擎；请先启动兼容版本。"
            raise BridgeError("engine_unreachable", detail) from exc
        except ValueError as exc:
            raise BridgeError("incompatible_engine", "引擎没有返回 JSON；请核对版本和端口。") from exc
        if not isinstance(result, dict) or result.get("status") != "OK":
            raise BridgeError("engine_rejected", "引擎未返回成功状态；请查看引擎界面的错误。")
        return result

    def read_state(self) -> dict:
        return self._request("GET", "/info")

    def write_setting(self, key: str, value: int | float | bool) -> None:
        encoded = str(value).lower() if type(value) is bool else str(value)
        self._request("POST", "/update_settings", {"key": key, "val": encoded})
