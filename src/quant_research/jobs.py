"""At-least-once local jobs with leases, bounded retry, pause, and coalesced schedules."""
from pathlib import Path
from datetime import date,datetime,timedelta,timezone
import json
import math
import time
from uuid import uuid4
from .database import connect,transaction
from .serialization import canonical,digest

KINDS={'audit','walk_forward','paper_update','fetch','refresh_paper'}


def enqueue(db_path,kind,payload,*,interval=0,due=None):
    if kind not in KINDS or type(payload) is not dict: raise ValueError('unknown job kind or invalid payload')
    if not math.isfinite(interval) or interval<0 or (interval and interval<60): raise ValueError('recurrence must be zero or at least 60 seconds')
    due=time.time() if due is None else due
    if not math.isfinite(due): raise ValueError('job due time must be finite')
    # Paths are frozen as absolute at submission, not reinterpreted from worker cwd.
    payload=dict(payload)
    for key in ('snapshot','output','actions'):
        if payload.get(key): payload[key]=str(Path(payload[key]).resolve())
    identity=digest(canonical({'kind':kind,'payload':payload,'interval':interval,'due':due}).encode())[:24]
    with connect(db_path) as db,transaction(db):
        db.execute('INSERT OR IGNORE INTO jobs(id,kind,payload,state,due,interval) VALUES (?,?,?,?,?,?)',
                   (identity,kind,canonical(payload),'pending',due,interval))
    return identity


def claim(db_path,now=None,lease_seconds=600):
    now=time.time() if now is None else now
    with connect(db_path) as db,transaction(db):
        db.execute("UPDATE jobs SET state='failed',error='lease repeatedly expired' WHERE state='running' AND lease<=? AND attempts>=3",(now,))
        row=db.execute("SELECT * FROM jobs WHERE (state='pending' AND due<=?) OR (state='running' AND lease<=? AND attempts<3) ORDER BY due,id LIMIT 1",(now,now)).fetchone()
        if not row:return None
        token=uuid4().hex
        db.execute("UPDATE jobs SET state='running',token=?,lease=?,attempts=attempts+1 WHERE id=?",(token,now+lease_seconds,row['id']))
        return {**dict(row),'token':token,'attempts':row['attempts']+1}


def finish(db_path,job,result=None,error=None,now=None):
    now=time.time() if now is None else now
    with connect(db_path) as db,transaction(db):
        row=db.execute("SELECT * FROM jobs WHERE id=? AND token=? AND state='running'",(job['id'],job['token'])).fetchone()
        if not row:return False  # A stale worker cannot overwrite a replacement's result.
        if error:
            state='failed' if row['attempts']>=3 else 'pending'
            due=now+min(300,30*row['attempts'])
            attempts=row['attempts']
        else:
            state='pending' if row['interval'] else 'succeeded'
            due=now+row['interval']  # Coalesce missed runs rather than storm after wake.
            attempts=0
        db.execute('UPDATE jobs SET state=?,due=?,attempts=?,token=NULL,lease=NULL,error=?,result=? WHERE id=?',
                   (state,due,attempts,str(error)[:2000] if error else None,canonical(result),job['id']))
        db.execute('INSERT INTO events(kind,subject,detail) VALUES (?,?,?)',('job_failed' if error else 'job_succeeded',job['id'],str(error)[:2000] if error else canonical(result)))
    return True


def set_paused(db_path,identity,paused=True):
    with connect(db_path) as db,transaction(db):
        if not db.execute('UPDATE jobs SET state=?,token=NULL,lease=NULL WHERE id=?',('paused' if paused else 'pending',identity)).rowcount:
            raise ValueError('unknown job')


def execute_job(db_path,job):
    from .market_data import load_snapshot,fetch
    from .paper import advance,inspect,freshness
    from .walk_forward import walk_forward
    from .uncertainty import UncertaintyConfig
    p=json.loads(job['payload'])
    if job['kind']=='refresh_paper':
        account=inspect(db_path,p['portfolio'])
        if account['status']!='active' or account['spec']['historical']:
            raise ValueError('refresh requires an active forward paper account')
        with connect(db_path) as db:
            saved=db.execute('SELECT raw FROM paper_updates WHERE portfolio=? ORDER BY revision DESC LIMIT 1',(p['portfolio'],)).fetchone()
        from .data import parse_csv
        from .calendar import latest_completed_session
        now=datetime.now(timezone.utc)
        completed=latest_completed_session(now)
        end=completed.date+timedelta(days=1)
        if str(completed.date)==account['summary']['through']:
            return {'id':p['portfolio'],'unchanged':True}
        path=fetch(Path(p['output']),account['spec']['symbol'],parse_csv(saved['raw'])[0].date,end,
                   Path(p['actions']).read_bytes() if p.get('actions') else b'')
        return advance(db_path,p['portfolio'],load_snapshot(path),now=now)
    if job['kind']=='fetch':
        path=fetch(Path(p['output']),p['symbol'],date.fromisoformat(p['start']),date.fromisoformat(p['end']),
                   Path(p['actions']).read_bytes() if p.get('actions') else b'')
        return {'snapshot':str(path.resolve())}
    dataset=load_snapshot(Path(p['snapshot']))
    if job['kind']=='audit':return {'symbol':dataset.symbol,'sessions':len(dataset.bars),'sha256':dataset.sha256}
    if job['kind']=='paper_update':return advance(db_path,p['portfolio'],dataset)
    if job['kind']=='walk_forward':
        output=walk_forward(Path(p['output']),dataset,uncertainty=UncertaintyConfig() if p.get('uncertainty') else None)
        return {'report':str((output/'report.html').resolve())}
    raise ValueError('unsupported job')


def run_one(db_path,now=None):
    job=claim(db_path,now)
    if not job:return None
    try:
        result=execute_job(db_path,job)
        finish(db_path,job,result=result)
        return {'id':job['id'],'result':result}
    except Exception as exc:
        finish(db_path,job,error=f'{type(exc).__name__}: {exc}')
        return {'id':job['id'],'error':str(exc)}


def worker(db_path,once=False):
    while True:
        result=run_one(db_path)
        if result: print(canonical(result),flush=True)
        if once:return result
        if not result:time.sleep(2)
