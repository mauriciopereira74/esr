import socket 
import sys
import json
import threading
from threading import Thread
import time
import heapq


global_lock = threading.Lock()
condition = threading.Condition(global_lock)
path_check_lock = threading.Lock()
path_check_condition = threading.Condition(path_check_lock)
tree_lock = threading.Lock()
tree_condition = threading.Condition(tree_lock)
start_tree_lock = threading.Lock()
start_tree_condition = threading.Condition(start_tree_lock)
global boot_name

bootstrapper_name=None

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
    "O2": [("10.0.7.1", 0), ("10.0.4.1", 0), ("10.0.1.1", 0), ("10.0.2.2", 0)],
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
routing_table = {}
next_hops={}
servers_socket={}



def handle_socket_listen(address, port):
    """
    Função para criar e gerenciar o socket UDP para escutar.
    """
    try:
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.bind((address, port))  # Associa o socket ao endereço e porta
        print(f"Socket UDP criado e escutando em {address}:{port}")

        while True:
            try:
                data, addr = udp_socket.recvfrom(65535)  # Receber dados com tamanho maior para frames
                if data:
                    # Verificar se os dados podem ser decodificados como UTF-8
                    try:
                        decoded_data = data.decode('utf-8')  # Tenta decodificar como UTF-8
                        data_json = json.loads(decoded_data)  # Tenta carregar como JSON
                        
                        # Se for JSON, processar conforme o código
                        if "code" in data_json:
                            code = data_json["code"]
                            sender = data_json["sender"]
                            destination = data_json["destination"]

                            if code == 1:  # Mensagem para reencaminhamento básico
                                udp_socket.sendto(b"0", addr)  # Envia ACK
                                print(f"ACK '0' enviado para {addr}")

                                # Reencaminhar mensagem para o próximo nó
                                if destination in next_hops:
                                    udp_ip, port_ip = next_hops[destination]
                                    threading.Thread(
                                        target=handle_socket_connect,
                                        args=(udp_ip, port_ip, sender, destination, 1),
                                        daemon=True
                                    ).start()
                                else:
                                    print(f"Destino desconhecido: {destination}")

                            elif code == 2:  # Mensagem de streams recebida
                                streams = data_json.get("streams", [])
                                udp_socket.sendto(b"0", addr)  # Envia ACK
                                print(f"ACK '0' enviado para {addr}")
                                print(f"Streams recebidas: {streams}")

                                # Reencaminhar streams para o próximo nó
                                if destination in next_hops:
                                    udp_ip, port_ip = next_hops[destination]
                                    threading.Thread(
                                        target=handle_socket_connect,
                                        args=(udp_ip, port_ip, sender, destination, 2, streams),
                                        daemon=True
                                    ).start()
                                else:
                                    print(f"Destino desconhecido: {destination}")

                            elif code == 3:  # Solicitação de stream
                                udp_socket.sendto(b"0", addr)  # Envia ACK
                                stream = data_json["stream"]

                                # Reencaminhar stream para o próximo nó
                                if destination in next_hops:
                                    udp_ip, port_ip = next_hops[destination]
                                    threading.Thread(
                                        target=handle_socket_connect,
                                        args=(udp_ip, port_ip, sender, destination, 3, None, stream),
                                        daemon=True
                                    ).start()
                                else:
                                    print(f"Destino desconhecido: {destination}")

                    except (UnicodeDecodeError, json.JSONDecodeError):
                        try:
                            # Extraindo as partes do cabeçalho
                            destination = data[:3].decode("utf-8").strip()
                            sender = data[3:6].decode("utf-8").strip()
                            payload = data[6:]

                            next_ip, next_port = next_hops[destination]

                            threading.Thread(
                                        target=forward_frame,
                                        args=(next_ip, next_port,data),
                                        daemon=True
                                    ).start()
                        except Exception as e:
                            print(f"Erro ao salvar frame: {e}")

            except Exception as e:
                print(f"Erro ao receber dados no socket UDP: {e}")

    except Exception as e:
        print(f"Erro ao criar socket UDP para escuta: {e}")
    finally:
        udp_socket.close()
        print(f"Socket UDP fechado em {address}:{port}")



def forward_frame(address, port, data):
    """
    Função para reencaminhar pacotes RTP (código 4) para o próximo nó.
    """
    try:
        if control:
            port+=1
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.settimeout(1.0)  # Configura timeout para 1 segundo
        udp_socket.connect((address, port))

        udp_socket.send(data)
       

    except Exception as e:
        print(f"Erro ao reencaminhar frame para {address}:{port}: {e}")
    finally:
        udp_socket.close()
    

