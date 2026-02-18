import fs from 'node:fs';
import http2 from 'node:http2';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const args = process.argv.slice(2);
const getArg = (name, fallback) => {
  const idx = args.indexOf(name);
  if (idx === -1 || idx + 1 >= args.length) {
    return fallback;
  }
  return args[idx + 1];
};

const port = Number.parseInt(getArg('--port', '8443'), 10);
const minDelayMs = Number.parseInt(getArg('--min-delay-ms', '5000'), 10);
const maxDelayMs = Number.parseInt(getArg('--max-delay-ms', '15000'), 10);

if (Number.isNaN(port) || Number.isNaN(minDelayMs) || Number.isNaN(maxDelayMs) || minDelayMs > maxDelayMs) {
  throw new Error('Invalid arguments. Check --port, --min-delay-ms and --max-delay-ms');
}

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const cert = fs.readFileSync(path.resolve(__dirname, '..', 'tests', 'files', 'certs', 'server.cert'));
const key = fs.readFileSync(path.resolve(__dirname, '..', 'tests', 'files', 'certs', 'server.key'));

const randomDelay = () => Math.floor(Math.random() * (maxDelayMs - minDelayMs + 1)) + minDelayMs;

const app = async (req, res) => {
  if (req.url === '/health') {
    res.writeHead(200, { 'content-type': 'text/plain' });
    res.end('ok');
    return;
  }

  if (req.url && req.url.startsWith('/infer')) {
    const delay = randomDelay();
    await new Promise((resolve) => setTimeout(resolve, delay));
    const payload = JSON.stringify({
      text: 'synthetic benchmark response',
      latency_ms: delay,
      http_version: req.httpVersion,
    });
    res.writeHead(200, {
      'content-type': 'application/json',
      'content-length': String(Buffer.byteLength(payload)),
    });
    res.end(payload);
    return;
  }

  res.writeHead(404, { 'content-type': 'text/plain' });
  res.end('not found');
};

const server = http2.createSecureServer(
  {
    key,
    cert,
    allowHTTP1: true,
  },
  (req, res) => {
    app(req, res).catch((err) => {
      res.writeHead(500, { 'content-type': 'text/plain' });
      res.end(`internal error: ${String(err)}`);
    });
  }
);

server.listen(port, '0.0.0.0', () => {
  process.stdout.write(`http-bench-server listening on https://0.0.0.0:${port}\n`);
});
