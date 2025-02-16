// ws-server.js
import fs from 'fs';
import { WebSocketServer } from 'ws';
import http from 'http';
import https from 'https';

const args = process.argv.slice(2);
const port = parseInt(args[0], 10);
const useSSL = args[1] && args[1].toLowerCase() === 'ssl';

let server;

if (useSSL) {
  const options = {
    cert: fs.readFileSync('tests/files/certs/server.cert'),
    key: fs.readFileSync('tests/files/certs/server.key'),
  };
  server = https.createServer(options);
  server.listen(port, () => {
    console.log('HTTPS server listening on port ' + port);
  });
} else {
  server = http.createServer();
  server.listen(port, () => {
    console.log('HTTP server listening on port ' + port);
  });
}

const wss = new WebSocketServer({ server });

wss.on('connection', (socket) => {
  console.log('Client connected');
  socket.on('message', (message, isBinary) => {
    if (isBinary) {
      console.log('Received binary message:', message);
      socket.send(`Echo binary: ${message}`, { binary: true });
    } else {
      const msgStr = message.toString();
      console.log('Received text message:', msgStr);
      if (msgStr.startsWith('wait ')) {
        const seconds = parseInt(msgStr.split(' ')[1], 10);
        setTimeout(() => {
          socket.send(`Echo: ${msgStr}`);
        }, seconds * 1000);
      } else {
        socket.send(`Echo: ${msgStr}`);
      }
    }
  });

  socket.on('close', () => {
    console.log('Client disconnected');
  });
});

if (useSSL) {
  console.log('Secure WebSocket server running on wss://localhost:' + port);
} else {
  console.log('WebSocket server running on ws://localhost:' + port);
}
