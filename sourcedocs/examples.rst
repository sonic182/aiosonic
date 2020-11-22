
========
Examples
========

TODO: More examples


Download file
#############


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
