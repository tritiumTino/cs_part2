import logging
import os
import select
import socket
import sys
import threading
from typing import Optional

import click
import configparser

from db.server_db import ServerDB
from meta.metaclasses import ServerMeta
from utils.port import Port
from variables import *
from messages import get_message, send_message
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import QTimer
from ui.server_gui import MainWindow, gui_create_model, HistoryWindow, create_stat_model, ConfigWindow
from PyQt5.QtGui import QStandardItemModel, QStandardItem


logger = logging.getLogger('server')
new_connection = False
conflag_lock = threading.Lock()


class Server(threading.Thread, metaclass=ServerMeta):
    port = Port()

    def __init__(self, addr: str, port: int, database) -> None:
        self.addr = addr
        self.port = port
        self.database = database

        self.clients = []
        self.messages = []
        self.names = dict()

        super().__init__()

    def init_socket(self):
        transport = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        transport.bind((self.addr, self.port))
        transport.settimeout(0.5)

        self.sock = transport
        self.sock.listen()

    def run(self):
        self.init_socket()

        while True:
            try:
                client, client_address = self.sock.accept()
            except OSError:
                pass
            else:
                logger.info(f'Receive connection from {client_address}')
                self.clients.append(client)

            read = []
            write = []
            try:
                if self.clients:
                    read, write, err_lst = select.select(self.clients, self.clients, [], 0)
            except OSError:
                pass

            if read:
                for client_with_message in read:
                    try:
                        self.process_client_message(get_message(client_with_message), client_with_message)
                    except Exception:
                        logger.info(f'Client {client_with_message.getpeername()} stopped connection')
                        for name in self.names:
                            if self.names[name] == client_with_message:
                                self.database.user_logout(name)
                                del self.names[name]
                                break
                        self.clients.remove(client_with_message)

            for message in self.messages:
                try:
                    self.process_message(message, write)
                except Exception:
                    logger.info(f'Lost connection with {message[DESTINATION]} client')
                    self.clients.remove(self.names[message[DESTINATION]])
                    self.database.user_logout(message[DESTINATION])
                    del self.names[message[DESTINATION]]
            self.messages.clear()

    def process_message(self, message: dict, listen_socks: list) -> None:
        if message[DESTINATION] in self.names and self.names[message[DESTINATION]] in listen_socks:
            send_message(self.names[message[DESTINATION]], message)
            logger.info(
                f'Send message from {message[DESTINATION]} to {message[SENDER]}.')
        elif message[DESTINATION] in self.names and self.names[message[DESTINATION]] not in listen_socks:
            raise ConnectionError
        else:
            logger.error(
                f'Client {message[DESTINATION]} is not registered')

    def process_client_message(self, message: dict, client) -> None:
        global new_connection
        if ACTION in message and message[ACTION] == PRESENCE and TIME in message and USER in message:
            if message[USER][ACCOUNT_NAME] not in self.names.keys():
                self.names[message[USER][ACCOUNT_NAME]] = client
                client_ip, client_port = client.getpeername()
                self.database.user_login(message[USER][ACCOUNT_NAME], client_ip, client_port)
                send_message(client, RESPONSE_200)
                with conflag_lock:
                    new_connection = True
            else:
                response = RESPONSE_400
                response[ERROR] = 'Name is already reserved'
                send_message(client, response)
                self.clients.remove(client)
                client.close()

        elif (
                ACTION in message and message[ACTION] == MESSAGE and DESTINATION in message
                and TIME in message and SENDER in message and MESSAGE_TEXT in message):
            self.messages.append(message)
            self.database.process_message(message[SENDER], message[DESTINATION])

        elif ACTION in message and message[ACTION] == EXIT and ACCOUNT_NAME in message:
            self.database.user_logout(message[ACCOUNT_NAME])
            self.clients.remove(self.names[ACCOUNT_NAME])
            self.names[ACCOUNT_NAME].close()
            del self.names[ACCOUNT_NAME]
            with conflag_lock:
                new_connection = True

        elif (
                ACTION in message and message[ACTION] == GET_CONTACTS
                and USER in message and self.names[message[USER]] == client
        ):
            response = RESPONSE_202
            response[LIST_INFO] = self.database.get_contacts(message[USER])
            send_message(client, response)

        elif ACTION in message and message[ACTION] == ADD_CONTACT and ACCOUNT_NAME in message and USER in message \
                and self.names[message[USER]] == client:
            self.database.add_contact(message[USER], message[ACCOUNT_NAME])
            send_message(client, RESPONSE_200)

        elif (
                ACTION in message and message[ACTION] == REMOVE_CONTACT and ACCOUNT_NAME in message
                and USER in message and self.names[message[USER]] == client
        ):
            self.database.remove_contact(message[USER], message[ACCOUNT_NAME])
            send_message(client, RESPONSE_200)

        elif (
                ACTION in message and message[ACTION] == USERS_REQUEST and ACCOUNT_NAME in message
                and self.names[message[ACCOUNT_NAME]] == client
        ):
            response = RESPONSE_202
            response[LIST_INFO] = [user[0] for user in self.database.users_list()]
            send_message(client, response)

        else:
            response = RESPONSE_400
            response[ERROR] = 'Bad request'
            send_message(client, response)


