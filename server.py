import json
import socket
import subprocess
import threading
import sys
import os
import time
import struct
from utils.videostream import VideoStream
from packets.rtp_packet import RtpPacket
from PIL import Image
from io import BytesIO

stop_stream_lock = threading.Lock()
# Lista de vídeos e portas onde cada um será transmitido
videos = {}
next_hops={}
stop_stream_destination=[]
stream_active=[]
client_requesting_stream={}

def stream_video(file, ip, port):
    """
    Função para iniciar o streaming de um vídeo.
    :param file: Caminho do arquivo de vídeo.
    :param ip: IP do servidor para o streaming.
    :param port: Porta onde o vídeo será transmitido.
    """
    ffmpeg_command = [
        "ffmpeg",
        "-re",                         # Simula taxa de leitura em tempo real
        "-i", file,                    # Input do arquivo de vídeo
        "-c:v", "libx264",             # Codec de vídeo
        "-preset", "fast",             # Configuração para tempo real
        "-f", "mpegts",                # Formato de streaming
        f"http://{ip}:{port}"           # Saída HTTP com IP e porta
    ]
    print(f"Iniciando streaming de {file} em {ip}:{port}")
    subprocess.run(ffmpeg_command)

def handle_client_connection(conn, addr):
    while True:
        try:
            data_encoded = conn.recv(1024).decode()
            if data_encoded:
                data_json = json.loads(data_encoded)
                print(f"Received data: {data_json}")

                # Identificar o tipo da mensagem
                message_code = data_json['type']  # Tipo da mensagem (0 ou 1)
                data = data_json['data']
                address = data['address']  # IP recebido
                port = data['port']   
                destinations = data['destinations']     # Porta recebida
                if message_code == 1:  # Mensagem do tipo 1
                    for d in destinations:
                        if d not in next_hops or next_hops[d] != address:
                            next_hops[d] = (address,port)
                            print(f"Destino {d} próximo passo {address} na porta {port}")

        except json.JSONDecodeError:
            print(f"Erro ao decodificar mensagem JSON de {addr}")
        except Exception as e:
                print(f"Erro ao processar a mensagem de {addr}: {e}")

    

def handle_socket_connect(address, port, sender, destination, code, streams=None):
    """
    Função para criar e gerenciar o socket UDP para conexão.
    Inclui lógica para enviar mensagens e, no caso de 'code == 2', as streams recebidas.
    """
    try:
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.settimeout(2.0)  # Configura o timeout para 1 segundo
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



def handle_udp_from_pcs(server_host, server_port):
    """
    Manipula as mensagens UDP para calcular RTT, responde com 'pong', processa mensagens JSON
    e realiza streaming de vídeos caso o código seja 3.
    """

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
            udp_socket.bind((server_host, server_port))
            print(f"UDP server listening at {server_host}:{server_port}")

            while True:
                # Receber dados do cliente
                data, addr = udp_socket.recvfrom(1024)
                if data:
                    message = data.decode()

                    # Responder ao "ping" com "pong"
                    if message == "ping":
                        udp_socket.sendto(b"pong", addr)
                        print(f"Received 'ping' from {addr}, sent 'pong'.")

                    # Receber e processar mensagens JSON
                    else:
                        try:
                            data_json = json.loads(message)
                            code = data_json.get("code")
                            destination = data_json.get("destination")
                            sender = data_json.get("sender")
                            
                            if code == 1:  # Mensagem de streams recebida
                                udp_socket.sendto(b"0", addr)  # Envia ACK

                                if sender in next_hops:
                                    udp_ip, port_ip = next_hops[sender]
                                    threading.Thread(
                                        target=handle_socket_connect,
                                        args=(udp_ip, port_ip, destination, sender, 2, videos),
                                        daemon=True
                                    ).start()

                            elif code == 3:  # Pedido de streaming de vídeo
                                udp_socket.sendto(b"0", addr)  # Envia ACK para o remetente original
                                
                                # Verifica se o vídeo solicitado está disponível
                                stream = data_json.get("stream")

                                if stream not in client_requesting_stream.keys():
                                    with stop_stream_lock:
                                        client_requesting_stream[stream] = []
                                        client_requesting_stream[stream].append(sender)
                                    
                                    if stream in videos:  # Verifica se a stream está no servidor
                                        print(f"Iniciando streaming da stream '{stream}' para {sender} via {destination}")

                                        # Verifica se o próximo nó está definido no dicionário next_hops
                                        if sender in next_hops:
                                            next_hop_ip, next_hop_port = next_hops[sender]  # Obtém o próximo nó
                                            print(f"Próximo nó: {next_hop_ip}:{next_hop_port}")

                                            # Inicia a thread para enviar o streaming para o próximo nó
                                            threading.Thread(
                                                target=send_stream,
                                                args=(stream, next_hop_ip, next_hop_port, destination, sender),
                                                daemon=True
                                            ).start()
                                        else:
                                            print(f"Sender '{sender}' não encontrado em next_hops.")
                                            error_msg = {"code": 404, "error": f"Sender '{sender}' não encontrado em next_hops"}
                                            udp_socket.sendto(json.dumps(error_msg).encode(), addr)
                                    else:
                                        print(f"Stream '{stream}' não encontrada no servidor.")
                                        error_msg = {"code": 404, "error": f"Stream '{stream}' não encontrada no servidor"}
                                        udp_socket.sendto(json.dumps(error_msg).encode(), addr)
                                else:
                                    with stop_stream_lock:
                                        client_requesting_stream[stream].append(sender)
                                    
                            elif code == 6:
                                udp_socket.sendto(b"0", addr)
                                sender = data_json.get("sender")
                                stream = data_json.get("stream")
                                with stop_stream_lock:
                                    client_requesting_stream[stream].remove(sender)
                                    

                            else:
                                print(f"Mensagem JSON com código desconhecido recebida de {addr}: {data_json}")

                        except json.JSONDecodeError:
                            print(f"Erro ao decodificar mensagem JSON de {addr}: {message}")

    except Exception as e:
        print(f"Erro no servidor UDP: {e}")
    except Exception as e:
        print(f"Error in UDP server: {e}")



