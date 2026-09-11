"""Loopback-only, read-only dashboard. No order endpoint or model execution endpoint."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from importlib.resources import files
from urllib.parse import urlsplit,parse_qs,unquote
from datetime import datetime,timezone
import json
import mimetypes
from .database import connect
from .paper import inspect,freshness
from .serialization import canonical


def experiments(root):
    root=Path(root).resolve();result=[]
    for pattern in ('research-results*/comparisons/*/report.html','demo-results*/*/report.html','market-results/*/report.html','var/calibration/comparisons/*/report.html','var/experiments/comparisons/*/report.html'):
        for path in root.glob(pattern):
            resolved=path.resolve()
            if not resolved.is_relative_to(root):continue
            plan=path.parent/'plan.json'
            try: data=json.loads(plan.read_text()) if plan.exists() else {}
            except (OSError,ValueError):continue
            result.append({'id':path.parent.name,'kind':data.get('kind','backtest'),'symbol':data.get('symbol',''),
                           'url':'/files/'+path.relative_to(root).as_posix(),'modified':path.stat().st_mtime})
    return sorted(result,key=lambda x:x['modified'],reverse=True)


def snapshot(db_path,root):
    portfolios=inspect(db_path)
    with connect(db_path) as db:
        jobs=[dict(r) for r in db.execute('SELECT id,kind,state,due,interval,attempts,error,result FROM jobs ORDER BY due')]
        research=[{**dict(r),'request':json.loads(r['request']),'response':json.loads(r['response']) if r['response'] else None} for r in db.execute('SELECT * FROM research ORDER BY created DESC')]
        events=[dict(r) for r in db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 100')]
    return {'portfolios':portfolios,'jobs':jobs,'research':research,'events':events,'experiments':experiments(root),
            'server_time':datetime.now(timezone.utc).isoformat(),'mode':'paper_only'}


def handler(db_path,root):
    root=Path(root).resolve()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):self.send_error(405,'Dashboard is read-only; use the explicit CLI for changes')
        def do_GET(self):
            if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'):
                self.send_error(403,'Invalid host');return
            parsed=urlsplit(self.path)
            try:
                if parsed.path=='/api/state':payload=canonical(snapshot(db_path,root)).encode();mime='application/json'
                elif parsed.path=='/api/portfolio':payload=canonical(inspect(db_path,parse_qs(parsed.query).get('id',[''])[0])).encode();mime='application/json'
                elif parsed.path in ('/','/dashboard.js','/dashboard.css'):
                    name='dashboard.html' if parsed.path=='/' else parsed.path[1:]
                    payload=files('quant_research').joinpath('resources/'+name).read_bytes()
                    mime={'dashboard.html':'text/html','dashboard.css':'text/css','dashboard.js':'text/javascript'}[name]
                elif parsed.path.startswith('/files/'):
                    relative=unquote(parsed.path[len('/files/'):]);path=(root/relative).resolve()
                    if not path.is_relative_to(root) or path.suffix not in ('.html','.json','.csv') or not (
                        relative.startswith(('research-results','demo-results','market-results','var/calibration/','var/experiments/'))):
                        self.send_error(403);return
                    payload=path.read_bytes();mime=mimetypes.guess_type(path.name)[0] or 'text/plain'
                else:self.send_error(404);return
            except (ValueError,OSError,KeyError):self.send_error(404,'Record or file unavailable');return
            self.send_response(200)
            self.send_header('Content-Type',mime+'; charset=utf-8')
            self.send_header('Content-Length',str(len(payload)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"sandbox allow-same-origin; default-src 'none'; style-src 'unsafe-inline'; img-src data:" if parsed.path.startswith('/files/') else "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers();self.wfile.write(payload)
    return Handler


def serve(db_path,root,port=8765):
    server=ThreadingHTTPServer(('127.0.0.1',port),handler(db_path,root))
    print(f'Research Desk: http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    finally:server.server_close()
