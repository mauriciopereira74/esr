import socket
import sys
import json
import threading
import time
import os
from tkinter import *
from PIL import Image, ImageTk
from io import BytesIO

rtt_lock = threading.Lock()
rtt_condition = threading.Condition(rtt_lock)
latencies = {}
streams=[]


CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"


class StreamClient:
    def __init__(self, master, host, port):
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.exit_client)

        self.host = host
        self.port = port+1
        self.stop_event = threading.Event()
        self.session_id = os.getpid()  # ID único baseado no PID
        self.frame_nr = 0

        self.create_widgets()

        # Criar socket UDP para mensagens
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind((host, self.port))

        # Inicia a thread para receber frames (mensagens do tipo 4)
        threading.Thread(target=self.handle_frames, daemon=True).start()

    def create_widgets(self):
        """Construir GUI."""
        self.label = Label(self.master, height=19)
        self.label.grid(row=0, column=0, columnspan=4, sticky=W + E + N + S, padx=5, pady=5)

        # Botão de saída
        self.exit_btn = Button(self.master, text="Exit", command=self.exit_client, width=20, padx=3, pady=3)
        self.exit_btn.grid(row=1, column=2, padx=2, pady=2)

    def write_frame(self, data):
        """Salva o frame como arquivo temporário."""
        cachename = CACHE_FILE_NAME + str(self.session_id) + CACHE_FILE_EXT
        with open(cachename, "wb") as file:
            file.write(data)
        return cachename

    def update_movie(self, image_file):
        
        """Atualiza o frame exibido na GUI."""

        print(image_file)
        
        photo = ImageTk.PhotoImage(Image.open(image_file))
        self.label.configure(image=photo, height=288)
        self.label.image = photo
        

    def handle_frames(self):
        """
        Processa frames recebidos via socket UDP e atualiza a GUI.
        """
        while True:
            data, addr = self.udp_socket.recvfrom(65525)  # Recebe dados do cliente

            # Extração do cabeçalho e do payload
            if len(data) < 6:  # Verifica se há pelo menos o cabeçalho
                print(f"Pacote inválido recebido de {addr}. Ignorando.")
                continue

            destination = data[:3].decode("utf-8").strip()
            sender = data[3:6].decode("utf-8").strip()
            rtp_packet = data[6:]  # O restante é o pacote RTP

            # Extraindo o frame_data do RTP Packet
            try:
                frame_data = self.extract_frame_data(rtp_packet)
            except Exception as e:
                print(f"Erro ao extrair frame_data de {addr}: {e}")
                continue

            # Exibir o frame na GUI diretamente da memória
            try:
                image = Image.open(BytesIO(frame_data))  # Carrega o frame diretamente como um arquivo temporário
                photo = ImageTk.PhotoImage(image)
                self.label.configure(image=photo, height=288)
                self.label.image = photo  # Armazena a referência para evitar garbage collection
            except Exception as e:
                print(f"Erro ao exibir o frame na GUI: {e}")

            self.frame_nr += 1


    def extract_frame_data(self, rtp_packet):
        """
        Extrai o payload (frame_data) de um RTP Packet.
        """
        # RTP Header é de tamanho fixo: 12 bytes
        header_size = 12
        if len(rtp_packet) < header_size:
            raise ValueError("Pacote RTP inválido: muito pequeno para conter cabeçalho RTP.")
        
        # Ignorar os primeiros 12 bytes do cabeçalho RTP e retornar o payload
        return rtp_packet[header_size:]

       
    def exit_client(self):
        """Fecha o cliente."""
        self.stop_event.set()
        self.udp_socket.close()
        self.master.destroy()


def start(host,port):
    
    root = Tk()
    print(host)
    print(port)
    app = StreamClient(root, host, port)
    app.master.title("Stream Client")
    root.mainloop()


