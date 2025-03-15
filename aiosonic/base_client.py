import json
from typing import Optional

from aiosonic import HTTPClient


class AioSonicBaseClient:
    base_url = ""
    default_headers = {}

    def __init__(self, http_client: Optional[HTTPClient] = None):
        """
        Initialize the API client.

        If an HTTPClient instance is provided, it will be used.
        Otherwise, a new HTTPClient is created for each instance.
        """
        if http_client is not None:
            self.client = http_client
        else:
            # Create a new client instance for each base client
            self.client = HTTPClient()

    def process_request_url(self, url: str) -> str:
        """
        Process the request URL. If the URL is relative, prepend the base_url.
        """
        if not url.startswith("http"):
            return self.base_url.rstrip("/") + "/" + url.lstrip("/")
        return url

    def process_response_body(self, body: str):
        """
        Process the response body by attempting to decode JSON.
        If decoding fails, return the raw text.
        """
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return body

    async def request(self, method: str, url: str, **kwargs):
        """
        General request method that:
          1. Processes the URL.
          2. Merges default headers with any provided headers.
          3. Uses the singleton HTTPClient to perform the request.
          4. Processes the response body.
        """
        full_url = self.process_request_url(url)
        # Merge default headers with any headers provided in kwargs.
        headers = kwargs.pop("headers", {})
        merged_headers = {**self.default_headers, **headers}
        kwargs["headers"] = merged_headers

        # Get the appropriate HTTP method from the client.
        method_func = getattr(self.client, method.lower(), None)
        if not method_func:
            raise ValueError(f"HTTP method {method} is not supported.")

        response = await method_func(full_url, **kwargs)
        text = await response.text()
        return self.process_response_body(text)

    # Convenience methods for common HTTP verbs.
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
