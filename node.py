import socket
import sys
import json
import threading
import time


global connections
global node
lock_host = threading.Lock()
condition_lock_host = threading.Condition(lock_host)
lock_neighbor = threading.Lock()
condition_lock_neighbor = threading.Condition(lock_neighbor)
connections = []
connection_active_host = []
connection_neighbor=[]


def listen_for_connections(host, port):
    """
    Escuta por conexões e gerencia o reencaminhamento de mensagens recebidas.
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Permite reutilizar o endereço
    server_socket.bind((host, port))
    server_socket.listen()
    print(f"Listening for connections on {host}:{port}")

    while True:
        client_socket, addr = server_socket.accept()
        print(f"Connection accepted from {addr}")
        connections.append(client_socket)

        # Inicia uma thread para tratar mensagens dessa conexão
        threading.Thread(target=handle_connection, args=(client_socket, host, port, addr), daemon=True).start()


def handle_connection(client_socket, host, port, addr):

    try:

        with lock_host:
            connection_active_host.append(addr)
            condition_lock_host.notify_all()


        new_port = port + 1
        threading.Thread(target=setup_heartbeat_connection, args=(host, new_port), daemon=True).start()

        while True:
            data = client_socket.recv(1024)
            if not data:
                break

            try:
                message = data.decode('utf-8')

                # Verifica se a mensagem é um ping
                if message == "ping":
                    # Envia a resposta "ping_ack" para o remetente
                    client_socket.send(b"ping_ack")
                    print(f"Ping received from {addr}, sent ping_ack")
                else:
                    # Trate outras mensagens (exemplo: JSON)
                    try:
                        json_message = json.loads(message)
                        print(f"Message received from {addr}: {json_message}")
                    except json.JSONDecodeError:
                        print(f"Invalid message from {addr}: {message}")

            except Exception as e:
                print(f"Error processing message from {addr}: {e}")

    except Exception as e:
        print(f"Connection error with {host}: {e}")
    finally:
        client_socket.close()
        connections.remove(client_socket)
        with lock_host:
            connection_active_host.remove(addr)
            notified = condition_lock_host.wait(timeout=10) 

        if(notified):
            print(f"Ligação com {addr} reestabelecida")
        else:
            print(f"{addr} dado como morto.")
        print(f"Closing connection with {host}")
        


def setup_heartbeat_connection(host, port):

    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((host, port))
        server_socket.listen()
        print(f"Heartbeat server listening on {host}:{port}")

        client_socket, addr = server_socket.accept()
        print(f"Heartbeat connection accepted from {host}")

        # Iniciar threads para enviar e receber heartbeats, passando o endereço como argumento
        threading.Thread(target=send_heartbeats, args=(client_socket, host), daemon=True).start()
        threading.Thread(target=receive_heartbeats, args=(client_socket, host), daemon=True).start()
    except Exception as e:
        print(f"Error {e}")


def send_heartbeats(socket, host):
    try:
        while True:
            socket.send(b"heartbeat")
            #print(f"Heartbeat sent from {host}")
            time.sleep(2)
    except Exception as e:
        pass
        #print(f"Error sending heartbeats from {host}: {e}")
    finally:
        socket.close()

def receive_heartbeats(socket, host):
    try:
        # Configura o timeout do socket para 3 segundos
        socket.settimeout(3)
        
        while True:
            try:
                data = socket.recv(1024)
                if data:
                    pass
                    #print(f"Heartbeat received in {host}")
                else:
                    # Quando data é vazio, significa que a conexão foi fechada pelo outro lado
                    print(f"Heartbeat connection lost in {host}")
                    break
            except socket.timeout:
                # Trata o caso de timeout onde nenhum dado foi recebido dentro do tempo especificado
                print(f"Timeout: No heartbeat received in {host} within 3 seconds.")
                break
    except Exception as e:
        pass
        #print(f"Error receiving heartbeats in {host}: {e}")
    finally:
        # Fechamento da conexão após a quebra do loop
        print("Closing heartbeat connection in", host)
        socket.close()

def send_heartbeats_connected(socket, neighbour):
    try:
        while True:
            socket.send(b"heartbeat")
            #print(f"Heartbeat sent to {neighbour}")
            time.sleep(2)
    except Exception as e:
        pass
    finally:
        print("Closing connection to", neighbour)
        socket.close()

def receive_heartbeats_connected(socket, neighbour):
    try:
        # Configura o timeout do socket para 3 segundos
        socket.settimeout(3)
        
        while True:
            try:
                data = socket.recv(1024)
                if data:
                    pass
                    #print(f"Heartbeat received from {neighbour}")
                else:
                    print(f"Heartbeat connection lost from {neighbour}")
                    break
            except socket.timeout:
                print(f"Timeout: No heartbeat received from {neighbour} within 3 seconds.")
                break
    except Exception as e:
        pass
        #print(f"AQUIIIIError receiving heartbeats from {neighbour}: {e}")
    finally:
        print("Closing connection to", neighbour)
        socket.close()

def connect_to_neighbors(neighbors, condition, lock, latencies):
    """
    Conecta a cada vizinho da lista e mede RTTs.
    Atualiza a lista de RTTs em `latencies` e utiliza threading para conexões.
    """
    completed_neighbors = 0

    def measure_rtt_for_neighbor(sock, neighbor_ip, neighbor_port):
        """
        Mede o RTT de um vizinho específico e atualiza a lista de latências.
        """
        nonlocal completed_neighbors
        rtt = measure_rtt_with_socket(sock)
        with lock:
            latencies[f"{neighbor_ip}:{neighbor_port}"] = rtt
            completed_neighbors += 1
            if completed_neighbors == len(neighbors):
                condition.notify_all()

    try:
        for neighbor_ip, neighbor_port in neighbors:
            try:
                print(f"Attempting to connect to neighbor {neighbor_ip}:{neighbor_port}")
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((neighbor_ip, int(neighbor_port)))
                print(f"Connected to neighbor {neighbor_ip}:{neighbor_port}")
                connections.append(sock)

                # Medir RTT em uma thread
                threading.Thread(
                    target=measure_rtt_for_neighbor,
                    args=(sock, neighbor_ip, neighbor_port),
                    daemon=True
                ).start()

                # Gerenciar comunicação com o vizinho
                threading.Thread(
                    target=manage_connection,
                    args=(sock, neighbor_ip, neighbor_port),
                    daemon=True
                ).start()

            except Exception as e:
                print(f"Failed to connect to neighbor {neighbor_ip}:{neighbor_port}: {e}")

    except Exception as e:
        print(f"Error connecting to neighbors: {e}")



def connect_to_neighbors_after_reconnection(neighbor_ip, neighbor_port):
    try:
        print(f"Attempting to connect to neighbor {neighbor_ip}:{neighbor_port}")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((neighbor_ip, int(neighbor_port)))
        print(f"Connected to neighbor {neighbor_ip}:{neighbor_port}")
        connections.append(sock)

        # Iniciar uma thread para gerenciar a comunicação após a conexão ser estabelecida
        threading.Thread(target=manage_connection, args=(sock,neighbor_ip,neighbor_port), daemon=True).start()
    except Exception as e:
        print(f"Failed to connect to neighbor {neighbor_ip}:{neighbor_port}: {e}")

def manage_connection(sock, neighbor_ip, base_port):
    """
    Conecta-se ao vizinho e gerencia a comunicação principal.
    Também inicia uma thread para gerenciar os heartbeats em uma porta separada.
    """
    try:
        # Inicia a thread de gerenciamento de heartbeats
        threading.Thread(target=manage_heartbeats, args=(neighbor_ip, base_port + 1), daemon=True).start()

        # Continuar recebendo dados no socket principal
        while True:
            data = sock.recv(1024)
            if not data:
                break  # Conexão foi fechada pelo vizinho
            print(f"Received data: {data.decode()}")

    except Exception as e:
        print(f"Error in managing connection with {neighbor_ip}:{base_port}: {e}")
    finally:
        print("Closing main communication channel")
        sock.close()
        connections.remove(sock)
        print("Attempting to reconnect...")
        reconnect_success = try_reconnect(neighbor_ip, base_port)

        if reconnect_success:
            print("Reconnection successful, client is alive.")
            connect_to_neighbors_after_reconnection(neighbor_ip, base_port)
        else:
            print("Failed to reconnect within 3 seconds, client is considered dead.")


def try_reconnect(neighbor_ip, base_port, timeout=3):
    """
    Tenta reconectar ao vizinho especificado após uma desconexão.
    Tenta a reconexão durante o período especificado pelo timeout.
    Retorna True se a reconexão for bem-sucedida, False caso contrário.
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            time.sleep(2)
            new_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            new_sock.settimeout(end_time - time.time())  # Define um timeout dinâmico
            new_sock.connect((neighbor_ip, base_port))
            new_sock.close()  # Fecha o socket após a reconexão bem-sucedida
            return True
        except Exception as e:
            continue  # Tenta novamente até que o timeout expire
        except socket.timeout:
            print(f"Failed to reconnect: {e}")
            new_sock.close()
            break  # Encerra se ocorrer uma falha que não seja timeout
    return False