def handle_socket_connect(address, port, sender, destination, code, streams=None,stream=None):
    """
    Função para criar e gerenciar o socket UDP para conexão.
    Inclui lógica para enviar mensagens e, no caso de 'code == 2', as streams recebidas.
    """
    try:
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.settimeout(1.0)  # Configura o timeout para 1 segundo
        udp_socket.connect((address, port))
        print(f"Conectado ao socket UDP no endereço {address}:{port}")

        # Prepara a mensagem inicial para envio
        message = {
            "code": code,
            "sender": sender,
            "destination": destination
        }
        if streams:  # Adicionar streams se existirem
            message["streams"] = streams

        if stream:
            message["stream"] = stream

        message_encoded = json.dumps(message).encode()

        ack_received = False
        max_retries = 5  # Define o número máximo de tentativas
        retries = 0

        while not ack_received and retries < max_retries:
            # Envia a mensagem inicial
            udp_socket.send(message_encoded)
            print(f"Mensagem enviada para {address}:{port}: {message} (tentativa {retries + 1})")

            try:
                # Aguardar ACK
                response = udp_socket.recv(1024).decode()
                print(f"Resposta recebida: {response}")

                if response == "0":
                    print("ACK (0) recebido com sucesso!")
                    ack_received = True
                else:
                    print(f"Resposta inesperada recebida: {response}")

            except socket.timeout:
                print(f"Timeout ao aguardar ACK. Reenviando a mensagem...")
                retries += 1

        if not ack_received:
            print(f"Falha ao receber ACK após múltiplas tentativas.")

    except Exception as e:
        print(f"Erro ao conectar ao socket UDP: {e}")
    finally:
        udp_socket.close()
        print("Socket fechado.")



def calculate_dijkstra_tree(start_node, graph):
    """
    Calcula a árvore de menor caminho a partir de um nó inicial (start_node) usando o algoritmo de Dijkstra.
    Retorna um dicionário que mapeia cada nó ao seu nó pai na árvore gerada e as distâncias.
    """

    distances = {node: float('inf') for node in graph}
    parent = {node: None for node in graph}
    distances[start_node] = 0
    priority_queue = [(0, start_node)]  # (distância acumulada, nó atual)

    while priority_queue:
        current_distance, current_node = heapq.heappop(priority_queue)

        # Se já exploramos este nó com menor distância, continue
        if current_distance > distances[current_node]:
            continue

        for neighbor, weight in graph[current_node].items():
            distance = current_distance + weight
            if distance < distances[neighbor]:
                distances[neighbor] = distance
                parent[neighbor] = current_node
                heapq.heappush(priority_queue, (distance, neighbor))

    return parent, distances
        
def find_best_path(start_node, end_node, parent, distances, graph):
    """
    Encontra o melhor caminho entre dois nós na árvore gerada por Dijkstra.
    Soma o custo de cada ligação ao longo do caminho.
    Retorna o caminho e o custo total.
    """
    path = []
    current_node = end_node  # Começa do nó final para reconstruir o caminho
    total_cost = 0

    # Reconstrói o caminho ao navegar nos pais
    while current_node is not None:
        path.append(current_node)
        if current_node == start_node:  # Chegamos ao início do caminho
            break
        parent_node = parent.get(current_node)
        if parent_node is None:
            return None, float('inf')  # Caminho inválido (não conectado)
        
        # Adiciona o custo da ligação entre o nó atual e o nó pai
        link_cost = graph[parent_node].get(current_node, float('inf'))
        total_cost += link_cost

        current_node = parent_node

    # Se o último nó não for o nó inicial, o caminho é inválido
    if path[-1] != start_node:
        return None, float('inf')  # Caminho não encontrado

    path.reverse()  # Reverte o caminho para começar no start_node
    return path, total_cost



def bfs_path_exists(start_node, end_node, graph, nodes_connected):
    # Verifica se o nó inicial está na lista dos conectados
    if start_node not in nodes_connected:
        return False

    visited = set()
    queue = [start_node]
    
    while queue:
        node = queue.pop(0)
        if node == end_node:
            return True

        visited.add(node)
        # Extende a fila com vizinhos conectados
        queue.extend([n for n in graph.get(node, []) if n in nodes_connected and n not in visited])

    return False


