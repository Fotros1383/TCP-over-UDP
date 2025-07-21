import threading, time

from tcp_socket import TCP_Socket
from settings import SERVER_IP, SERVER_PORT


def recieve(sock:TCP_Socket):
    try:
        while True:
            data = sock.recieve().decode('utf-8')
            print(data)
    except:
        return
    
client_socket = TCP_Socket()
client_socket.connect((SERVER_IP,SERVER_PORT))

try:
    recieve_thread = threading.Thread(target=recieve, args=(client_socket,))
    recieve_thread.start()

    for i in range(1,5):
        client_socket.send(f"message{i} from client")
        time.sleep(5)

    recieve_thread.join(timeout=100)
    client_socket.close()
except:
    client_socket.force_close()








    