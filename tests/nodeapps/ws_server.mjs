
import { WebSocketServer } from 'ws';

const myArgs = process.argv.slice(2);
const server = new WebSocketServer({ port: myArgs[0] });

server.on('connection', (socket) => {
    console.log('Client connected');

    socket.on('message', (message, isBinary) => {
        if (isBinary) {
            console.log('Received binary message:', message);
            socket.send(`Echo binary: ${message}`, { binary: true });
        } else {
            const msgStr = message.toString();
            console.log('Received text message:', msgStr);
            
            if (msgStr.startsWith('wait ')) {
                const seconds = parseInt(msgStr.split(' ')[1]);
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

console.log('WebSocket server running on ws://localhost:' + myArgs[0]);
