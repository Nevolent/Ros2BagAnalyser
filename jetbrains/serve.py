#!/usr/bin/env python3
"""Serve only the JetBrains experiment on localhost; Python stdlib + FFmpeg."""
import argparse
import json
import mimetypes
import re
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from synthetic import Synthetic, ApiError, KINDS, SCENARIOS, stamp

ROOT = Path(__file__).resolve().parent
STATIC = {p.name for p in ROOT.iterdir() if p.suffix in ('.html','.css','.js')}
LOCK = threading.RLock()
STATE = Synthetic()

class Handler(BaseHTTPRequestHandler):
    def reply(self, body, status=200, content_type='application/json', headers=None):
        data = json.dumps(body,allow_nan=False).encode() if content_type == 'application/json' else body
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Tectrace-Synthetic','true')
        for key,value in (headers or {}).items():
            self.send_header(key,value)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        self.dispatch()

    def do_POST(self):
        self.dispatch()

    def dispatch(self):
        try:
            expected = f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host') not in (expected,f'localhost:{self.server.server_port}'):
                raise ApiError('Local host required.',403)
            origin = self.headers.get('Origin')
            if origin and origin not in (f'http://{expected}',f'http://localhost:{self.server.server_port}'):
                raise ApiError('Same-origin requests required.',403)
            url = urlsplit(self.path)
            body = {}
            if self.command == 'POST':
                length = int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 65536 or self.headers.get_content_type() != 'application/json':
                    raise ApiError('A bounded JSON body is required.')
                body = json.loads(self.rfile.read(length))
                if not isinstance(body,dict):
                    raise ApiError('Expected JSON object.')
            if STATE.scenario == 'slow' and url.path.startswith('/api/'):
                time.sleep(1.2)
            with LOCK:
                if url.path == '/__experiment' and self.command in ('GET','HEAD'):
                    return self.reply(dict(synthetic=True,scenario=STATE.scenario,scenarios=SCENARIOS))
                if url.path == '/__experiment/scenario' and self.command == 'POST':
                    STATE.reset(body.get('scenario'))
                    return self.reply(dict(synthetic=True,scenario=STATE.scenario))
                if url.path.startswith('/api/'):
                    if STATE.scenario == 'api-error':
                        raise ApiError('Synthetic service unavailable. Change the experiment scenario to recover.',503)
                    return self.api(url.path,parse_qs(url.query),body)
                name = 'index.html' if url.path == '/' else url.path.lstrip('/')
                if self.command not in ('GET','HEAD') or name not in STATIC:
                    raise ApiError('Not found.',404)
                data = (ROOT/name).read_bytes()
                if name.endswith('.html'):
                    data = data.replace(b'</head>',b'<script src="experiment.js" defer></script></head>')
                self.reply(data,content_type=mimetypes.guess_type(name)[0] or 'application/octet-stream')
        except ApiError as error:
            self.reply(dict(detail=dict(code='synthetic_error',message=error.message)),error.status)
        except (ValueError,TypeError,KeyError):
            self.reply(dict(detail=dict(code='invalid_request',message='Invalid request.')),422)
        except (BrokenPipeError,ConnectionResetError):
            pass

    def api(self,path,query,body):
        method = 'GET' if self.command == 'HEAD' else self.command
        if path == '/api/v1/catalog' and method == 'GET':
            return self.reply(STATE.catalog())
        if path == '/api/v1/catalog/rescan' and method == 'POST':
            if STATE.scenario == 'scan-error':
                raise ApiError('Synthetic traversal failed. The previous catalog is retained.',503)
            STATE.generation += 1
            STATE.scanned = stamp()
            return self.reply(dict(scan=STATE.catalog()['scan'],diagnostics=[]))
        if path == '/api/v1/recordings/prepare' and method == 'POST':
            return self.reply(STATE.prepare(body.get('recording_ids'),body.get('output_kinds',list(KINDS))),202)
        detail = re.fullmatch(r'/api/v1/recordings/(\d+)',path)
        if detail and method == 'GET':
            return self.reply(STATE.detail(STATE.record(int(detail[1]))))
        if path == '/api/v1/processing/overview' and method == 'GET':
            return self.reply(STATE.overview())
        if path == '/api/v1/processing/jobs' and method == 'GET':
            view = query.get('view',['queued'])[0]
            limit = int(query.get('limit',['25'])[0])
            cursor = query.get('cursor',[None])[0]
            if not 1 <= limit <= 100:
                raise ApiError('Invalid limit.')
            rows = STATE.listing(view)
            if cursor:
                marker = int(cursor)
                rows = [j for j in rows if j['id'] < marker] if view != 'queued' else rows[next((i+1 for i,j in enumerate(rows) if j['id'] == marker),len(rows)):]
            items = rows[:limit]
            return self.reply(dict(items=[STATE.view_job(j) for j in items],next_cursor=str(items[-1]['id']) if len(rows)>limit else None))
        control = re.fullmatch(r'/api/v1/processing/jobs/(\d+)/(pause|resume|cancel|retry)',path)
        if control and method == 'POST':
            return self.reply(STATE.control(int(control[1]),control[2]))
        if path == '/api/v1/processing/jobs/reorder' and method == 'POST':
            return self.reply(STATE.reorder(body.get('job_ids'),body.get('direction')))
        if path in ('/api/v1/processing/jobs/cancel','/api/v1/processing/jobs/retry') and method == 'POST':
            ids = STATE.ids(body.get('job_ids'))
            action = path.rsplit('/',1)[1]
            items = []
            for jid in ids:
                try:
                    items.append(STATE.control(jid,action))
                except ApiError:
                    items.append(dict(requested_job_id=jid,outcome='conflict',job=None,server_time=stamp()) if action == 'cancel' else dict(outcome='not_retryable',state='unavailable',recording_id=None,kind=None,job_id=None,artifact_id=None,diagnostic=None))
            return self.reply(dict(items=items,server_time=stamp()))
        artifact = re.fullmatch(r'/api/recordings/(\d+)/(front-preview|topdown-preview|imu-series)(?:/(media|data)/(\d+))?',path)
        if artifact and method == 'GET':
            r = STATE.record(int(artifact[1]))
            kind = artifact[2].replace('-','_')
            o = next(o for o in r['outputs'] if o['kind'] == kind)
            if artifact[4] and (o['state'] != 'ready' or str(o['artifact']['id']) != artifact[4]):
                raise ApiError('Artifact is no longer ready.',409)
            if kind == 'imu_series':
                manifest,payload = STATE.imu(r)
                return self.reply(payload if artifact[4] else manifest)
            if artifact[3] != 'media':
                raise ApiError('Not found.',404)
            data = (ROOT/'.fixtures'/f'{kind}.mp4').read_bytes()
            total = len(data)
            etag = f'"synthetic-{o["artifact"]["id"]}-{total}"'
            headers = {'Accept-Ranges':'bytes','ETag':etag}
            byte_range = self.headers.get('Range')
            if byte_range and self.headers.get('If-Range',etag) == etag:
                match = re.fullmatch(r'bytes=(\d*)-(\d*)',byte_range)
                if not match or not any(match.groups()):
                    return self.reply(b'',416,'video/mp4',dict(headers,**{'Content-Range':f'bytes */{total}'}))
                start = int(match[1]) if match[1] else max(0,total-int(match[2]))
                end = min(total-1,int(match[2])) if match[1] and match[2] else total-1
                if start > end or start >= total:
                    return self.reply(b'',416,'video/mp4',dict(headers,**{'Content-Range':f'bytes */{total}'}))
                headers['Content-Range'] = f'bytes {start}-{end}/{total}'
                return self.reply(data[start:end+1],206,'video/mp4',headers)
            return self.reply(data,200,'video/mp4',headers)
        raise ApiError('Endpoint not found.',404)

    def log_message(self,format,*args):
        if self.command == 'POST' or (len(args)>1 and str(args[1]) != '200'):
            super().log_message(format,*args)

def fixtures():
    target = ROOT/'.fixtures'
    target.mkdir(exist_ok=True)
    for kind,size in (('front_preview','640x360'),('topdown_preview','480x360')):
        output = target/f'{kind}.mp4'
        if output.exists():
            continue
        subprocess.run(['ffmpeg','-v','error','-nostdin','-f','lavfi','-i',f'testsrc2=size={size}:rate=20','-t','12','-an','-c:v','libx264','-preset','ultrafast','-crf','28','-pix_fmt','yuv420p','-movflags','+faststart',str(output)],check=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=4174)
    args = parser.parse_args()
    fixtures()
    STATE.media_sizes = {kind: (ROOT/'.fixtures'/f'{kind}.mp4').stat().st_size for kind in KINDS if kind != 'imu_series'}
    STATE.reset('mixed')
    server = ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    def advance():
        while True:
            time.sleep(.25)
            with LOCK:
                STATE.tick()
    threading.Thread(target=advance,daemon=True).start()
    print(f'Synthetic JetBrains experiment: http://127.0.0.1:{args.port}',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
if __name__ == '__main__':
    main()
