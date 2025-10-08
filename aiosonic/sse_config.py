from dataclasses import dataclass, field
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

    def with_headers_copy(self) -> "RequestConfig":
        new = RequestConfig(
            method=self.method,
            url=self.url,
            headers=dict(self.headers) if self.headers else {},
            params=self.params,
            data=self.data,
            json=self.json,
            request_kwargs=dict(self.request_kwargs) if self.request_kwargs else {},
            reconnect=self.reconnect,
            retry_delay=self.retry_delay,
            keep_connection=self.keep_connection,
        )
        return new
