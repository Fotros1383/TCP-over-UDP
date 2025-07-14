from tcp_socket import TCP_Socket
import settings 

server = TCP_Socket(is_server=True)
server.bind((settings.SERVER_IP,settings.SERVER_PORT))
server.listen()
print("Server listening on localhost:9000")
try:
    while True:
        connection, addr = server.accept()
        print(f"New connection from {addr}")
                
except KeyboardInterrupt:
    print("Server shutting down...")



