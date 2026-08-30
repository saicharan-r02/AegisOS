import pytest
from pydantic import BaseModel, Field
from Aegis_OS.tools.base import BaseAegisTool,ToolResult
from Aegis_OS.kernel.llm import get_llm


class DummyArgs(BaseModel):
    number: int =Field(description="A number to double")

class DoubleNumberTool(BaseAegisTool):
    name="double_number"
    description="Doubles the input number"
    args_schema=DummyArgs

    def _run(self,number: int)->ToolResult:
        return ToolResult(success=True,output=number*2)

def test_base_tool_execution():
    tool=DoubleNumberTool()
    # Test valid execution
    res=tool.execute(number=5)
    assert res.success is True
    assert res.output==10

    # Test invalid argument handling (no crash)
    res_invalid=tool.execute(number="invalid_string")
    assert res_invalid.success is False
    assert "error" in res_invalid.error.lower()

def test_llm_factory_init():
    # Verify get_llm() returns a valid chat model instance
    llm=get_llm()
    assert llm is not None