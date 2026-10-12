from __future__ import annotations
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Optional, Union


@dataclass
class RequestConfig:
    method: str
    url: str
    headers: Dict[str, str] = field(default_factory=dict)
    params: Optional[Dict[str, Any]] = None
    data: Optional[Any] = None
    json: Optional[Union[dict, list]] = None
    request_kwargs: Dict[str, Any] = field(default_factory=dict)
    reconnect: bool = True
    retry_delay: int = 3000
    keep_connection: bool = False

    def with_headers_copy(self) -> RequestConfig:
        return replace(self, headers=dict(self.headers or {}), request_kwargs=dict(self.request_kwargs or {}))
