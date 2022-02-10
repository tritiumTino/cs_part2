import json
import socket
import time
import threading

import click

from messages import get_message, send_message
from variables import *
from errors import IncorrectDataRecivedError, ReqFieldMissingError, ServerError
from meta.metaclasses import ClientMeta

logger = logging.getLogger('client')


class ClientSender(threading.Thread, metaclass=ClientMeta):
    def __init__(self, account_name, sock):
        self.account_name = account_name
        self.sock = sock
        super().__init__()

    def create_exit_message(self):
        return {
            ACTION: EXIT,
            TIME: time.time(),
            ACCOUNT_NAME: self.account_name
        }

    def create_message(self):
        to = input('Choose destination: ')
        message = input('Write your message: ')
        message_dict = {
            ACTION: MESSAGE,
            SENDER: self.account_name,
            DESTINATION: to,
            TIME: time.time(),
            MESSAGE_TEXT: message
        }

        try:
            send_message(self.sock, message_dict)
            logger.info(f'Send message to {to}')
        except Exception:
            logger.critical('Lost connection with server')
            exit(1)

    def run(self):
        self.print_help()
        while True:
            command = input('Choose your action: ')
            if command == 'message':
                self.create_message()
            elif command == 'help':
                self.print_help()
            elif command == 'exit':
                try:
                    send_message(self.sock, self.create_exit_message())
                except Exception:
                    pass
                logger.info('Shutdown by user command.')
                time.sleep(0.5)
                break
            else:
                print('Invalid command. Please use `help` to see list of commands')

    @staticmethod
    def print_help():
        print('message - send message')
        print('help - show this instruction')
        print('exit - disconnect from server')


class ClientReader(threading.Thread , metaclass=ClientMeta):
    def __init__(self, account_name, sock):
        self.account_name = account_name
        self.sock = sock
        super().__init__()

    def run(self):
        while True:
            try:
                message = get_message(self.sock)
                if ACTION in message and message[ACTION] == MESSAGE and SENDER in message and DESTINATION in message \
                        and MESSAGE_TEXT in message and message[DESTINATION] == self.account_name:
                    logger.info(f'Receive message from {message[SENDER]}:\n{message[MESSAGE_TEXT]}')
                else:
                    logger.error(f'Receive non correct answer from server: {message}')
            except IncorrectDataRecivedError:
                logger.error('Failed to decode received message.')
            except (OSError, ConnectionError, ConnectionAbortedError, ConnectionResetError, json.JSONDecodeError):
                logger.critical('Lost connection with server')
                break


def create_presence(account_name):
    out = {
        ACTION: PRESENCE,
        TIME: time.time(),
        USER: {
            ACCOUNT_NAME: account_name
        }
    }
    logger.debug(f'Create {PRESENCE} message to user {account_name}')
    return out


def process_response_ans(message):
    if RESPONSE in message:
        if message[RESPONSE] == 200:
            return '200 : OK'
        elif message[RESPONSE] == 400:
            raise ServerError(f'400 : {message[ERROR]}')
    raise ReqFieldMissingError(RESPONSE)


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
        module_reciver = ClientReader(name, transport)
        module_reciver.daemon = True
        module_reciver.start()

        module_sender = ClientSender(name, transport)
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
