from settings import State, PacketType, get_current_time
from packet import Packet
import random, socket

WINDOW_SIZE = 5
ESTABLISH = "establish"

class Connection:
    def __init__(self, local_addr, remote_addr, socket:socket.socket):
        
        self.local_addr = local_addr
        self.remote_addr = remote_addr
        self.socket = socket

        self.state = State.CLOSED

        self.seq_num = random.randint(1000, 65000)   # can be change
        self.ack_num = 0

    def send_packet(self, packet:Packet):
        packet.src_port = self.local_addr[1]
        packet.dest_port = self.remote_addr[1]
        data = packet.to_bytes()
        self.socket.sendto(data, self.remote_addr)
        print(f"[{get_current_time()}]  Sending packet to {self.remote_addr}")

    def close(self):
        print(f"[{get_current_time()}]  Connection closed : {self.local_addr} <-> {self.remote_addr}")
        self.state = State.CLOSED
