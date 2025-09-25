import http from 'http';
import { parse as parseUrl } from 'url';
import zlib from 'zlib';

let keepalive_calls = 0;  // Global counter for /keepalive calls

/**
 * Helper function to send response with proper Content-Length header
 * This prevents chunked transfer encoding
 */
const sendResponse = (res, statusCode, contentType, body) => {
  res.writeHead(statusCode, {
    'Content-Type': contentType,
    'Content-Length': Buffer.byteLength(body)
  });
  res.end(body);
};

/**
 * Helper to read request body as string
 */
const readBody = (req) => {
  return new Promise((resolve) => {
    const buffers = [];
    req.on('data', (chunk) => buffers.push(chunk));
    req.on('end', () => resolve(Buffer.concat(buffers).toString('utf8')));
  });
};

/**
 * Parse a multipart/form-data body into an array of parts.
 *
 * Each part is an object with a headers object and a data string.
 */
const parseMultipart = (body, boundary) => {
  const parts = [];
  const rawParts = body.split(`--${boundary}`);
  for (const rawPart of rawParts) {
    const part = rawPart.trim();
    if (!part || part === '--') continue;

    const headerDelimiter = '\r\n\r\n';
    const headerEndIndex = part.indexOf(headerDelimiter);
    if (headerEndIndex === -1) continue;

    const rawHeaders = part.slice(0, headerEndIndex);
    const content = part.slice(headerEndIndex + headerDelimiter.length);

    const headers = {};
    rawHeaders.split('\r\n').forEach(line => {
      const [key, ...rest] = line.split(':');
      if (!rest.length) return;
      const value = rest.join(':').trim();
      headers[key.toLowerCase()] = value;

      if (key.toLowerCase() === 'content-disposition') {
        const nameMatch = value.match(/name="([^"]+)"/);
        if (nameMatch) headers.name = nameMatch[1];
        const filenameMatch = value.match(/filename="([^"]+)"/);
        if (filenameMatch) headers.filename = filenameMatch[1];
      }
    });

    parts.push({ headers, data: content });
  }
  return parts;
};

