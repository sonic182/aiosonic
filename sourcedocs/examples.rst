
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
      client = aiosonic.HttpClient()

      res = await client.get(url, verify=False)
      assert res.status_code == 200
      assert res.chunked

      # write in chunks
      with open('dog_image.jpg', 'wb') as _file:
          async for chunk in res.read_chunks():
              _file.write(chunk)

      # or write all bytes
      # with open('dog_image.jpg', 'wb') as _file:
      #     _file.write(await res.content())
  
  
  if __name__ == '__main__':
      loop = asyncio.get_event_loop()
      loop.run_until_complete(run())
