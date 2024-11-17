# pylint: disable=broad-exception-caught
import socket
import sys
import json
import threading
import logging
from threading import Thread

# Configure logging
logging.basicConfig(
    filename='bootstrapper.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

nodes_neighbors = {
    "O2": ["O3"],
    "O3": ["O2", "O4", "O7"],
    "O4": ["O3", "O5"],
    "O5": ["O4"],
    "O6": ["PC1"],
    "O7": ["O3", "PC4"],
    "PC1": ["O6"],
    "PC4": ["O7"],
    "S": ["O2"]
}

nodes = {
    "O7": [("10.0.7.2", 0), ("10.0.8.1", 0)],
    "O6": [("10.0.10.2", 0), ("10.0.12.1", 0), ("10.0.13.1", 0), ("10.0.19.2", 0), ("10.0.11.2", 0)],
    "O5": [("10.0.6.2", 0), ("10.0.9.1", 0)],
    "O4": [("10.0.9.2", 0), ("10.0.17.1", 0), ("10.0.12.2", 0), ("10.0.16.1", 0), ("10.0.15.1", 0)],
    "O3": [("10.0.20.2", 0), ("10.0.14.2", 0), ("10.0.16.2", 0), ("10.0.23.1", 0), ("10.0.22.2", 0)],
    "O2": [("10.0.21.2", 0), ("10.0.22.1", 0), ("10.0.24.2", 0), ("10.0.26.1", 0)],
    "PC1": [("10.0.0.20", 0)],
    "PC4": [("10.0.1.21", 0)],
    "S": [("10.0.26.10", 0), ("10.0.25.10", 0)]
}

streams = []

nodes_connected = []


def find_ip(addr):
    for node, interfaces in nodes.items():
        for ip, _ in interfaces:
            if ip == addr:
                return node                                     
    return None

def handle_node_connection(conn, addr):
    logging.info(f"Connection received from {addr}")

    node = find_ip(addr[0])
    if node:
        nodes_connected.append(node)
        neighbors = nodes_neighbors.get(node, [])

        if not neighbors:
            logging.warning(f"No neighbors found for node {node}")
            return None

        selected_interfaces = []

        for neighbor in neighbors:
            if neighbor in nodes_connected:
                interfaces = nodes.get(neighbor, [])

                if interfaces:
                    min_interface = min(interfaces, key=lambda x: x[1])
                    selected_interfaces.append(min_interface[0])

        data_to_send = json.dumps(selected_interfaces)

        conn.send(data_to_send.encode('utf-8'))
        logging.info(f"Sent available interfaces: {selected_interfaces}")
    else:
        logging.error("Node not found for given address")
    conn.close()

def start_bootstrapper(host='0.0.0.0', port=5001):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, port))
        s.listen()
        logging.info(f"Bootstrapper started at {host}:{port}, waiting for node connections...")

        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_node_connection, args=(conn, addr)).start()

# Logic for requesting available streams from the server
def server_con(server_host, server_port):
    # Create a socket object
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Connect to the server
    client_socket.connect((server_host, server_port))
    logging.info(f"Connected to server at {server_host}:{server_port}")

    response = client_socket.recv(1024).decode()
    logging.info(f"Available streams: {response}")
    streams.extend(response.split(","))
    response = client_socket.recv(1024).decode()
   
if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Usage: python name.py <BOOTSTRAPPER_IP> <BOOTSTRAPPER_PORT> <SERVER_IP> <SERVER_PORT>")
        sys.exit(1)

    bootstrapper_host = sys.argv[1]
    try:
        bootstrapper_port = int(sys.argv[2])
    except ValueError:
        print("Port should be an integer")
        sys.exit(1)

    server_ip = sys.argv[3]
    try:
        server_port = int(sys.argv[4])
    except ValueError:
        print("Port should be an integer")
        sys.exit(1)

    # First, request streams from the server
    server_con(server_ip, server_port)

    # Then, start the bootstrapper to handle node connections
    threading.Thread(target=start_bootstrapper, args=(bootstrapper_host, bootstrapper_port), daemon=True).start()

    # Keep the main thread running
    try:
        while True:
            pass
    except KeyboardInterrupt:
        logging.info("Shutting down...")
