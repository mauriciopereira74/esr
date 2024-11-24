import socket
import sys
import json
import threading
import time


def handle_connection(host, port, listen=False):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            # No UDP, o connect() define o endereço de destino para chamadas de send() e o endereço de origem esperado para recv()
            sock.connect((host, int(port)))
            print(f"UDP socket prepared for {host}:{port}")

            if listen:
                # Se listen for True, mantenha o socket ouvindo por dados
                print(f"Listening for data from {host}:{port}")
                while True:
                    data, _ = sock.recvfrom(1024)
                    if data:
                        print(f"Received data from {host}:{port}: {data.decode()}")
                    else:
                        print("Connection closed by remote host.")
                        break
            else:
                # Se não for para ouvir, apenas envie uma mensagem inicial
                initial_message = "Hello from UDP client"
                sock.send(initial_message.encode('utf-8'))
                print(f"Sent initial message to {host}:{port} via UDP")
    except Exception as e:
        print(f"Failed to communicate over UDP with {host}:{port}: {e}")

def handle_message(data):
    # Processa as mensagens recebidas do bootstrapper
    message_code = data['code']
    if message_code == 0:
        # Conexão direta disponível com vizinhos
        for neighbor in data['data']:
            threading.Thread(target=handle_connection, args=(neighbor[0], neighbor[1])).start()
    elif message_code == 1:
        # Vizinhos disponíveis, mas ainda não conectados, manter ouvindo
        for neighbor in data['data']:
            print("Neighbor available but not yet connected, setting up listening UDP socket.")
            threading.Thread(target=handle_connection, args=(neighbor[0], neighbor[1], True)).start()
    elif message_code == 2:
        # Vizinhos conectados sem interfaces válidas
        print("Neighbors connected but with invalid interfaces.")

def connect_to_bootstrapper(host, port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.connect((host, port))
            print(f"Connected to bootstrapper at {host}:{port}")

            while True:
                # Recebe dados do bootstrapper
                data_encoded = client_socket.recv(1024)
                if data_encoded:
                    data = json.loads(data_encoded)
                    print(f"Received data: {data}")
                    handle_message(data)
                else:
                    print("No data received, ending connection.")
                    break
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python client.py <BOOTSTRAPPER_IP> <BOOTSTRAPPER_PORT>")
        sys.exit(1)

    bootstrapper_host = sys.argv[1]
    bootstrapper_port = int(sys.argv[2])

    # Connect to the bootstrapper
    threading.Thread(target=connect_to_bootstrapper, args=(bootstrapper_host, bootstrapper_port)).start()