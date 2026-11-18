from datetime import datetime,timedelta,timezone
from factory.calendar import next_slot,available


def test_daily_limit_uses_channel_local_date():
    planned=[datetime(2026,11,18,22,tzinfo=timezone.utc)]
    earliest=datetime(2026,11,19,1,tzinfo=timezone.utc)
    slot=next_slot(earliest,planned,1,60,'America/New_York')
    assert slot==datetime(2026,11,19,5,tzinfo=timezone.utc)


def test_minimum_spacing_across_dst_fall_back():
    first=datetime(2026,11,1,5,30,tzinfo=timezone.utc)
    assert not available(first+timedelta(minutes=60),[first],5,120,'America/New_York')
    assert next_slot(first+timedelta(minutes=60),[first],5,120,'America/New_York')==first+timedelta(minutes=180)


def test_calendar_checks_future_slot_on_both_sides():
    future=datetime(2026,11,20,12,tzinfo=timezone.utc)
    assert not available(future-timedelta(minutes=30),[future],3,120,'Europe/Kyiv')
