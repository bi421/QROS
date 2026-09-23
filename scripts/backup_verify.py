#!/usr/bin/env python3
"""Verify a PostgreSQL backup can be restored into a disposable container."""
from __future__ import annotations
import argparse, hashlib, os, shutil, subprocess
from pathlib import Path
def run(cmd:list[str], **kwargs:object)->None: subprocess.run(cmd,check=True,**kwargs)
def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("--database-url",default=os.getenv("QROS_BACKUP_DATABASE_URL")); p.add_argument("--output",type=Path,default=Path("backup/qros.dump")); p.add_argument("--skip-restore",action="store_true"); a=p.parse_args()
    if not a.database_url: raise SystemExit("QROS_BACKUP_DATABASE_URL or --database-url is required")
    for tool in ("pg_dump","psql"):
        if shutil.which(tool) is None: raise SystemExit(f"{tool} is required")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    run(["pg_dump","--format=custom","--no-owner","--file",str(a.output),a.database_url])
    digest=hashlib.sha256(a.output.read_bytes()).hexdigest(); size=a.output.stat().st_size
    if size<=0: raise SystemExit("backup is empty")
    report={"backup":str(a.output),"bytes":size,"sha256":digest,"restored":False}
    if not a.skip_restore:
        if shutil.which("docker") is None: raise SystemExit("docker is required for restore verification")
        name="qros-backup-verify"; subprocess.run(["docker","rm","-f",name],capture_output=True,check=False)
        try:
            run(["docker","run","-d","--name",name,"-e","POSTGRES_PASSWORD=qros","postgres:17"])
            for _ in range(60):
                if subprocess.run(["docker","exec",name,"pg_isready","-U","postgres"],capture_output=True).returncode==0: break
            else: raise SystemExit("temporary postgres did not become ready")
            run(["pg_restore","--clean","--if-exists","--no-owner","--dbname","postgresql://postgres:qros@127.0.0.1:5432/postgres",str(a.output)])
            report["restored"]=True
        finally: subprocess.run(["docker","rm","-f",name],capture_output=True,check=False)
    print(report); return 0
if __name__=="__main__": raise SystemExit(main())
