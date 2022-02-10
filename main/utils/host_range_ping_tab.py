from tabulate import tabulate

from host_range_ping import host_range_ping


def host_range_ping_tab() -> None:
    hosts_dict = host_range_ping()
    print(tabulate(hosts_dict, headers=hosts_dict.keys()))


if __name__ == "__main__":
    host_range_ping_tab()
