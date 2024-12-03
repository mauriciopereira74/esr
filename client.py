import socket
import sys
import json
import threading
import time

rtt_lock = threading.Lock()
rtt_condition = threading.Condition(rtt_lock)
latencies = {}
streams=[]

def handle_connection(host, port):
    global calculated_rtt

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((host, int(port)))
            print(f"UDP socket prepared for {host}:{port}")

            sock.settimeout(0.5)  # Configura o timeout de 0.5 segundos

            while True:
                try:
                    start_time = time.time()
                    message = json.dumps({
                        "code": 0,
                    })
                    sock.send(message.encode())  # Envia uma mensagem "ping"
                    data, addr = sock.recvfrom(1024)  # Aguarda a resposta "pong"
                    end_time = time.time()

                    if data.decode() == "pong":  # Verifica se a resposta é "pong"
                        rtt = (end_time - start_time) * 1000  # Calcula o RTT em milissegundos
                        print(f"Pong recebido de {addr} com RTT de {rtt:.2f} ms")
                        break  # Sai do loop após receber o "pong"
                except socket.timeout:
                    print("Timeout: Não recebeu pong, reenviando ping...")
                    # Timeout expirou, o loop continua e envia outro "ping"
                except Exception as e:
                    print(f"Erro ao processar ping/pong: {e}")
                    break
            with rtt_lock:
                latencies[f"{host}:{port}"] = rtt
                rtt_condition.notify_all()

            # Interface inicial
            while True:
                print("\n-------------------------")
                print("1 - Ver streams disponíveis")
                print("2 - Desligar")
                option = input("Escolha uma opção: ")

                if option == "1":
                    # Solicitar streams disponíveis
                    sock.settimeout(0.1)  # Set a timeout of 0.5 seconds

                    while True:
                        try:
                            message = json.dumps({
                                    "code": 1,  # Tipo de mensagem 2
                                    "sender": "PC1",
                                    "destination":"S"
                            })
                            sock.send(message.encode())  # Send the request
                            data, addr = sock.recvfrom(1024)  # Wait for a response with a timeout
                            if data:  # If data is received
                                ack = data.decode() # Process the received data
                                print(f"ACK received: {ack}")
                                break  # Exit the loop if acknowledgment is received
                        except socket.timeout:
                            print("Timeout: No response received, resending request...")
                        except Exception as e:
                            print(f"An error occurred: {e}")
                            break

                    # Interface para escolher uma stream
                    while True:
                        print("\n--- Streams Disponíveis ---")
                        for i, stream in enumerate(streams, start=1):
                            print(f"{i} - {stream}")
                        print("0 - Voltar")

                        stream_option = input("Escolha uma stream para visualizar (ou 0 para voltar): ")

                        if stream_option == "0":
                            break  # Voltar para a interface inicial
                        elif stream_option.isdigit() and 1 <= int(stream_option) <= len(streams):
                            stream_name = streams[int(stream_option) - 1]
                            print(f"Você escolheu visualizar a stream: {stream_name}")

                            # Solicitar a stream específica
                            request_message = f"view_stream:{stream_name}"
                            sock.send(request_message.encode())
                            print(f"Solicitando stream: {stream_name}...")

                            # Receber a stream (simulação)
                            print("Recebendo stream (Ctrl+C para interromper)...")
                            try:
                                while True:
                                    data, addr = sock.recvfrom(1024)
                                    if not data:
                                        break
                                    print(f"Stream recebido: {data.decode()}")
                            except KeyboardInterrupt:
                                print("\nInterrompendo visualização da stream.")
                                continue
                        else:
                            print("Opção inválida. Tente novamente.")

                elif option == "2":
                    # Desligar
                    print("Desligando conexão.")
                    break

                else:
                    print("Opção inválida. Tente novamente.")

    except Exception as e:
        print(f"Failed to communicate over UDP with {host}:{port}: {e}")


    

def handle_connection_bind(pc_address, pc_port, listen=False):

    global calculated_rtt

    try:
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.bind((pc_address, pc_port))  # Vincula ao endereço com uma porta específica
            print(f"UDP socket bound to {pc_address}:{pc_port}")

            if listen:
                print(f"Listening for data from {pc_address}:{pc_port}")
                while True:
                    data, _ = udp_socket.recvfrom(1024)
                    if data:
                        print(f"Received data from {pc_address}:{pc_port}: {data.decode()}")
                    else:
                        print("Connection closed by remote pc_address.")
                        break
            else:
                # Cálculo do RTT
                start_time = time.time()
                message = json.dumps({
                    "code": 0,
                })
                udp_socket.send(message.encode())  # Envia uma mensagem "ping"
                data, addr = udp_socket.recvfrom(1024)  # Aguarda a resposta "pong"
                end_time = time.time()

                if data and data.decode() == "pong":
                    rtt = (end_time - start_time) * 1000  # RTT em milissegundos
                    print(f"RTT calculado para {pc_address}:{pc_port}: {rtt:.2f} ms")

                    # Atualiza a variável de RTT e sinaliza a condição
                    with rtt_lock:
                        calculated_rtt = {"neighbor": f"{pc_address}:{pc_port}", "rtt": rtt}
                        rtt_condition.notify_all()

    except Exception as e:
        print(f"Failed to communicate over UDP with {pc_address}:{pc_port}: {e}")


def handle_message(data):
    message_code = data['code']
    print(message_code)
    if message_code == 0:
        # Vizinhos disponíveis, mas ainda não conectados, manter ouvindo
        address, port_received = data['data']
        my_udp = address
        my_port = port_received+1
        threading.Thread(target=handle_connection_bind, args=(my_udp, my_port, True)).start()
    elif message_code == 1:
        # Conexão direta disponível com vizinhos
        for neighbor in data['data']:
            threading.Thread(target=handle_connection, args=(neighbor[0], neighbor[1]+1)).start()
    elif message_code == 2:
        neighbors_list, address_port = data['data']
        address, port_received = address_port

        my_udp = address
        my_port = port_received+1

        threading.Thread(target=handle_connection_bind, args=(my_udp, my_port, True)).start()

        for neighbor in neighbors_list:
            threading.Thread(target=handle_connection, args=(neighbor[0], neighbor[1]+1)).start()


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

                    # Aguarda o cálculo do RTT antes de continuar
                    with rtt_lock:
                        rtt_condition.wait()

                    # Envia o RTT calculado ao bootstrapper
                    if latencies:
                        rtt_message = {"code": 1, "node": "client_node", "latencies": latencies}
                        client_socket.send(json.dumps(rtt_message).encode('utf-8'))
                        print(f"RTT enviado ao bootstrapper: {rtt_message}")
                    else:
                        # Caso não haja RTT calculado, envia mensagem de código 10
                        rtt_message = {"code": 10, "node": "client_node", "message": "No latencies to send"}
                        client_socket.send(json.dumps(rtt_message).encode('utf-8'))
                        print(f"Mensagem de código 10 enviada ao bootstrapper: {rtt_message}")
                else:
                    break
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python client.py <BOOTSTRAPPER_IP> <BOOTSTRAPPER_PORT>")
        sys.exit(1)

    bootstrapper_host = sys.argv[1]
    bootstrapper_port = int(sys.argv[2])

    # Conecta ao bootstrapper
    threading.Thread(target=connect_to_bootstrapper, args=(bootstrapper_host, bootstrapper_port)).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
