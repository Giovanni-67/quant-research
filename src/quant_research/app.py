"""Explicit operational commands. Dashboard reads; CLI performs local mutations."""
import json
from pathlib import Path
from . import paper,jobs,research
from .dashboard import serve,snapshot
from .serialization import canonical
from .strategies import research_strategies


def register(sub):
    for name in ('paper-create','paper-update','paper-list','paper-pause','paper-resume',
                 'job-add','job-list','job-pause','job-resume','worker','dashboard',
                 'research-submit','research-export','research-import','research-run','calibrate'):
        p=sub.add_parser(name)
        p.set_defaults(operational=True)
        p.add_argument('--db',type=Path,default=Path('var/app.sqlite'))
        if name.startswith('paper-') and name!='paper-list':p.add_argument('--name',required=True)
        if name in ('paper-create','paper-update'):p.add_argument('--snapshot',type=Path,required=True)
        if name=='paper-create':
            p.add_argument('--strategy',choices=sorted(research_strategies()),default='cash')
            p.add_argument('--historical',action='store_true')
        if name=='paper-list':p.add_argument('--name')
        if name=='job-add':
            p.add_argument('--kind',choices=sorted(jobs.KINDS),required=True)
            p.add_argument('--payload',type=Path,required=True,help='JSON job arguments; paths resolve from submission cwd')
            p.add_argument('--interval',type=float,default=0,help='seconds between runs; zero means once')
        if name in ('job-pause','job-resume') or name in ('research-export','research-import','research-run'):p.add_argument('--id',required=True)
        if name=='worker':p.add_argument('--once',action='store_true')
        if name=='dashboard':
            p.add_argument('--root',type=Path,default=Path('.'))
            p.add_argument('--port',type=int,default=8765)
        if name=='research-submit':
            p.add_argument('--role',choices=sorted(research.ROLES),required=True)
            p.add_argument('--question',required=True)
            p.add_argument('--evidence',type=Path,required=True)
        if name in ('research-export','research-run'):p.add_argument('--output',type=Path,required=True)
        if name=='research-import':p.add_argument('--response',type=Path,required=True)
        if name=='calibrate':
            p.add_argument('--output',type=Path,default=Path('var/calibration'))
            p.add_argument('--trials',type=int,default=40)
            p.add_argument('--repetitions',type=int,default=199)
            p.add_argument('--seed',type=int,default=98231)


def dispatch(a):
    from .market_data import load_snapshot
    c=a.command;result=None
    if c=='paper-create':result=paper.create(a.db,a.name,load_snapshot(a.snapshot),a.strategy,historical=a.historical)
    elif c=='paper-update':result=paper.advance(a.db,a.name,load_snapshot(a.snapshot))
    elif c=='paper-list':result=paper.inspect(a.db,a.name)
    elif c in ('paper-pause','paper-resume'):paper.set_paused(a.db,a.name,c=='paper-pause');result={'id':a.name,'paused':c=='paper-pause'}
    elif c=='job-add':result={'id':jobs.enqueue(a.db,a.kind,json.loads(a.payload.read_text(encoding='utf-8-sig')),interval=a.interval)}
    elif c=='job-list':result=snapshot(a.db,Path('.'))['jobs']
    elif c in ('job-pause','job-resume'):jobs.set_paused(a.db,a.id,c=='job-pause');result={'id':a.id,'paused':c=='job-pause'}
    elif c=='worker':jobs.worker(a.db,a.once);return
    elif c=='dashboard':serve(a.db,a.root,a.port);return
    elif c=='research-submit':result={'id':research.submit(a.db,a.role,a.question,json.loads(a.evidence.read_text(encoding='utf-8-sig')))}
    elif c=='research-export':result={'directory':str(research.export_request(a.db,a.id,a.output).resolve())}
    elif c=='research-import':result=research.accept(a.db,a.id,json.loads(a.response.read_text(encoding='utf-8-sig')))
    elif c=='research-run':result=research.run_codex(a.db,a.id,a.output)
    elif c=='calibrate':
        from .calibration import calibrate
        result={'report':str((calibrate(a.output,a.trials,a.repetitions,a.seed)/'report.html').resolve())}
    else:raise ValueError('unknown operational command')
    print(canonical(result))
