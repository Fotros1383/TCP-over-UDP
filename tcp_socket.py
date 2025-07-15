import socket, queue, time, random
from threading import Thread, Lock, Event
from packet import Packet
from connection import Connection
from settings import log_format, PacketType, State, BACKLOG, BUFFER_SIZE, TIMEOUT


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

        socket_type = "Server" if is_server else "Client"
        print(log_format( f"TCP Socket created - Type: {socket_type}"))
    
    def bind(self, address):

        try:

            self.sock.bind(address)
            print(log_format(f"Successfully bound to {address[0]}:{address[1]}"))

            self.local_addr = address
            print(log_format(f"Local address set to: {self.local_addr}"))
        
        except Exception as e:

            print(log_format(f"ERROR: Failed to bind to {address}: {e}"))
            raise Exception(f"Faild to bind to {address}: {e}")

    def listen(self, backlog = BACKLOG):

        if not self.is_server:

            print(log_format("ERROR: Client sockets cannot use listen method"))
            raise PermissionError("Client sockets can not use listen method.")
        
        if not self.local_addr:
            print(log_format("ERROR: Socket must be bound before listen"))
            raise Exception("Socket must be bound before listen.")

        self.listening = True
        self.running = True
        self.state = State.LISTEN
        self.backlog = backlog
        self.accept_queue = queue.Queue(maxsize=backlog)
        
        self.listener_thread = Thread(target=self._server_listen_thread,daemon=True)
        self.listener_thread.start()

        print(log_format(f"Server listening on {self.local_addr[0]}:{self.local_addr[1]} | Backlog size: {self.backlog} | state change to: {self.state.name}"))

    def _server_listen_thread(self):

        while self.listening and self.running:

            try:

                data, addr = self.sock.recvfrom(BUFFER_SIZE)
                print(log_format(f"Packet received from {addr}"))

                packet = Packet.from_bytes(data)

                if packet is None:
                    print(log_format(f" WARNING: Failed to parse packet from {addr}"))
                    continue

                print(log_format(f"Packet successfully parsed from {addr} \n {packet}"))

                self._handle_packet(packet, addr)

            except Exception as e:
                print(log_format(f"ERROR in server listener thread: {e}"))  

        print(log_format("Server listener thread stopping..."))
        
    def _handle_packet(self, packet:Packet, addr):

        if packet.has_flag(PacketType.SYN) and addr not in self.connections:

            print(log_format(f"Processing SYN packet from new client {addr}"))
            self._handle_SYN_packet(packet, addr)

        elif addr in self.connections:

            conn:Connection = self.connections[addr]
            print(log_format(f"Processing packet from existing connection {addr} | Connection state: {conn.state.name}"))
                  
            if conn.state == State.SYN_RECIEVED and packet.has_flag(PacketType.ACK) and packet.ack_num == conn.seq_num+1:
                conn.state = State.ESTABLISHED
                conn.seq_num += 1
                conn.expected_seq_num = conn.ack_num  
                conn.start_management_thread() 

                with self.lock:
                    self.accept_queue.put(conn)
                
                print(log_format(f"Connection established with {addr}"))
            
            elif conn.state == State.ESTABLISHED:
                conn.handle_packet(packet)

        else:
            print(log_format(f"invalid packet - sending RST to {addr}"))
            self._send_RST_packet(packet, addr)

    def _handle_SYN_packet(self, packet:Packet, addr):

        if self.accept_queue.qsize() >= self.backlog:
            print(log_format(f"WARNING: Accept queue is full, dropping SYN from {addr}"))
            return
        
        print(log_format(f"Creating new connection for {addr}"))

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

        print(log_format(f"Sending SYN-ACK packet to {addr}"))
        conn.send_packet(SYN_ACK_packet)

        self.connections[addr] = conn

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
        print(log_format(f"RST packet sent successfully to {addr}"))

    def accept(self):

        if not self.is_server:
            print(log_format("ERROR: Client sockets cannot use accept method"))
            raise PermissionError("Client sockets can not use accept method.")
        
        while True:
            with self.lock:
                if not self.accept_queue.empty():
                    conn:Connection = self.accept_queue.get()
                    print(log_format(f"Connection accepted from {conn.remote_addr}"))
                    return conn, conn.remote_addr
            time.sleep(0.1)

    def connect(self, addr):

        if self.is_server:
            print(log_format("ERROR: Server sockets cannot use connect method"))
            raise PermissionError("Server sockets can not use connect method.")
        
        if self.local_addr is None:
            local_port = random.randint(1024, 65535)
            print(log_format(f"No local address set, binding to random port {local_port}"))
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

        print(log_format(f"Sending SYN packet to {addr}"))
        self.client_connection.send_packet(SYN_packet)

        self.listening = True
        self.running = True
        self.listener_thread = Thread(target=self._client_listen_thread, daemon=True)
        self.listener_thread.start()

        start_time = time.time()

        while self.client_connection.state != State.ESTABLISHED and (time.time() - start_time < TIMEOUT):
            time.sleep(0.1)

        if self.client_connection.state != State.ESTABLISHED:
            print(log_format(f"ERROR: Connection timeout after {TIMEOUT} seconds"))
            self.listening = False
            raise Exception("Connection timeout")
        
        print(log_format(f"Successfully connected to {addr}"))

    def _client_listen_thread(self):

        while self.listening and self.client_connection.state != State.ESTABLISHED:
            try:
                data, addr = self.sock.recvfrom(BUFFER_SIZE)
                print(log_format(f"Packet received from {addr}"))
                packet = Packet.from_bytes(data)

                if not packet:
                    print(log_format("WARNING: Failed to parse packet"))
                    continue

                print(log_format(f"Packet received from {addr} \n{packet}"))


                if packet.has_flag(PacketType.SYN_ACK) and self.client_connection.state == State.SYN_SENT and\
                    packet.ack_num == self.client_connection.seq_num+1:

                    print(log_format("Valid SYN-ACK received"))
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

                    print(log_format("Sending ACK packet to complete handshake"))

                    self.client_connection.send_packet(ACK_packet)
                    self.client_connection.state = State.ESTABLISHED
                    self.state = State.ESTABLISHED
                    print(log_format("Connection established successfully"))

                    self.client_connection.start_management_thread()

                elif self.client_connection.state == State.ESTABLISHED:

                    self.client_connection.handle_packet(packet)

            except Exception as e:
                print(log_format(f"ERROR in client listener thread: {e}"))
                break 
        print(log_format("Client listener thread stopping..."))

    def send(self, data):
        
        if self.client_connection and self.client_connection.state == State.ESTABLISHED:
            print(log_format("Forwarding data to client connection"))
            return self.client_connection.send(data)
        else:
            print(log_format("ERROR: No established connection available"))
            raise Exception("No established connection")

    def recieve(self, num_bytes = BUFFER_SIZE):

        if self.client_connection and self.client_connection.state == State.ESTABLISHED:
            print(log_format("Forwarding receive request to client connection"))
            return self.client_connection.receive(num_bytes)
        else:
            print(log_format("ERROR: No established connection available"))
            raise Exception("No established connection")

    def close(self):

        if self.is_server:

            print(log_format(f" Closing server socket"))
            
            self.listening = False
            self.running = False
            self.state = State.CLOSED
            
            if self.accept_queue:
                print(log_format(f"Closing connections in accept queue..."))
                while not self.accept_queue.empty():
                    try:
                        conn:Connection = self.accept_queue.get_nowait()
                        conn.close()
                    except:
                        break

            for addr, conn in self.connections.items():
                print(log_format(f"Closing connection with {addr}"))
                conn.close()

            self.connections.clear()
            print(log_format("All connections closed"))

            # if self.sock:
            #     self.sock.close()
            #     print(f"[{get_current_time()}] Server socket closed")

            if self.listener_thread and self.listener_thread.is_alive():

                print(log_format("Waiting for listener thread to stop..."))
                self.listener_thread.join(timeout=1.0)

            print(log_format(f"Server socket closed successfully"))

        else:

            print(log_format(f"Closing client socket..."))
            
            self.listening = False
            self.running = False
            self.state = State.CLOSED

            if self.client_connection and self.client_connection.state == State.ESTABLISHED:
                print(log_format("Closing established client connection"))
                self.client_connection.close()    
   
            if self.listener_thread and self.listener_thread.is_alive():
                print(log_format("Waiting for listener thread to stop..."))
                self.listener_thread.join(timeout=1.0)
                
            # if self.sock:
            #     self.sock.close()

            print(log_format(f"Client socket closed successfully"))
