import http from 'http';

let keepalive_calls = 0;  // Global counter for /keepalive calls

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
 * HTTP request handler.
 *
 * Listens for:
 * - POST requests to /upload_file. It expects a multipart/form-data body with:
 *   - a file part with field name "foo"
 *   - a regular text field with field name "field1"
 *   The response will be "<file-content>-<field1-value>".
 *
 * - DELETE requests to /delete, returning "deleted".
 *
 * - GET requests to /keepalive, returning a counter value that increments with each call.
 *
 * All other requests will return "Hello, World!" (or 405 for wrong method on /upload_file).
 */
const requestListener = async function (req, res) {
  console.log(`---- REQUEST received, url: ${req.url}, method: ${req.method}`);

  if (req.url === '/upload_file' && req.method === 'POST') {
    const buffers = [];
    req.on('data', (chunk) => {
      buffers.push(chunk);
    });

    req.on('end', () => {
      // Verify Content-Type header.
      const contentType = req.headers['content-type'];
      if (!contentType || !contentType.includes('multipart/form-data')) {
        res.writeHead(400, { 'Content-Type': 'text/plain' });
        res.end('Content-Type must be multipart/form-data');
        return;
      }

      // Extract the boundary.
      const boundaryMatch = contentType.match(/boundary=(?:"?([^";]+)"?)/i);
      if (!boundaryMatch) {
        res.writeHead(400, { 'Content-Type': 'text/plain' });
        res.end('No boundary found in multipart/form-data');
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
        res.writeHead(200, { 'Content-Type': 'text/plain' });
        res.end(responseData);
      } else {
        res.writeHead(400, { 'Content-Type': 'text/plain' });
        res.end('Invalid form data');
      }
    });
  } else if (req.url === '/delete' && req.method === 'DELETE') {
    res.writeHead(200, { 'Content-Type': 'text/plain' });
    res.end('deleted');
  } else if (req.url === '/keepalive') {
    // Increment the counter and return its value.
    keepalive_calls++;
    res.writeHead(200, { 'Content-Type': 'text/plain' });
    res.end(`${keepalive_calls}`);
  } else if (req.url === '/upload_file') {
    res.writeHead(405, { 'Content-Type': 'text/plain' });
    res.end('Method Not Allowed');
  } else {
    res.writeHead(200, { 'Content-Type': 'text/plain' });
    res.end('Hello, World!');
  }
};

// Create and start the server.
const server = http.createServer(requestListener);
server.keepAliveTimeout = 2;
const myArgs = process.argv.slice(2);
server.listen(myArgs[0]);
console.log(`--- LISTENING ON PORT ${myArgs[0]}`);

