"""Measure isolated SQLite visit reads with synthetic data, never production state.

This measures storage/query cost only. It does not certify concurrent throughput,
PostgreSQL capacity, hosting limits, network latency or a production service SLA.
"""
import argparse
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
from unittest.mock import patch
from zoneinfo import ZoneInfo


def positive(value):
    result=int(value)
    if result<1:raise argparse.ArgumentTypeError('Use a positive integer.')
    return result


def run():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--visits-per-day',type=positive,default=150000)
    parser.add_argument('--days',type=int,choices=range(1,8),default=7)
    parser.add_argument('--repeats',type=positive,default=5)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root))
    with tempfile.TemporaryDirectory(prefix='electronicama-visit-benchmark-') as directory:
        # Select an empty disposable database before importing the application.
        # Neither source database files nor credentials are read by this tool.
        os.environ.pop('DATABASE_URL',None)
        os.environ.pop('VERCEL',None)
        os.environ['MAGGY_DATA_DIR']=directory
        from app import app
        import membership as m
        import visitor_registry as visits
        app.config.update(MEMBERSHIP_DATABASE_URL=None,MEMBERSHIP_DATABASE=str(Path(directory)/'benchmark.sqlite3'))
        instant=datetime(2026,11,4,12,tzinfo=timezone.utc)
        zone=ZoneInfo(visits.PUBLIC_TIME_ZONE)
        since=m.stamp((instant.astimezone(zone)-timedelta(days=14)).replace(hour=0,minute=0,second=0,microsecond=0))
        total=args.visits_per_day*args.days
        began=time.perf_counter()
        with app.app_context():
            m.init_database()
            with m.database() as connection:
                latest=m.stamp(instant-timedelta(hours=1))
                connection.executemany('INSERT INTO visitor_devices(id,first_seen,last_seen) VALUES(?,?,?)',
                    ((f'{number:032x}',latest,latest) for number in range(args.visits_per_day)))
                insert='INSERT INTO visitor_sessions(id,device_id,member_id,account_kind,started_at,last_seen,pageviews,last_page,network_id,network_day,device,os,browser) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)'
                for day in range(args.days):
                    at=instant-timedelta(days=args.days-1-day,hours=1)
                    stamp=m.stamp(at)
                    connection.executemany(insert,
                        ((f'{day*args.visits_per_day+number:032x}',f'{number:032x}',None,'guest',stamp,stamp,1,'/',None,at.date().isoformat(),'Móvil','iOS','Safari') for number in range(args.visits_per_day)))
                    connection.execute('INSERT INTO visitor_public_days(day,sessions) VALUES(?,?)',(at.astimezone(zone).date().isoformat(),args.visits_per_day))
                connection.execute('INSERT INTO visitor_public_totals(id,since,sessions) VALUES(?,?,?)',(visits.PUBLIC_TOTAL_ID,since,total))
                connection.execute('INSERT INTO visitor_public_history(id,since,initialized_at,unassigned) VALUES(?,?,?,0)',(visits.PUBLIC_TOTAL_ID,since,m.stamp(instant-timedelta(days=args.days+1))))
                connection.execute('ANALYZE')
        seed_seconds=time.perf_counter()-began
        client=app.test_client()
        readings={}
        with patch.object(visits,'now_utc',return_value=instant):
            for name,path in [('compact','/api/visits/public?compact=1'),('full','/api/visits/public')]:
                response=client.get(path)
                assert response.status_code==200,response.get_data(as_text=True)
                assert response.json['cumulative']['sessions']==total
                assert sum(row['sessions'] or 0 for row in response.json['history']['days'])==total
                if name=='full':assert response.json['summary']['sessions']==args.visits_per_day
                elapsed=[]
                for _ in range(args.repeats):
                    started=time.perf_counter();response=client.get(path)
                    assert response.status_code==200
                    elapsed.append((time.perf_counter()-started)*1000)
                readings[name]={'median_ms':round(statistics.median(elapsed),3),'min_ms':round(min(elapsed),3),'max_ms':round(max(elapsed),3),'samples':args.repeats,'response_bytes':len(response.data)}
        queries={
            'recent_feed':('SELECT started_at,device,last_page FROM visitor_sessions WHERE started_at>=? ORDER BY started_at DESC,id DESC LIMIT 20',(m.stamp(instant-timedelta(hours=24)),)),
            'recent_summary':('SELECT COUNT(*) AS sessions,COUNT(DISTINCT device_id) AS browsers FROM visitor_sessions WHERE started_at>=?',(m.stamp(instant-timedelta(hours=24)),)),
            'device_cleanup':('DELETE FROM visitor_devices WHERE last_seen<?',(m.stamp(instant-timedelta(days=7)),)),
            'daily_history':('SELECT day,sessions FROM visitor_public_days WHERE day>=? AND day<=? ORDER BY day',('2026-10-21','2026-11-04')),
        }
        with app.app_context(),m.database() as connection:
            plans={name:[row['detail'] for row in connection.execute('EXPLAIN QUERY PLAN '+query,parameters)] for name,(query,parameters) in queries.items()}
        report={'scope':'synthetic SQLite read benchmark; not a production capacity guarantee','visits_per_day':args.visits_per_day,'retained_days':args.days,'session_rows':total,'device_rows':args.visits_per_day,'seed_seconds':round(seed_seconds,3),'requests':readings,'query_plans':plans}
    rendered=json.dumps(report,indent=2,ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(rendered+'\n')
    print(rendered)


if __name__=='__main__':run()
