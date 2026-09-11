"""Persistent single-instrument paper accounts, advanced by strict append-only replay."""
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal
import json
import re
from .calendar import latest_completed_session
from .data import Dataset
from .database import connect,transaction
from .engine import run
from .models import Config
from .reporting import metrics
from .risk import RiskManaged,RiskRules
from .serialization import canonical,digest
from .source import checked_source
from .strategies import research_strategies


def freshness(dataset, now=None):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None: raise ValueError('clock must include timezone')
    expected=latest_completed_session(now).date
    return {'expected_session':str(expected),'actual_session':str(dataset.bars[-1].date),
            'fresh':dataset.bars[-1].date==expected}


def create(db_path,name,dataset,strategy='cash',config=Config(),*,historical=False,rules=RiskRules(),now=None):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,60}',name): raise ValueError('portfolio ID needs letters, digits, underscore or dash')
    if strategy not in research_strategies(): raise ValueError('strategy must be registered')
    if config.max_position_weight > rules.max_exposure: raise ValueError('entry allocation exceeds risk exposure ceiling')
    if not historical and (dataset.kind != 'vendor_checked_engineering_only' or not freshness(dataset,now)['fresh']):
        raise ValueError('forward paper needs a fresh checked snapshot; historical replay requires --historical')
    source,code=checked_source()
    spec={'symbol':dataset.symbol,'kind':dataset.kind,'strategy':strategy,'execution':config,'risk':rules,
          'decision_start':str(dataset.bars[0].date if historical else dataset.bars[-1].date),
          'historical':historical,'source_sha256':code}
    result=_simulate(dataset,spec)
    identity=digest(canonical({'bars':dataset.bars_sha256,'actions':dataset.actions_sha256}).encode())
    with connect(db_path) as db,transaction(db):
        if db.execute('SELECT 1 FROM portfolios WHERE id=?',(name,)).fetchone(): raise ValueError('portfolio already exists')
        db.execute('INSERT INTO portfolios VALUES (?,?,?,1)',(name,canonical(spec),'active'))
        db.execute('INSERT OR IGNORE INTO source_snapshots VALUES (?,?)',(code,canonical(source)))
        _insert(db,name,1,identity,dataset,result)
    return inspect(db_path,name)


def _simulate(dataset,spec):
    cfg=Config(**{k:Decimal(v) for k,v in json.loads(canonical(spec['execution'])).items()})
    raw=json.loads(canonical(spec['risk']))
    rules=RiskRules(**{k:(v if k=='atr_window' else Decimal(v)) for k,v in raw.items()})
    strategy=RiskManaged(research_strategies()[spec['strategy']],cfg.initial_cash,rules)
    return run(dataset.bars,strategy,cfg,actions=dataset.actions,decision_start=date.fromisoformat(spec['decision_start']))


def _insert(db,name,revision,identity,dataset,result):
    summary=metrics(result)
    summary.update({'through':str(dataset.bars[-1].date),'risk_halted':result.risk_halted})
    db.execute('INSERT INTO paper_updates VALUES (?,?,?,?,?,?,?,?)',
        (name,revision,identity,dataset.raw,dataset.actions_raw,dataset.provenance_json,canonical(result),canonical(summary)))
    db.execute('INSERT INTO events(kind,subject,detail) VALUES (?,?,?)',('paper_update',name,canonical({'revision':revision,'through':summary['through']})))


def advance(db_path,name,dataset,*,now=None):
    # Compute inside a serialized transaction: acceptable for small daily-bar histories.
    with connect(db_path) as db,transaction(db):
        row=db.execute('SELECT * FROM portfolios WHERE id=?',(name,)).fetchone()
        if not row: raise ValueError('unknown portfolio')
        if row['status']!='active': raise ValueError('portfolio is paused')
        spec=json.loads(row['spec'])
        if spec['source_sha256']!=checked_source()[1]: raise ValueError('paper code changed; retain this ledger and explicitly create a reviewed new account')
        if dataset.symbol!=spec['symbol'] or dataset.kind!=spec['kind']: raise ValueError('paper dataset identity changed')
        if not spec['historical'] and not freshness(dataset,now)['fresh']: raise ValueError('stale or future data; paper update refused')
        previous=db.execute('SELECT * FROM paper_updates WHERE portfolio=? AND revision=?',(name,row['revision'])).fetchone()
        old=Dataset(previous['raw'],spec['symbol'],spec['kind'],previous['provenance'],previous['actions'])
        if dataset.bars[:len(old.bars)]!=old.bars: raise ValueError('historical bars changed or were removed')
        past=tuple(a for a in dataset.actions if a.effective_date<=old.bars[-1].date)
        if past!=old.actions: raise ValueError('historical corporate actions changed')
        identity=digest(canonical({'bars':dataset.bars_sha256,'actions':dataset.actions_sha256}).encode())
        if identity==previous['identity']: return {'id':name,'revision':row['revision'],'unchanged':True}
        result=_simulate(dataset,spec)
        old_result=json.loads(previous['result']); new_result=json.loads(canonical(result))
        through=str(old.bars[-1].date)
        for key in ('equity','fills','signals','rejections','action_ledger'):
            if [r for r in new_result[key] if r['date']<=through]!=old_result[key]:
                raise ValueError(f'paper replay changed prior {key}')
        revision=row['revision']+1
        _insert(db,name,revision,identity,dataset,result)
        db.execute('UPDATE portfolios SET revision=? WHERE id=?',(revision,name))
    return inspect(db_path,name)


def inspect(db_path,name=None):
    with connect(db_path) as db:
        rows=db.execute('SELECT p.*,u.summary,u.result FROM portfolios p JOIN paper_updates u ON u.portfolio=p.id AND u.revision=p.revision'+(' WHERE p.id=?' if name else '')+' ORDER BY p.id', (name,) if name else ()).fetchall()
        result=[{'id':r['id'],'status':r['status'],'revision':r['revision'],'spec':json.loads(r['spec']),
                 'summary':json.loads(r['summary']),**({'result':json.loads(r['result'])} if name else {})} for r in rows]
    if name and not result: raise ValueError('unknown portfolio')
    return result[0] if name else result


def set_paused(db_path,name,paused=True):
    with connect(db_path) as db,transaction(db):
        if not db.execute('UPDATE portfolios SET status=? WHERE id=?',('paused' if paused else 'active',name)).rowcount: raise ValueError('unknown portfolio')
        db.execute('INSERT INTO events(kind,subject,detail) VALUES (?,?,?)',('paper_status',name,'paused' if paused else 'active'))