def check_stream_path():
    global boot_name
    pcs = [node for node in nodes if node.startswith("PC")]  # Identifica todos os PCs
    paths_available = {pc: False for pc in pcs}  # Inicia um dicionário para controlar os caminhos disponíveis

    while True:
        with path_check_condition:
            path_check_condition.wait()  # Espera notificação de nova conexão
        
        paths_found_this_round = []
        # Verifica se existe caminho para o servidor "S" de cada PC
        for pc in pcs:
            if not paths_available[pc] and bfs_path_exists(pc, 'S', nodes_neighbors, nodes_connected):
                paths_available[pc] = True  # Marca o PC como tendo um caminho disponível
                paths_found_this_round.append(pc)

        # Verifica se todos os PCs têm caminhos disponíveis
        if all(paths_available.values()):
            print("Caminhos disponíveis para stream de todos os PCs para o servidor S.")

            # Calcula a árvore de menor caminho
            parent, distances = calculate_dijkstra_tree("S", rtt_weights)
            # print("Árvore de menor caminho gerada:")
            # for node, parent_node in parent.items():
            #     print(f"{node} <- {parent_node} (Distância: {distances[node]})")

            # Determinar o melhor caminho de cada PC para o servidor S
            for pc in pcs:
                print(f"Verificando caminhos para {pc}...")
                path, cost = find_best_path("S", pc, parent, distances, rtt_weights)

                if path:
                    print(f"Melhor caminho de {pc} para S: {' -> '.join(path)}")
                    print(f"Custo total: {cost:.2f}")

                    # Determinar e imprimir os caminhos de todos os nós intermediários para S e para PC
                    for i, current_node in enumerate(path):
                        if i < len(path) - 1:
                            next_node = path[i + 1]

                            # Inicializar a entrada do nó na tabela de roteamento, se ainda não existir
                            if current_node not in routing_table:
                                routing_table[current_node] = []

                            # Verificar se já existe uma entrada com o mesmo `next_hop`
                            existing_entry = next((entry for entry in routing_table[current_node] if entry["next_hop"] == next_node), None)

                            if existing_entry:
                                # Atualizar a lista de destinos, se o destino atual não estiver presente
                                if pc not in existing_entry["destinations"]:
                                    existing_entry["destinations"].append(pc)
                            else:
                                # Criar uma nova entrada para o `next_hop` e destino atual
                                routing_table[current_node].append({"next_hop": next_node, "destinations": [pc]})


                    print(f"Tabela de roteamento atualizada para {pc}: {routing_table}")
                    nodes_local = [node for node in nodes.keys() if node.startswith("S")]
                    for node in nodes_local:
                        for key,entries in routing_table.items():
                            for entry in entries:
                                # Itera sobre cada dicionário na lista de entradas
                                destination_nodes = entry["destinations"]  # Extrai os destinos
                                next_hop = entry["next_hop"]  # Extrai o próximo salto
                                if key.startswith("S"):
                                    server=key
                                if key == node and next_hop.startswith("O"):  # Verifica se o nó atual é o próximo salto
                                    # Busca a interface (IP e porta) do próximo salto no dicionário de nós
                                    next_hop_interfaces = nodes.get(next_hop, [])
                                    next_hop_interface = next((ip, port) for ip, port in next_hop_interfaces if port != 0)
                                    
                                    if next_hop_interface:
                                        next_hop_ip, next_hop_port = next_hop_interface
                                        message = json.dumps({
                                            "type": 1,
                                            "data": {
                                                "address": next_hop_ip,
                                                "port": next_hop_port + 5,  # Porta incrementada em 5
                                                "destinations": [node for node in destination_nodes] 
                                            }
                                        })
                                        
                                        print(f"Nó {node} enviando mensagem do tipo 1 para próximo salto {next_hop} com destinos {destination_nodes}: {message}")
                                        servers_socket[node].send(message.encode('utf-8'))

                    node=boot_name
                    server = None
                    if node in routing_table:
                        
                        for key, entries in routing_table.items():  # Itera sobre as chaves e valores
                            for entry in entries: 
                                 # Itera sobre cada dicionário na lista de entradas
                                destination_nodes = entry["destinations"]  # Extrai os destinos
                                next_hop = entry["next_hop"]  # Extrai o próximo salto
                                if key.startswith("S"):
                                    server=key
                                if key == node and next_hop.startswith("O"):  # Verifica se o nó atual é o próximo salto
                                    # Busca a interface (IP e porta) do próximo salto no dicionário de nós
                                    next_hop_interfaces = nodes.get(next_hop, [])
                                    next_hop_interface = next((ip, port) for ip, port in next_hop_interfaces if port != 0)
                                    
                                    if next_hop_interface:
                                        next_hop_ip, next_hop_port = next_hop_interface
                                        address = next_hop_ip
                                        port = next_hop_port + 5
                                        destinations = [node for node in destination_nodes] 
                                            
                                        for d in destinations:
                                            next_hops[d] = (address,port)
                                            print(f"Destino {d} próximo passo {address} na porta {port}")

                                       

                                if next_hop == node and (key.startswith("O") or key.startswith("S")):  # Verifica se o nó atual é o próximo salto
                                    # Busca a interface (IP e porta) do próximo salto no dicionário de nós
                                    key_interfaces = nodes.get(key, [])
                                    key_interface = next((ip, port) for ip, port in key_interfaces if port != 0)

                                    if key_interface:
                                        key_ip, key_port = key_interface
                                        
                                        address = key_ip
                                        if key.startswith("S"):
                                            port = key_port
                                        else:
                                            port = key_port + 6
                                        destinations= server
                                        if key.startswith("S"):
                                            next_hops[destinations] = (address,port)
                                            print(f"Destino {destinations} próximo passo {address} na porta {port}")
                                        else:  
                                            for d in destinations:
                                                next_hops[d] = (address,port)
                                                print(f"Destino {d} próximo passo {address} na porta {port}")
                                        
                    with start_tree_lock:
                        start_tree_condition.notify_all()
                else:
                    print(f"Não foi possível encontrar um caminho de {pc} para S.")

            with tree_lock:
                tree_condition.notify_all()
            break  # Ou continue, dependendo se você quer parar após a primeira verificação bem-sucedida ou não
        elif paths_found_this_round:
            # Mostra quais PCs tiveram caminhos encontrados nesta verificação
            available_paths = ', '.join(paths_found_this_round)
            print(f"Caminhos disponíveis para stream dos PCs: {available_paths} para o servidor S.")

            # Calcula a árvore de menor caminho imediatamente
            parent, distances = calculate_dijkstra_tree("S", rtt_weights)
            # print("Árvore de menor caminho gerada nesta rodada:")
            # for node, parent_node in parent.items():
            #     print(f"{node} <- {parent_node} (Distância: {distances[node]})")

            # Determinar o melhor caminho de cada PC para o servidor S
            for pc in pcs:
                print(f"Verificando caminhos para {pc}...")
                path, cost = find_best_path("S", pc, parent, distances, rtt_weights)

                if path:
                    print(f"Melhor caminho de {pc} para S: {' -> '.join(path)}")
                    print(f"Custo total: {cost:.2f}")

                    # Determinar e imprimir os caminhos de todos os nós intermediários para S e para PC
                    for i, current_node in enumerate(path):
                        if i < len(path) - 1:
                            next_node = path[i + 1]

                            # Inicializar a entrada do nó na tabela de roteamento, se ainda não existir
                            if current_node not in routing_table:
                                routing_table[current_node] = []

                            # Verificar se já existe uma entrada com o mesmo `next_hop`
                            existing_entry = next((entry for entry in routing_table[current_node] if entry["next_hop"] == next_node), None)

                            if existing_entry:
                                # Atualizar a lista de destinos, se o destino atual não estiver presente
                                if pc not in existing_entry["destinations"]:
                                    existing_entry["destinations"].append(pc)
                            else:
                                # Criar uma nova entrada para o `next_hop` e destino atual
                                routing_table[current_node].append({"next_hop": next_node, "destinations": [pc]})

                    print(f"Tabela de roteamento atualizada para {pc}: {routing_table}")

                    nodes_local = [node for node in nodes.keys() if node.startswith("S")]
                    for node in nodes_local:
                        for key,entries in routing_table.items():
                            for entry in entries:
                                # Itera sobre cada dicionário na lista de entradas
                                destination_nodes = entry["destinations"]  # Extrai os destinos
                                next_hop = entry["next_hop"]  # Extrai o próximo salto
                                if key.startswith("S"):
                                    server=key
                                if key == node and next_hop.startswith("O"):  # Verifica se o nó atual é o próximo salto
                                    # Busca a interface (IP e porta) do próximo salto no dicionário de nós
                                    next_hop_interfaces = nodes.get(next_hop, [])
                                    next_hop_interface = next((ip, port) for ip, port in next_hop_interfaces if port != 0)
                                    
                                    if next_hop_interface:
                                        next_hop_ip, next_hop_port = next_hop_interface
                                        message = json.dumps({
                                            "type": 1,
                                            "data": {
                                                "address": next_hop_ip,
                                                "port": next_hop_port + 5,  # Porta incrementada em 5
                                                "destinations": [node for node in destination_nodes] 
                                            }
                                        })
                                        
                                        print(f"Nó {node} enviando mensagem do tipo 1 para próximo salto {next_hop} com destinos {destination_nodes}: {message}")
                                        servers_socket[node].send(message.encode('utf-8'))
    
                    node = boot_name
                    server = None
                    if node in routing_table:
                        for key, entries in routing_table.items():  # Itera sobre as chaves e valores
                            for entry in entries:
                                 # Itera sobre cada dicionário na lista de entradas
                                destination_nodes = entry["destinations"]  # Extrai os destinos
                                next_hop = entry["next_hop"]  # Extrai o próximo salto
                                if key.startswith("S"):
                                    server=key
                                if key == node and next_hop.startswith("O"):  # Verifica se o nó atual é o próximo salto
                                    # Busca a interface (IP e porta) do próximo salto no dicionário de nós
                                    next_hop_interfaces = nodes.get(next_hop, [])
                                    next_hop_interface = next((ip, port) for ip, port in next_hop_interfaces if port != 0)
                                    
                                    if next_hop_interface:
                                        next_hop_ip, next_hop_port = next_hop_interface
                                        address = next_hop_ip
                                        port = next_hop_port + 5
                                        destinations = [node for node in destination_nodes] 

                                        for d in destinations:
                                            next_hops[d] = (address,port)
                                            print(f"Destino {d} próximo passo {address} na porta {port}")

                                       

                                if next_hop == node and (key.startswith("O") or key.startswith("S")):  # Verifica se o nó atual é o próximo salto
                                    # Busca a interface (IP e porta) do próximo salto no dicionário de nós
                                    key_interfaces = nodes.get(key, [])
                                    key_interface = next((ip, port) for ip, port in key_interfaces if port != 0)

                                    if key_interface:
                                        key_ip, key_port = key_interface
                                        
                                        address = key_ip
                                        if key.startswith("S"):
                                            port = key_port
                                        else:
                                            port = key_port + 6
                                        destinations= server
                                        if key.startswith("S"):
                                            next_hops[destinations] = (address,port)
                                            print(f"Destino {destinations} próximo passo {address} na porta {port}")
                                        else:  
                                            for d in destinations:
                                                next_hops[d] = (address,port)
                                                print(f"Destino {d} próximo passo {address} na porta {port}")
                    with start_tree_lock:
                        start_tree_condition.notify_all()
                else:
                    print(f"Não foi possível encontrar um caminho de {pc} para S.")
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
    elif node_name.startswith("PC"):
        return 4000 + int(node_name[2:]) * 10
    return None

