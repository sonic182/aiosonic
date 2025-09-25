import http from 'http';
import { parse as parseUrl } from 'url';
import zlib from 'zlib';

let keepalive_calls = 0;  // Global counter for /keepalive calls
let redirect_count = 0;   // Counter for redirect tests

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
 * Parse a multipart/form-data body into an array of parts.
 *
 * Each part is an object with a headers object and a data string.
 */
const parseMultipart = (body, boundary) => {
  const parts = [];
  const rawParts = body.split(`--${boundary}`);
  for (const rawPart of rawParts) {
    // Remove any extra whitespace and skip empty parts.
    const part = rawPart.trim();
    if (!part || part === '--') continue;

    // Separate headers from the content. The headers and body are separated by a blank line.
    const headerDelimiter = '\r\n\r\n';
    const headerEndIndex = part.indexOf(headerDelimiter);
    if (headerEndIndex === -1) continue; // Skip if malformed.

    const rawHeaders = part.slice(0, headerEndIndex);
    const content = part.slice(headerEndIndex + headerDelimiter.length);

    // Parse headers into an object.
    const headers = {};
    rawHeaders.split('\r\n').forEach(line => {
      const [key, ...rest] = line.split(':');
      if (!rest.length) return;
      const value = rest.join(':').trim();
      headers[key.toLowerCase()] = value;

      // For Content-Disposition, extract "name" and "filename"
      if (key.toLowerCase() === 'content-disposition') {
        const nameMatch = value.match(/name="([^"]+)"/);
        if (nameMatch) {
          headers.name = nameMatch[1];
        }
        const filenameMatch = value.match(/filename="([^"]+)"/);
        if (filenameMatch) {
          headers.filename = filenameMatch[1];
        }
      }
    });

    parts.push({ headers, data: content });
  }
  return parts;
};

/**
 * Parse query parameters from URL
 */
const parseQuery = (url) => {
  const parsed = parseUrl(url, true);
  return parsed.query || {};
};

/**
 * HTTP request handler.
 *
 * Listens for:
 * - GET requests to / with optional query parameters
 * - GET requests to /cookies for cookie handling
 * - GET requests to /gzip for gzip compression
 * - GET requests to /deflate for deflate compression
 * - GET requests to /chunked for chunked responses
 * - GET requests to /get_redirect for redirects
 * - GET requests to /get_redirect_full for full URL redirects
 * - GET requests to /max_redirects for max redirect testing
 * - GET requests to /slow_request for slow requests
 * - GET requests to /keepalive, returning a counter value
 * - POST requests to /post with form data or JSON
 * - POST requests to /post_json with JSON data
 * - POST requests to /upload_file with multipart data
 * - PUT/PATCH requests to /put_patch
 * - DELETE requests to /delete
 * 
 * All other requests will return "Hello, World!" (or 405 for wrong method on specific endpoints).
 */
