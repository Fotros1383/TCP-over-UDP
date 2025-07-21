from settings import State, PacketType, log_format, get_current_time, WINDOW_SIZE, MSS, RETRANSMIT_TIMEOUT,\
    MAX_DUPLICATE_ACK_TO_RETRANSMITION, BUFFER_SIZE, TIMEOUT, MSL

from packet import Packet
from threading import Thread, Lock, Event
import random, socket, time
from collections import deque


class Connection:

    def __init__(self, local_addr, remote_addr, socket:socket.socket):
        
        self.local_addr = local_addr
        self.remote_addr = remote_addr
        self.socket = socket

        self.state = State.CLOSED
        self.seq_num = random.randint(0, 2**32 - 1)  
        self.ack_num = 0
        self.next_seq_num = self.seq_num

        self.window_size = WINDOW_SIZE
        self.send_base = self.seq_num


        self.send_buffer = deque()
        self.receive_buffer = {}
        self.app_receive_buffer = deque()

        self.unacked_packets = {}

        self.send_lock = Lock()
        self.receive_lock = Lock()

        self.management_thread = None
        self.running = False
        self.in_accept_queue = False

        self.duplicate_ack_count = 0
        self.last_ack_received = 0

        # self.send_space_available = Event()
        # self.data_available = Event()

        # self.send_space_available.set()

        print(f"[{get_current_time()}]  Connection created : {self.local_addr} <-> {self.remote_addr}")
   
    def send_packet(self, packet:Packet):
        
        try:
            packet.src_port = self.local_addr[1]
            packet.dest_port = self.remote_addr[1]
            data = packet.to_bytes()

            self.socket.sendto(data, self.remote_addr)

            if self.next_seq_num == packet.seq_num:
                if packet.has_flag(PacketType.DATA):
                    self.next_seq_num +=  packet.len_data
                elif packet.has_flag(PacketType.SYN) or packet.has_flag(PacketType.FIN):
                    self.next_seq_num += 1

            print(log_format(f"Packet sent successfully to {self.remote_addr}\n{packet}"))

        except Exception as e:
            print(log_format(f"ERROR sending packet to {self.remote_addr} : {e}"))

    def start_management_thread(self):

        if not self.running:
            self.running = True
            self.management_thread = Thread(target=self._manager, daemon=True)
            self.management_thread.start()
            print(log_format(f"Management thread started for connection {self.local_addr} <-> {self.remote_addr}"))

    def _manager(self):

        while self.running and self.state != State.CLOSED:
            try:
                self._handle_send_buffer()
                self._handle_retransmition()
                time.sleep(0.1)
                
            except Exception as e:
                print(log_format(f"ERROR in management thread: {e}"))
                break
        print(log_format(f"Management thread stopping for {self.local_addr} <-> {self.remote_addr}"))

    def _handle_retransmition(self):

        current_time = time.time()
        packets_to_retransmit = []
        
        with self.send_lock:
            for seq_num, (packet, timestamp) in self.unacked_packets.items():
                if current_time - timestamp > RETRANSMIT_TIMEOUT:
                    packets_to_retransmit.append((seq_num, packet))
            
            for seq_num, packet in packets_to_retransmit:
                print(f"[{get_current_time()}] Retransmitting packet \n {packet}")
                self.send_packet(packet)
                self.unacked_packets[seq_num] = (packet, current_time)

    def _handle_send_buffer(self):

        with self.send_lock:

            while self.send_buffer and (self.next_seq_num - self.send_base) < self.window_size:
                
                print(log_format(f"Window check: next_seq={self.next_seq_num}, base={self.send_base}, window={self.window_size}"))

                data = self.send_buffer.popleft()
                
                packet = Packet(
                    src_port=self.local_addr[1],
                    dest_port=self.remote_addr[1],
                    seq_num=self.next_seq_num,
                    ack_num=self.ack_num,
                    flags=PacketType.DATA,
                    data=data
                )
                
                self.send_packet(packet)
                self.unacked_packets[packet.seq_num] = (packet, time.time())
   
    def handle_packet(self, packet:Packet):
        
        if packet.has_flag(PacketType.DATA):
            self._handle_DATA_packet(packet)

        elif packet.has_flag(PacketType.ACK):
            self._handle_ACK_packet(packet)

        elif packet.has_flag(PacketType.RST):
            self._handle_RST_packet(packet)

        elif packet.has_flag(PacketType.FIN):
            self._handle_FIN_packet(packet)

    def _handle_DATA_packet(self, packet:Packet):

        with self.receive_lock:

            expected_seq_num = self.ack_num
            
            if packet.seq_num == expected_seq_num:

                self.app_receive_buffer.append(packet.data)
                self.ack_num += len(packet.data)
                
                self._handle_buffered_packets()
                self._send_ACK(self.ack_num)
                
            elif packet.seq_num > expected_seq_num:

                if packet.seq_num not in self.receive_buffer:
                    self.receive_buffer[packet.seq_num] = packet.data
                
                self._send_ACK(self.ack_num)
                
            else:
                self._send_ACK(self.ack_num)

    def _handle_buffered_packets(self):

        while self.ack_num in self.receive_buffer:

            data = self.receive_buffer.pop(self.ack_num)
            self.app_receive_buffer.append(data)
            self.ack_num += len(data)

    def _send_ACK(self, ack_num):

        ACK_packet = Packet(
            src_port=self.local_addr[1],
            dest_port=self.remote_addr[1],
            seq_num=self.next_seq_num,
            ack_num=ack_num,
            flags=PacketType.ACK
        )
        self.send_packet(ACK_packet)
    
    def _handle_ACK_packet(self, packet:Packet):

        with self.send_lock:

            ack_num = packet.ack_num

            if self.state == State.FIN_WAIT_1:
                if ack_num == self.next_seq_num:
                    self.state = State.FIN_WAIT_2
                    print(f"[{get_current_time()}] ACK for FIN received, state: FIN_WAIT_2")
        
            elif self.state == State.LAST_ACK:
                if ack_num == self.next_seq_num:
                    self.state = State.CLOSED
                    self.running = False
                    print(f"[{get_current_time()}] Final ACK received, connection closed")

            elif self.state == State.CLOSING:
                if ack_num == self.next_seq_num:
                    self.state = State.TIME_WAIT
                    print(f"[{get_current_time()}] ACK in CLOSING state, entering TIME_WAIT")
                
                    def time_wait_timer():
                        time.sleep(2 * MSL)
                        if self.state == State.TIME_WAIT:  
                            self.state = State.CLOSED
                            self.running = False
                
                    Thread(target=time_wait_timer, daemon=True).start()
            
            if ack_num <= self.send_base: 

                if ack_num == self.last_ack_received:
                    self.duplicate_ack_count += 1
                else:
                    self.duplicate_ack_count = 1
                    self.last_ack_received = ack_num
                
                if self.duplicate_ack_count >= MAX_DUPLICATE_ACK_TO_RETRANSMITION:
                    self._fast_retransmit(ack_num)
                    self.duplicate_ack_count = 0
            else:

                must_remove = []
                for seq_num in self.unacked_packets:
                    if seq_num < ack_num:
                        must_remove.append(seq_num)
                
                for seq_num in must_remove:
                    del self.unacked_packets[seq_num]


                self.send_base = ack_num


                self.duplicate_ack_count = 0
                self.last_ack_received = ack_num
                print(f"[{get_current_time()}] ACK received: {ack_num}, window advanced")
    
    def _fast_retransmit(self, ack_num):

        for seq_num in sorted(self.unacked_packets.keys()):
            if seq_num >= ack_num:
                packet = self.unacked_packets[seq_num][0] 
                print(log_format(f"Fast retransmit for packet:\n{packet}"))
                self.send_packet(packet)
                self.unacked_packets[seq_num] = (packet, time.time())

                break

    def _handle_RST_packet(self, packet:Packet):
        
        print(f"[{get_current_time()}]  RST received, closing connection")
        self.state = State.CLOSED
        self.running = False

    def _handle_FIN_packet(self, packet: Packet):
        
        print(f"[{get_current_time()}] FIN received from {self.remote_addr} in state {self.state.name}")
        
        expected_fin_seq = self.ack_num

        if packet.seq_num == expected_fin_seq:
            self.ack_num = packet.seq_num + 1
            self._send_ACK(self.ack_num)
        else:
            print(log_format(f"Unexpected FIN seq: {packet.seq_num}, expected: {expected_fin_seq}"))
            return
        
        if self.state == State.ESTABLISHED:

            self.state = State.CLOSE_WAIT
            print(log_format(f"ACK sent, state changed to CLOSE_WAIT"))
            
            FIN_packet = Packet(
                src_port=self.local_addr[1],
                dest_port=self.remote_addr[1],
                seq_num=self.next_seq_num,
                ack_num=self.ack_num,
                flags=PacketType.FIN
            )
            
            self.send_packet(FIN_packet)
            self.unacked_packets[self.next_seq_num] = (FIN_packet, time.time())
            self.state = State.LAST_ACK
            print(f"[{get_current_time()}] FIN sent, state changed to LAST_ACK")
            
        elif self.state == State.FIN_WAIT_1:
            
            self.state = State.CLOSING

            print(f"[{get_current_time()}] Simultaneous close detected, state changed to CLOSING")
            
        elif self.state == State.FIN_WAIT_2:
            
            self.state = State.TIME_WAIT
            print(f"[{get_current_time()}] Normal termination, state changed to TIME_WAIT")
            

            def time_wait_timer():
                time.sleep(2*MSL)  
                if self.state == State.TIME_WAIT:  
                    self.state = State.CLOSED
                    self.running = False
                    print(f"[{get_current_time()}] TIME_WAIT expired, connection closed")
            
            Thread(target=time_wait_timer, daemon=True).start()
        
        else:
            print(f"[{get_current_time()}] FIN received in unexpected state: {self.state.name}")

    def send(self, data):

        if self.state != State.ESTABLISHED:
            raise Exception("Connection not established")
        
        if isinstance(data, str):
            data = data.encode('utf-8')
        
        chunks = []
        for i in range(0, len(data), MSS):
            chunk = data[i:i + MSS]
            chunks.append(chunk)
        
        with self.send_lock:
            for chunk in chunks:
                while len(self.send_buffer) >= self.window_size:
                    self.send_lock.release()
                    time.sleep(0.1)
                    self.send_lock.acquire()

                    if not self.running or self.state != State.ESTABLISHED:
                        raise Exception("Connection closed or not established")
                
                self.send_buffer.append(chunk)
        
        print(f"[{get_current_time()}] Added {len(data)} bytes to send buffer")

    def receive(self, num_bytes=BUFFER_SIZE):
        
        if self.state != State.ESTABLISHED:
            raise Exception("Connection not established")
        
        if not self.running:
            self.start_management_thread()
        
        received_data = b""
        bytes_needed = num_bytes
        
        while bytes_needed > 0 and self.running:
    
            # if not self.app_receive_buffer:           #
            #     self.data_available.wait(timeout=1.0)
            #     if not self.app_receive_buffer:
            #         continue

            while not self.app_receive_buffer and self.running:
                time.sleep(0.1)

            if not self.running:
                break
            
            with self.receive_lock:
                if self.app_receive_buffer:
                    data_chunk = self.app_receive_buffer.popleft()
                    
                    if isinstance(data_chunk, str):
                        data_chunk = data_chunk.encode('utf-8')
                    
                    if len(data_chunk) <= bytes_needed:
                        received_data += data_chunk
                        bytes_needed -= len(data_chunk)
                    else:
                        received_data += data_chunk[:bytes_needed]
                        self.app_receive_buffer.appendleft(data_chunk[bytes_needed:])
                        bytes_needed = 0
                
                # if not self.app_receive_buffer:
                #     self.data_available.clear()
        
        return received_data 

    def close(self):
    
        if self.state == State.CLOSED:
            print(f"[{get_current_time()}] Connection already closed")
            return
        
        print(f"[{get_current_time()}] Initiating connection termination from state: {self.state.name}")
        
        try:
            if self.state == State.ESTABLISHED:
                print(f"[{get_current_time()}] Sending FIN packet")
                
                FIN_packet = Packet(
                    src_port=self.local_addr[1],
                    dest_port=self.remote_addr[1],
                    seq_num=self.next_seq_num,
                    ack_num=self.ack_num,
                    flags=PacketType.FIN
                )
                
                self.send_packet(FIN_packet)
                self.unacked_packets[self.next_seq_num] = (FIN_packet, time.time())
                self.state = State.FIN_WAIT_1
                print(f"[{get_current_time()}] State changed to FIN_WAIT_1")
                
                timeout_start = time.time()
                
                while (self.state not in [State.CLOSED, State.TIME_WAIT] and (time.time() - timeout_start) < TIMEOUT):
                    time.sleep(0.1)
                
                if self.state == State.TIME_WAIT:
                    print(f"[{get_current_time()}] Entering TIME_WAIT, waiting {MSL*2} seconds...")
                    timeout_start = time.time()
                    while (self.state == State.TIME_WAIT and (time.time() - timeout_start) < 2*MSL):
                        time.sleep(0.1)

                elif self.state != State.CLOSED:
                    print(f"[{get_current_time()}] Termination timeout after {TIMEOUT}s, forcing close")
            

            elif self.state == State.CLOSE_WAIT:

                print(f"[{get_current_time()}] In CLOSE_WAIT, sending FIN")
                
                FIN_packet = Packet(
                    src_port=self.local_addr[1],
                    dest_port=self.remote_addr[1],
                    seq_num=self.next_seq_num,
                    ack_num=self.ack_num,
                    flags=PacketType.FIN
                )
                
                self.send_packet(FIN_packet)
                self.unacked_packets[self.next_seq_num] = (FIN_packet, time.time())
                self.state = State.LAST_ACK
                
                timeout_start = time.time()
                while self.state != State.CLOSED and (time.time() - timeout_start) < TIMEOUT:
                    time.sleep(0.1)

            elif self.state in [State.LAST_ACK, State.FIN_WAIT_1, State.FIN_WAIT_2, State.CLOSING]:
                print(f"[{get_current_time()}] Connection in {self.state.name}, waiting for completion...")
                
                timeout_start = time.time()
                while self.state not in [State.CLOSED, State.TIME_WAIT] and (time.time() - timeout_start) < TIMEOUT:
                    time.sleep(0.1)
                
                if self.state != State.CLOSED:
                    print(f"[{get_current_time()}] Force closing from {self.state.name}")
        
        except Exception as e:
            print(f"[{get_current_time()}] Error during graceful close: {e}")

        self.force_close()
        
    def force_close(self):
        
        self.state = State.CLOSED
        self.running = False        
        
        if self.management_thread and self.management_thread.is_alive():
            try:
                self.management_thread.join(timeout=1.0)
                if self.management_thread.is_alive():
                    print(f"[{get_current_time()}] WARNING: Management thread did not stop gracefully")
            except Exception as e:
                print(f"[{get_current_time()}] Error joining management thread: {e}")
        
        try:
            with self.send_lock:
                self.send_buffer.clear()
                self.unacked_packets.clear()
            
            with self.receive_lock:
                self.receive_buffer.clear()
                self.app_receive_buffer.clear()
        except Exception as e:
            print(f"[{get_current_time()}] Error clearing buffers: {e}")
        
        self.management_thread = None
        
        print(f"[{get_current_time()}] Connection closed: {self.local_addr} <-> {self.remote_addr}")