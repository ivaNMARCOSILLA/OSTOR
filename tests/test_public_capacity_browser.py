"""Bounded concurrent requests to the isolated loopback app, never a public host."""
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit
import json,time
from pathlib import Path
import requests
from browser_support import BASE_URL

def run():
 assert urlsplit(BASE_URL).hostname in {'127.0.0.1','localhost','::1'},'Load checks require an isolated loopback server'
 paths=[('/',200),('/account',200),('/live',200),('/api/account/me',200),('/api/status',200),('/api/admin/members',403),('/api/admin/statistics',403),('/assets/operations.js',200)]
 def fetch(index):
  path,expected=paths[index%len(paths)];started=time.monotonic()
  response=requests.get(BASE_URL+path,timeout=20)
  assert response.status_code==expected,(path,response.status_code)
  return (time.monotonic()-started)*1000
 started=time.monotonic()
 with ThreadPoolExecutor(max_workers=12) as pool:latencies=sorted(pool.map(fetch,range(240)))
 report={'requests':len(latencies),'concurrency':12,'failures':0,'elapsed_seconds':round(time.monotonic()-started,3),'p95_local_ms':round(latencies[int(len(latencies)*.95)-1],2),'scope':'isolated loopback, no payments or external provider calls; not a production capacity estimate'}
 Path('/tmp/electronicama-final-local-load.json').write_text(json.dumps(report,indent=2))
 print('OK: 240 isolated concurrent requests, 12 workers, public routes and assets available, admin routes denied to guests; p95 '+str(report['p95_local_ms'])+' ms locally')
if __name__=='__main__':run()
