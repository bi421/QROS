"""Leakage-safe nested discovery of conditional XAUUSD M1 edge candidates.

Exploratory only: candidates are selected inside each chronological training
window using an inner validation split, then evaluated once on untouched outer
validation data. No outer validation labels are used for selection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

@dataclass(frozen=True)
class Candidate:
    name: str
    predicate: Callable[[dict], bool]

def _finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)

def _library() -> list[Candidate]:
    out=[]
    for v in ("bullish","bearish"):
        out.append(Candidate(f"direction={v}", lambda e,v=v:e["direction"]==v))
    for field, values in (("market_regime",["Trending_Up","Trending_Down","Ranging","Volatile","Quiet"]),("session",["Asian","European","US","Overlap"]),("volatility_state",["High","Low","Normal","Unknown"])):
        for v in values:
            out.append(Candidate(f"{field}={v}",lambda e,f=field,v=v:e.get(f)==v))
    for field in ("preceding_return_1d","preceding_return_3d","preceding_return_5d"):
        out.append(Candidate(f"{field}>0",lambda e,f=field:_finite(e.get(f)) and e[f]>0))
        out.append(Candidate(f"{field}<0",lambda e,f=field:_finite(e.get(f)) and e[f]<0))
    for lo,hi,name in ((0,30,"<30"),(30,50,"30-50"),(50,70,"50-70"),(70,101,">=70")):
        out.append(Candidate(f"rsi={name}",lambda e,lo=lo,hi=hi:_finite(e.get("rsi")) and lo<=e["rsi"]<hi))
    out.append(Candidate("macd_histogram>0",lambda e:_finite(e.get("macd_histogram")) and e["macd_histogram"]>0))
    out.append(Candidate("macd_histogram<0",lambda e:_finite(e.get("macd_histogram")) and e["macd_histogram"]<0))
    return out

def _improvement(all_rows, selected):
    if not selected: return float("nan"),0
    ya=[int(e["outcome"]["hit_threshold_1d"]) for e in all_rows]
    ys=[int(e["outcome"]["hit_threshold_1d"]) for e in selected]
    p_all=sum(ya)/len(ya); p_sel=sum(ys)/len(ys)
    model=sum((p_sel-y)**2 for y in ys)/len(ys)
    base=sum((p_all-y)**2 for y in ys)/len(ys)
    return base-model,len(selected)

def run(source:Path,output:Path,train_size:int,validation_size:int,step_size:int):
    raw=source.read_bytes(); a=json.loads(raw.decode("utf-8")); events=sorted([e for e in a["events_data"] if e.get("outcome",{}).get("hit_threshold_1d") is not None],key=lambda e:e["timestamp"])
    lib=_library(); folds=[]; start=train_size; fold=0
    while start+validation_size<=len(events):
        train=events[:start]; valid=events[start:start+validation_size]; cut=max(1000,int(len(train)*.70)); inner= train[cut:]
        ranked=[]
        for c in lib:
            s=[e for e in inner if c.predicate(e["context"])]
            if len(s)<100: continue
            imp,n=_improvement(inner,s); ranked.append((imp,n,c.name,c))
        if not ranked: raise RuntimeError(f"fold {fold}: no candidate >=100 inner events")
        ranked.sort(key=lambda x:(-x[0],-x[1],x[2])); best=ranked[0][3]
        vs=[e for e in valid if best.predicate(e["context"])]
        ts=[e for e in train if best.predicate(e["context"])]
        imp,n=_improvement(valid,vs); rate=sum(int(e["outcome"]["hit_threshold_1d"]) for e in vs)/n if n else None
        folds.append({"fold":fold,"candidate":best.name,"train_end":train[-1]["timestamp"],"validation_start":valid[0]["timestamp"],"validation_end":valid[-1]["timestamp"],"selected_train_events":len(ts),"selected_validation_events":n,"validation_events":len(valid),"conditional_rate":rate,"brier_improvement":imp})
        fold+=1; start+=step_size
    usable=[f for f in folds if f["selected_validation_events"]>0]; imps=[f["brier_improvement"] for f in usable]; pos=sum(x>0 for x in imps)
    result={"stage":"XAUUSD_M1_NESTED_EDGE_DISCOVERY","scientific_status":"EXPLORATORY_NO_EDGE_CLAIM","source_sha256":hashlib.sha256(raw).hexdigest(),"complete_events":len(events),"candidate_count":len(lib),"fold_count":len(folds),"usable_folds":len(usable),"selected_oos_events":sum(f["selected_validation_events"] for f in usable),"positive_selected_folds":pos,"selected_fold_win_rate":pos/len(usable) if usable else None,"mean_selected_fold_brier_improvement":statistics.fmean(imps) if imps else None,"folds":folds,"candidate_library":[c.name for c in lib]}
    output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps({k:result[k] for k in ("complete_events","candidate_count","fold_count","usable_folds","selected_oos_events","positive_selected_folds","selected_fold_win_rate","mean_selected_fold_brier_improvement")},indent=2))

def main():
    p=argparse.ArgumentParser(); p.add_argument("source",type=Path); p.add_argument("--output",type=Path,default=Path("artifacts/xauusd_m1_nested_edge_discovery.json")); p.add_argument("--train-size",type=int,default=2000); p.add_argument("--validation-size",type=int,default=500); p.add_argument("--step-size",type=int,default=500); a=p.parse_args(); run(a.source,a.output,a.train_size,a.validation_size,a.step_size)
if __name__=="__main__": main()
