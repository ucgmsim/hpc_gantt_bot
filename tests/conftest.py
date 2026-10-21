import pytest
from helpers import EXAMPLE_TABS, MON

from hpc_gantt import parse_schedule


@pytest.fixture
def example_schedule():
    return parse_schedule(EXAMPLE_TABS, MON)
