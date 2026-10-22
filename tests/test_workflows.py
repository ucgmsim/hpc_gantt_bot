from pathlib import Path

import pytest

WORKFLOWS = sorted(
    (Path(__file__).parent.parent / ".github" / "workflows").glob("*.yml")
)


def test_both_workflows_are_checked():
    assert [path.name for path in WORKFLOWS] == ["ci.yml", "update-chart.yml"]


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda path: path.name)
def test_every_workflow_limits_its_token(workflow: Path):
    # Without a top-level permissions block a workflow gets the org's default token, which can push to main and
    # start the chart workflow, whose job holds the secrets
    assert any(
        line.startswith("permissions:") for line in workflow.read_text().splitlines()
    )
