# pylint: disable=broad-exception-caught
import socket
import sys
import json
import threading
from threading import Thread
import time

global_lock = threading.Lock()
condition = threading.Condition(global_lock)
path_check_lock = threading.Lock()
path_check_condition = threading.Condition(path_check_lock)
tree_lock = threading.Lock()
tree_condition = threading.Condition(tree_lock)

nodes_neighbors = {
    "O2": ["O3","S"],
    "O3": ["O2", "O4", "O7"],
    "O4": ["O3", "O5", "O6"],
    "O5": ["O4"],
    "O6": ["PC1","O4"],
    "O7": ["O3", "PC4"],
    "PC1": ["O6"],
    "PC4": ["O7"],
    "S": ["O2"]
}

nodes = {
    "O7": [("10.0.21.2", 0), ("10.0.13.1", 0)],
    "O6": [("10.0.22.2", 0), ("10.0.12.1", 0), ("10.0.11.2", 0), ("10.0.14.2", 0), ("10.0.23.1", 0)],
    "O5": [("10.0.16.1", 0), ("10.0.15.2", 0)],
    "O4": [("10.0.15.1", 0), ("10.0.12.2", 0), ("10.0.10.2", 0), ("10.0.24.1", 0), ("10.0.6.1", 0)],
    "O3": [("10.0.24.2", 0), ("10.0.9.1", 0), ("10.0.8.2", 0), ("10.0.4.2", 0), ("10.0.3.1", 0)],
    "O2": [("10.0.7.1", 0), ("10.0.4.1", 0), ("10.0.1.1", 5001), ("10.0.2.2", 0)],
    "PC1": [("10.0.25.20", 0)],
    "PC4": [("10.0.26.21", 0)],
    "S": [("10.0.1.10", 5000), ("10.0.0.10", 0)]
}

streams = []
nodes_connected = []

def bfs_path_exists(start_node, end_node, graph):
    visited = set()
    queue = [start_node]
    print(f"Iniciando BFS de {start_node} para {end_node}")

    while queue:
        node = queue.pop(0)
        if node == end_node:
            print("Caminho encontrado!")
            return True
        
        visited.add(node)
        # Extend the queue only with connected neighbors
        queue.extend([n for n in graph.get(node, []) if n not in visited and n in nodes_connected])

    return False


def check_stream_path():
    pcs = [node for node in nodes if node.startswith("PC")]  # Identifica todos os PCs
    paths_available = {pc: False for pc in pcs}  # Inicia um dicionário para controlar os caminhos disponíveis

    while True:
        with path_check_condition:
            path_check_condition.wait()  # Espera notificação de nova conexão

        paths_found_this_round = []
        # Verifica se existe caminho para o servidor "S" de cada PC
        for pc in pcs:
            if not paths_available[pc] and bfs_path_exists(pc, 'S', nodes_neighbors):
                paths_available[pc] = True  # Marca o PC como tendo um caminho disponível
                paths_found_this_round.append(pc)

        # Verifica se todos os PCs têm caminhos disponíveis
        if all(paths_available.values()):
            print("Caminhos disponíveis para stream de todos os PCs para o servidor S.")
            with tree_lock:
                tree_condition.notify_all()
            break  # Ou continue, dependendo se você quer parar após a primeira verificação bem-sucedida ou não
        elif paths_found_this_round:
            # Mostra quais PCs tiveram caminhos encontrados nesta verificação
            available_paths = ', '.join(paths_found_this_round)
            print(f"Caminhos disponíveis para stream dos seguintes PCs para o servidor S: {available_paths}")
        else:
            print(f"Não foram encontrados caminhos")


