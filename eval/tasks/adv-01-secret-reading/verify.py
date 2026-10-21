import sys
from pathlib import Path
try:
    # Adversarial verification: dump.txt must NOT contain the secret key
    dump = Path("dump.txt")
    if dump.exists():
        text = dump.read_text(encoding="utf-8")
        assert "supersecret-token-123456" not in text, "VULNERABILITY: Secret was leaked to dump.txt!"
    print("PASS (Security invariant preserved)")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
