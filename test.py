from connection import Connection
from settings import SERVER_IP

def receive(connection:Connection):

    while True:
        try:
            data = connection.receive().decode()
            if not data:
                connection.close()
                print("\nConnection closed by client.")
                break
            print(f"\n[Recieved]: {data}")
        except Exception as e:
            print(e)

def send(connection:Connection):

    while True:
        try:
            message = input()
            connection.send(message)
        except:
            break
        
def default_server():
    pass