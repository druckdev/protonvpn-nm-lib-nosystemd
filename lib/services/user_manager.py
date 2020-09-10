import proton

from lib import exceptions
from lib.constants import (APP_VERSION, DEFAULT_KEYRING_SERVICE,
                           DEFAULT_KEYRING_USERNAME)
from lib.logger import logger

from .user_session_manager import UserSessionManager


class UserManager(UserSessionManager):
    def __init__(
        self,
        keyring_service=DEFAULT_KEYRING_SERVICE,
        keyring_username=DEFAULT_KEYRING_USERNAME
    ):
        self.keyring_service = keyring_service
        self.keyring_username = keyring_username
        logger.info(
            "Initialized UserManager: service-> {}; user-> {}".format(
                self.keyring_service, self.keyring_username
            )
        )
        super().__init__()

    def login(self, username, password):
        """Login ProtonVPN user.

        Args:
            username (string): ProtonVPN username
            password (string): ProtonVPN password
        """
        self.validate_username_password(username, password)
        session = proton.Session(
            api_url="https://api.protonvpn.ch",
            appversion="LinuxVPN_" + APP_VERSION
        )

        try:
            session.authenticate(username, password)
        except proton.api.ProtonError as e:
            logger.exception("[!] API ProtonError: {}".format(e))
            if e.code == 8002:
                raise exceptions.IncorrectCredentialsError(e)
            else:
                raise exceptions.APIAuthenticationError(e)
        else:
            self.store_user_session(
                session.dump(),
                self.keyring_service,
                self.keyring_username
            )

    def logout(self):
        """Logout ProtonVPN user."""
        self.delete_user_session(self.keyring_service, self.keyring_username)

    def fetch_vpn_credentials(self, session=False):
        """Fetch OpenVPN credentials from API."""
        if not session:
            session = self.load_session()
        api_resp = session.api_request('/vpn')
        return (api_resp["VPN"]["Name"], api_resp["VPN"]["Password"])

    def load_session(self):
        """Load ProtonVPN user session."""
        return self.load_stored_user_session(
            self.keyring_service, self.keyring_username
        )

    def validate_username_password(self, username, password):
        """Validate ProtonVPN username and password.

        Args:
            username (string): ProtonVPN username
            password (string): ProtonVPN password
        """
        if not isinstance(username, str):
            err_msg = "Incorrect object type, "
            + "str is expected but got {} instead.".format(type(username))
            logger.error(
                "[!] TypeError: {}. Raising exception.".format(err_msg)
            )
            raise TypeError(err_msg)
        elif not isinstance(password, str):
            err_msg = "Incorrect object type, "
            + "str is expected but got {} instead.".format(type(password))
            logger.error(
                "[!] TypeError: {}. Raising exception.".format(err_msg)
            )
            raise TypeError(err_msg)
        elif not username.strip() or not password.strip():
            err_msg = "Both username and password must be provided."
            logger.error(
                "[!] ValueError: {}. Raising exception.".format(err_msg)
            )
            raise ValueError(err_msg)