def add_node_to_connected(node):
    if node not in nodes_connected:
        nodes_connected.append(node)
        

def handle_node_connection(conn, addr):
    print(f"Conexão recebida de {addr}")
    global boot_name
    node = find_ip(addr[0])
    print(f"Nó identificado: {node}")
    try:
        bootneighbor = 0
        if node.startswith("O") or node.startswith("PC"):
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
                pc_interface= []
                server = None
                for neighbor in neighbors:
                    if neighbor.startswith("PC"):
                            pc = 1
                    if neighbor in nodes_connected:
                        if neighbor == boot_name or neighbor.startswith("S"):
                            if neighbor.startswith("S"):
                                interfaces = nodes.get(neighbor, [])
                                if interfaces:
                                    valid_interfaces = [iface for iface in interfaces if iface[1] != 0]
                                    if valid_interfaces:
                                        min_interface = min(valid_interfaces, key=lambda x: x[1])
                                    else:
                                        min_interface = min(interfaces, key=lambda x: x[1])
                                    server = min_interface
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
                            if neighbor.startswith("PC"):
                                count += 1
                                interfaces = nodes.get(neighbor, [])
                                if interfaces:
                                    valid_interfaces = [iface for iface in interfaces if iface[1] != 0]
                                    if valid_interfaces:
                                        min_interface = min(valid_interfaces, key=lambda x: x[1])
                                    else:
                                        min_interface = min(interfaces, key=lambda x: x[1])
                                    pc_interface.append(min_interface)
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

                if len(selected_interfaces) == 0 :
                    data_to_send = [addr[0], port]
                    message_code = 0
                elif count == len(neighbors) and not node.startswith("PC"):  
                    data_to_send = selected_interfaces
                    message_code = 1
                elif count == len(neighbors) and node.startswith("PC"):  
                    data_to_send = [selected_interfaces, [addr[0], port]]
                    message_code = 1
                else:
                    data_to_send = [selected_interfaces, [addr[0], port]]
                    message_code = 2
                if bootstrapper_name in nodes_neighbors and node in nodes_neighbors[bootstrapper_name]:
                    if node != "S": 
                        bootneighbor = 1

                my_udp = [addr[0], port+5]
                control[node]=(message_code,selected_interfaces)
                
                
                complete_message = json.dumps({"code": message_code, "bootneighbor":bootneighbor ,"node": node ,"data": data_to_send, "pc": pc, "pc_interface": pc_interface, "my_udp": my_udp, "server":server})
                print(f"Message sent to {addr[0]}")
                conn.send(complete_message.encode('utf-8'))

            else:
                pc=0
                add_node_to_connected(node)
                pc_interface = []
                port = update_port(node)  # Atualiza a porta baseada no nome do nó
                my_udp=None
                server=None
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
                    pc_interface = []
                    for neighbor in neighbors:
                        if neighbor.startswith("PC"):
                            pc = 1
                        if neighbor in nodes_connected:
                            if neighbor == boot_name or neighbor.startswith("S"):
                                if neighbor.startswith("S"):
                                    interfaces = nodes.get(neighbor, [])
                                    if interfaces:
                                        valid_interfaces = [iface for iface in interfaces if iface[1] != 0]
                                        if valid_interfaces:
                                            min_interface = min(valid_interfaces, key=lambda x: x[1])
                                        else:
                                            min_interface = min(interfaces, key=lambda x: x[1])
                                        server = min_interface
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
                                if neighbor.startswith("PC"):
                                    count += 1
                                    interfaces = nodes.get(neighbor, [])
                                    if interfaces:
                                        valid_interfaces = [iface for iface in interfaces if iface[1] != 0]
                                        if valid_interfaces:
                                            min_interface = min(valid_interfaces, key=lambda x: x[1])
                                        else:
                                            min_interface = min(interfaces, key=lambda x: x[1])
                                        pc_interface.append(min_interface)
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

                    if len(selected_interfaces) == 0 :
                        data_to_send = [addr[0], port]
                        message_code = 0
                    elif count == len(neighbors) and not node.startswith("PC"):  
                        data_to_send = selected_interfaces
                        message_code = 1
                    elif count == len(neighbors) and node.startswith("PC"):  
                        data_to_send = [selected_interfaces, [addr[0], port]]
                        message_code = 1
                    else:
                        data_to_send = [selected_interfaces, [addr[0], port]]
                        message_code = 2
                    if bootstrapper_name in nodes_neighbors and node in nodes_neighbors[bootstrapper_name]:
                        if node != "S": 
                            bootneighbor = 1

                    control[node]=(message_code,selected_interfaces)
                    my_udp = [addr[0], port+5]
                    

                complete_message = json.dumps({"code": message_code, "bootneighbor":bootneighbor ,"node": node ,"data": data_to_send, "pc": pc, "pc_interface": pc_interface, "my_udp": my_udp, "server":server})
                conn.send(complete_message.encode('utf-8'))

            try:
                # Recebe a mensagem do nó
                data = conn.recv(1024)
                message = json.loads(data.decode('utf-8'))
                # Processar mensagem com código 0 (RTT Start e latências enviadas pelo nó)
                if message.get("code") == 0:
                    start_time = float(message.get("start_time"))
                    current_time = time.time()

                    # Calcula o RTT (tempo de ida) como a diferença entre o tempo atual e o tempo de início
                    one_way_delay = (current_time - start_time) * 1000  # Convertendo para milissegundos

                    # Atualizar o dicionário de RTTs
                    with global_lock:
                        if node not in rtt_weights:
                            rtt_weights[node] = {}
                        if bootstrapper_name not in rtt_weights:
                            rtt_weights[bootstrapper_name] = {}

                        # RTT é bidirecional
                        rtt_weights[node][bootstrapper_name] = one_way_delay
                        rtt_weights[bootstrapper_name][node] = one_way_delay

                        # Atualizar também as latências enviadas pelo nó
                        latencies = message.get("latencies", {})
                        for neighbor, rtt in latencies.items():
                            neighbor_ip = neighbor.split(':')[0]
                            neighbor_name = find_ip(neighbor_ip)
                            if neighbor_name not in rtt_weights[node]:
                                rtt_weights[node][neighbor_name] = rtt
                            if node not in rtt_weights[neighbor_name]:
                                rtt_weights[neighbor_name][node] = rtt
                        
                        # RTT é bidirecional
                            rtt_weights[node][neighbor_name] = rtt
                            rtt_weights[neighbor_name][node] = rtt

                        print("Dicionário de RTTs atualizado")
                        print(rtt_weights)

                # Processar mensagem com código 10 (sem latências enviadas pelo nó)
                elif message.get("code") == 10:
                    print(f"O nó {addr[0]} enviou mensagem de código 10: Nenhuma latência a ser reportada.")

                # Processar mensagem com código 1 (RTT Update com novas latências enviadas pelo nó)
                elif message.get("code") == 1:
                    latencies = message.get("latencies", {})
                    for neighbor, rtt in latencies.items():
                        # Separar o endereço IP da porta
                        neighbor_ip = neighbor.split(':')[0]
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

                    print("Dicionário de RTTs atualizado")
                    print(rtt_weights)

                # Mensagem com código desconhecido
                else:
                    print(f"Mensagem desconhecida recebida de {addr}: {message}")

                with path_check_lock:
                        path_check_condition.notifyAll()

            except json.JSONDecodeError:
                print(f"Mensagem inválida recebida de {addr}: {data.decode('utf-8')}")
            except Exception as e:
                print(f"Erro ao processar mensagem RTT: {e}")

        node = find_ip(addr[0])
        while True:
            with start_tree_lock:
                start_tree_condition.wait()
                #print(f"TABELA DE ROUTING: {routing_table}")

                node = find_ip(addr[0])
                server = None
                if node in routing_table:
                    for key, entries in routing_table.items():  # Itera sobre as chaves e valores
                        for entry in entries:  # Itera sobre cada dicionário na lista de entradas
                            destination_nodes = entry["destinations"]  # Extrai os destinos
                            next_hop = entry["next_hop"]  # Extrai o próximo salto
                            if key.startswith("S"):
                                server=key
                            if key == node and (next_hop.startswith("O") or next_hop.startswith("PC")):  # Verifica se o nó atual é o próximo salto
                                # Busca a interface (IP e porta) do próximo salto no dicionário de nós
                                next_hop_interfaces = nodes.get(next_hop, [])
                                next_hop_interface = next((ip, port) for ip, port in next_hop_interfaces if port != 0)

                                if next_hop_interface:
                                    next_hop_ip, next_hop_port = next_hop_interface
                                    if next_hop.startswith("PC"):
                                        message = json.dumps({
                                            "type": 1,  # Tipo de mensagem 1
                                            "data": {
                                                "address": next_hop_ip,
                                                "port": next_hop_port+2,  # Porta incrementada em 2
                                                "destinations": [node for node in destination_nodes] 
                                            }
                                        })
                                    else:
                                        message = json.dumps({
                                            "type": 1,  # Tipo de mensagem 1
                                            "data": {
                                                "address": next_hop_ip,
                                                "port": next_hop_port + 5,  # Porta incrementada em 5
                                                "destinations": [node for node in destination_nodes] 
                                            }
                                        })
                                    
                                    print(f"Nó {node} enviando mensagem do tipo 1 para próximo salto {next_hop} com destinos {destination_nodes}: {message}")
                                    conn.send(message.encode('utf-8'))

                            if next_hop == node and (key.startswith("O") or key.startswith("S")):  # Verifica se o nó atual é o próximo salto
                                # Busca a interface (IP e porta) do próximo salto no dicionário de nós
                                key_interfaces = nodes.get(key, [])
                                key_interface = next((ip, port) for ip, port in key_interfaces if port != 0)

                                if key_interface:
                                    key_ip, key_port = key_interface
                                    if (key.startswith("S")):
                                        message = json.dumps({
                                            "type": 2,  # Tipo de mensagem 2
                                            "data": {
                                                "address": key_ip,
                                                "port": key_port,  # Porta incrementada em 5
                                                "destinations": server
                                            }
                                        })
                                    else:
                                        message = json.dumps({
                                            "type": 2,  # Tipo de mensagem 2
                                            "data": {
                                                "address": key_ip,
                                                "port": key_port + 6,  # Porta incrementada em 5
                                                "destinations": server
                                            }
                                        })
                                    
                                    print(f"Nó {node} enviando mensagem do tipo 2 para próximo salto {next_hop} com destinos {destination_nodes}: {message}")
                                    conn.send(message.encode('utf-8'))

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
        

