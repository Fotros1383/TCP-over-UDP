import json
from settings import PacketType, log_format


class Packet:
    def __init__(self, src_port, dest_port, seq_num, ack_num, flags=PacketType.DATA, data="", len_data = None):
        self.src_port = src_port
        self.dest_port = dest_port
        self.seq_num = seq_num
        self.ack_num = ack_num
        self.flags = flags.value if type(flags)==PacketType else flags
        self.data = str(data)
        self.len_data = len_data if len_data else len(data)

    def to_bytes(self):
        try:
            return json.dumps(self.__dict__).encode('utf-8')
        except Exception as e:
            print(log_format(f"ERROR in packet to bytes: {e}"))
            return None
        
    @staticmethod
    def from_bytes(data_bytes:bytes):
        try:
            data = json.loads(data_bytes.decode('utf-8'))
            return Packet(**data)
        except Exception as e:
            print(log_format("ERROR in packet from bytes: {e}"))
            return None
    
    def has_flag(self, flag:PacketType):
        return flag.value == self.flags

    def __str__(self):
        string = f'''
        packet info:\n
        src port: {self.src_port}
        dst port: {self.dest_port}
        seq num: {self.seq_num}
        ack num: {self.ack_num}
        flag: {PacketType(self.flags).name}
        data: {str(self.data)}
        len data: {self.len_data}
'''

        return string


    
