import logging
import select
import socket
import click

from meta.metaclasses import ServerMeta
from utils.port import Port
from variables import (
    DESTINATION,
    SENDER,
    ACTION,
    PRESENCE,
    TIME,
    USER,
    ACCOUNT_NAME,
    RESPONSE_200,
    RESPONSE_400,
    ERROR,
    MESSAGE,
    MESSAGE_TEXT,
    EXIT, DEFAULT_IP_ADDRESS, DEFAULT_PORT
)
from messages import get_message, send_message


logger = logging.getLogger('server')


class Server(metaclass=ServerMeta):
    port = Port()

    def __init__(self, addr: str, port: int) -> None:
        self.addr = addr
        self.port = port

        self.clients = []
        self.messages = []
        self.names = dict()

    def init_socket(self):
        transport = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        transport.bind((self.addr, self.port))
        transport.settimeout(0.5)

        self.sock = transport
        self.sock.listen()

    def loop(self):
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
                        self.clients.remove(client_with_message)

            for message in self.messages:
                try:
                    self.process_message(message, write)
                except Exception:
                    logger.info(f'Lost connection with {message[DESTINATION]} client')
                    self.clients.remove(self.names[message[DESTINATION]])
                    del self.names[message[DESTINATION]]
            self.messages.clear()

    def process_message(self, message, listen_socks):
        if message[DESTINATION] in self.names and self.names[message[DESTINATION]] in listen_socks:
            send_message(self.names[message[DESTINATION]], message)
            logger.info(
                f'Send message from {message[DESTINATION]} to {message[SENDER]}.')
        elif message[DESTINATION] in self.names and self.names[message[DESTINATION]] not in listen_socks:
            raise ConnectionError
        else:
            logger.error(
                f'Client {message[DESTINATION]} is not registered')

    def process_client_message(self, message, client):
        if ACTION in message and message[ACTION] == PRESENCE and TIME in message and USER in message:
            if message[USER][ACCOUNT_NAME] not in self.names.keys():
                self.names[message[USER][ACCOUNT_NAME]] = client
                send_message(client, RESPONSE_200)
            else:
                response = RESPONSE_400
                response[ERROR] = 'Name is already reserved'
                send_message(client, response)
                self.clients.remove(client)
                client.close()
            return

        elif ACTION in message and message[ACTION] == MESSAGE and DESTINATION in message and TIME in message \
                and SENDER in message and MESSAGE_TEXT in message:
            self.messages.append(message)
            return

        elif ACTION in message and message[ACTION] == EXIT and ACCOUNT_NAME in message:
            self.clients.remove(self.names[ACCOUNT_NAME])
            self.names[ACCOUNT_NAME].close()
            del self.names[ACCOUNT_NAME]
            return

        else:
            response = RESPONSE_400
            response[ERROR] = 'Bad request'
            send_message(client, response)
            return


@click.command()
@click.option('--addr', '-a', default=DEFAULT_IP_ADDRESS, help='IP address to listen to')
@click.option('--port', '-p', default=DEFAULT_PORT, help='TCP-port')
def run(addr: str, port: int) -> None:
    server = Server(addr, port)
    server.loop()


if __name__ == '__main__':
    run()
