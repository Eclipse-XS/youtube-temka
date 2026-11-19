"""Channel-local daily quotas and UTC spacing across DST transitions."""
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import json


def local_time(value,timezone_name='Europe/Kyiv'):
    """Reject nonexistent/ambiguous wall times rather than silently picking DST."""
    wall=datetime.fromisoformat(value)
    if wall.tzinfo is not None:return wall.astimezone(timezone.utc).isoformat()
    zone=ZoneInfo(timezone_name);matches=set()
    for fold in (0,1):
        candidate=wall.replace(tzinfo=zone,fold=fold).astimezone(timezone.utc)
        if candidate.astimezone(zone).replace(tzinfo=None)==wall:matches.add(candidate)
    if len(matches)!=1:raise ValueError('This local time is ambiguous or nonexistent due to daylight saving. Select another time or provide an explicit UTC offset')
    return matches.pop().isoformat()


def planned_times(db,channel,exclude=None):
    result=[]
    for row in db.execute("SELECT id,metadata,seen,state FROM publications WHERE channel=? AND state NOT IN ('DRAFT','CANCELLED')",(channel,)):
        if row['id']==exclude:continue
        when=json.loads(row['metadata'])['status'].get('publishAt')
        if when:result.append(datetime.fromisoformat(when.replace('Z','+00:00')))
        elif row['seen'] and row['state'] in ('PUBLISHED','PUBLISHING'):
            result.append(datetime.fromtimestamp(row['seen'],timezone.utc))
    return result


def available(candidate,planned,daily_limit,minutes,timezone_name):
    local=ZoneInfo(timezone_name)
    if sum(t.astimezone(local).date()==candidate.astimezone(local).date() for t in planned)>=daily_limit:return False
    return all(abs((candidate-t).total_seconds())>=minutes*60 for t in planned)


def next_slot(earliest,planned,daily_limit,minutes,timezone_name='UTC'):
    candidate=earliest.astimezone(timezone.utc)
    for _ in range(20000):
        if available(candidate,planned,daily_limit,minutes,timezone_name):return candidate
        candidate+=timedelta(minutes=minutes)
    raise ValueError('No calendar slot is available within the bounded planning horizon')


def schedule(db,channel,earliest,daily_limit,minutes,timezone_name='UTC',exclude=None,manual=False):
    planned=planned_times(db,channel,exclude)
    if manual:
        if not available(earliest,planned,daily_limit,minutes,timezone_name):raise ValueError('Requested time conflicts with channel daily limit or minimum spacing')
        return earliest
    return next_slot(earliest,planned,daily_limit,minutes,timezone_name)