def manage_heartbeats(neighbor_ip, neighbor_port):
    """
    Gerencia os heartbeats com um vizinho específico utilizando o IP e porta fornecidos.
    """
    try:
        heartbeat_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        heartbeat_socket.connect((neighbor_ip, neighbor_port))
        address = f"{neighbor_ip}:{neighbor_port}"
        print(f"Heartbeat channel established with {neighbor_ip}")

        # Inicia uma thread para enviar heartbeats
        threading.Thread(target=send_heartbeats_connected, args=(heartbeat_socket, neighbor_ip), daemon=True).start()

        # Inicia uma thread para receber heartbeats
        threading.Thread(target=receive_heartbeats_connected, args=(heartbeat_socket, neighbor_ip), daemon=True).start()

    except Exception as e:
        print(f"Error establishing heartbeat channel ")
        heartbeat_socket.close()



def connect_to_pc(pc_address, pc_port):
    """
    Cria uma conexão UDP para o PC.
    """
    try:
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.bind((pc_address, pc_port))  # Vincula ao endereço com uma porta específica
        print(f"UDP socket bound to {pc_address}:{pc_port}")
        # Aqui você pode implementar lógica para enviar dados ou manter o socket ouvindo
    except Exception as e:
        print(f"Failed to open UDP socket to PC at {pc_address}:{pc_port}: {e}")

