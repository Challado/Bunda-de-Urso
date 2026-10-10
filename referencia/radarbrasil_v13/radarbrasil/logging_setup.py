import json
import logging
import sys
from datetime import datetime, timezone

class JSONFormatter(logging.Formatter):
    def format(self, record):
        value={'timestamp':datetime.fromtimestamp(record.created,timezone.utc).isoformat(),
               'level':record.levelname,'logger':record.name,'message':record.getMessage()}
        if hasattr(record,'context'): value.update(record.context)
        if record.exc_info: value['exception']=self.formatException(record.exc_info)
        return json.dumps(value,ensure_ascii=False,default=str)

def setup(level='INFO'):
    root=logging.getLogger()
    if root.handlers: return
    root.setLevel(level)
    handler=logging.StreamHandler(sys.stderr)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)
