import sys
try:
    from report import ReportConfig, generate_header
    cfg = ReportConfig(title="Security Audit", author="AegisSec", version=2)
    assert generate_header(cfg) == "Security Audit by AegisSec (v2)"
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
