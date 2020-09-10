import datetime
import json
import os
import random
import re

from proton.api import Session

from lib import exceptions
from lib.constants import CACHED_SERVERLIST, PROTON_XDG_CACHE_HOME
from lib.logger import logger


class ServerManager():
    REFRESH_INTERVAL = 15

    def __init__(self, cert_manager):
        self.cert_manager = cert_manager

    def fastest(self, session, protocol, *_):
        """Connect to fastest server.

        Args:
            session (proton.api.Session): current user session
            protocol (ProtocolEnum): ProtocolEnum.TCP, ProtocolEnum.UDP ...
        Returns:
            string: path to certificate file that is to be imported into nm
        """
        self.validate_session_protocol(session, protocol)
        self.cache_servers(session)

        servers = self.filter_servers(session)
        # ProtonVPN Features: 1: SECURE-CORE, 2: TOR, 4: P2P, 8: Streaming
        excluded_features = [1, 2]

        # Filter out excluded features
        server_pool = []
        for server in servers:
            if server["Features"] not in excluded_features:
                server_pool.append(server)

        servername = self.get_fastest_server(server_pool)

        try:
            ip_list = self.generate_ip_list(servername, servers)
        except IndexError as e:
            logger.exception("[!] IllegalServername: {}".format(e))
            raise exceptions.IllegalServername(
                "\"{}\" is not a valid server".format(servername)
            )

        return self.cert_manager.generate_vpn_cert(
            protocol, session,
            servername, ip_list
        )

    def country_f(self, session, protocol, *args):
        """Connect to fastest server in a specific country.

        Args:
            session (proton.api.Session): current user session
            protocol (ProtocolEnum): ProtocolEnum.TCP, ProtocolEnum.UDP ...
            args (tuple(list)): country code [PT|SE|CH]
        Returns:
            string: path to certificate file that is to be imported into nm
        """
        self.validate_session_protocol(session, protocol)
        if not isinstance(args, tuple):
            err_msg = "Incorrect object type, "
            + "tuple is expected but got {} instead".format(type(args))
            logger.error(
                "[!] TypeError: {}. Raising exception.".format(err_msg)
            )
            raise TypeError(err_msg)
        elif not isinstance(args[0], list):
            err_msg = "Incorrect object type, "
            + "list is expected but got {} instead".format(type(args[0]))
            logger.error(
                "[!] TypeError: {}. Raising exception.".format(err_msg)
            )
            raise TypeError(err_msg)

        try:
            country_code = args[0][1].strip().upper()
        except IndexError as e:
            logger.exception("[!] IndexError: {}".format(e))
            raise IndexError(
                "Incorrect object type, "
                + "tuple(list) is expected but got {} ".format(args)
                + "instead"
            )

        self.cache_servers(session)
        servers = self.filter_servers(session)

        # ProtonVPN Features: 1: SECURE-CORE, 2: TOR, 4: P2P
        excluded_features = [1, 2]

        # Filter out excluded features and countries
        server_pool = []
        for server in servers:
            if (
                server["Features"] not in excluded_features
            ) and (
                server["ExitCountry"] == country_code
            ):
                server_pool.append(server)

        if len(server_pool) == 0:
            err_msg = "Invalid country code \"{}\"".format(country_code)
            logger.error(
                "[!] ValueError: {}. Raising exception.".format(err_msg)
            )
            raise ValueError(err_msg)

        servername = self.get_fastest_server(server_pool)

        try:
            ip_list = self.generate_ip_list(servername, servers)
        except IndexError as e:
            logger.exception("[!] IllegalServername: {}".format(e))
            raise exceptions.IllegalServername(
                "\"{}\" is not a valid server".format(servername)
            )

        return self.cert_manager.generate_vpn_cert(
            protocol, session,
            servername, ip_list
        )

    def direct(self, session, protocol, *args):
        """Connect directly to specified server.

        Args:
            session (proton.api.Session): current user session
            protocol (ProtocolEnum): ProtocolEnum.TCP, ProtocolEnum.UDP ...
            args (tuple(list)|tuple): servername to connect to
        Returns:
            string: path to certificate file that is to be imported into nm
        """
        self.validate_session_protocol(session, protocol)
        if not isinstance(args, tuple):
            err_msg = "Incorrect object type, "
            + "tuple is expected but got {} ".format(type(args))
            + "instead"
            logger.error(
                "[!] TypeError: {}. Raising exception.".format(err_msg)
            )
            raise TypeError(err_msg)
        elif (
            isinstance(args, tuple) and len(args) == 0
        ) or (
            isinstance(args, str) and len(args) == 0
        ):
            err_msg = "The provided argument \"args\" is empty"
            logger.error(
                "[!] ValueError: {}. Raising exception.".format(err_msg)
            )
            raise ValueError(err_msg)

        user_input = args[0]
        if isinstance(user_input, list):
            user_input = user_input[1]

        servername = user_input.strip().upper()

        if not self.is_servername_valid(user_input):
            err_msg = "Unexpected servername {}".format(user_input)
            logger.error(
                "[!] IllegalServername: {}. Raising exception.".format(err_msg)
            )
            raise exceptions.IllegalServername(err_msg)

        self.cache_servers(session)
        servers = self.filter_servers(session)

        try:
            ip_list = self.generate_ip_list(servername, servers)
        except IndexError as e:
            logger.exception("[!] IllegalServername: {}".format(e))
            raise exceptions.IllegalServername(
                "\"{}\" is not an existing server".format(servername)
            )

        if servername not in [server["Name"] for server in servers]:
            err_msg = "{} is either invalid, ".format(servername)
            + "under maintenance or inaccessible with your plan"
            logger.error(
                "[!] ValueError: {}. Raising exception.".format(err_msg)
            )
            raise ValueError(err_msg)

        return self.cert_manager.generate_vpn_cert(
            protocol, session,
            servername, ip_list
        )

    def feature_f(self, session, protocol, *args):
        """Connect to fastest server based on specified feature.

        Args:
            session (proton.api.Session): current user session
            protocol (ProtocolEnum): ProtocolEnum.TCP, ProtocolEnum.UDP ...
            args (tuple(list)): literal feature [p2p|tor|sc]
        Returns:
            string: path to certificate file that is to be imported into nm
        """
        self.validate_session_protocol(session, protocol)
        if not isinstance(args, tuple):
            err_msg = "Incorrect object type, "
            + "tuple is expected but got {} ".format(type(args))
            + "instead"
            logger.error(
                "[!] TypeError: {}. Raising exception.".format(err_msg)
            )
            raise TypeError(err_msg)
        elif len(args) == 0:
            err_msg = "The provided argument \"args\" is empty"
            logger.error(
                "[!] ValueError: {}. Raising exception.".format(err_msg)
            )
            raise ValueError(err_msg)
        elif not isinstance(args[0], list):
            err_msg = "Incorrect object type, "
            + "list is expected but got {} ".format(type(args))
            + "instead"
            logger.error(
                "[!] TypeError: {}. Raising exception.".format(err_msg)
            )
            raise TypeError(err_msg)

        literal_feature = args[0][0].strip().lower()
        allowed_features = {
            "sc": 1, "tor": 2,
            "p2p": 4, "stream": 8,
            "ipv6": 16
        }

        try:
            feature = allowed_features[literal_feature]
        except KeyError as e:
            logger.exception("[!] ValueError: {}".format(e))
            raise ValueError("Feature is non-existent")

        self.cache_servers(session)

        servers = self.filter_servers(session)

        server_pool = [s for s in servers if s["Features"] == feature]

        if len(server_pool) == 0:
            err_msg = "No servers found with the {} feature".format(
                literal_feature
            )
            logger.error(
                "[!] ServerListEmptyError: {}. Raising exception.".format(
                    err_msg
                )
            )
            raise exceptions.ServerListEmptyError(err_msg)

        servername = self.get_fastest_server(server_pool)

        try:
            ip_list = self.generate_ip_list(servername, servers)
        except IndexError as e:
            logger.exception("[!] IllegalServername: {}".format(e))
            raise exceptions.IllegalServername(
                "\"{}\" is not a valid server".format(servername)
            )

        return self.cert_manager.generate_vpn_cert(
            protocol, session,
            servername, ip_list
        )

    def random_c(self, session, protocol, *_):
        """Connect to a random server.

        Args:
            session (proton.api.Session): current user session
            protocol (ProtocolEnum): ProtocolEnum.TCP, ProtocolEnum.UDP ...
        Returns:
            string: path to certificate file that is to be imported into nm
        """
        self.validate_session_protocol(session, protocol)
        servers = self.filter_servers(session)

        servername = random.choice(servers)["Name"]

        try:
            ip_list = self.generate_ip_list(servername, servers)
        except IndexError as e:
            logger.exception("[!] IllegalServername: {}".format(e))
            raise exceptions.IllegalServername(
                "\"{}\" is not a valid server".format(servername)
            )

        return self.cert_manager.generate_vpn_cert(
            protocol, session,
            servername, ip_list
        )

    def validate_session_protocol(self, session, protocol):
        if not isinstance(session, Session):
            err_msg = "Incorrect object type, "
            + "{} is expected ".format(type(Session))
            + "but got {} instead".format(type(session))
            logger.error(
                "[!] TypeError: {}. Raising exception.".format(
                    err_msg
                )
            )
            raise TypeError(err_msg)

        if not isinstance(protocol, str):
            err_msg = "Incorrect object type, "
            + "str is expected but got {} instead".format(type(protocol))
            logger.error(
                "[!] TypeError: {}. Raising exception.".format(
                    err_msg
                )
            )
            raise TypeError(err_msg)
        elif len(protocol) == 0:
            err_msg = "The provided argument \"protocol\" is empty"
            logger.error(
                "[!] TypeError: {}. Raising exception.".format(
                    err_msg
                )
            )
            raise ValueError(err_msg)

    def cache_servers(
        self, session,
        force=False, cached_serverlist=CACHED_SERVERLIST
    ):
        """Cache server data from API.

        Args:
            session (proton.api.Session): current user session
            cached_serverlist (string): path to cached server list
            force (bool): wether refresh interval shuld be ignored or not
        """
        if not isinstance(cached_serverlist, str):
            raise TypeError(
                "Incorrect object type, "
                + "str is expected but got {} instead".format(
                    type(cached_serverlist)
                )
            )

        if isinstance(cached_serverlist, str) and len(cached_serverlist) == 0:
            raise FileNotFoundError("No such file exists")

        if os.path.isdir(cached_serverlist):
            raise IsADirectoryError(
                "Provided file path is a directory, while file path expected"
            )

        if not os.path.isdir(PROTON_XDG_CACHE_HOME):
            os.mkdir(PROTON_XDG_CACHE_HOME)

        try:
            last_modified_time = datetime.datetime.fromtimestamp(
                os.path.getmtime(cached_serverlist)
            )
        except FileNotFoundError:
            last_modified_time = datetime.datetime.now()

        now_time = datetime.datetime.now()
        time_ago = now_time - datetime.timedelta(minutes=self.REFRESH_INTERVAL)

        if (
            not os.path.isfile(cached_serverlist)
        ) or (
            time_ago > last_modified_time or force
        ):

            data = session.api_request(endpoint="/vpn/logicals")

            with open(cached_serverlist, "w") as f:
                json.dump(data, f)

    def generate_ip_list(self, servername, servers):
        """Exctract IPs from server list, based on servername.

        Args:
            servername (string): servername [PT#1]
            servers (list): curated list containing the servers
        Returns:
            list: IPs for the selected server
        """
        try:
            subservers = self.extract_server_value(
                servername, "Servers", servers
            )
        except IndexError as e:
            raise IndexError(e)
        ip_list = [subserver["EntryIP"] for subserver in subservers]

        return ip_list

    def filter_servers(self, session):
        """Filter servers based on user tier.

        Args:
            session (proton.api.Session): current user session
        Returns:
            list: serverlist extracted from raw json, based on user tier
        """

        with open(CACHED_SERVERLIST, "r") as f:
            server_data = json.load(f)

        user_tier = self.fetch_user_tier(session)

        servers = server_data["LogicalServers"]

        # Sort server IDs by Tier
        return [server for server in servers if server["Tier"] <= user_tier and server["Status"] == 1] # noqa

    def fetch_user_tier(self, session):
        """Fetches a users tier from the API.

        Args:
            session (proton.api.Session): current user session
        Returns:
            int: current user session tier
        """
        data = session.api_request(endpoint="/vpn")
        return data["VPN"]["MaxTier"]

    def get_fastest_server(self, server_pool):
        """Get fastest server from a list of servers.

        Args:
            server_pool (list): pool with servers
        Returns:
            string: servername with the highest score (fastest)
        """
        if not isinstance(server_pool, list):
            raise TypeError(
                "Incorrect object type, "
                + "list is expected but got {} instead".format(
                    type(server_pool)
                )
            )

        # Sort servers by "speed" and select top n according to pool_size
        fastest_pool = sorted(
            server_pool, key=lambda server: server["Score"]
        )
        if len(fastest_pool) >= 50:
            pool_size = 4
        else:
            pool_size = 1

        fastest_server = random.choice(fastest_pool[:pool_size])["Name"]

        return fastest_server

    def extract_server_value(self, servername, key, servers):
        """Extract server data based on servername.

        Args:
            servername (string): servername [PT#1]
            key (string): keyword that contains servernames in json
            servers (list): a list containing the servers
        Returns:
            string: server name [PT#1]
        """
        value = [
            server[key] for server
            in servers if
            server['Name'] == servername
        ]
        return value[0]

    def extract_country_name(self, code):
        """Extract country name based on specified code.

        Args:
            code (string): country code [PT|SE|CH]
        Returns:
            string:
                country name if found, else returns country code
        """
        from lib.country_codes import country_codes
        return country_codes.get(code, code)

    def is_servername_valid(self, servername):
        """Check if the provided servername is in a valid format.

        Args:
            servername (string): the servername [SE-PT#1]
        Returns:
            bool
        """
        if not isinstance(servername, str):
            raise TypeError(
                "Incorrect object type, "
                + "str is expected but got {} instead".format(type(servername))
            )

        re_short = re.compile(r"^((\w\w)(-|#)?(\d{1,3})-?(TOR)?)$")
        # For long format (IS-DE-01 | Secure-Core/Free/US Servers)
        re_long = re.compile(
            r"^(((\w\w)(-|#)?([A-Z]{2}|FREE))(-|#)?(\d{1,3})-?(TOR)?)$"
        )
        return_servername = False

        if re_short.search(servername):
            user_server = re_short.search(servername)

            country_code = user_server.group(2)
            number = user_server.group(4).lstrip("0")
            tor = user_server.group(5)
            servername = "{0}#{1}".format(country_code, number)
            return_servername = servername + "{0}".format(
                '-' + tor if tor is not None else ''
            )

        elif re_long.search(servername):
            user_server = re_long.search(servername)
            country_code = user_server.group(3)
            country_code2 = user_server.group(5)
            number = user_server.group(7).lstrip("0")
            tor = user_server.group(8)
            return_servername = "{0}-{1}#{2}".format(
                country_code, country_code2, number
            ) + "{0}".format(
                '-' + tor if tor is not None else ''
            )

        return False if not return_servername else True