const requestListener = async function (req, res) {
  console.log(`---- REQUEST received, url: ${req.url}, method: ${req.method}`);
  
  const parsedUrl = parseUrl(req.url, true);
  const pathname = parsedUrl.pathname;
  const query = parsedUrl.query;

  // Handle GET requests with query parameters
  if (req.method === 'GET' && pathname === '/' && query.foo) {
    sendResponse(res, 200, 'text/plain', query.foo);
  } 
  // Handle cookies endpoint
  else if (req.method === 'GET' && pathname === '/cookies') {
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
  }
  // Handle gzip endpoint
  else if (req.method === 'GET' && pathname === '/gzip') {
    const responseBody = 'Hello, world';
    const compressed = zlib.gzipSync(responseBody);
    res.writeHead(200, {
      'Content-Type': 'text/plain',
      'Content-Encoding': 'gzip',
      'Content-Length': Buffer.byteLength(compressed)
    });
    res.end(compressed);
  }
  // Handle deflate endpoint
  else if (req.method === 'GET' && pathname === '/deflate') {
    const responseBody = 'Hello, world';
    const compressed = zlib.deflateSync(responseBody);
    res.writeHead(200, {
      'Content-Type': 'text/plain',
      'Content-Encoding': 'deflate',
      'Content-Length': Buffer.byteLength(compressed)
    });
    res.end(compressed);
  }
  // Handle chunked endpoint
  else if (req.method === 'GET' && pathname === '/chunked') {
    // For chunked responses, we don't set Content-Length
    res.writeHead(200, { 'Content-Type': 'text/plain' });
    res.write('foo');
    res.write('bar');
    res.end();
  }
  // Handle redirect endpoints
  else if (req.method === 'GET' && pathname === '/get_redirect') {
    res.writeHead(302, { 'Location': '/' });
    res.end();
  } else if (req.method === 'GET' && pathname === '/get_redirect_full') {
    const host = req.headers.host || 'localhost';
    const protocol = req.headers['x-forwarded-proto'] || 'http';
    res.writeHead(302, { 'Location': `${protocol}://${host}/` });
    res.end();
  } else if (req.method === 'GET' && pathname === '/max_redirects') {
    res.writeHead(302, { 'Location': '/max_redirects' });
    res.end();
  }
  // Handle slow request
  else if (req.method === 'GET' && pathname === '/slow_request') {
    // Simulate a slow request
    setTimeout(() => {
      sendResponse(res, 200, 'text/plain', 'foo');
    }, 1000);
  }
  // Handle keepalive
  else if (req.method === 'GET' && pathname === '/keepalive') {
    keepalive_calls++;
    sendResponse(res, 200, 'text/plain', `${keepalive_calls}`);
  }
  // Handle POST requests to /post
  else if (req.method === 'POST' && pathname === '/post') {
    const buffers = [];
    req.on('data', (chunk) => {
      buffers.push(chunk);
    });

    req.on('end', () => {
      const body = Buffer.concat(buffers).toString('utf8');
      
      // If body contains 'close', force close connection
      if (body.includes('close')) {
        res.shouldKeepAlive = false;
      }
      
      // If body is form data
      if (req.headers['content-type'] && req.headers['content-type'].includes('application/x-www-form-urlencoded')) {
        const params = new URLSearchParams(body);
        if (params.get('foo')) {
          sendResponse(res, 200, 'text/plain', params.get('foo'));
        } else {
          sendResponse(res, 200, 'text/plain', body || 'Hello, world');
        }
      } else {
        sendResponse(res, 200, 'text/plain', body || 'Hello, world');
      }
    });
  }
  // Handle POST requests to /post_json
  else if (req.method === 'POST' && pathname === '/post_json') {
    const buffers = [];
    req.on('data', (chunk) => {
      buffers.push(chunk);
    });

    req.on('end', () => {
      try {
        const body = Buffer.concat(buffers).toString('utf8');
        const json = JSON.parse(body);
        if (json.foo) {
          sendResponse(res, 200, 'text/plain', json.foo);
        } else {
          sendResponse(res, 200, 'text/plain', 'Hello, world');
        }
      } catch (e) {
        sendResponse(res, 400, 'text/plain', 'Invalid JSON');
      }
    });
  }
  // Handle POST requests to /upload_file
  else if (req.method === 'POST' && pathname === '/upload_file') {
    const buffers = [];
    req.on('data', (chunk) => {
      buffers.push(chunk);
    });

    req.on('end', () => {
      // Verify Content-Type header.
      const contentType = req.headers['content-type'];
      if (!contentType || !contentType.includes('multipart/form-data')) {
        sendResponse(res, 400, 'text/plain', 'Content-Type must be multipart/form-data');
        return;
      }

      // Extract the boundary.
      const boundaryMatch = contentType.match(/boundary=(?:"?([^";]+)"?)/i);
      if (!boundaryMatch) {
        sendResponse(res, 400, 'text/plain', 'No boundary found in multipart/form-data');
        return;
      }
      const boundary = boundaryMatch[1];

      // Combine buffers and convert to a string.
      const body = Buffer.concat(buffers).toString('utf8');

      // Parse the multipart body.
      const parts = parseMultipart(body, boundary);

      // Look for the file part (with field name "foo") and the text field "field1".
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

      // Respond if both parts were found.
      if (fileContent && field1Value) {
        const responseData = `${fileContent}-${field1Value}`;
        sendResponse(res, 200, 'text/plain', responseData);
      } else {
        sendResponse(res, 400, 'text/plain', 'Invalid form data');
      }
    });
  }
  // Handle PUT/PATCH requests
  else if ((req.method === 'PUT' || req.method === 'PATCH') && pathname === '/put_patch') {
    sendResponse(res, 200, 'text/plain', 'put_patch');
  }
  // Handle DELETE requests
  else if (req.method === 'DELETE' && pathname === '/delete') {
    sendResponse(res, 200, 'text/plain', 'deleted');
  }
  // Handle method not allowed for specific endpoints
  else if (pathname === '/upload_file') {
    sendResponse(res, 405, 'text/plain', 'Method Not Allowed');
  }
  // Handle default case
  else if (req.method === 'GET') {
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