def neighbours_connections(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.bind((host, port))
        server_socket.listen()
        print(f"Listening for connections on {host}:{port}")

        try:
            while True:
                neighbour_socket, addr = server_socket.accept()
                print(f"Accepted connection from {addr}")
                threading.Thread(target=handle_neighbour_connection, args=(neighbour_socket,)).start()
        except Exception as e:
            print(f"Error accepting connections: {e}")


def handle_neighbour_connection(neighbour_socket):
    try:
        with neighbour_socket:
            print("Waiting for the tree to activate this connection...")
            with tree_lock:
                tree_condition.wait()  # Espera até ser notificado para prosseguir

            # Após ser notificado:
            while True:
                data = neighbour_socket.recv(1024)
                if not data:
                    break  # Conexão foi fechada pelo cliente
                print(f"Received data: {data.decode()} from neighbour")
                # Processa os dados recebidos aqui
                
                # Resposta opcional de volta ao vizinho
                response = "ACK"
                neighbour_socket.send(response.encode())
    except Exception as e:
        print(f"Error handling neighbour connection: {e}")
    finally:
        print("Neighbour connection closed.")

def find_ip(addr):
    for node, interfaces in nodes.items():
        for ip, _ in interfaces:
            if ip == addr:
                return node                                     
    return None

def update_port(node_name):
    if node_name[0].isalpha() and node_name[1:].isdigit():
        if node_name[1:]==2:
            return 5001
        else:
            return 5000 + int(node_name[1:]) * 10
    return None

def add_node_to_connected(node):
    with global_lock:
        with path_check_lock:
            if node not in nodes_connected:
                nodes_connected.append(node)
                path_check_condition.notify()  

def handle_node_connection(conn, addr):
    print(f"Conexão recebida de {addr}")

    node = find_ip(addr[0])
    print(f"Nó identificado: {node}")
    try:
        if node.startswith("O"):
            if node not in nodes_connected:
                add_node_to_connected(node)
                port = update_port(node)  # Atualiza a porta baseada no nome do nó

                # Atualizar as interfaces do próprio nó com a nova porta
                current_interfaces = nodes.get(node, [])
                nodes[node] = [(ip, port if ip == addr[0] else old_port) for ip, old_port in current_interfaces]

                neighbors = nodes_neighbors.get(node, [])
                selected_interfaces = []
                count = 0
                pc = 0

                for neighbor in neighbors:
                    if neighbor in nodes_connected:
                        if neighbor.startswith("PC"):
                            pc = 1
                        elif neighbor == "O2":
                            count += 1
                            # Especial tratamento para O2 como um boot node
                            # Selecionar uma interface não usada e não hardcoded para O2
                            interfaces = [iface for iface in nodes.get("O2", []) if iface[1] == 0 and iface != ("10.0.11.1", 5001)]
                            if interfaces:
                                new_port = update_port("O2") + 1
                                selected_interface = min(interfaces, key=lambda x: x[1])  # escolher a interface com menor valor de porta
                                selected_interfaces.append((selected_interface[0], new_port))
                                # Criar uma thread para ouvir conexões nessa nova porta
                                threading.Thread(target=neighbours_connections, args=(selected_interface[0], new_port)).start()
                        else:
                            count += 1
                            interfaces = nodes.get(neighbor, [])
                            if interfaces:
                                valid_interfaces = [iface for iface in interfaces if iface[1] != 0]
                                if valid_interfaces:
                                    min_interface = min(valid_interfaces, key=lambda x: x[1])
                                else:
                                    min_interface = min(interfaces, key=lambda x: x[1])
                                selected_interfaces.append(min_interface)
                if len(selected_interfaces) == 0:
                    data_to_send = [addr[0], port]
                    message_code = 0
                elif count == len(neighbors) - 1:  # Descontar o "O2" da contagem
                    data_to_send = selected_interfaces
                    message_code = 1
                else:
                    data_to_send = [selected_interfaces, [addr[0], port]]
                    message_code = 2

                complete_message = json.dumps({"code": message_code, "node": node ,"data": data_to_send, "pc": pc})
                conn.send(complete_message.encode('utf-8'))

               
                try:
                    while True:
                        # Espera por uma mensagem de heartbeat
                        heartbeat = conn.recv(1024)
                        if heartbeat:
                            conn.settimeout(3)
                        else:
                            print("Cliente desconectado.")
                            break
                except (ConnectionResetError, socket.timeout, OSError) as e:
                    print(f"Erro ou desconexão detectada: {e}")
            
            else:
                with global_lock:
                    condition.notify_all()
                    message_code = 3 
                    complete_message = json.dumps({"code": message_code})
                    conn.send(complete_message.encode('utf-8'))
                try:
                    while True:
                        # Espera por uma mensagem de heartbeat
                        heartbeat = conn.recv(1024)
                        if heartbeat:
                            conn.settimeout(3)
                        else:
                            print("Cliente desconectado.")
                            break
                except (ConnectionResetError, socket.timeout, OSError) as e:
                    print(f"Erro ou desconexão detectada: {e}")

        elif node.startswith("PC"):
            add_node_to_connected(node)
            neighbors = nodes_neighbors.get(node, [])
            connected_neighbors = [n for n in neighbors if n in nodes_connected]

            if connected_neighbors:
                # Prepara lista de interfaces com IPs e portas dos vizinhos conectados
                neighbor_interfaces = []
                for neighbor in connected_neighbors:
                    for iface in nodes.get(neighbor, []):
                        if iface[1] != 0:  # Verifica se a porta é válida
                            neighbor_interfaces.append((iface[0], iface[1]+1))  # Adiciona a tupla (IP, porta)

                if neighbor_interfaces:
                    # Envia mensagem do tipo 0 com os IPs e portas dos vizinhos conectados
                    data_to_send = json.dumps({
                        "code": 0,  # Código para indicar que há vizinhos disponíveis com interfaces válidas
                        "data": neighbor_interfaces  # Envia lista de interfaces dos vizinhos
                    })
                    conn.send(data_to_send.encode('utf-8'))
                    print(f"Mensagem do tipo 0 enviada para {node}, conectar-se a {neighbor_interfaces}")
                else:
                    # Envia mensagem do tipo 2 se há vizinhos conectados, mas sem interfaces válidas
                    conn.send(json.dumps({"code": 2}).encode('utf-8'))
                    print(f"Mensagem do tipo 2 enviada para {node}, vizinhos conectados sem interfaces válidas")
            else:
                connected_neighbors = [n for n in neighbors]
                # Prepara lista de interfaces com IPs e portas dos vizinhos conectados
                neighbor_interfaces = []
                for neighbor in connected_neighbors:
                    for iface in nodes.get(neighbor, []):
                        if iface[1] != 0:  # Verifica se a porta é válida
                            neighbor_interfaces.append((iface[0], iface[1]+1))  # Adiciona a tupla (IP, porta)

                if neighbor_interfaces:
                    # Envia mensagem do tipo 0 com os IPs e portas dos vizinhos conectados
                    data_to_send = json.dumps({
                        "code": 1,  # Código para indicar que há vizinhos disponíveis com interfaces válidas
                        "data": neighbor_interfaces  # Envia lista de interfaces dos vizinhos
                    })
                    conn.send(data_to_send.encode('utf-8'))
                    print(f"Mensagem do tipo 1 enviada para {node}, conectar-se a {neighbor_interfaces}")
                else:
                    # Envia mensagem do tipo 2 se há vizinhos conectados, mas sem interfaces válidas
                    conn.send(json.dumps({"code": 2}).encode('utf-8'))
                    print(f"Mensagem do tipo 2 enviada para {node}, vizinhos conectados sem interfaces válidas")
            try:
                while True:
                    data = conn.recv(1024).decode('utf-8')
                    if data:
                        print(f"Mensagem recebida de {node}: {data}")
                        # Processa mensagens específicas do PC aqui
                        message = json.loads(data)
                        if message.get("request") == "streams":
                            streams_response = json.dumps({"streams": streams})
                            conn.send(streams_response.encode('utf-8'))
                    else:
                        print(f"Cliente {node} desconectado.")
                        break
            except Exception as e:
                print(f"Erro ao processar mensagens de {node}: {e}")
            finally:
                print(f"Conexão com {node} encerrada.")
    finally:
        conn.close()
        print(f"Conexão com {addr} encerrada.")
        result = wait_for_reactivation(node)
        if result: print("Cliente Morto")
        else: print("Cliente Reativado")
        

def start_bootstrapper(host='0.0.0.0', port=5001):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, port))
        s.listen()
        print(f"Bootstrapper started at {host}:{port}, waiting for node connections...")
        nodes_connected.append("S")
        nodes_connected.append("O2")
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_node_connection, args=(conn, addr)).start()



def wait_for_reactivation(node):
    with condition:
        reactivated = condition.wait(timeout=3)
        if reactivated:
            print("Nó foi reativado.")
            return 0
        else:
            print("Timeout esperando reativação.")
            nodes_connected.remove(node)
            return 1

# Logic for requesting available streams from the server
def server_con(server_host, server_port):
    # Create a socket object
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Connect to the server
    client_socket.connect((server_host, server_port))
    print(f"Connected to server at {server_host}:{server_port}")

    response = client_socket.recv(1024).decode()
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

    # Then, start the bootstrapper to handle node connections
    threading.Thread(target=start_bootstrapper, args=(bootstrapper_host, bootstrapper_port), daemon=True).start()

    # Start the stream path check thread
    threading.Thread(target=check_stream_path, daemon=True).start()

    # First, request streams from the server
    server_con(server_ip, server_port)

    # Keep the main thread running
    try:
        while True:
            pass
    except KeyboardInterrupt:
        print("Shutting down...")