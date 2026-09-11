"""Synthetic Monte Carlo diagnostics for the bootstrap, not market evidence."""
from dataclasses import dataclass
from datetime import date,timedelta
from pathlib import Path
import math
import platform
import random
from .uncertainty import FoldSample,UncertaintyConfig,analyze
from .serialization import canonical,digest
from .source import checked_source
from .storage import publish


def wilson(successes,total,z=1.959963984540054):
    if type(total) is not int or type(successes) is not int or not 0<=successes<=total or total<1:raise ValueError('invalid binomial counts')
    p=successes/total;den=1+z*z/total
    center=(p+z*z/(2*total))/den
    radius=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/den
    return max(0.,center-radius),min(1.,center+radius)


def synthetic_folds(seed,phi,shift,fold_count=2,length=120):
    rng=random.Random(seed);samples=[]
    for f in range(fold_count):
        values=[0.]*3;rows=[]
        for i in range(length+200):
            common=rng.gauss(0,.003)
            values=[phi*v+math.sqrt(1-phi*phi)*(common+rng.gauss(0,.002)) for v in values]
            if i>=200:rows.append(tuple(v+shift for v in values))
        dates=tuple(date(2020,1,1)+timedelta(days=f*length+i) for i in range(length))
        # Artificial counts bypass the activity guard to exercise the statistical algorithm.
        samples.append(FoldSample(dates,tuple(rows),(100,100,100)))
    return tuple(samples)


def calibrate(root,trials=40,repetitions=199,seed=98231):
    if type(trials) is not int or trials<2 or type(seed) is not int or seed<0:raise ValueError('invalid calibration settings')
    config=UncertaintyConfig(repetitions=repetitions)
    source,code=checked_source()
    plan={'kind':'synthetic_bootstrap_calibration','trials_per_case':trials,'bootstrap':config,'seed':seed,
          'cases':[(phi,shift) for phi in (0.,.5,.9) for shift in (0.,.001)],
          'source_sha256':code,'python_version':platform.python_version(),
          'limitations':'Gaussian AR(1) toy differences only; not portfolio selection, transaction accounting or empirical market stationarity'}
    identity=digest(canonical(plan).encode())[:20]
    publish(Path(root)/'plans',identity,{'plan.json':canonical(plan).encode(),'source_snapshot.json':canonical(source).encode()})
    cases=[]
    for case,(phi,shift) in enumerate(plan['cases']):
        family_rejections=0;coverage=[0]*9;available=[0]*9
        for trial in range(trials):
            samples=synthetic_folds(seed+case*100000+trial,phi,shift)
            result=analyze(samples,config)
            family_rejections+=any(r['exploratory_reject_null'] for r in result['rows'])
            for j,row in enumerate(result['rows']):
                interval=row['exploratory_percentile_interval']
                if interval is not None:
                    available[j]+=1
                    coverage[j]+=interval[0]<=shift<=interval[1]
        cases.append({'phi':phi,'true_mean_difference':shift,'family_rejections':family_rejections,
                      'trials':trials,'rejection_rate':family_rejections/trials,'rejection_rate_interval':wilson(family_rejections,trials),
                      'marginal_coverage':[{'covered':c,'available':n,'rate':c/n if n else None,
                                            'interval':wilson(c,n) if n else None} for c,n in zip(coverage,available)]})
        print(f'Calibration phi={phi}, shift={shift}: {family_rejections}/{trials} family flags',flush=True)
    rows=''.join(f'<tr><td>{c["phi"]}</td><td>{c["true_mean_difference"]}</td><td>{c["family_rejections"]}/{trials}</td><td>{c["rejection_rate"]:.1%}</td><td>{c["rejection_rate_interval"][0]:.1%}–{c["rejection_rate_interval"][1]:.1%}</td></tr>' for c in cases)
    report=f'<!doctype html><html lang="en"><meta charset="utf-8"><title>Calibration</title><style>body{{font:16px system-ui;max-width:1000px;margin:40px auto}}td,th{{padding:12px;border-bottom:1px solid #ddd}}</style><h1>Bootstrap calibration</h1><p>Synthetic AR(1) processes. Shift 0 measures null family flags; positive shift measures detection. Wilson intervals show Monte Carlo uncertainty. This does not certify market validity.</p><table><tr><th>Dependence phi</th><th>True shift</th><th>Flags</th><th>Rate</th><th>95% MC interval</th></tr>{rows}</table><p>See calibration.json for each marginal interval coverage result. High persistence may expose undercoverage and inflated false positives.</p></html>'
    return publish(Path(root)/'comparisons',identity,{'plan.json':canonical(plan).encode(),'calibration.json':canonical(cases).encode(),'report.html':report.encode()})