def handle_streams(host, port):
    """
    Função para receber mensagens do tipo 2 (streams) e do tipo 4 (frames).
    Para o tipo 2, exibe as streams disponíveis.
    Para o tipo 4, exibe os frames diretamente no ecrã.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind((host, int(port)))  # O socket agora fica "ouvindo" na porta especificada
            print(f"UDP socket bound to {host}:{port}")
            # Loop infinito para receber mensagens do cliente
            while True:
                try:
                    data, addr = sock.recvfrom(65525)  # Recebe dados do cliente
                    try:
                        # Tenta decodificar a mensagem recebida como JSON
                        data_json = json.loads(data.decode('utf-8'))
                    except json.JSONDecodeError:
                        print(f"Mensagem inválida recebida de {addr}: {data.decode('utf-8')}")
                        continue

                    # Processar mensagens do tipo 2 (streams disponíveis)
                    if data_json.get("code") == 2:
                        sender = data_json.get("sender", "Desconhecido")
                        global streams
                        streams = data_json.get("streams", [])

                        print(f"\nMensagem recebida de {addr}:")
                        print("Streams disponíveis:")

                        # Exibe as streams recebidas
                        for i, stream in enumerate(streams, start=1):
                            print(f"{i}. {stream}")
                        print_menu()

                        # Envia um ACK com código 0 de volta ao cliente
                        ack_message = "0"
                        sock.sendto(ack_message.encode(), addr)

                    else:
                        print(f"Mensagem ignorada: {data_json}")

                except socket.timeout:
                    # Timeout pode ser usado se necessário, mas aqui está infinito
                    print("Timeout ao aguardar mensagem.")
                except Exception as e:
                    print(f"Erro ao processar mensagem do cliente: {e}")

    except Exception as e:
        print(f"Erro ao iniciar socket UDP: {e}")


def display_frame(frame_data):
    """
    Exibe o frame de vídeo no ecrã usando PIL.
    """
    try:
        # Converte os bytes do frame para uma imagem usando PIL
        frame_image = Image.open(BytesIO(frame_data))
        frame_image.show()  # Exibe a imagem no visualizador padrão
    except Exception as e:
        print(f"Erro ao exibir frame: {e}")


def handle_connection(host, port):
    global calculated_rtt
    global streams

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

            print_menu()
            while True:
                
                option = input()
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
                                break  # Exit the loop if acknowledgment is received
                        except socket.timeout:
                            print("Timeout: No response received, resending request...")
                        except Exception as e:
                            print(f"An error occurred: {e}")
                            break

                elif option == "2":
                        if streams:
                            print("\n-------------------------")
                            print("Escolha uma das Streams Disponiveis:")
                            stream_keys = list(streams.keys())  # Extrai as chaves (nomes dos vídeos) do dicionário
                            for i, stream in enumerate(stream_keys, start=1):
                                print(f"{i} - {stream}")
                            print("0 - Voltar atrás")
                            print("-------------------------\n")
                            option = input("Escolha uma opção:")
                            
                            if option == "0":
                                print_menu()
                                break
                            while True:
                                try:
                                    message = json.dumps({
                                            "code": 3,
                                            "sender": "PC1",
                                            "stream": stream_keys[int(option)-1],
                                            "destination": "S"
                                    })
                                    sock.send(message.encode())
                                    sock.settimeout(1)  # Send the request
                                    data, addr = sock.recvfrom(1024)  # Wait for a response with a timeout
                                    if data:  # If data is received
                                        ack = data.decode() # Process the received data
                                        break  # Exit the loop if acknowledgment is received
                                except socket.timeout:
                                    print("Timeout: No response received, resending request...")
                        else:
                            print("Ainda não foi realizado o pedido de streams disponiveis: Opção 1 do menu principal")


                elif option == "0":
                    # Desligar
                    print("Desligando conexão.")
                    break

                else:
                    print("Opção inválida. Tente novamente.")

    except Exception as e:
        print(f"Failed to communicate over UDP with {host}:{port}: {e}")


def print_menu():
    print("\n---------MENU PRINCIPAL--------")
    print("1 - Ver streams disponíveis")
    print("2 - Escolher Streams")
    print("0 - Desligar")
    print("Escolha uma opção: ")





def handle_message(data):
    message_code = data['code']
    print(message_code)
    if message_code == 0:
        # Vizinhos disponíveis, mas ainda não conectados, manter ouvindo
        address, port_received = data['data']
        my_udp = address
        my_port = port_received +1
        threading.Thread(target=handle_connection_bind, args=(my_udp, my_port)).start()
    elif message_code == 1:
        neighbors_list, address_port = data['data']
        address, port_received = address_port

        my_udp = address
        my_port = port_received+2
        threading.Thread(target=start, args=(my_udp,my_port)).start()
        threading.Thread(target=handle_streams, args=(my_udp, my_port)).start()

        for neighbor in neighbors_list:
            threading.Thread(target=handle_connection, args=(neighbor[0], neighbor[1]+1)).start()
            
    elif message_code == 2:
        neighbors_list, address_port = data['data']
        address, port_received = address_port

        my_udp = address
        my_port = port_received+1

        threading.Thread(target=handle_connection_bind, args=(my_udp, my_port)).start()

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


















def handle_connection_bind(host, port):
    global calculated_rtt
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind((host, int(port)))  # O socket agora fica "ouvindo" na porta especificada
            print(f"UDP socket bound to {host}:{port}")

            # Remover o timeout para esperar indefinidamente pela primeira mensagem
            print("Aguardando primeira mensagem do cliente...")
            data, addr = sock.recvfrom(1024)  # Espera pela primeira mensagem do cliente

            data_json = json.loads(data.decode())  # Decodifica a mensagem
            print(f"\nPrimeira mensagem recebida de {addr}: {data_json}\n")

            # Responde com um ACK para o cliente após receber a primeira mensagem
            ack_message = json.dumps({"code": 0})  # "ping" ACK
            sock.sendto(ack_message.encode(), addr)

            # Após a primeira mensagem, configurar o timeout e continuar o processo
            sock.settimeout(0.5)  # Configura o timeout de 0.5 segundos para as próximas mensagens

            # Processo de enviar ping e receber pong
            while True:
                try:
                    start_time = time.time()
                    message = json.dumps({
                        "code": 0,  # Envia "ping"
                    })
                    sock.sendto(message.encode(), addr)  # Envia "ping"
                    data, addr = sock.recvfrom(1024)  # Aguarda a resposta "pong"
                    end_time = time.time()

                    if data.decode() == "pong":  # Verifica se a resposta é "pong"
                        rtt = (end_time - start_time) * 1000  # Calcula o RTT em milissegundos
                        print(f"RTT: {rtt}ms")
                        with rtt_lock:
                            latencies[f"{addr[0]}:{port}"] = rtt
                            rtt_condition.notify_all()
                        break

                except socket.timeout:
                    print("Timeout: Não recebeu pong, reenviando ping...")
                    # Timeout expirou, o loop continua e envia outro "ping"
                except Exception as e:
                    print(f"Erro ao processar ping/pong: {e}")
                    break

            print("\n-------------------------")
            print("1 - Ver streams disponíveis")
            print("2 - Escolher Streams")
            print("0 - Desligar")
            print("Escolha uma opção: ")
            
            while True:
                
                option = input()

                if option == "1":
                    # Solicitar streams disponíveis
                    sock.settimeout(0.1)  # Set a timeout of 0.5 seconds

                    while True:
                        try:
                            message = json.dumps({
                                    "code": 1,  # Tipo de mensagem 1
                                    "sender": "PC1",
                                    "destination":"S"
                            })
                            print(f"address{addr}")
                            sock.sendto(message.encode(), addr)  # Send the request
                            data, addr = sock.recvfrom(1024)  # Wait for a response with a timeout
                            if data:  # If data is received
                                ack = data.decode() # Process the received data
                                break  # Exit the loop if acknowledgment is received
                        except socket.timeout:
                            print("Timeout: No response received, resending request...")
                        except Exception as e:
                            print(f"An error occurred: {e}")
                            break

                    # Interface para escolher uma stream
                    while True:
                        # Recebe os dados do socket
                        data, addr = sock.recvfrom(1024)
                        message = json.loads(data.decode())

                        print(f"Mensagem recebida de {addr}: {message}")

                        # Verifica se o código é 2, o que indica que o sender está enviando streams
                        if message.get("code") == 2:
                            sender = message.get("sender")
                            streams = message.get("streams")

                            if sender and streams:
                                print(f"\n--- Streams Disponíveis do Servidor {sender} ---")
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
                            sock.sendto(request_message.encode(), addr)
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
