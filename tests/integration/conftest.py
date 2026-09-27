"""Integration test fixtures for Agent Coordination System."""

import pytest
from gltest import get_contract_factory, get_accounts, get_default_account
from gltest.clients import get_gl_client


@pytest.fixture(scope="session")
def deployed_contract():
    """Deploy contract once for all integration tests."""
    factory = get_contract_factory("AgentCoordination")
    contract = factory.deploy()
    return contract


@pytest.fixture(scope="session")
def integration_deploy():
    """Factory fixture that deploys a fresh contract for tests that need it."""
    def _deploy(contract_path):
        factory = get_contract_factory("AgentCoordination")
        return factory.deploy()
    return _deploy


@pytest.fixture(scope="session")
def integration_alice():
    """First test account - agent."""
    return get_accounts()[0]


@pytest.fixture(scope="session")
def integration_bob():
    """Second test account - poster."""
    return get_accounts()[1]


@pytest.fixture(scope="session")
def poster():
    """Poster account."""
    return get_accounts()[0]


@pytest.fixture(scope="session")
def integration_vm():
    """VM with balance checking via gl_client."""
    client = get_gl_client()

    class IntegrationVM:
        def __init__(self, c):
            self.client = c

        def get_balance(self, account):
            addr = account.address if hasattr(account, "address") else account
            return self.client.get_balance(addr)

    return IntegrationVM(client)