// Handler functions
const handlers = {
  'GET /': (req, res, parsedUrl) => {
    const query = parsedUrl.query;
    if (query.foo) {
      sendResponse(res, 200, 'text/plain', query.foo);
    } else {
      sendResponse(res, 200, 'text/plain', 'Hello, world');
    }
  },

  'GET /cookies': (req, res) => {
    const hasCookies = req.headers.cookie ? 'Got cookies' : 'Hello, world';
    const headers = {
      'Content-Type': 'text/plain',
      'Content-Length': Buffer.byteLength(hasCookies)
    };
    if (!req.headers.cookie) {
      headers['Set-Cookie'] = 'csrftoken=sometoken; expires=Sat, 04-Dec-2021 11:33:13 GMT; Max-Age=31449600; Path=/';
    }
    res.writeHead(200, headers);
    res.end(hasCookies);
  },

  'GET /gzip': (req, res) => {
    const responseBody = 'Hello, world';
    const compressed = zlib.gzipSync(responseBody);
    res.writeHead(200, {
      'Content-Type': 'text/plain',
      'Content-Encoding': 'gzip',
      'Content-Length': Buffer.byteLength(compressed)
    });
    res.end(compressed);
  },

  'GET /deflate': (req, res) => {
    const responseBody = 'Hello, world';
    const compressed = zlib.deflateSync(responseBody);
    res.writeHead(200, {
      'Content-Type': 'text/plain',
      'Content-Encoding': 'deflate',
      'Content-Length': Buffer.byteLength(compressed)
    });
    res.end(compressed);
  },

  'GET /chunked': (req, res) => {
    res.writeHead(200, { 'Content-Type': 'text/plain' });
    res.write('foo');
    res.write('bar');
    res.end();
  },

  'GET /get_redirect': (req, res) => {
    res.writeHead(302, { 'Location': '/' });
    res.end();
  },

  'GET /get_redirect_full': (req, res) => {
    const host = req.headers.host || 'localhost';
    const protocol = req.headers['x-forwarded-proto'] || 'http';
    res.writeHead(302, { 'Location': `${protocol}://${host}/` });
    res.end();
  },

  'GET /max_redirects': (req, res) => {
    res.writeHead(302, { 'Location': '/max_redirects' });
    res.end();
  },

  'GET /slow_request': (req, res) => {
    setTimeout(() => {
      sendResponse(res, 200, 'text/plain', 'foo');
    }, 1000);
  },

  'GET /keepalive': (req, res) => {
    keepalive_calls++;
    sendResponse(res, 200, 'text/plain', `${keepalive_calls}`);
  },

  'POST /post': async (req, res) => {
    const body = await readBody(req);

    if (body.includes('close')) {
      res.shouldKeepAlive = false;
    }

    if (req.headers['content-type']?.includes('application/x-www-form-urlencoded')) {
      const params = new URLSearchParams(body);
      const response = params.get('foo') || body || 'Hello, world';
      sendResponse(res, 200, 'text/plain', response);
    } else {
      sendResponse(res, 200, 'text/plain', body || 'Hello, world');
    }
  },

  'POST /post_json': async (req, res) => {
    const body = await readBody(req);
    try {
      const json = JSON.parse(body);
      const response = json.foo || 'Hello, world';
      sendResponse(res, 200, 'text/plain', response);
    } catch (e) {
      sendResponse(res, 400, 'text/plain', 'Invalid JSON');
    }
  },

  'POST /upload_file': async (req, res) => {
    const contentType = req.headers['content-type'];
    if (!contentType?.includes('multipart/form-data')) {
      sendResponse(res, 400, 'text/plain', 'Content-Type must be multipart/form-data');
      return;
    }

    const boundaryMatch = contentType.match(/boundary=(?:"?([^";]+)"?)/i);
    if (!boundaryMatch) {
      sendResponse(res, 400, 'text/plain', 'No boundary found in multipart/form-data');
      return;
    }

    const body = await readBody(req);
    const parts = parseMultipart(body, boundaryMatch[1]);

    let fileContent = null;
    let field1Value = null;
    for (const part of parts) {
      if (part.headers.name === 'foo' && part.headers.filename) {
        fileContent = part.data.trim();
      }
      if (part.headers.name === 'field1') {
        field1Value = part.data.trim();
      }
    }

    if (fileContent && field1Value) {
      sendResponse(res, 200, 'text/plain', `${fileContent}-${field1Value}`);
    } else {
      sendResponse(res, 400, 'text/plain', 'Invalid form data');
    }
  },

  'PUT /put_patch': (req, res) => {
    sendResponse(res, 200, 'text/plain', 'put_patch');
  },

  'PATCH /put_patch': (req, res) => {
    sendResponse(res, 200, 'text/plain', 'put_patch');
  },

  'DELETE /delete': (req, res) => {
    sendResponse(res, 200, 'text/plain', 'deleted');
  }
};

/**
 * HTTP request handler.
 */
const requestListener = async function(req, res) {
  console.log(`---- REQUEST received, url: ${req.url}, method: ${req.method}`);

  const parsedUrl = parseUrl(req.url, true);
  const pathname = parsedUrl.pathname;
  const key = `${req.method} ${pathname}`;

  const handler = handlers[key];
  if (handler) {
    await handler(req, res, parsedUrl);
  } else if (pathname === '/upload_file') {
    sendResponse(res, 405, 'text/plain', 'Method Not Allowed');
  } else if (req.method === 'GET') {
    sendResponse(res, 200, 'text/plain', 'Hello, world');
  } else {
    sendResponse(res, 405, 'text/plain', 'Method Not Allowed');
  }
};

// Create and start the server.
const server = http.createServer(requestListener);
server.keepAliveTimeout = 2;
const myArgs = process.argv.slice(2);
server.listen(myArgs[0]);
console.log(`--- LISTENING ON PORT ${myArgs[0]}`);

