from enum import Enum
from datetime import datetime

SERVER_IP = "127.0.0.1"
SERVER_PORT = 9500
CLIENT_IP = "127.0.0.1"
BACKLOG = 5
BUFFER_SIZE = 4096
TIMEOUT = 10


def get_current_time():
    now = datetime.now()
    formatted_time = now.strftime("%Y-%m-%d  %H:%M:%S")
    return formatted_time

class PacketType(Enum):

    DATA = 0
    SYN = 1
    SYN_ACK = 2
    ACK = 3
    FIN = 4
    RST = 5


class State(Enum):
    CLOSED = 0
    LISTEN = 1
    SYN_RECIEVED = 2
    SYN_SENT = 3
    ESTABLISHED = 4
