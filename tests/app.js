
const { createSecureServer } = require('http2');
const { readFileSync, createReadStream } = require('fs');

const cert = readFileSync('tests/files/certs/server.cert');
const key = readFileSync('tests/files/certs/server.key');

var myArgs = process.argv.slice(2);

const server = createSecureServer(
  { cert, key, allowHTTP1: true },
  onRequest
).listen(myArgs[0], "0.0.0.0");

function onRequest(req, res) {
  // Detects if it is a HTTPS request or HTTP/2
  const { socket: { alpnProtocol } } = req.httpVersion === '2.0' ?
    req.stream.session : req;

  if (req.url == '/sample.png') {
    streamFile("sample.png", res);
  } else {
    res.writeHead(200, { 'content-type': 'text/plain' });
    res.end('Hello World')
  }
}


function streamFile(filename, res) {
  // This line opens the file as a readable stream
  var readStream = createReadStream(`tests/${filename}`);

  // This will wait until we know the readable stream is actually valid before piping
  readStream.on('open', function () {
    // This just pipes the read stream to the response object (which goes to the client)
    readStream.pipe(res);
  });

  // This catches any errors that happen while creating the readable stream (usually invalid names)
  readStream.on('error', function(err) {
    console.log("--- err")
    console.log(err)
    res.end(err);
  });
}
console.log(`server listen on port ${myArgs[0]}`);
