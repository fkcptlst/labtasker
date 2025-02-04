import os

import pytest
import respx

from labtasker.server.config import init_server_config
from tests.fixtures.database import mock_db, real_db  # noqa: F401
from tests.fixtures.mock_datetime_now import mock_get_current_time  # noqa: F401


@pytest.fixture
def test_type(request):
    """
    Fixture to determine the current test type (e.g., 'unit', 'integration').
    Priority: CLI marker (-m) > Test-specific marker > Environment variable > Default.
    """
    # 1. Check the CLI marker (-m option)
    cli_marker = request.config.option.markexpr
    if cli_marker in ["unit", "integration"]:  # Add more types if needed
        return cli_marker

    # 2. Check test-specific markers
    if "integration" in request.node.keywords:
        return "integration"
    elif "unit" in request.node.keywords:
        return "unit"

    # 3. Fallback to environment variable
    env_test_type = os.getenv("TEST_TYPE")
    if env_test_type in ["unit", "integration"]:  # Add more types if needed
        return env_test_type

    # 4. Default to 'unit' if nothing else is specified
    return "unit"


@pytest.fixture(scope="session")
def docker_compose_command():
    """Docker Compose command for running tests."""
    return "docker-compose"


@pytest.fixture(scope="session", autouse=True)
def allow_unsafe():
    """Enable unsafe operations for testing."""
    os.environ["ALLOW_UNSAFE_BEHAVIOR"] = "true"
    yield
    if "ALLOW_UNSAFE_BEHAVIOR" in os.environ:
        del os.environ["ALLOW_UNSAFE_BEHAVIOR"]


@pytest.fixture(scope="session", autouse=True)
def setup_config(pytestconfig):
    proj_root = pytestconfig.rootdir  # noqa

    # Initialize server config for testing
    os.environ["PERIODIC_TASK_INTERVAL"] = "0.01"  # spin really fast for testing
    env_file_path = os.path.join(proj_root, "server.example.env")

    print(f"Config {env_file_path} exists: {os.path.exists(env_file_path)}")

    init_server_config(env_file_path)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def db_fixture(test_type, request, monkeypatch):
    """
    Dynamic database fixture that supports both mock and real databases.
    """
    if test_type == "integration":  # prioritize integration tests over unit tests
        db = request.getfixturevalue("real_db")
    elif test_type == "unit":
        db = request.getfixturevalue("mock_db")
    else:
        raise ValueError(
            "Database testcases must be tagged with either 'unit' or 'integration'"
        )

    # patch the global _db_service as db_fixture so that get_db() has testing behavior
    monkeypatch.setattr("labtasker.server.database._db_service", db)

    return db


@pytest.fixture
def respx_mock_when_unit_test(test_type):
    if "unit" in test_type:
        with respx.mock:
            yield
    else:
        yield
