"""Import a browser capture into the shared regional library, without credentials."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sabc.local_sources import save_capture
from sabc.store import Store


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('capture',type=Path)
    parser.add_argument('--database',type=Path,default=Path('data/sabc.db'))
    args=parser.parse_args()
    record=save_capture(Store(args.database),json.loads(args.capture.read_text(encoding='utf-8-sig')))
    print(record['id'])
