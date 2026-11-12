import sys

try:
    from events.broker import Broker
    from events.handlers import received, record_handler
    b = Broker()
    b.subscribe(record_handler)
    b.dispatch("mission_started")
    assert received == ["mission_started"]
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
