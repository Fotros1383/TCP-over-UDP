import socket, queue, time, random
from threading import Thread, Lock, Event
from packet import Packet
from connection import Connection
from settings import get_current_time, PacketType, State, BACKLOG, BUFFER_SIZE, TIMEOUT


class TCP_Socket:
    def __init__(self, is_server=False):

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.local_addr = None
        self.remote_addr = None  
        self.is_server = is_server
        self.state = State.CLOSED

        self.connections = {}
        self.accept_queue = None
        self.backlog = 0

        self.client_connection = None

        self.listener_thread = None
        self.listening = False
        self.running = False

        self.lock = Lock()

        print(f"[{get_current_time()}] Socket created")
    
    def bind(self, address):
        try:
            self.sock.bind(address)
            self.local_addr = address
            print(f"[{get_current_time()}]  Binding to {address[0]}:{address[1]}")
        except Exception as e:
            raise Exception(f"Faild to bind to {address}: {e}")

    def listen(self, backlog = BACKLOG):

        if not self.is_server:
            raise PermissionError("Client sockets can not use listen method.")
        if not self.local_addr:
            raise Exception("Socket must be bound before listen.")
        
        self.listening = True
        self.running = True
        self.state = State.LISTEN
        self.backlog = backlog
        self.accept_queue = queue.Queue(maxsize=backlog)

        print(f"[{get_current_time()}]  Listening on {self.local_addr[0]}:{self.local_addr[1]} | Backlog size: {self.backlog}")
        
        self.listener_thread = Thread(target=self._server_listen_thread,daemon=True)
        self.listener_thread.start()

    def _server_listen_thread(self):

        while self.listening and self.running:
            try:
                data, addr = self.sock.recvfrom(BUFFER_SIZE)
                packet = Packet.from_bytes(data)

                if packet is None:
                    continue

                print(f"[{get_current_time()}]  A packet recived from {addr}")
                print(packet)

                self._handle_packet(packet, addr)

            except Exception as e:
                print(f"[{get_current_time()}]  Error in listening : {e}")    
        
    def _handle_packet(self, packet:Packet, addr):

        if packet.has_flag(PacketType.SYN) and addr not in self.connections:
            self._handle_SYN_packet(packet, addr)

        elif addr in self.connections:

            conn:Connection = self.connections[addr]
            
            if conn.state == State.SYN_RECIEVED and packet.has_flag(PacketType.ACK) and packet.ack_num == conn.seq_num+1:
                conn.state = State.ESTABLISHED
                conn.seq_num += 1
                conn.expected_seq_num = conn.ack_num  
                conn.start_management_thread() 

                with self.lock:
                    self.accept_queue.put(conn)
                
                print(f"[{get_current_time()}] Connection established with {addr}")
            
            elif conn.state == State.ESTABLISHED:
                conn.handle_packet(packet)

        else:
            print("invalid packet - sending RST")
            self._send_RST_packet(packet, addr)

    def _handle_SYN_packet(self, packet:Packet, addr):
        if self.accept_queue.qsize() >= self.backlog:
            print("accept queue is full")
            return
        
        conn = Connection(self.local_addr, addr, self.sock)
        conn.state = State.SYN_RECIEVED
        conn.ack_num = packet.seq_num + 1
        conn.expected_seq_num = packet.seq_num + 1

        SYN_ACK_packet = Packet(
            src_port=self.local_addr[1],
            dest_port=packet.src_port,
            seq_num=conn.seq_num,
            ack_num=conn.ack_num,
            flags=PacketType.SYN_ACK
        )

        conn.send_packet(SYN_ACK_packet)
        self.connections[addr] = conn
        print("recive syn send syn ack")

    def _send_RST_packet(self, packet:Packet, addr):

        RST_packet = Packet(
            src_port=self.local_addr[1],
            dest_port=packet.src_port,
            seq_num=0,
            ack_num=packet.seq_num + 1, 
            flags=PacketType.RST
        )

        data = RST_packet.to_bytes()
        self.sock.sendto(data, addr)
        print(f"send RST packet to {addr}")

    def accept(self):

        if not self.is_server:
            raise PermissionError("Client sockets can not use accept method.")
        
        while True:
            with self.lock:
                if not self.accept_queue.empty():
                    conn:Connection = self.accept_queue.get()
                    return conn, conn.remote_addr
                time.sleep(0.1)

    def connect(self, addr):

        if self.is_server:
            raise PermissionError("Server sockets can not use connect method.")
        if self.local_addr is None:
            local_port = random.randint(1024, 65535)
            self.bind(('', local_port))

        self.client_connection = Connection(self.local_addr, addr, self.sock)
        self.client_connection.state = State.SYN_SENT
        self.state = State.SYN_SENT

        SYN_packet = Packet(
            src_port=self.local_addr[1],
            dest_port=addr[1],
            seq_num=self.client_connection.seq_num,
            ack_num=0,
            flags=PacketType.SYN
        )

        self.client_connection.send_packet(SYN_packet)

        self.listening = True
        self.running = True
        self.listener_thread = Thread(target=self._client_listen_thread, daemon=True)
        self.listener_thread.start()

        start_time = time.time()

        while self.client_connection.state != State.ESTABLISHED and (time.time() - start_time < TIMEOUT):
            time.sleep(0.1)

        if self.client_connection.state != State.ESTABLISHED:
            self.listening = False
            raise Exception("connection timeout")
        
        print(f"connected to {addr}")

    def _client_listen_thread(self):
        while self.listening and self.client_connection.state != State.ESTABLISHED:
            try:
                data, addr = self.sock.recvfrom(BUFFER_SIZE)
                packet = Packet.from_bytes(data)

                if not packet:
                    continue

                print(f"[{get_current_time()}] Client received packet from {addr} :")
                print(packet)

                if packet.has_flag(PacketType.SYN_ACK) and self.client_connection.state == State.SYN_SENT and\
                    packet.ack_num == self.client_connection.seq_num+1:

                    self.client_connection.ack_num = packet.seq_num + 1
                    self.client_connection.seq_num += 1
                    self.client_connection.expected_seq_num = packet.seq_num + 1

                    ACK_packet = Packet(
                        src_port=self.local_addr[1],
                        dest_port=addr[1],
                        seq_num=self.client_connection.seq_num,
                        ack_num=self.client_connection.ack_num,
                        flags=PacketType.ACK
                    )

                    self.client_connection.send_packet(ACK_packet)
                    self.client_connection.state = State.ESTABLISHED
                    self.state = State.ESTABLISHED
                    self.client_connection.start_management_thread()

                    print(f"[{get_current_time()}]  Client connection established")

                elif self.client_connection.state == State.ESTABLISHED:

                    self.client_connection.handle_packet(packet)

            except Exception as e:
                print(f"[{get_current_time()}]  Error in client listen thread : {e}")
                break 

            

    def send(self, data):
        
        if self.client_connection and self.client_connection.state == State.ESTABLISHED:
            return self.client_connection.send(data)
        else:
            raise Exception("No established connection")

    def recieve(self, num_bytes = BUFFER_SIZE):

        if self.client_connection and self.client_connection.state == State.ESTABLISHED:
            return self.client_connection.receive(num_bytes)
        else:
            raise Exception("No established connection")

    def close(self):
        pass