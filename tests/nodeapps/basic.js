
// server.js
const http = require('http');
const url = require('url');
const querystring = require('querystring');
const zlib = require('zlib');

// Helper: read request body and return a promise that resolves to a string.
function readRequestBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => (body += chunk));
    req.on('end', () => resolve(body));
    req.on('error', reject);
  });
}

const server = http.createServer(async (req, res) => {
  const parsedUrl = url.parse(req.url, true);
  const pathname = parsedUrl.pathname;
  const method = req.method.toUpperCase();

  // --------------------------------------------------
  // GET endpoints
  // --------------------------------------------------
  if (method === 'GET') {
    if (pathname === '/') {
      // If query parameter "foo" exists, return its value.
      const text = parsedUrl.query && parsedUrl.query.foo
        ? parsedUrl.query.foo
        : 'Hello, world';
      res.writeHead(200, { 'Content-Type': 'text/plain' });
      res.end(text);

    } else if (pathname === '/cookies') {
      // Return "Got cookies" if any cookie header is present; otherwise "Hello, world".
      const hasCookies = Boolean(req.headers.cookie);
      const text = hasCookies ? 'Got cookies' : 'Hello, world';
      res.writeHead(200, {
        'Content-Type': 'text/plain',
        'Set-Cookie': 'csrftoken=sometoken; expires=Sat, 04-Dec-2021 11:33:13 GMT; Max-Age=31449600; Path=/'
      });
      res.end(text);

    } else if (pathname === '/gzip') {
      // Return gzip-compressed "Hello, world"
      const body = 'Hello, world';
      const compressed = zlib.gzipSync(body);
      res.writeHead(200, {
        'Content-Type': 'text/plain',
        'Content-Encoding': 'gzip'
      });
      res.end(compressed);

    } else if (pathname === '/deflate') {
      // Return deflate-compressed "Hello, world"
      const body = 'Hello, world';
      const compressed = zlib.deflateSync(body);
      res.writeHead(200, {
        'Content-Type': 'text/plain',
        'Content-Encoding': 'deflate'
      });
      res.end(compressed);

    } else if (pathname === '/chunked') {
      // Write a response in two chunks ("foo" and "bar")
      res.writeHead(200, { 'Content-Type': 'text/plain' });
      res.write('foo');
      res.write('bar');
      res.end();

    } else if (pathname === '/get_redirect') {
      // Redirect to "/"
      res.writeHead(302, { Location: '/' });
      res.end();

    } else if (pathname === '/get_redirect_full') {
      // Build a full URL redirect using the request scheme and host.
      // (For simplicity, we assume HTTP unless the connection is encrypted.)
      const scheme = req.connection.encrypted ? 'https' : 'http';
      const host = req.headers.host;
      const fullUrl = `${scheme}://${host}/`;
      res.writeHead(302, { Location: fullUrl });
      res.end();

    } else if (pathname === '/max_redirects') {
      // Self-redirect (note: this will cause an infinite redirect loop in a client).
      res.writeHead(302, { Location: '/max_redirects' });
      res.end();

    } else if (pathname === '/slow_request') {
      // Wait one second then return "foo"
      setTimeout(() => {
        res.writeHead(200, { 'Content-Type': 'text/plain' });
        res.end('foo');
      }, 1000);

    } else {
      // 404 Not Found for unknown GET endpoints.
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('Not found');
    }

  // --------------------------------------------------
  // POST endpoints
  // --------------------------------------------------
  } else if (method === 'POST') {
    if (pathname === '/post') {
      const body = await readRequestBody(req);
      const contentType = req.headers['content-type'] || '';

      // Try to parse form data if content-type is URL-encoded.
      if (contentType.includes('application/x-www-form-urlencoded')) {
        const formData = querystring.parse(body);
        if (formData.foo) {
          res.writeHead(200, { 'Content-Type': 'text/plain' });
          res.end(formData.foo);
          return;
        }
      }
      // If body contains "close", set Connection header to close.
      if (body && body.indexOf('close') !== -1) {
        // Create a Buffer for the body to ensure we know its byte length.
        const bodyBuffer = Buffer.from(body, 'utf8');
        res.writeHead(200, {
          'Content-Type': 'text/plain',
          'Connection': 'close',
          'Content-Length': bodyBuffer.length
        });
        res.end(bodyBuffer, () => {
          // Forcefully destroy the socket after the response is finished.
          req.socket.destroy();
        });
        return;
      }
      // If there is any body text, return it.
      if (body) {
        res.writeHead(200, { 'Content-Type': 'text/plain' });
        res.end(body);
        return;
      }
      // Default response.
      res.writeHead(200, { 'Content-Type': 'text/plain' });
      res.end('Hello, world');

    } else if (pathname === '/post_json') {
      const body = await readRequestBody(req);
      let data = null;
      try {
        data = JSON.parse(body);
      } catch (err) {
        // If JSON parsing fails, data remains null.
      }
      const text = data && data.foo ? data.foo : 'Hello, world';
      res.writeHead(200, { 'Content-Type': 'text/plain' });
      res.end(text);

    } else {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('Not found');
    }

  // --------------------------------------------------
  // PUT and PATCH endpoints
  // --------------------------------------------------
  } else if (method === 'PUT' || method === 'PATCH') {
    if (pathname === '/put_patch') {
      res.writeHead(200, { 'Content-Type': 'text/plain' });
      res.end('put_patch');
    } else {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('Not found');
    }

  // --------------------------------------------------
  // DELETE endpoint
  // --------------------------------------------------
  } else if (method === 'DELETE') {
    if (pathname === '/delete') {
      res.writeHead(200, { 'Content-Type': 'text/plain' });
      res.end('deleted');
    } else {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('Not found');
    }

  // --------------------------------------------------
  // Unknown methods
  // --------------------------------------------------
  } else {
    res.writeHead(405, { 'Content-Type': 'text/plain' });
    res.end('Method not allowed');
  }
});

// Create and start the server.
server.keepAliveTimeout = 60;
const myArgs = process.argv.slice(2);
server.listen(myArgs[0]);
console.log(`--- LISTENING ON PORT ${myArgs[0]}`);

