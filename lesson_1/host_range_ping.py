import ipaddress
from threading import Thread
from typing import Dict, List
import queue

from host_ping import host_ping

my_queue = queue.Queue()


def store_in_queue(f):
    def wrapper(*args):
        my_queue.put(f(*args))
    return wrapper


@store_in_queue
def form_dict(result_dict: Dict[str, List[str]], addr_list: List) -> Dict[str, List[str]]:
    addr_from, addr_to = addr_list[0], addr_list[-1]
    while addr_from <= addr_to:
        if host_ping(str(addr_from)):
            result_dict["Reachable"].append(str(addr_from))
        else:
            result_dict["Unreachable"].append(str(addr_from))
        addr_from += 1
    return result_dict


def host_range_ping() -> Dict[str, str]:
    result_dict = {"Reachable": [], "Unreachable": []}
    while True:
        try:
            addr_from = ipaddress.ip_address(input("Введите начальный адрес: "))
        except ValueError:
            print("Адрес невозможно привести к формату IP4")
        else:
            break
    addr_to = addr_from + int(input("Введите количество адресов:"))
    addr_list = [ipaddress.ip_address(i) for i in range(int(addr_from), int(addr_to)+1)]
    center = len(addr_list) // 2
    thread_1 = Thread(target=form_dict, args=(result_dict, addr_list[:center]))
    thread_2 = Thread(target=form_dict, args=(result_dict, addr_list[center:],))
    thread_1.start()
    thread_2.start()

    result_dict.update(my_queue.get())
    return result_dict


if __name__ == "__main__":
    print(host_range_ping())
