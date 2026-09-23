#!/usr/bin/env python3
"""Run the exact release health gate and emit health_evidence_<sha>.json."""
from __future__ import annotations
import argparse, datetime as dt, json, os, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
HEALTH=ROOT/".health"
def run(label, command, env=None):
    p=subprocess.run(command,cwd=ROOT,env=env,text=True,capture_output=True,check=False)
    return {"label":label,"command":command,"returncode":p.returncode,"status":"PASS" if p.returncode==0 else "FAIL","stdout":p.stdout[-10000:],"stderr":p.stderr[-10000:]}
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--expected-commit",required=True); ap.add_argument("--db-url",required=True)
    ap.add_argument("--source-db-url",required=True); ap.add_argument("--admin-db-url",required=True)
    ap.add_argument("--object-before",type=Path); ap.add_argument("--object-after",type=Path)
    a=ap.parse_args()
    actual=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,text=True,capture_output=True,check=True).stdout.strip()
    if actual!=a.expected_commit:
        print(f"commit mismatch: expected {a.expected_commit}, got {actual}",file=sys.stderr); return 1
    env={**os.environ,"QROS_VERIFY_DATABASE_URL":a.db_url}
    checks={}
    checks["ruff"]=run("ruff",[sys.executable,"-m","ruff","check","."])
    checks["mypy"]=run("mypy",[sys.executable,"-m","mypy","researchos/saas","--strict"])
    checks["pytest"]=run("pytest",[sys.executable,"-m","pytest","--real-db","-q","--cov=researchos","--cov-report=json:.health/coverage.json"],env)
    checks["verify_migrations"]=run("verify_migrations",[sys.executable,"scripts/verify_migrations.py"],env)
    checks["authz"]=run("authz",[sys.executable,"scripts/check_authz_coverage.py","--db-url",a.db_url])
    checks["tenant_isolation"]=run("tenant_isolation",["supabase","test","db","supabase/tests/tenant_isolation_test.sql","--db-url",a.db_url])
    backup=[sys.executable,"scripts/backup_verify.py","--source-db-url",a.source_db_url,"--admin-db-url",a.admin_db_url]
    if a.object_before and a.object_after: backup += ["--object-before",str(a.object_before),"--object-after",str(a.object_after)]
    checks["backup_restore"]=run("backup_restore",backup,env)
    coverage={}
    cp=ROOT/".health/coverage.json"
    if cp.exists(): coverage=json.loads(cp.read_text(encoding="utf-8")).get("totals",{})
    passed=all(c["status"]=="PASS" for c in checks.values())
    evidence={"schema_version":1,"commit":actual,"timestamp":dt.datetime.now(dt.timezone.utc).isoformat(),"tests_passed":passed,"health_status":"PASS" if passed else "FAIL","coverage":coverage,"rls_check":checks["authz"]["status"]=="PASS","authz_check":checks["authz"]["status"]=="PASS","tenant_isolation_check":checks["tenant_isolation"]["status"]=="PASS","checks":checks}
    HEALTH.mkdir(parents=True,exist_ok=True)
    path=HEALTH/f"health_evidence_{actual}.json"; path.write_text(json.dumps(evidence,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(evidence,indent=2,sort_keys=True)); print(f"EVIDENCE={path}")
    return 0 if passed else 1
if __name__=="__main__": raise SystemExit(main())
