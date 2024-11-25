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

control = {
    "O7": (0,[]),
    "O6": (0,[]),
    "O5": (0,[]),
    "O4": (0,[]),
    "O3": (0,[])
}

streams = []
nodes_connected = []
rtt_weights = {}

def dijkstra_path_exists(start_node, end_node, graph):
    """
    Verifica se há um caminho de menor custo entre start_node e end_node usando o algoritmo de Dijkstra.
    Retorna True se o caminho existir, False caso contrário.
    """
    import heapq

    # Verifica se os nós estão no grafo
    if start_node not in graph or end_node not in graph:
        print(f"Nós {start_node} ou {end_node} não estão no grafo. Caminho não encontrado.")
        return False

    distances = {node: float('inf') for node in graph}
    distances[start_node] = 0
    priority_queue = [(0, start_node)]  # (custo acumulado, nó atual)

    while priority_queue:
        current_distance, current_node = heapq.heappop(priority_queue)

        # Se chegamos ao nó final, o caminho existe
        if current_node == end_node:
            return True

        # Se o nó já foi visitado com menor custo, ignore
        if current_distance > distances[current_node]:
            continue

        # Explora os vizinhos
        for neighbor, weight in graph[current_node].items():
            distance = current_distance + weight
            if distance < distances[neighbor]:
                distances[neighbor] = distance
                heapq.heappush(priority_queue, (distance, neighbor))

    # Se o loop terminar sem alcançar o end_node, o caminho não existe
    return False



def check_stream_path():
    """
    Verifica continuamente se todos os PCs têm caminhos válidos para o servidor 'S'
    usando os pesos de RTT.
    """
    pcs = [node for node in nodes if node.startswith("PC")]  # Identifica todos os PCs
    paths_available = {pc: False for pc in pcs}  # Dicionário para monitorar caminhos encontrados

    while True:
        with path_check_condition:
            path_check_condition.wait()  # Espera até que novos nós ou latências sejam adicionados

        # Verifica se os nós principais estão no rtt_weights
        if "S" not in rtt_weights or any(pc not in rtt_weights for pc in pcs):
            print("Nodos principais ainda não registrados no RTT weights.")
            continue

        # Verifica caminhos para todos os PCs
        for pc in pcs:
            if not paths_available[pc]:  # Apenas verifica os PCs que ainda não têm caminhos
                if dijkstra_path_exists(pc, "S", rtt_weights):
                    paths_available[pc] = True
                    print(f"Caminho disponível para o stream do {pc} ao servidor S.")

        # Verifica se todos os PCs têm caminhos
        if all(paths_available.values()):
            print("Caminhos disponíveis para stream de todos os PCs para o servidor S.")
            with tree_lock:
                tree_condition.notify_all()  # Notifica que todos os caminhos foram encontrados
            break



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
    with path_check_lock:
        if node not in nodes_connected:
            nodes_connected.append(node)
        path_check_condition.notifyAll()