def start_bootstrapper(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Permite reutilizar o endereço
        s.bind((host, port))
        s.listen()
        print(f"Bootstrapper started at {host}:{port}, waiting for node connections...")
        nodes_connected.append("S")
        node = find_ip(host)
        if node in nodes:
            updated_list = []
            for tup in nodes[node]:
                if tup[0] == host:
                    # Cria um novo tuplo com o valor atualizado
                    updated_list.append((tup[0], 5001))
                else:
                    # Mantém o tuplo original
                    updated_list.append(tup)
        # Atualiza a lista da chave
        nodes[node] = updated_list
        global boot_name
        boot_name = node
        nodes_connected.append(node)
        threading.Thread(target=handle_socket_listen, args=(host, port+5)).start()
        threading.Thread(target=handle_socket_listen, args=(host, port+6)).start()

        initialize_rtt_weights()
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_node_connection, args=(conn, addr)).start()


def server_con(server_host, server_port, bootstrapper_host):
    """
    Conecta ao servidor via TCP para obter streams disponíveis,
    encerra a conexão e calcula o RTT via UDP.
    """
    try:
        # Criar uma conexão TCP inicial para obter informações
        tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_socket.connect((server_host, server_port))
        print(f"Connected to server at {server_host}:{server_port} via TCP")

        response = tcp_socket.recv(1024).decode()
        streams.extend(response.split(","))
        print(f"Available streams received: {response}")

        # Encerra a conexão TCP
        tcp_socket.close()
        

        # Inicia a conexão UDP para calcular RTT
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.settimeout(2)  # Define o timeout de 5 segundos
        udp_socket.connect((server_host, server_port))

        while True:  # Loop até receber o "pong"
            start_time = time.time()
            udp_socket.send(b"ping")  # Envia mensagem "ping"

            try:
                data, addr = udp_socket.recvfrom(1024)  # Aguarda resposta "pong"
                end_time = time.time()
                if data and data.decode() == "pong":
                    rtt = (end_time - start_time) * 1000  # RTT em milissegundos
                    
                    # Resolver o nome do cliente e do servidor
                    server_name = find_ip(server_host)
                    client_name = find_ip(bootstrapper_host)

                    if not server_name or not client_name:
                        print(f"Erro ao resolver nomes: server_name={server_name}, client_name={client_name}")
                        return

                    with global_lock:
                        # Garante que os nós existam no dicionário antes de adicionar o RTT
                        if server_name not in rtt_weights:
                            rtt_weights[server_name] = {}
                        if client_name not in rtt_weights:
                            rtt_weights[client_name] = {}

                        # Atualiza os valores no dicionário
                        rtt_weights[client_name][server_name] = rtt / 2  # One-way delay
                        rtt_weights[server_name][client_name] = rtt / 2  # Bidirecional
                    break
                else:
                    print("No valid response received for RTT calculation.")

                # Fechar a conexão UDP
                udp_socket.close()
                print("UDP connection closed.")
                
            except socket.timeout:
                # Se o timeout for atingido, reenvia o "ping"
                print("Timeout reached. Resending Ping...")
                continue
    except Exception as e:
        print(f"Error in server_con: {e}")


