
from tcp_socket import TCP_Socket
from settings import SERVER_IP, SERVER_PORT


#--------------- 1th scenario -----------------
 
server = TCP_Socket(is_server=True)
try:
    server.bind((SERVER_IP, SERVER_PORT))
    server.listen(5)

    conn, addr = server.accept()
except:
    pass