def handle_node_connection(conn, addr):
    print(f"Conexão recebida de {addr}")

    node = find_ip(addr[0])
    print(f"Nó identificado: {node}")
    try:
        if node.startswith("O"):
            if node not in nodes_connected or (node in nodes_connected and control[node][0]==1) :
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
                            """ interfaces = [iface for iface in nodes.get("O2", []) if iface[1] == 0 and iface != ("10.0.11.1", 5001)]
                            if interfaces:
                                new_port = update_port("O2") + 1
                                selected_interface = min(interfaces, key=lambda x: x[1])  # escolher a interface com menor valor de porta
                                selected_interfaces.append((selected_interface[0], new_port))
                                # Criar uma thread para ouvir conexões nessa nova porta
                                threading.Thread(target=neighbours_connections, args=(selected_interface[0], new_port)).start() """
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
                elif count == len(neighbors):  # Descontar o "O2" da contagem
                    data_to_send = selected_interfaces
                    message_code = 1
                else:
                    data_to_send = [selected_interfaces, [addr[0], port]]
                    message_code = 2

                control[node]=(message_code,selected_interfaces)
                complete_message = json.dumps({"code": message_code, "node": node ,"data": data_to_send, "pc": pc})
                conn.send(complete_message.encode('utf-8'))

            else:
                pc=0
                add_node_to_connected(node)
                port = update_port(node)  # Atualiza a porta baseada no nome do nó
                if control[node][0]==0:
                    data_to_send = [addr[0], port]
                    message_code = 0
                
                else:
                                
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
                                """ interfaces = [iface for iface in nodes.get("O2", []) if iface[1] == 0 and iface != ("10.0.11.1", 5001)]
                                if interfaces:
                                    new_port = update_port("O2") + 1
                                    selected_interface = min(interfaces, key=lambda x: x[1])  # escolher a interface com menor valor de porta
                                    selected_interfaces.append((selected_interface[0], new_port))
                                    # Criar uma thread para ouvir conexões nessa nova porta
                                    threading.Thread(target=neighbours_connections, args=(selected_interface[0], new_port)).start() """
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
                    elif count == len(neighbors):  # Descontar o "O2" da contagem
                        data_to_send = selected_interfaces
                        message_code = 1
                    else:
                        data_to_send = [selected_interfaces, [addr[0], port]]
                        message_code = 2

                    control[node]=(message_code,selected_interfaces)

                complete_message = json.dumps({"code": message_code, "node": node ,"data": data_to_send, "pc": pc})
                conn.send(complete_message.encode('utf-8'))

            data = conn.recv(1024)

            try:
                message = json.loads(data.decode('utf-8'))

                # Processar mensagem de RTT
                if message.get("type") == "rtt_update":
                    latencies = message.get("latencies", {})
                    for neighbor, rtt in latencies.items():
                        # Separar o endereço IP da porta
                        neighbor_ip = neighbor.split(':')[0]  # Extrai o IP antes do ';'
                        one_way_delay = rtt / 2  # Dividindo o RTT por 2
                        print(f"Tempo de ida (one-way delay) entre {node} e {neighbor_ip}: {one_way_delay:.2f} ms")

                        # Resolver o nome do nó a partir do IP
                        node_name = None
                        for n, interfaces in nodes.items():
                            for interface_ip, _ in interfaces:
                                if neighbor_ip == interface_ip:
                                    node_name = n
                                    break
                            if node_name:
                                break

                        # Ignorar se o IP não for encontrado
                        if not node_name:
                            print(f"IP {neighbor_ip} não encontrado no dicionário nodes.")
                            continue

                        # Atualizar o peso no dicionário de RTTs
                        with global_lock:
                            if node not in rtt_weights:
                                rtt_weights[node] = {}
                            if node_name not in rtt_weights:
                                rtt_weights[node_name] = {}
                            rtt_weights[node][node_name] = one_way_delay
                            rtt_weights[node_name][node] = one_way_delay  # Direção oposta

                    print("Dicionário de RTTs atualizado:")
                    print(rtt_weights)

            except json.JSONDecodeError:
                print(f"Mensagem inválida recebida de {node}: {data.decode('utf-8')}")
                
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
    finally:
        conn.close()
        print(f"Conexão com {addr} encerrada.")

def initialize_rtt_weights():
    """
    Inicializa o dicionário rtt_weights com pesos infinitos entre todos os nós.
    Isso garante que todos os nós estejam no grafo antes de qualquer cálculo.
    """
    global rtt_weights

    # Inicializa todos os nós no rtt_weights
    for node in nodes_neighbors:
        if node not in rtt_weights:
            rtt_weights[node] = {}
        for neighbor in nodes_neighbors[node]:
            # Garante que o vizinho também esteja no dicionário
            if neighbor not in rtt_weights:
                rtt_weights[neighbor] = {}

            # Define pesos infinitos bidirecionais
            if neighbor not in rtt_weights[node]:
                rtt_weights[node][neighbor] = float('inf')
            if node not in rtt_weights[neighbor]:
                rtt_weights[neighbor][node] = float('inf')

    print("RTT weights inicializado:")
    print(rtt_weights)

        

def start_bootstrapper(host='0.0.0.0', port=5001):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Permite reutilizar o endereço
        s.bind((host, port))
        s.listen()
        print(f"Bootstrapper started at {host}:{port}, waiting for node connections...")
        nodes_connected.append("S")
        nodes_connected.append("O2")
        initialize_rtt_weights()
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_node_connection, args=(conn, addr)).start()


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