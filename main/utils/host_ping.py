import platform
import subprocess


def ping(host) -> bool:
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    command = ['ping', param, '1', host]
    reply = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    return reply.wait() == 0


def host_ping(addr: str) -> bool:
    return True if ping(addr) else False


if __name__ == "__main__":
    addr = input("Введите адрес для проверки: ")
    print(f"{addr}: {'Reachable' if host_ping(addr) else 'Unreachable'}")
