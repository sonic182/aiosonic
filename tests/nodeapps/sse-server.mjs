import http from 'http';

const clients = [];

function sseHandler(req, res) {
    res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
    });

    const sendEvent = (data, event = 'message', id = null, retry = null) => {
        if (id) res.write(`id: ${id}\n`);
        if (event) res.write(`event: ${event}\n`);
        if (retry) res.write(`retry: ${retry}\n`);
        res.write(`data: ${data}\n\n`);
    };

    clients.push(res);

    req.on('close', () => {
        const index = clients.indexOf(res);
        if (index !== -1) {
            clients.splice(index, 1);
        }
    });

    // Send initial events
    sendEvent('hello', 'message', '1');
    sendEvent('world', 'message', '2');
    sendEvent('test data\nwith two lines', 'custom', '3');
}

const reconnectCounts = {};

function sseReconnectHandler(req, res) {
    res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
    });

    const sendEvent = (data, event = 'message', id = null, retry = null) => {
        if (id) res.write(`id: ${id}\n`);
        if (event) res.write(`event: ${event}\n`);
        if (retry) res.write(`retry: ${retry}\n`);
        res.write(`data: ${data}\n\n`);
    };

    // Count how many times this endpoint was requested and vary the response
    const key = req.url || '/sse-reconnect';
    reconnectCounts[key] = (reconnectCounts[key] || 0) + 1;

    if (reconnectCounts[key] === 1) {
        // first connection: send event 1 then close
        sendEvent('event 1', 'message', '1');
        res.end();
    } else {
        // subsequent connections: send event 2
        sendEvent('event 2', 'message', '2');
        // keep the connection open briefly to simulate a live stream
        setTimeout(() => {
            res.end();
        }, 50);
    }
}

function sseMalformedHandler(req, res) {
    res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
    });

    res.write('data: valid event\n\n');
    res.write('malformed event\n\n'); // Missing 'data:' prefix
    res.end();
}

function ssePostHandler(req, res) {
    let body = '';
    
    req.on('data', chunk => {
        body += chunk.toString();
    });
    
    req.on('end', () => {
        res.writeHead(200, {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
        });

        const sendEvent = (data, event = 'message', id = null, retry = null) => {
            if (id) res.write(`id: ${id}\n`);
            if (event) res.write(`event: ${event}\n`);
            if (retry) res.write(`retry: ${retry}\n`);
            res.write(`data: ${data}\n\n`);
        };

        try {
            const parsedBody = JSON.parse(body);
            sendEvent(`POST received: ${parsedBody.message || 'no message'}`, 'post-response', '1');
            sendEvent(`Stream data for: ${parsedBody.model || 'unknown'}`, 'post-response', '2');
        } catch (e) {
            sendEvent(`POST received raw: ${body}`, 'post-response', '1');
        }
        
        setTimeout(() => {
            res.end();
        }, 100);
    });
}

function ssePutHandler(req, res) {
    let body = '';
    
    req.on('data', chunk => {
        body += chunk.toString();
    });
    
    req.on('end', () => {
        res.writeHead(200, {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
        });

        const sendEvent = (data, event = 'message', id = null, retry = null) => {
            if (id) res.write(`id: ${id}\n`);
            if (event) res.write(`event: ${event}\n`);
            if (retry) res.write(`retry: ${retry}\n`);
            res.write(`data: ${data}\n\n`);
        };

        sendEvent(`PUT received: ${body}`, 'put-response', '1');
        sendEvent('PUT update confirmed', 'put-response', '2');
        
        setTimeout(() => {
            res.end();
        }, 100);
    });
}

function ssePatchHandler(req, res) {
    let body = '';
    
    req.on('data', chunk => {
        body += chunk.toString();
    });
    
    req.on('end', () => {
        res.writeHead(200, {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
        });

        const sendEvent = (data, event = 'message', id = null, retry = null) => {
            if (id) res.write(`id: ${id}\n`);
            if (event) res.write(`event: ${event}\n`);
            if (retry) res.write(`retry: ${retry}\n`);
            res.write(`data: ${data}\n\n`);
        };

        sendEvent(`PATCH received: ${body}`, 'patch-response', '1');
        sendEvent('PATCH applied', 'patch-response', '2');
        
        setTimeout(() => {
            res.end();
        }, 100);
    });
}

function sseDeleteHandler(req, res) {
    res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
    });

    const sendEvent = (data, event = 'message', id = null, retry = null) => {
        if (id) res.write(`id: ${id}\n`);
        if (event) res.write(`event: ${event}\n`);
        if (retry) res.write(`retry: ${retry}\n`);
        res.write(`data: ${data}\n\n`);
    };

    sendEvent('DELETE initiated', 'delete-response', '1');
    sendEvent('DELETE completed', 'delete-response', '2');
    
    setTimeout(() => {
        res.end();
    }, 100);
}

function sseParamsHandler(req, res) {
    const url = new URL(req.url, `http://localhost:${process.argv[2]}`);
    const params = Object.fromEntries(url.searchParams.entries());
    
    res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
    });

    const sendEvent = (data, event = 'message', id = null, retry = null) => {
        if (id) res.write(`id: ${id}\n`);
        if (event) res.write(`event: ${event}\n`);
        if (retry) res.write(`retry: ${retry}\n`);
        res.write(`data: ${data}\n\n`);
    };

    sendEvent(`Params received: ${JSON.stringify(params)}`, 'params-response', '1');
    sendEvent(`Channel: ${params.channel || 'default'}`, 'params-response', '2');
    
    setTimeout(() => {
        res.end();
    }, 100);
}

const postReconnectCounts = {};

function ssePostReconnectHandler(req, res) {
    let body = '';
    
    req.on('data', chunk => {
        body += chunk.toString();
    });
    
    req.on('end', () => {
        res.writeHead(200, {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
        });

        const sendEvent = (data, event = 'message', id = null, retry = null) => {
            if (id) res.write(`id: ${id}\n`);
            if (event) res.write(`event: ${event}\n`);
            if (retry) res.write(`retry: ${retry}\n`);
            res.write(`data: ${data}\n\n`);
        };

        const key = req.url || '/sse-post-reconnect';
        postReconnectCounts[key] = (postReconnectCounts[key] || 0) + 1;

        if (postReconnectCounts[key] === 1) {
            sendEvent(`First POST: ${body}`, 'post-reconnect', '1');
            res.end();
        } else {
            sendEvent(`Reconnected POST: ${body}`, 'post-reconnect', '2');
            setTimeout(() => {
                res.end();
            }, 50);
        }
    });
}

const server = http.createServer((req, res) => {
    if (req.url === '/sse') {
        sseHandler(req, res);
    } else if (req.url === '/sse-reconnect') {
        sseReconnectHandler(req, res);
    } else if (req.url === '/sse-malformed') {
        sseMalformedHandler(req, res);
    } else if (req.url === '/sse-post') {
        ssePostHandler(req, res);
    } else if (req.url === '/sse-put') {
        ssePutHandler(req, res);
    } else if (req.url === '/sse-patch') {
        ssePatchHandler(req, res);
    } else if (req.url === '/sse-delete') {
        sseDeleteHandler(req, res);
    } else if (req.url.startsWith('/sse-params')) {
        sseParamsHandler(req, res);
    } else if (req.url === '/sse-post-reconnect') {
        ssePostReconnectHandler(req, res);
    } else {
        res.writeHead(404);
        res.end('Not Found');
    }
});

const port = process.argv[2];
server.listen(port, () => {
    console.log(`SSE Test Server running on port ${port}`);
});