@click.command()
@click.option('--addr', '-a', help='IP address to listen to')
@click.option('--port', '-p', help='TCP-port')
def run(addr: Optional[str], port: Optional[int]) -> None:
    config = configparser.ConfigParser()
    dir_path = os.path.dirname(os.path.realpath(__file__))
    config.read(f"{dir_path}/{'server.ini'}")
    listen_address = addr or config['SETTINGS']['Listen_Address']
    listen_port = port or config['SETTINGS']['Default_port']

    database = ServerDB(os.path.join(config['SETTINGS']['Database_path'], config['SETTINGS']['Database_file']))
    server = Server(listen_address, listen_port, database)
    server.daemon = True
    server.start()

    # PyQt5
    server_app = QApplication(sys.argv)
    main_window = MainWindow()

    main_window.statusBar().showMessage('Server Working')
    main_window.active_clients_table.setModel(gui_create_model(database))
    main_window.active_clients_table.resizeColumnsToContents()
    main_window.active_clients_table.resizeRowsToContents()

    # Update list of clients
    def list_update():
        global new_connection
        if new_connection:
            main_window.active_clients_table.setModel(gui_create_model(database))
            main_window.active_clients_table.resizeColumnsToContents()
            main_window.active_clients_table.resizeRowsToContents()
            with conflag_lock:
                new_connection = False

    # Clients statistic
    def show_statistics():
        global stat_window
        stat_window = HistoryWindow()
        stat_window.history_table.setModel(create_stat_model(database))
        stat_window.history_table.resizeColumnsToContents()
        stat_window.history_table.resizeRowsToContents()
        stat_window.show()

    # Server settings window
    def server_config():
        global config_window
        # Add current settings
        config_window = ConfigWindow()
        config_window.db_path.insert(config['SETTINGS']['Database_path'])
        config_window.db_file.insert(config['SETTINGS']['Database_file'])
        config_window.port.insert(config['SETTINGS']['Default_port'])
        config_window.ip.insert(config['SETTINGS']['Listen_Address'])
        config_window.save_btn.clicked.connect(save_server_config)

    # Save new server settings
    def save_server_config():
        global config_window
        message = QMessageBox()
        config['SETTINGS']['Database_path'] = config_window.db_path.text()
        config['SETTINGS']['Database_file'] = config_window.db_file.text()
        try:
            port = int(config_window.port.text())
        except ValueError:
            message.warning(config_window, 'Error', 'Port param must be integer')
        else:
            config['SETTINGS']['Listen_Address'] = config_window.ip.text()
            if 1023 < port < 65536:
                config['SETTINGS']['Default_port'] = str(port)
                print(port)
                with open('server.ini', 'w') as conf:
                    config.write(conf)
                    message.information(config_window, 'OK', 'Settings saved successfully!')
            else:
                message.warning(config_window, 'Error', 'Port must have value between 1024 and 65536')

    timer = QTimer()
    timer.timeout.connect(list_update)
    timer.start(1000)

    main_window.refresh_button.triggered.connect(list_update)
    main_window.show_history_button.triggered.connect(show_statistics)
    main_window.config_btn.triggered.connect(server_config)

    server_app.exec_()


if __name__ == '__main__':
    run()
