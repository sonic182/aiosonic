
const http = require('http');
const querystring = require('querystring');
const { StringDecoder } = require('string_decoder');

// Use process.argv to get the port from the command line
const port = parseInt(process.argv[2], 10) || 3000; // Default to 3000 if no port is provided

const server = http.createServer((req, res) => {
  if (req.method === 'POST' && req.url === '/upload_file') {
    let body = [];
    req.on('data', (chunk) => {
      body.push(chunk);
    }).on('end', () => {
      body = Buffer.concat(body).toString();

      // Basic parsing of multipart form data (Note: This is a simplified approach and may not handle all cases)
      const boundary = body.split('\r\n')[0].slice(2);
      const parts = body.split(boundary).slice(1, -1);

      let fileContent = null;
      let field1Value = '';

      for (const part of parts) {
        const lines = part.split('\r\n');
        if (lines[2]) {
          if (lines[1].includes('filename')) {
            //This assumes the whole file is in memory
            fileContent = Buffer.from(lines.slice(4, -2).join('\r\n'));
          } else if (lines[1].includes('field1')) {
            field1Value = lines[3];
          }
        }
      }

      if (fileContent) {
        const responseData = Buffer.concat([fileContent, Buffer.from('-'), Buffer.from(field1Value)]);
        res.writeHead(200, { 'Content-Type': 'application/octet-stream' });
        res.end(responseData);
      } else {
        res.writeHead(400, { 'Content-Type': 'text/plain' });
        res.end('No file uploaded.');
      }
    });
  } else {
    res.writeHead(405, { 'Content-Type': 'text/plain' });
    res.end('Method Not Allowed');
  }
});

server.listen(port, () => {
  console.log(`Server listening at http://localhost:${port}`);
});
