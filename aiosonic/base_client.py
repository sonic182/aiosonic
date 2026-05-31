from typing import Optional

from aiosonic.client import HTTPClient


class BaseClient:
    base_url = ""
    default_headers = {}

    def __init__(self, http_client: Optional[HTTPClient] = None):
        """Initialize the API client while allowing client reuse."""
        if http_client is not None:
            self.client = http_client
        else:
            self.client = HTTPClient()

    def process_request_url(self, url: str) -> str:
        """Process the request URL and prepend the base URL when needed."""
        if not url.startswith("http"):
            return self.base_url.rstrip("/") + "/" + url.lstrip("/")
        return url

    def merge_headers(self, headers: Optional[dict] = None) -> dict:
        """Merge default headers with the provided ones."""
        headers = headers or {}
        return {**self.default_headers, **headers}

    async def process_request(self, method: str, url: str, **kwargs):
        """Execute the request and return the raw aiosonic response."""
        full_url = self.process_request_url(url)
        headers = kwargs.pop("headers", None)
        kwargs["headers"] = self.merge_headers(headers)
        method_func = getattr(self.client, method.lower(), None)
        if not method_func:
            raise ValueError(f"HTTP method {method} is not supported.")
        return await method_func(full_url, **kwargs)

    async def process_response(self, response):
        """Return the response as-is, allowing overrides in subclasses."""
        return response

    async def request(self, method: str, url: str, **kwargs):
        """Execute the full request lifecycle."""
        response = await self.process_request(method, url, **kwargs)
        return await self.process_response(response)

    async def get(self, url: str, **kwargs):
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs):
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs):
        return await self.request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs):
        return await self.request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs):
        return await self.request("DELETE", url, **kwargs)
