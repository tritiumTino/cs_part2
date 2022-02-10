import logging

logger = logging.getLogger(__name__)


class Port:
    def __set_name__(self, owner, name):
        self.name = name

    def __set__(self, instance, value: int):
        if not isinstance(value, int) or not 1023 < value < 65536:
            logger.critical(f"The port with value {value} is not available")
            exit(1)
        instance.__dict__[self.name] = value
