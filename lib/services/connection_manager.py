
import os

import gi
gi.require_version("NM", "1.0")
from gi.repository import NM, GLib

from lib import exceptions
from lib.constants import ENV_CI_NAME, VIRTUAL_DEVICE_NAME


class ConnectionManager():
    def __init__(
        self,
        plugin_manager,
        virtual_device_name=VIRTUAL_DEVICE_NAME
    ):
        self.plugin_manager = plugin_manager
        self.virtual_device_name = virtual_device_name

    def add_connection(self, filename, username, password, delete_cached_cert):
        """Setup and add ProtonVPN connection

            Args:
                filename (string): certificate filename
                username (string): openvpn username
                password (string): openvpn password
                delete_cached_cert (method): method that delete cached cert
        """
        if not isinstance(filename, str):
            raise TypeError(
                "Incorrect object type, "
                + "str is expected but got {} instead".format(type(filename))
            )
        elif not filename.strip():
            raise ValueError("A valid filename must be provided")

        if not isinstance(username, str):
            raise TypeError(
                "Incorrect object type, "
                + "str is expected but got {} instead".format(type(username))
            )
        elif not isinstance(password, str):
            raise TypeError(
                "Incorrect object type, "
                + "str is expected but got {} instead".format(type(password))
            )
        elif not username.strip() or not password.strip():
            raise ValueError("Both username and password must be provided")

        try:
            delete_cached_cert("test")
        except FileNotFoundError:
            pass
        except Exception:
            raise NotImplementedError(
                "Expects object method, "
                + "{} was passed".format(delete_cached_cert)
            )

        # https://lazka.github.io/pgi-docs/NM-1.0/classes/Client.html
        client = NM.Client.new(None)
        main_loop = GLib.MainLoop()

        connection = self.plugin_manager.import_connection_from_file(
            filename
        )

        # returns NM.SettingVpn if the connection contains one, otherwise None
        # https://lazka.github.io/pgi-docs/NM-1.0/classes/SettingVpn.html
        vpn_settings = connection.get_setting_vpn()

        try:
            vpn_settings.add_data_item("username", username)
            vpn_settings.add_secret("password", password)
        except Exception as e:
            raise exceptions.AddConnectionCredentialsError(e)

        self.set_virtual_device_type(vpn_settings, filename)

        try:
            self.remove_connection()
        except exceptions.ConnectionNotFound:
            pass

        client.add_connection_async(
            connection,
            True,
            None,
            self.dynamic_callback,
            dict(
                callback_type="add",
                main_loop=main_loop,
                conn_name=connection.get_id(),
                delete_cached_cert=delete_cached_cert,
                filename=filename
            )
        )

        main_loop.run()

    def start_connection(self):
        """Start ProtonVPN connection"""
        client = NM.Client.new(None)
        main_loop = GLib.MainLoop()

        conn = self.get_proton_connection("all_connections", client=client)

        if len(conn) < 2 and conn[0] is False:
            raise exceptions.ConnectionNotFound("Connection not found")

        conn_name = conn[1]
        conn = conn[0]

        client.activate_connection_async(
            conn,
            None,
            None,
            None,
            self.dynamic_callback,
            dict(
                callback_type="start",
                main_loop=main_loop,
                conn_name=conn_name
            )
        )

        main_loop.run()

    def stop_connection(self, client=None):
        """Stop ProtonVPN connection"""
        if not client:
            client = NM.Client.new(None)

        main_loop = GLib.MainLoop()

        conn = self.get_proton_connection("active_connections", client)

        if len(conn) < 2 and conn[0] is False:
            return False

        conn_name = conn[1]
        conn = conn[0]

        client.deactivate_connection_async(
            conn,
            None,
            self.dynamic_callback,
            dict(
                callback_type="stop",
                main_loop=main_loop,
                conn_name=conn_name
            )
        )

        main_loop.run()

    def remove_connection(self):
        """Stop and remove ProtonVPN connection"""
        client = NM.Client.new(None)
        main_loop = GLib.MainLoop()
        conn = self.get_proton_connection("all_connections", client)

        if len(conn) < 2 and conn[0] is False:
            raise exceptions.ConnectionNotFound(
                "ProtonVPN connection was not found"
            )

        self.stop_connection(client)

        conn_name = conn[1]
        conn = conn[0]

        # conn is a NM.RemoteConnection
        # https://lazka.github.io/pgi-docs/NM-1.0/classes/RemoteConnection.html#NM.RemoteConnection

        conn.delete_async(
            None,
            self.dynamic_callback,
            dict(
                callback_type="remove",
                main_loop=main_loop,
                conn_name=conn_name
            )
        )

        main_loop.run()

    def dynamic_callback(self, client, result, data):
        callback_type = data.get("callback_type")
        main_loop = data.get("main_loop")
        conn_name = data.get("conn_name")
        delete_cached_cert = data.get("delete_cached_cert")
        filename = data.get("filename")

        try:
            callback_type_dict = dict(
                remove=dict(
                    finish_function=client.delete_finish,
                    exception=exceptions.RemoveConnectionFinishError
                )
            )
        except AttributeError:
            callback_type_dict = dict(
                add=dict(
                    finish_function=client.add_connection_finish,
                    exception=exceptions.AddConnectionFinishError,
                ),
                start=dict(
                    finish_function=client.activate_connection_finish,
                    exception=exceptions.StartConnectionFinishError,
                ),
                stop=dict(
                    finish_function=client.deactivate_connection_finish,
                    exception=exceptions.StopConnectionFinishError,
                )
            )

        try:
            (callback_type_dict[callback_type]["finish_function"])(result)
            print(
                "The connection profile "
                + "\"{}\" has been {}ed".format(conn_name, callback_type)
            )
        except Exception as e:
            raise (callback_type_dict[callback_type]["exception"])(e)

        if not os.environ.get(ENV_CI_NAME):
            if callback_type == "add":
                delete_cached_cert(filename)

        main_loop.quit()

    def extract_virtual_device_type(self, filename):
        """Get virtual device type from .ovpn file"""
        virtual_dev_type_list = ["tun", "tap"]

        with open(filename, "r") as f:
            content_list = f.readlines()
            dev_type = [dev.rstrip() for dev in content_list if "dev" in dev]
            try:
                dev_type = dev_type[0].split()[1]
            except IndexError:
                raise exceptions.VirtualDeviceNotFound(
                    "No virtual device type was specified in .ovpn file"
                )

            try:
                index = virtual_dev_type_list.index(dev_type)
            except (ValueError, KeyError, TypeError):
                raise exceptions.IllegalVirtualDevice(
                    "Only {} are permitted, though \"{}\" "
                    .format(' and '.join(virtual_dev_type_list), dev_type)
                    + "was provided"
                )
            else:
                return virtual_dev_type_list[index]

    def set_virtual_device_type(self, vpn_settings, filename):
        """Set virtual device type from .ovpn file"""
        virtual_device_type = self.extract_virtual_device_type(filename)

        # Changes virtual tunnel name
        vpn_settings.add_data_item("dev", self.virtual_device_name)
        vpn_settings.add_data_item("dev-type", virtual_device_type)

    def get_proton_connection(self, connection_type, client=None):
        """Get saved ProtonVPN connection"""
        return_conn = [False]

        if not client:
            client = NM.Client.new(None)

        connection_types = {
            "all_connections": client.get_connections,
            "active_connections": client.get_active_connections
        }

        all_cons = connection_types[connection_type]()

        for conn in all_cons:
            if conn.get_connection_type() == "vpn":
                conn_for_vpn = conn
                # conn can be either NM.RemoteConnection or NM.ActiveConnection
                if connection_type == "active_connections":
                    conn_for_vpn = conn.get_connection()

                vpn_settings = conn_for_vpn.get_setting_vpn()

                if (
                    vpn_settings.get_data_item("dev")
                    == self.virtual_device_name
                ):
                    return_conn = [conn, conn.get_id()]
                    break

        return tuple(return_conn)
