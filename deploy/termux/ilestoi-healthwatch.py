#!/data/data/com.termux/files/usr/bin/python3
import json, os, subprocess, time, urllib.request, urllib.error, socket
from datetime import datetime, timezone
from pathlib import Path
home=Path.home()
state=home/'.local/state/ilestoi-ops'
state.mkdir(mode=0o700,parents=True,exist_ok=True)
status=state/'health-last.json'
log=state/'health-watch.log'
sv=str(Path(os.environ.get('PREFIX','/data/data/com.termux/files/usr'))/'var/service/cloudflared')
errors=0
last_restart=0
previous=''
def probe(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'IleStoi-HealthWatch/1'}),timeout=8) as r:
            return str(r.status)
    except urllib.error.HTTPError as e:
        return str(e.code)
    except Exception as e:
        return type(e).__name__
def internet_probe():
    try:
        with socket.create_connection(('1.1.1.1',443),timeout=4):return 'ok'
    except Exception as e:return type(e).__name__
def note(line):
    if log.exists() and log.stat().st_size>256000:
        log.rename(state/'health-watch.previous.log')
    with log.open('a') as f:
        f.write(datetime.now(timezone.utc).isoformat()+' '+line+'\n')
while True:
    ready=probe('http://127.0.0.1:8001/api/health/ready')
    public=probe('https://ilestoi.pl/api/health/live')
    internet=internet_probe()
    if ready=='200' and internet=='ok' and public in ('502','503','504','520','521','522','523','524'):
        errors+=1
    else:
        errors=0
    now=time.time()
    action='observe'
    if errors>=3 and now-last_restart>1800:
        try:
            p=subprocess.run(['sv','restart',sv],capture_output=True,text=True,timeout=20)
            action='cloudflared_restart_ok' if p.returncode==0 else 'cloudflared_restart_failed'
        except Exception as e:
            action='restart_'+type(e).__name__
        last_restart=now
        errors=0
    v={'utc':datetime.now(timezone.utc).isoformat(),'ready':ready,'public':public,'internet':internet,'consecutive_public_failures':errors,'action':action}
    tmp=state/'health-last.json.tmp'
    with tmp.open('w') as f:json.dump(v,f)
    os.chmod(tmp,0o600)
    os.replace(tmp,status)
    label=f"ready={ready} public={public} internet={internet} action={action}"
    if label!=previous:
        note(label)
        previous=label
    time.sleep(180)
