"""Explicit, repeatable historical demo setup. Never resets an existing ledger."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from quant_research.paper import create,inspect,advance
from quant_research.evaluation import prefix_dataset
from quant_research.market_data import load_snapshot
from quant_research.jobs import enqueue,run_one
from quant_research.research import submit,export_request

db=ROOT/'var/app.sqlite'
source=ROOT/'market-snapshots/96a7da745819284a3fc8'
name='xlf-historical-cash'
if not any(p['id']==name for p in inspect(db)):
    create(db,name,load_snapshot(source),historical=True)
trend='xlf-historical-trend'
if not any(p['id']==trend for p in inspect(db)):
    data=load_snapshot(source)
    create(db,trend,prefix_dataset(data,data.bars[120].date),'trend_swing',historical=True)
    advance(db,trend,data)
enqueue(db,'audit',{'snapshot':str(source)},due=0,interval=86400)
run_one(db)
request=submit(db,'critique','Explain why this historical cash demonstration does not establish a profitable strategy. Propose one preregistered next experiment without calculating results.',
               {'account':inspect(db,name),'scope':'USD stocks/ETFs; days to one week; no paid services; deterministic code owns all calculations'})
export_request(db,request,ROOT/'var/research'/request)
print(json.dumps({'dashboard_account':name,'research_request':request,'database':str(db)},indent=2))
