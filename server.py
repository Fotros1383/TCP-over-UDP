import threading, time
from tcp_socket import TCP_Socket
from connection import Connection
from settings import SERVER_IP, SERVER_PORT, State

def recieve(conn:Connection):
    try:
        while True:
            data = conn.receive().decode('utf-8')
            print(data)
    except:
        return

server_socket = TCP_Socket(is_server=True)
server_socket.bind((SERVER_IP, SERVER_PORT))
server_socket.listen()

try:

    conn, addr = server_socket.accept()
    recieve_thread = threading.Thread(target=recieve, args=(conn,))
    recieve_thread.start()

    # for i in range(1,5):
    #     conn.send(f"message{i} from client")
    #     time.sleep(5)

    recieve_thread.join(timeout=100)
    conn.close()
except:
    conn.force_close()