def has_neighbor_starting_with_s(node, nodes_neighbors):
    neighbors = nodes_neighbors.get(node, [])
    for neighbor in neighbors:
        if neighbor.startswith("S"):
            return True
    return False

   
if __name__ == "__main__":

    
    if len(sys.argv) != 5:
        print("Usage: python name.py <BOOTSTRAPPER_IP> <BOOTSTRAPPER_PORT> <SERVER_IP> <SERVER_PORT>")
        sys.exit(1)


    bootstrapper_host = sys.argv[1]
    bootstrapper_name=find_ip(bootstrapper_host)
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
    
    server = find_ip(server_ip) 
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.connect((server_ip, server_port))
    print(f"Connected to server at {server_ip}:{server_port} via TCP")
    servers_socket[server] = server_socket

    node = find_ip(bootstrapper_host)

    if has_neighbor_starting_with_s(node, nodes_neighbors):
        server_con(server_ip, server_port, bootstrapper_host)

    # start the bootstrapper to handle node connections
    threading.Thread(target=start_bootstrapper, args=(bootstrapper_host, bootstrapper_port), daemon=True).start()

    threading.Thread(target=check_stream_path, daemon=True).start()
    
    

    # Keep the main thread running
    try:
        while True:
            pass
    except KeyboardInterrupt:
        print("Shutting down...")