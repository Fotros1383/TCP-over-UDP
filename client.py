from tcp_socket import TCP_Socket
import settings

client = TCP_Socket()
try:
    client.connect((settings.SERVER_IP, settings.SERVER_PORT))
    print("Connected to server")
except Exception as e:
    print(f"clint error: {e}")

    