import json
import socket
import time
import threading
from typing import Dict, Any, Optional

import click

from db.client_db import ClientDB
from messages import get_message, send_message
from variables import *
from errors import IncorrectDataRecivedError, ReqFieldMissingError, ServerError
from meta.metaclasses import ClientMeta

logger = logging.getLogger('client')
sock_lock = threading.Lock()
database_lock = threading.Lock()


class ClientSender(threading.Thread, metaclass=ClientMeta):
    def __init__(self, account_name: str, sock, database) -> None:
        self.account_name = account_name
        self.sock = sock
        self.database = database
        super().__init__()

    def create_exit_message(self) -> Dict[str, Any]:
        return {
            ACTION: EXIT,
            TIME: time.time(),
            ACCOUNT_NAME: self.account_name
        }

    def create_message(self) -> None:
        to = input('Choose destination: ')
        message = input('Write your message: ')
        with database_lock:
            if not self.database.check_user(to):
                logger.error(f'User {to} is unknown')
                return

        message_dict = {
            ACTION: MESSAGE,
            SENDER: self.account_name,
            DESTINATION: to,
            TIME: time.time(),
            MESSAGE_TEXT: message
        }

        with database_lock:
            self.database.save_message(self.account_name, to, message)

        with sock_lock:
            try:
                send_message(self.sock, message_dict)
                logger.info(f'Send message to {to}')
            except Exception as e:
                logger.critical(f'Lost connection with server: {e}')
                exit(1)

    def run(self) -> None:
        self.print_help()
        while True:
            command = input('Choose your action: ')
            if command == 'message':
                self.create_message()
            elif command == 'help':
                self.print_help()
            elif command == 'exit':
                with sock_lock:
                    try:
                        send_message(self.sock, self.create_exit_message())
                    except Exception:
                        pass
                    logger.info('Shutdown by user command.')
                time.sleep(0.5)
                break
            elif command == 'contacts':
                with database_lock:
                    contacts_list = self.database.get_contacts()
                for contact in contacts_list:
                    print(contact)
            elif command == 'edit':
                self.edit_contacts()
            elif command == 'history':
                self.print_history()
            else:
                print('Invalid command. Please use `help` to see list of commands')

    def print_history(self) -> None:
        ask = input('Input messages - in, output - out, all - only Enter: ')
        with database_lock:
            if ask == 'in':
                history_list = self.database.get_history(to_who=self.account_name)
                for message in history_list:
                    print(f'\nMessage from: {message[0]} date {message[3]}:\n{message[2]}')
            elif ask == 'out':
                history_list = self.database.get_history(from_who=self.account_name)
                for message in history_list:
                    print(f'\nMessage to: {message[1]} date {message[3]}:\n{message[2]}')
            else:
                history_list = self.database.get_history()
                for message in history_list:
                    print(f'\nMessage from: {message[0]} to {message[1]} date {message[3]}\n{message[2]}')

    def edit_contacts(self) -> None:
        ans = input('For delete any contact - del, for add contact - add: ')
        if ans == 'del':
            edit = input('Choose username for delete: ')
            with database_lock:
                if self.database.check_contact(edit):
                    self.database.del_contact(edit)
                else:
                    logger.error('User is unknown')
        elif ans == 'add':
            edit = input('Choose username for add: ')
            if self.database.check_user(edit):
                with database_lock:
                    self.database.add_contact(edit)
                with sock_lock:
                    try:
                        add_contact(self.sock, self.account_name, edit)
                    except ServerError:
                        logger.error('Failed to send information to the server.')

    @staticmethod
    def print_help():
        print('message - send message')
        print('history - message history')
        print('contacts - list of contacts')
        print('edit - edit list of contacts')
        print('help - show this instruction')
        print('exit - disconnect from server')


class ClientReader(threading.Thread, metaclass=ClientMeta):
    def __init__(self, account_name: str, sock, database) -> None:
        self.account_name = account_name
        self.sock = sock
        self.database = database
        super().__init__()

    def run(self):
        while True:
            try:
                message = get_message(self.sock)
                if ACTION in message and message[ACTION] == MESSAGE and SENDER in message and DESTINATION in message \
                        and MESSAGE_TEXT in message and message[DESTINATION] == self.account_name:
                    logger.info(f'Receive message from {message[SENDER]}:\n{message[MESSAGE_TEXT]}')
                    with database_lock:
                        try:
                            self.database.save_message(message[SENDER], self.account_name, message[MESSAGE_TEXT])
                        except Exception as e:
                            logger.error(e)
                else:
                    logger.error(f'Receive non correct answer from server: {message}')
            except IncorrectDataRecivedError:
                logger.error('Failed to decode received message.')
            except (OSError, ConnectionError, ConnectionAbortedError, ConnectionResetError, json.JSONDecodeError):
                logger.critical('Lost connection with server')
                break


