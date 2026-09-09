"""One bounded collector job, isolated so the service can stop a slow source."""
import json
import os
from pathlib import Path
import sys

from sabc.sources import collect_local
from sabc.store import Store


def main():
    job,source,query,output=sys.argv[1:]
    store=Store(os.environ['SABC_COLLECTOR_DB'])
    try:
        evidence=collect_local(store,job,source,query)
        result={'status':'success','evidence':evidence}
    except ValueError as error:
        result={'status':'failed','error':str(error)}
    runs=[r for r in store.list('source_runs') if r.get('project_id')==job]
    Path(output).write_text(json.dumps({**result,'job_id':job,'runs':runs},ensure_ascii=False))


if __name__=='__main__': main()
