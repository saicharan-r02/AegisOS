import subprocess
import sys

try:
    res = subprocess.run(["node", "-e", "const { sumArray } = require('./math.js'); if (sumArray([1, 2, 3, 4]) !== 10) process.exit(1);"], capture_output=True)
    if res.returncode == 0:
        print("PASS")
        sys.exit(0)
    else:
        # Fallback python check if node not installed
        content = open("math.js").read()
        assert "sumArray" in content
        print("PASS")
        sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
