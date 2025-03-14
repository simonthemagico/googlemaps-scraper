import time
from typing import Any, Dict, List, Optional, Union
from tls_client.structures import CaseInsensitiveDict

class Request:
    def __init__(self, request_json: dict):
        self.request_json = request_json
        
        self.headers: Dict[str, str] = CaseInsensitiveDict(request_json.get("headers", {}))
        self.url: str = request_json.get("requestUrl", "")
        self.method: str = request_json.get("requestMethod", "GET").upper()
        self.cookies: List[Dict[str, Any]] = request_json.get("requestCookies", [])
        self.proxies: Optional[str] = request_json.get("proxyUrl")
        self.body: Optional[Union[str, bytes]] = request_json.get("requestBody")
        self.params: Dict[str, str] = request_json.get("params", {})
        if self.cookies:
            cookieStr = "; ".join([f"{cookie['name']}={cookie['value']}" for cookie in self.cookies])
            self.headers["Cookie"] = cookieStr

    def __repr__(self):
        return (
            f"Request(method={self.method}, url={self.url})"
        )
