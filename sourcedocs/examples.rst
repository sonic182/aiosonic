
========
Examples
========

Download file
=============


.. code-block::  python

 import asyncio
 import aiosonic
 import json


 async def run():
     url = 'https://images.dog.ceo/breeds/leonberg/n02111129_2301.jpg'
     async with aiosonic.HTTPClient() as client:

        res = await client.get(url)
        assert res.status_code == 200

     if res.chunked:
         # write in chunks
         with open('dog_image.jpg', 'wb') as _file:
             async for chunk in res.read_chunks():
                 _file.write(chunk)
     else:
         # or write all bytes, for chunked this also works
         with open('dog_image.jpg', 'wb') as _file:
             _file.write(await res.content())


 if __name__ == '__main__':
     loop = asyncio.get_event_loop()
     loop.run_until_complete(run())


Concurrent Requests
===================


.. code-block::  python

   import aiosonic
   import asyncio


   async def main():
       urls = [
           'https://www.facebook.com/',
           'https://www.google.com/',
           'https://twitch.tv/',
           'https://linkedin.com/',
       ]
       async with aiosonic.HTTPClient() as client:
           # asyncio.gather is the key for concurrent requests.
           responses = await asyncio.gather(*[client.get(url) for url in urls])
           assert all([res.status_code in [200, 301] for res in responses])

   loop = asyncio.get_event_loop()
   loop.run_until_complete(main())


Chunked Requests (Stream request or response)
=============================================

Specifying an iterator as the request body, it will make the request transfer made by chunks


.. code-block::  python

 import aiosonic
 import asyncio
 import json
 
 
 async def main():
     async def data():
         yield b'foo'
         yield b'bar'
 
     async with aiosonic.HTTPClient() as client:
         url = 'https://postman-echo.com/post'
         response = await client.post(url, data=data())
         print(json.dumps(await response.json(), indent=10))
 
 
 loop = asyncio.get_event_loop()
 loop.run_until_complete(main())

Multiple Pool Configurations
============================

You can configure different connection pools for different domains, which is useful when you need specialized settings for specific services.


.. code-block::  python

   import aiosonic
   import asyncio
   from aiosonic.pools import PoolConfig
   
   
   async def main():
       pool_configs = {
           "https://www.google.com": PoolConfig(
               size=5,  # Only 5 connections for Google
               max_conn_requests=100  # Recycle connection after 100 requests
           ),
           "https://api.github.com": PoolConfig(
               size=20,  # More connections for GitHub API
               max_conn_idle_ms=60000  # Close idle connections after 60 seconds
           ),
           ":default": PoolConfig(
               size=30  # Use 30 connections for any other domains
           )
       }
   
       # Create connector with custom pool configurations
       connector = aiosonic.TCPConnector(pool_configs=pool_configs)
       
       async with aiosonic.HTTPClient(connector=connector) as client:
           # ... client usage
           pass

Cookies handling
================

Adding `handle_cookies=True` to the client, it will save response cookies and send it again for new requests. This is useful to have same cookies workflow as in browsers, also for web scraping.

.. code-block::  python

 import aiosonic
 import asyncio
 
 
 async def main():
     async with aiosonic.HTTPClient(handle_cookies=True) as client:
         cookies = {'foo1': 'bar1', 'foo2': 'bar2'}
         url = 'https://postman-echo.com/cookies/set'
         # server will respond those cookies
         response = await client.get(url, params=cookies, follow=True)
         # client keep cookies in "cookies_map"
         print(client.cookies_map['postman-echo.com'])
         print(await response.text())
 
 
 loop = asyncio.get_event_loop()
 loop.run_until_complete(main())


Use custom DNS
================

Install `aiodns` in your dependencies and use AsyncResolver

.. code-block::  python

 import aiosonic
 import asyncio
 from aiosonic.resolver import AsyncResolver
 
 
 async def main():
     resolver = AsyncResolver(nameservers=["8.8.8.8", "8.8.4.4"])
     connector = aiosonic.TCPConnector(resolver=resolver)
 
     async with aiosonic.HTTPClient(connector=connector) as client:
         data = {'foo1': 'bar1', 'foo2': 'bar2'}
         url = 'https://postman-echo.com/post'
         # server will respond those cookies
         response = await client.post(url, json=data)
         # client keep cookies in "cookies_map"
         print(await response.text())
 
 loop = asyncio.get_event_loop()
 loop.run_until_complete(main())


Use a Proxy Server
==================

Just use Proxy class.

You can install `proxy.py <https://github.com/abhinavsingh/proxy.py>`_ and use it as a proxy demo.

.. code-block::  python

  import asyncio
  
  from aiosonic import HTTPClient, Proxy
  
  
  async def main():
      # Proxy class accepts `auth` argument in the format `user:password`
      client = HTTPClient(proxy=Proxy("http://localhost:8899"))
  
      res = await client.get("https://www.google.com/")
      print(res)
      print(await res.text())
      assert res.status_code == 200
  
  
  asyncio.run(main())


Debug log
=========

Configure aiosonic logger at debug level to see some logging

.. code-block::  python

 import asyncio
 import aiosonic
 import json
 import logging
 
 
 async def run():
     # setup debug level at log
     logger = logging.getLogger('aiosonic')
     logger.setLevel(logging.DEBUG)

     async with aiosonic.HTTPClient() as client:
       response = await client.get('https://www.google.com/')
       assert response.status_code == 200
       assert 'Google' in (await response.text())

 loop = asyncio.get_event_loop()
 loop.run_until_complete(run())


Fastapi Usage
=============

.. code-block::  python


  from contextlib import asynccontextmanager
  from typing import Union

  from aiosonic import HTTPClient

  from fastapi import FastAPI

  client = HTTPClient()


  @asynccontextmanager
  async def lifespan(_app: FastAPI):
      global client
      yield
      # useful function to wait all pending requests to finish
      await client.wait_requests()


  app = FastAPI(lifespan=lifespan)


  @app.get("/")
  async def home():
      assert client, "no client"
      url = "https://postman-echo.com/post"
      res = await client.post(url, params={"foo": "bar"})
      return (await res.json())["args"]
