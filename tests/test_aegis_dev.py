import os
import pytest
from pathlib import Path
from Aegis_OS.agents.dev.agent import AegisDevAgent
from Aegis_OS.tools.filesystem_tools import WriteFileTool,ReadFileTool

def test_aegis_dev_autonomous_investigation(tmp_path):
    orig_cwd=os.getcwd()
    try:
        os.chdir(tmp_path)

        # 1. Create a buggy python file
        buggy_code=(
            "def calculate_discount(price: float, discount_percent: float) -> float:\n"
            "    # BUG: Multiplying instead of applying discount\n"
            "    return price * discount_percent\n"
        )
        WriteFileTool().execute(file_path="pricing.py",content=buggy_code)

        # 2. Run AegisDev with an investigation task
        agent=AegisDevAgent()
        state=agent.run(goal="Inspect 'pricing.py', identify the bug in calculate_discount, and explain what is wrong.",max_steps=5)

        # 3. Assertions with clear failure messages
        assert state.error is None, f"Agent failed with error: {state.error}"
        assert len(state.steps)>0, "Agent took no steps."
        assert state.is_completed is True, "Agent did not finish the task."
        assert state.final_response is not None, "Agent returned empty response."
        assert "discount" in state.final_response.lower()

    finally:
        os.chdir(orig_cwd)