def measure_rtt_with_socket(sock):
    """
    Mede o RTT usando um socket já aberto.
    Envia um 'ping' e espera a resposta 'ping_ack'.
    """
    try:
        start_time = time.time()
        sock.send(b"ping")  # Envia o ping
        response = sock.recv(1024)  # Aguarda a resposta
        end_time = time.time()

        if response == b"ping_ack":
            rtt = (end_time - start_time) * 1000  # RTT em milissegundos
            return rtt
        else:
            print(f"Unexpected response: {response}")
            return float('inf')
    except Exception as e:
        print(f"Failed to measure RTT: {e}")
        return float('inf')


def connect_to_bootstrapper(host, port):
    """
    Conecta ao bootstrapper para obter informações iniciais.
    """
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    my_tcp = None
    my_port = None
    global node

    # Variáveis para medir RTT
    latencies = {}
    lock = threading.Lock()
    condition = threading.Condition(lock)


    try:
        client_socket.connect((host, port))
        print(f"Connected to bootstrapper at {host}:{port}")

        data_encoded = client_socket.recv(1024).decode()
        if data_encoded:
            data_json = json.loads(data_encoded)
            print(f"Received data: {data_json}")

            message_code = data_json['code']
            node = data_json['node']

            if message_code == 0:
                data = data_json['data']
                address, port_received = data

                my_tcp = address
                my_port = port_received

                threading.Thread(target=listen_for_connections, args=(my_tcp, my_port), daemon=True).start()

                pc = data_json['pc']
                if pc:
                    pc_ip = my_tcp
                    pc_port = my_port + 1
                    threading.Thread(target=connect_to_pc, args=(pc_ip, pc_port), daemon=True).start()

            elif message_code == 1:
                data = data_json['data']
                neighbors_list = data

                # Chama connect_to_neighbors em uma thread
                threading.Thread(
                    target=connect_to_neighbors,
                    args=(neighbors_list, condition, lock, latencies),
                    daemon=True
                ).start()

                with lock:
                    condition.wait()

                # Enviar RTTs ao bootstrapper
                data_to_send = {
                    "type": "rtt_update",
                    "node": node,
                    "latencies": latencies
                }
                client_socket.send(json.dumps(data_to_send).encode('utf-8'))
                #print(f"RTTs sent to bootstrapper: {latencies}")

            elif message_code == 2:
                data = data_json['data']
                neighbors_list, address_port = data
                address, port_received = address_port

                my_tcp = address
                my_port = port_received

                threading.Thread(target=listen_for_connections, args=(my_tcp, my_port), daemon=True).start()

                # Chama connect_to_neighbors em uma thread
                threading.Thread(
                    target=connect_to_neighbors,
                    args=(neighbors_list, condition, lock, latencies),
                    daemon=True
                ).start()

                # Espera até que todos os RTTs sejam medidos
                with condition:
                    condition.wait()  # Espera o notify_all()

                print(f"All RTTs measured: {latencies}")

                # Enviar RTTs ao bootstrapper
                data_to_send = {
                    "type": "rtt_update",
                    "node": node,
                    "latencies": latencies
                }
                client_socket.send(json.dumps(data_to_send).encode('utf-8'))
                print(f"RTTs sent to bootstrapper: {latencies}")

                pc = data_json['pc']
                if pc:
                    pc_ip = my_tcp
                    pc_port = my_port + 1
                    threading.Thread(target=connect_to_pc, args=(pc_ip, pc_port), daemon=True).start()

            elif message_code == 3:
                print("No neighbors to connect to.")

        else:
            print("No data received from the bootstrapper")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        client_socket.close()



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

    connection_thread = threading.Thread(target=connect_to_bootstrapper, args=(bootstrapper_host, bootstrapper_port))
    connection_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
