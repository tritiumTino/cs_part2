import socket
import sys
import time
import logging
import json
import threading
from typing import Any, Dict

from PyQt5.QtCore import pyqtSignal, QObject

from main.messages import send_message, get_message
from main.variables import *
from main.errors import ServerError

logger = logging.getLogger('client_dist')
socket_lock = threading.Lock()


class ClientTransport(threading.Thread, QObject):
    new_message = pyqtSignal(str)
    connection_lost = pyqtSignal()

    def __init__(self, port: int, ip_address: str, database, username: str) -> None:
        threading.Thread.__init__(self)
        QObject.__init__(self)

        self.database = database
        self.username = username
        self.transport = None
        self.connection_init(port, ip_address)
        try:
            self.user_list_update()
            self.contacts_list_update()
        except OSError as err:
            if err.errno:
                logger.critical('Lost connection with server.')
                raise ServerError('Lost connection with server!')
            logger.error('Timeout error when updating user lists.')
        except json.JSONDecodeError:
            logger.critical(f'Lost connection with server.')
            raise ServerError('Lost connection with server!')
        self.running = True

    def connection_init(self, port: int, ip: str) -> None:
        self.transport = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.transport.settimeout(5)

        connected = False
        for i in range(5):
            logger.info(f'Try to connect №{i + 1}')
            try:
                self.transport.connect((ip, port))
            except (OSError, ConnectionRefusedError):
                pass
            else:
                connected = True
                break
            time.sleep(1)

        if not connected:
            logger.critical('Failed to connect to server')
            raise ServerError('Failed to connect to server')

        logger.debug('Connected to server')

        try:
            with socket_lock:
                send_message(self.transport, self.create_presence())
                self.process_server_ans(get_message(self.transport))
        except (OSError, json.JSONDecodeError):
            logger.critical('Lost connection with server!')
            raise ServerError('Lost connection with server!')

        logger.info('The connection to the server was successfully established.')

    def create_presence(self) -> Dict[str, Any]:
        out = {
            ACTION: PRESENCE,
            TIME: time.time(),
            USER: {
                ACCOUNT_NAME: self.username
            }
        }
        logger.debug(f'Create {PRESENCE} message to user {self.username}')
        return out

    def process_server_ans(self, message: Dict[str, Any]) -> None:
        logger.debug(f'Parsing a message from the server: {message}')

        if RESPONSE in message:
            if message[RESPONSE] == 200:
                return
            elif message[RESPONSE] == 400:
                raise ServerError(f'{message[ERROR]}')
            else:
                logger.debug(f'Unknown verification code received: {message[RESPONSE]}')

        elif (
                ACTION in message and message[ACTION] == MESSAGE
                and SENDER in message and DESTINATION in message
                and MESSAGE_TEXT in message and message[DESTINATION] == self.username):
            logger.debug(f'Receive message from user {message[SENDER]}: {message[MESSAGE_TEXT]}')
            self.database.save_message(message[SENDER], 'in', message[MESSAGE_TEXT])
            self.new_message.emit(message[SENDER])

    def contacts_list_update(self) -> None:
        logger.debug(f'Request a contact list for a user {self.name}')
        req = {
            ACTION: GET_CONTACTS,
            TIME: time.time(),
            USER: self.username
        }
        logger.debug(f'Request generated {req}')
        with socket_lock:
            send_message(self.transport, req)
            ans = get_message(self.transport)
        logger.debug(f'Receive answer: {ans}')
        if RESPONSE in ans and ans[RESPONSE] == 202:
            for contact in ans[LIST_INFO]:
                self.database.add_contact(contact)
        else:
            logger.error('Failed to update contact list.')

    def user_list_update(self) -> None:
        logger.debug(f'Query a list of known users of {self.username}')
        req = {
            ACTION: USERS_REQUEST,
            TIME: time.time(),
            ACCOUNT_NAME: self.username
        }
        with socket_lock:
            send_message(self.transport, req)
            ans = get_message(self.transport)
        if RESPONSE in ans and ans[RESPONSE] == 202:
            self.database.add_users(ans[LIST_INFO])
        else:
            logger.error('Failed to update list of known users.')

    def add_contact(self, contact: str) -> None:
        logger.debug(f'Create the contact: {contact}')
        req = {
            ACTION: ADD_CONTACT,
            TIME: time.time(),
            USER: self.username,
            ACCOUNT_NAME: contact
        }
        with socket_lock:
            send_message(self.transport, req)
            self.process_server_ans(get_message(self.transport))

    def remove_contact(self, contact: str) -> None:
        logger.debug(f'Delete the contact: {contact}')
        req = {
            ACTION: REMOVE_CONTACT,
            TIME: time.time(),
            USER: self.username,
            ACCOUNT_NAME: contact
        }
        with socket_lock:
            send_message(self.transport, req)
            self.process_server_ans(get_message(self.transport))

    def transport_shutdown(self) -> None:
        self.running = False
        message = {
            ACTION: EXIT,
            TIME: time.time(),
            ACCOUNT_NAME: self.username
        }
        with socket_lock:
            try:
                send_message(self.transport, message)
            except OSError:
                pass
        logger.debug('Transport shuts down.')
        time.sleep(0.5)

    def send_message(self, to: str, message: str) -> None:
        message_dict = {
            ACTION: MESSAGE,
            SENDER: self.username,
            DESTINATION: to,
            TIME: time.time(),
            MESSAGE_TEXT: message
        }
        logger.debug(f'Message dictionary generated: {message_dict}')

        with socket_lock:
            send_message(self.transport, message_dict)
            self.process_server_ans(get_message(self.transport))
            logger.info(f'Send message to: {to}')

    def run(self) -> None:
        logger.debug('The process is running - the receiver of messages from the server.')
        while self.running:
            time.sleep(1)
            with socket_lock:
                try:
                    self.transport.settimeout(0.5)
                    message = get_message(self.transport)
                except OSError as err:
                    if err.errno:
                        logger.critical(f'Lost connection with server.')
                        self.running = False
                        self.connection_lost.emit()
                except (ConnectionError, ConnectionAbortedError,
                        ConnectionResetError, json.JSONDecodeError, TypeError):
                    logger.debug(f'Lost connection with server.')
                    self.running = False
                    self.connection_lost.emit()
                else:
                    logger.debug(f'Receive message from server: {message}')
                    self.process_server_ans(message)
                finally:
                    self.transport.settimeout(5)