def send_stream(stream, next_hop_ip, next_hop_port, sender, destination):
    """
    Envia pacotes RTP (apenas frames) para o próximo nó na rota até o destino final.
    """
    video = VideoStream("Videos/" + stream)
    try:
        frame_number = 0
        d=[]
        while True:
            with stop_stream_lock:
                values_list = client_requesting_stream.get(stream)
                for value in values_list:
                    d.append(value)
                if not d:
                    break
            for dest in d:
                time.sleep(0.05)  # Pausa entre frames para simular streaming em tempo real
                
                # Obter próximo frame usando .get_next_frame()
                frame_data = video.get_next_frame()

                # Construir o cabeçalho (reserva o número exato de bytes para cada campo)
                destination_bytes = dest.encode("utf-8").ljust(3, b'\x00')  # Máximo 3 bytes, preenchendo com '\x00'
                sender_bytes = sender.encode("utf-8").ljust(3, b'\x00')  # Máximo 3 bytes, preenchendo com '\x00'

                # Criar pacote RTP com o payload
                rtp_packet = make_rtp_packet(frame_data, frame_number)

                # Pacote final (cabeçalho + pacote RTP)
                packet = destination_bytes + sender_bytes + rtp_packet
                # Enviar pacote para o próximo nó
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as send_socket:
                    send_socket.sendto(packet, (next_hop_ip, next_hop_port))

                frame_number += 1
                d=[]
    except Exception as e:
        print(f"Erro no streaming da stream '{stream}' para {destination} via {sender}: {e}")

def make_rtp_packet(payload, frame_nr):
    """
    Cria um pacote RTP com os dados do payload.
    """
    version = 2
    padding = 0
    extension = 0
    cc = 0
    marker = 0
    pt = 26  # MJPEG type
    seqnum = frame_nr
    ssrc = 0

    rtp_packet = RtpPacket()
    rtp_packet.encode(version, padding, extension, cc, seqnum, marker, pt, ssrc, payload)
    return rtp_packet.get_packet()



def start_server(ip, port):
    """
    Inicia o servidor para conexões TCP e UDP.
    """
    # Iniciar o servidor UDP em paralelo
    udp_thread = threading.Thread(target=handle_udp_from_pcs, args=(ip, port), daemon=True)
    udp_thread.start()

    # Iniciar o servidor TCP
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((ip, port))
        server_socket.listen()
        print(f"Server started at {ip}:{port}, waiting for connections...")

        while True:
            conn, addr = server_socket.accept()
            print(f"TCP connection accepted from {addr}")
            threading.Thread(target=handle_client_connection, args=(conn, addr)).start()


def start_streaming(ip):
    threads = []
    for video_file, port in videos.items():
        thread = threading.Thread(target=stream_video, args=(video_file, ip, port))
        thread.start()
        threads.append(thread)
    
    for thread in threads:
        thread.join()

def load_videos():

    global videos  # Acessar o dicionário global
    video_directory = os.path.join(os.getcwd(), "Videos")  # Caminho completo para a diretoria "Videos"

    if not os.path.exists(video_directory):
        print("A diretoria 'Videos' não existe.")
        return

    # Percorrer todos os arquivos na diretoria "Videos"
    for filename in os.listdir(video_directory):
        filepath = os.path.join(video_directory, filename)

        # Verificar se é um arquivo de vídeo
        if os.path.isfile(filepath) and filename.endswith(('.mp4', '.avi', '.mov', '.mkv', '.Mjpeg')):
            file_size = os.path.getsize(filepath)  # Obtém o tamanho do arquivo em bytes
            videos[filename] = file_size  # Adicionar ao dicionário global

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python name.py <IP> <PORT>")
        sys.exit(1)

    load_videos()

    server_ip = sys.argv[1]
    try:
        server_port = int(sys.argv[2])
    except ValueError:
        print("Port should be an integer")
        sys.exit(1)

    # Start the server to handle client connections for stream information
    threading.Thread(target=start_server, args=(server_ip, server_port), daemon=True).start()

    # Start streaming videos
    #start_streaming(server_ip)

    # Keep the main thread running
    try:
        while True:
            pass
    except KeyboardInterrupt:
        print("Shutting down...")