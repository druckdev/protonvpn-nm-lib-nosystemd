import pytest
from protonvpn_nm_lib.core.environment import ExecutionEnvironment
env = ExecutionEnvironment()
accounting = ExecutionEnvironment().accounting
from protonvpn_nm_lib import exceptions


class MockSessionBase:
    def __init__(self):
        self.__delinquent = False
        self.__vpn_tier = 3
        self.__vpn_password = "vpn_password"

    def refresh_vpn_data(self):
        pass

    @property
    def delinquent(self):
        return self.__delinquent

    @delinquent.setter
    def delinquent(self, newavalue):
        self.__delinquent = newavalue

    @property
    def max_connections(self):
        return 2

    @property
    def vpn_tier(self):
        return self.__vpn_tier

    @vpn_tier.setter
    def vpn_tier(self, newvalue):
        self.__vpn_tier = newvalue

    @property
    def vpn_password(self):
        return self.__vpn_password

    @vpn_password.setter
    def vpn_password(self, newvalue):
        self.__vpn_password = newvalue

    def get_sessions(self):
        return []


class MockDelinquentSession(MockSessionBase):
    def __init__(self):
        super().__init__()

    def refresh_vpn_data(self):
        self.delinquent = True


class MockAccountDowngradeSession(MockSessionBase):
    def __init__(self):
        super().__init__()

    def refresh_vpn_data(self):
        self.vpn_tier = 0


class MockChangedVPNPasswordSession(MockSessionBase):
    def __init__(self):
        super().__init__()

    def refresh_vpn_data(self):
        self.vpn_password = "changed_password"


class MockMaxAmmountOfSessionsReachedSession(MockSessionBase):
    def __init__(self):
        super().__init__()

    def get_sessions(self):
        return ["MockSession1", "MockSession2"]


class TestDefaultAccounting:
    def test_delinquent_user(self):
        env.api_session = MockDelinquentSession()
        with pytest.raises(exceptions.AccountIsDelinquentError):
            env.accounting.ensure_accounting_has_expected_values()

    def test_account_downgrade(self):
        env.api_session = MockAccountDowngradeSession()
        with pytest.raises(exceptions.AccountWasDowngradedError):
            env.accounting.ensure_accounting_has_expected_values()

    def test_changed_vpn_password(self):
        env.api_session = MockChangedVPNPasswordSession()
        with pytest.raises(exceptions.VPNPasswordHasBeenChangedError):
            env.accounting.ensure_accounting_has_expected_values()

    def test_exceeded_amount_of_concurrent_sessions(self):
        env.api_session = MockMaxAmmountOfSessionsReachedSession()
        with pytest.raises(exceptions.ExceededAmountOfConcurrentSessionsError):
            env.accounting.ensure_accounting_has_expected_values()
