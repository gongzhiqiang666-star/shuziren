#!/usr/bin/env node
// Local static preview only. No uploads, model APIs, credentials or shell calls.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const args = process.argv.slice(2);
let directory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../web/dist');
let port = 5173;
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--dir' && args[i + 1]) directory = path.resolve(args[++i]);
  else if (args[i] === '--port' && args[i + 1]) port = Number(args[++i]);
  else { console.error('用法：node serve_avatar3d.mjs [--dir 构建目录] [--port 5173]'); process.exit(1); }
}
if (!Number.isInteger(port) || port < 1024 || port > 65535 || !fs.existsSync(path.join(directory, 'index.html'))) {
  console.error('端口或构建目录无效。请先构建前端，或使用完整的本地验证包。'); process.exit(1);
}
directory = fs.realpathSync(directory);
const mime = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.glb': 'model/gltf-binary', '.bin': 'application/octet-stream', '.md': 'text/plain; charset=utf-8', '.txt': 'text/plain; charset=utf-8' };
const server = http.createServer((request, response) => {
  const fail = (code, text) => { response.writeHead(code, { 'Content-Type': 'text/plain; charset=utf-8' }); response.end(text); };
  if (!['127.0.0.1:' + port, 'localhost:' + port].includes(request.headers.host)) return fail(403, '仅供本机访问。');
  if (!['GET', 'HEAD'].includes(request.method)) return fail(405, '本地验证包只提供静态页面。');
  let pathname;
  try { pathname = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname); } catch { return fail(400, '路径无效。'); }
  if (pathname === '/') { response.writeHead(302, { Location: '/avatar3d' }); response.end(); return; }
  if (pathname === '/avatar3d' || pathname === '/avatar3d/') pathname = '/index.html';
  if (pathname.includes('\0') || pathname.includes('\\')) return fail(400, '路径无效。');
  let file;
  try {
    file = fs.realpathSync(path.resolve(directory, '.' + pathname));
    if (!file.startsWith(directory + path.sep) || !fs.statSync(file).isFile()) return fail(404, '资源不存在。');
  } catch { return fail(404, '资源不存在。'); }
  const info = fs.statSync(file);
  response.writeHead(200, {
    'Content-Type': mime[path.extname(file).toLowerCase()] || 'application/octet-stream',
    'Content-Length': info.size,
    'Cache-Control': 'no-cache',
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
    'Permissions-Policy': 'microphone=(self), camera=()',
    'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; media-src 'self' blob:; worker-src 'self'; connect-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
  });
  if (request.method === 'HEAD') response.end();
  else { const stream = fs.createReadStream(file); stream.on('error', () => response.destroy()); response.on('close', () => stream.destroy()); stream.pipe(response); }
});
server.on('error', error => { console.error(error.code === 'EADDRINUSE' ? '端口已被占用。关闭旧预览，或使用 --port 指定其他端口。' : '本地预览服务无法启动：' + error.code); process.exitCode = 1; });
server.listen(port, '127.0.0.1', () => {
  console.log('\n3D 本地验证版已启动： http://127.0.0.1:' + port + '/avatar3d');
  console.log('在浏览器打开该地址。首次点击播放或录音时，按浏览器提示操作。');
  console.log('仅监听本机，不上传人物或音频。按 Ctrl+C 停止服务。\n');
});
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.close());
