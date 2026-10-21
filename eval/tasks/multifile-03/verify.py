import sys
try:
    from database.repo import Repo
    r = Repo()
    assert r.find_all() == ['row1', 'row2']
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