def create_presence(account_name: str) -> Dict[str, Any]:
    out = {
        ACTION: PRESENCE,
        TIME: time.time(),
        USER: {
            ACCOUNT_NAME: account_name
        }
    }
    logger.debug(f'Create {PRESENCE} message to user {account_name}')
    return out


def process_response_ans(message: str) -> Optional[str]:
    if RESPONSE in message:
        if message[RESPONSE] == 200:
            return '200 : OK'
        elif message[RESPONSE] == 400:
            raise ServerError(f'400 : {message[ERROR]}')
    raise ReqFieldMissingError(RESPONSE)


def contacts_list_request(sock, name: str) -> Optional[str]:
    logger.debug(f'Request a contact list for a user {name}')
    req = {
        ACTION: GET_CONTACTS,
        TIME: time.time(),
        USER: name
    }
    send_message(sock, req)
    ans = get_message(sock)
    logger.debug(f'Receive the answer: {ans}')
    if RESPONSE in ans and ans[RESPONSE] == 202:
        return ans[LIST_INFO]
    else:
        raise ServerError


def add_contact(sock, username: str, contact: str) -> None:
    logger.debug(f'Create a contact {contact}')
    req = {
        ACTION: ADD_CONTACT,
        TIME: time.time(),
        USER: username,
        ACCOUNT_NAME: contact
    }
    send_message(sock, req)
    ans = get_message(sock)
    if RESPONSE in ans and ans[RESPONSE] == 200:
        pass
    else:
        raise ServerError('Contact creation error')
    print('Successful contact creation')


def user_list_request(sock, username: str) -> Optional[str]:
    logger.debug(f'Query a list of known users of {username}')
    req = {
        ACTION: USERS_REQUEST,
        TIME: time.time(),
        ACCOUNT_NAME: username
    }
    send_message(sock, req)
    ans = get_message(sock)
    if RESPONSE in ans and ans[RESPONSE] == 202:
        return ans[LIST_INFO]
    else:
        raise ServerError


def remove_contact(sock, username: str, contact: str) -> None:
    req = {
        ACTION: REMOVE_CONTACT,
        TIME: time.time(),
        USER: username,
        ACCOUNT_NAME: contact
    }
    send_message(sock, req)
    ans = get_message(sock)
    if RESPONSE in ans and ans[RESPONSE] == 200:
        pass
    else:
        raise ServerError('Client deletion error')
    print('Successful removal')


def database_load(sock, database, username: str) -> None:
    try:
        users_list = user_list_request(sock, username)
    except ServerError:
        logger.error('Failed to query list of known users.')
    else:
        database.add_users(users_list)

    try:
        contacts_list = contacts_list_request(sock, username)
    except ServerError:
        logger.error('Contact list request failed.')
    else:
        for contact in contacts_list:
            database.add_contact(contact)


@click.command()
@click.option('--addr', '-a', default=DEFAULT_IP_ADDRESS, help='IP address of server')
@click.option('--port', '-p', default=DEFAULT_PORT, help='TCP-port of server')
@click.option('--name', '-n', default=None, help='username')
def run(addr: str, port: int, name: str):
    if not name:
        name = input('Choose username: ')
    else:
        print(f'Start client with name: {name}')

    logger.info(
        f'Start client on {addr} with {port} port and username {name}')

    try:
        transport = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        transport.connect((addr, port))
        send_message(transport, create_presence(name))
        answer = process_response_ans(get_message(transport))
        logger.info(f'Create connection with server. Receive answer: {answer}')

    except json.JSONDecodeError:
        logger.error('Invalid JSON received')
        exit(1)
    except ServerError as error:
        logger.error(error.text)
        exit(1)
    except ReqFieldMissingError as missing_error:
        logger.error(missing_error.missing_field)
        exit(1)
    except (ConnectionRefusedError, ConnectionError):
        logger.critical(
            f'Failed to connect to server {addr}:{port}')
        exit(1)
    else:
        database = ClientDB(name)
        database_load(transport, database, name)

        module_reciver = ClientReader(name, transport, database)
        module_reciver.daemon = True
        module_reciver.start()

        module_sender = ClientSender(name, transport, database)
        module_sender.daemon = True
        module_sender.start()
        logger.debug('Start processes')

        while True:
            time.sleep(1)
            if module_reciver.is_alive() and module_sender.is_alive():
                continue
            break


if __name__ == '__main__':
    run()
