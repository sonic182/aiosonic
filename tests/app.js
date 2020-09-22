
const { createSecureServer } = require('http2');
const { readFileSync } = require('fs');

const cert = readFileSync('tests/files/certs/server.cert');
const key = readFileSync('tests/files/certs/server.key');

var myArgs = process.argv.slice(2);

const server = createSecureServer(
  { cert, key, allowHTTP1: true },
  onRequest
).listen(myArgs[0]);

function onRequest(req, res) {
  // Detects if it is a HTTPS request or HTTP/2
  const { socket: { alpnProtocol } } = req.httpVersion === '2.0' ?
    req.stream.session : req;

  res.writeHead(200, { 'content-type': 'text/plain' });

  res.end('Hello World')
}
console.log(`server listen on port ${myArgs[0]}`);
