from pathlib import Path
import subprocess


REPO = Path(__file__).resolve().parents[1]


def test_diagnose_script_requires_remote_sync_language():
    text = (REPO / "diagnose.sh").read_text()
    assert "REMOTE MAIN:" in text
    assert "LOCAL HEAD:" in text
    assert "LOCAL CODE IS NOT SYNCHRONIZED WITH REMOTE MAIN" in text


def test_start_demo_does_not_print_ready_before_health():
    text = (REPO / "start-demo.sh").read_text()
    assert "SYSTEM READY" in text
    assert "/health" in text
    assert "GENOGUIDE_DRUG_LOCAL=true" in text
    assert "roxanna-matterless" not in text


def test_git_head_matches_origin_main_when_on_main():
    branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=REPO).decode().strip()
    if branch != "main":
        return
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO).decode().strip()
    origin = subprocess.check_output(["git", "rev-parse", "origin/main"], cwd=REPO).decode().strip()
    assert head == origin
