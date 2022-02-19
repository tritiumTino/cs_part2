import sys
import click
from PyQt5.QtWidgets import QApplication

from db.client_db import ClientDB
from client.main_window import ClientMainWindow
from client.start_dialog import UserNameDialog
from client.transport import ClientTransport
from variables import *
from errors import ServerError

logger = logging.getLogger('client')


@click.command()
@click.option('--addr', '-a', default=DEFAULT_IP_ADDRESS, help='IP address of server')
@click.option('--port', '-p', default=DEFAULT_PORT, help='TCP-port of server')
@click.option('--name', '-n', default=None, help='username')
def run(addr: str, port: int, name: str):
    client_app = QApplication(sys.argv)
    if not name:
        start_dialog = UserNameDialog()
        client_app.exec_()
        if start_dialog.ok_pressed:
            name = start_dialog.client_name.text()
            del start_dialog
        else:
            exit(0)

    logger.info(
        f'Start client on {addr} with {port} port and username {name}')

    database = ClientDB(name)

    try:
        transport = ClientTransport(port, addr, database, name)
    except ServerError as error:
        logger.critical(error.text)
        exit(1)
    transport.setDaemon(True)
    transport.start()

    main_window = ClientMainWindow(database, transport)
    main_window.make_connection(transport)
    main_window.setWindowTitle(f'Chat alpha - {name}')
    client_app.exec_()

    transport.transport_shutdown()
    transport.join()


if __name__ == '__main__':
    run()
