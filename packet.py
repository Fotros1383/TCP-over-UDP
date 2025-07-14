import json
from settings import PacketType


class Packet:
    def __init__(self, src_port, dest_port, seq_num, ack_num, flags=PacketType.DATA, data="", len_data = None):
        self.src_port = src_port
        self.dest_port = dest_port
        self.seq_num = seq_num
        self.ack_num = ack_num
        self.flags = flags.value if type(flags)==PacketType else flags
        self.data = data
        self.len_data = len_data if len_data else len(data)

    def to_bytes(self):
        return json.dumps(self.__dict__).encode('utf-8')
    
    @staticmethod
    def from_bytes(data_bytes:bytes):
        data = json.loads(data_bytes.decode('utf-8'))
        return Packet(**data)
    
    def has_flag(self, flag:PacketType):
        if flag.value == self.flags:
            return True
        return False
    def __str__(self):
        string = f'''
        packet info:\n
        src port: {self.src_port}
        dst port: {self.dest_port}
        seq num: {self.seq_num}
        ack num: {self.ack_num}
        flag: {self.flags}
        data: {self.data}
        len data: {self.len_data}
'''

        return string
