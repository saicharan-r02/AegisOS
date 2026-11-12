from pathlib import Path

from aegis_os.security.scanners import SecurityScannerRunner


def test_bandit_and_detect_secrets_run_on_a_real_temporary_project(tmp_path: Path) -> None:
    (tmp_path/"unsafe.py").write_text("user_input = input()\neval(user_input)\n",encoding="utf-8")
    (tmp_path/".env").write_text("GITHUB_TOKEN=ghp_"+"x"*36+"\n",encoding="utf-8")

    report=SecurityScannerRunner(tmp_path).run(".")

    statuses={run.scanner:run.status for run in report.runs}
    assert statuses["bandit"]=="completed"
    assert statuses["detect-secrets"]=="completed"
    assert any(finding.scanner=="bandit" and finding.rule_id=="B307" for finding in report.findings)
    assert all("ghp_" not in finding.description for finding in report.findings)


def test_detect_secrets_parser_never_returns_secret_value(tmp_path: Path) -> None:
    runner=SecurityScannerRunner(tmp_path)
    findings=runner._parse_detect_secrets({
        "results":{
            "src/settings.py":[
                {"type":"GitHub Token","line_number":7,"hashed_secret":"secret-value"}
            ]
        }
    })

    assert len(findings)==1
    assert findings[0].file=="src/settings.py"
    assert findings[0].line==7
    assert "secret-value" not in findings[0].description
