import socket
import sys
import json
import threading
import time

def listen_for_connections(host, port):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((host, port))
    server_socket.listen()
    print(f"Listening for connections on {host}:{port}")

    while True:
        client_socket, addr = server_socket.accept()
        print(f"Connection accepted from {addr}")
        # Aqui você pode adicionar lógica para manipular a conexão recebida

def connect_to_neighbors(neighbors):
    for neighbor in neighbors:
        try:
            neighbor_ip, neighbor_port = neighbor  
            print(f"Attempting to connect to {neighbor_ip}:{neighbor_port}")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((neighbor_ip, int(neighbor_port)))
            print(f"Connected to {neighbor_ip}:{neighbor_port}")
            # Aqui você pode adicionar lógica para manipular a conexão estabelecida
        except Exception as e:
            print(f"Failed to connect to {neighbor_ip}:{neighbor_port}: {str(e)}")


def connect_to_pc(pc_address, pc_port):
    # Cria uma conexão UDP para o PC
    try:
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.bind((pc_address, pc_port))  # Binding to the address with the specific port
        print(f"UDP socket bound to {pc_address}:{pc_port}")
        # Aqui, você pode implementar lógica para enviar dados ou manter o socket ouvindo
    except Exception as e:
        print(f"Failed to open UDP socket to PC at {pc_address}:{pc_port}: {e}")


def connect_to_bootstrapper(host, port):
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    my_tcp = None
    my_port = None

    try:
        client_socket.connect((host, port))
        print(f"Connected to bootstrapper at {host}:{port}")

        data_encoded = client_socket.recv(1024).decode()
        if data_encoded:
            data_json = json.loads(data_encoded)
            print(f"Received data: {data_json}")

            message_code = data_json['code']

            if message_code == 0:
                data = data_json['data']

                address, port_received = data
                my_tcp = address
                my_port = port_received

                print(f"Address received and stored: {my_tcp}")
                print(f"Port received and stored: {my_port}")

                # Iniciar thread para ouvir conexões
                threading.Thread(target=listen_for_connections, args=(my_tcp, my_port)).start()

                pc = data_json['pc']
                if pc:
                    pc_ip = my_tcp
                    pc_port = my_port + 1
                    threading.Thread(target=connect_to_pc, args=(pc_ip, pc_port)).start

            elif message_code == 1:
                data = data_json['data']

                neighbors_list = data
                print(f"Neighbor interfaces received: {neighbors_list}")

                # Iniciar thread para conectar-se a vizinhos
                threading.Thread(target=connect_to_neighbors, args=(neighbors_list,)).start()

            elif message_code == 2:
                data = data_json['data']

                neighbors_list, address_port = data
                address, port_received = address_port

                my_tcp = address
                my_port = port_received

                print(f"Address and port received: {my_tcp}, {my_port}")
                print(f"Neighbor interfaces received and stored: {neighbors_list}")

                threading.Thread(target=listen_for_connections, args=(my_tcp, my_port)).start()
                threading.Thread(target=connect_to_neighbors, args=(neighbors_list,)).start()

                pc = data_json['pc']
                if pc:
                    pc_ip = my_tcp
                    pc_port = my_port + 1
                    threading.Thread(target=connect_to_pc, args=(pc_ip, pc_port)).start

            elif message_code == 3:
                pass
        else:
            print("No data received from the bootstrapper")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        pass
        
if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python name.py <BOOTSTRAPPER_IP> <BOOTSTRAPPER_PORT>")
        sys.exit(1)

    bootstrapper_host = sys.argv[1]
    try:
        bootstrapper_port = int(sys.argv[2])
    except ValueError:
        print("Port should be an integer")
        sys.exit(1)

    # Connect to the bootstrapper in a separate thread to handle communication
    connection_thread = threading.Thread(target=connect_to_bootstrapper, args=(bootstrapper_host, bootstrapper_port))
    connection_thread.start()

    # Keep the main thread running
    try:
        while True:
            pass
    except KeyboardInterrupt:
        print("Shutting down...")
        connection_thread.join()  # Ensure the connection thread has cleaned up properly



