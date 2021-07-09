
import http from 'http';

const requestListener = function (req, res) {
  console.log(` ---- REQUEST received http1_serv, url: ${req.url}, method: ${req.method} `)

  switch(req.url) {
    case '/':
      res.writeHead(200);
      res.end('path /');

    break;

    case '/delete':
      res.writeHead(200);
      res.end('deleted');

    break;

    default:
      res.writeHead(200);
      res.end('Hello, World!');
  }
}

const server = http.createServer(requestListener);
let myArgs = process.argv.slice(2);
server.listen(myArgs[0]);
console.log(`--- LISTENING ON PORT ${myArgs[0]}`)
