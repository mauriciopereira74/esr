# pylint: disable=invalid-name
import json
import socket
import subprocess
import threading
import sys


# Lista de vídeos e portas onde cada um será transmitido
videos = {
    "video1.mp4": 8080,
    "video2.mp4": 8081,
    "video3.mp4": 8082 
}

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
    """
    Manipula a conexão TCP inicial com o cliente para enviar streams disponíveis.
    """
    try:
        # Enviar a lista de streams disponíveis
        response = ",".join(videos.keys())
        conn.send(response.encode('utf-8'))
        print(f"Sent available streams to {addr}: {response}")

        try:
            while True:
                # Aguarda uma mensagem do cliente
                data = conn.recv(1024)
                if not data:
                    print(f"Conexão encerrada pelo cliente {addr}")
                    break

                try:
                    # Decodifica a mensagem como JSON
                    message = json.loads(data.decode('utf-8'))
                    code = message.get("code")

                    if code == 1:
                        print(f"Mensagem recebida de {addr}: {message}")

                        # Envia um ACK "0" de confirmação
                        ack = "0"
                        conn.send(ack.encode('utf-8'))
                        print(f"ACK '0' enviado para {addr}")

                        # Envia a lista de streams disponíveis
                        response = {
                            "streams": list(videos.keys())
                        }
                        conn.send(json.dumps(response).encode('utf-8'))
                        print(f"Streams enviados para {addr}: {response['streams']}")

                        # Aguarda confirmação de recebimento do cliente
                        confirmation = conn.recv(1024)
                        if confirmation:
                            confirmation_message = confirmation.decode('utf-8')
                            if confirmation_message == "0":
                                print(f"Confirmação de recebimento dos streams recebida de {addr}")
                            else:
                                print(f"Confirmação inválida recebida de {addr}: {confirmation_message}")

                    else:
                        print(f"Mensagem com código desconhecido recebida de {addr}: {message}")

                except json.JSONDecodeError:
                    print(f"Erro ao decodificar mensagem JSON de {addr}: {data.decode('utf-8')}")
        except Exception as e:
            print(f"Erro ao processar a mensagem de {addr}: {e}")

    except Exception as e:
        print(f"Erro ao manipular conexão com o cliente {addr}: {e}")
    finally:
        conn.close()
        print(f"Conexão TCP com {addr} encerrada.")


def handle_udp_rtt(server_host, server_port):
    """
    Manipula as mensagens UDP para calcular RTT, responde com 'pong' e processa mensagens JSON.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
            udp_socket.bind((server_host, server_port))
            print(f"UDP server listening at {server_host}:{server_port}")
            data, addr = udp_socket.recvfrom(1024)
            if data:
                print(f"Received UDP message from {addr}: {data.decode()}")

                # Responder ao ping com "pong"
                if data.decode() == "ping":
                    udp_socket.sendto(b"pong", addr)
                    print(f"Sent 'pong' to {addr}")

            while True:
                # Receber dados do cliente
                data, addr = udp_socket.recvfrom(1024)
                if data:
                    message = data.decode()
                    print(f"Received UDP message from {addr}: {message}")

                    # Responder ao "ping" com "pong"
                    if message == "ping":
                        udp_socket.sendto(b"pong", addr)
                        print(f"Sent 'pong' to {addr}")

                    # Receber e processar mensagens JSON após "ping-pong"
                    else:
                        try:
                            # Decodifica a mensagem como JSON
                            data_json = json.loads(message)
                            code = data_json.get("code")
                            sender = data_json.get("sender")
                            destination = data_json.get("destination")

                            if code == 1:
                                # Enviar ACK ("0")
                                udp_socket.sendto(b"0", addr)
                                print(f"ACK '0' enviado para {addr}")

                                # Enviar a lista de streams
                                response = {
                                    "code": 2,
                                    "streams": list(videos.keys()),
                                    "sender": destination,  # Troca sender pelo destination recebido
                                    "destination": sender  # Troca destination pelo sender recebido
                                }
                                udp_socket.sendto(json.dumps(response).encode('utf-8'), addr)
                                print(f"Lista de streams enviada para {addr}: {response}")

                            else:
                                print(f"Mensagem JSON com código desconhecido recebida de {addr}: {data_json}")

                        except json.JSONDecodeError:
                            print(f"Erro ao decodificar mensagem JSON de {addr}: {message}")

    except Exception as e:
        print(f"Error in UDP server: {e}")
        

    except Exception as e:
        print(f"Error in UDP server: {e}")

def start_server(ip, port):
    """
    Inicia o servidor para conexões TCP e UDP.
    """
    # Iniciar o servidor UDP em paralelo
    udp_thread = threading.Thread(target=handle_udp_rtt, args=(ip, port), daemon=True)
    udp_thread.start()

    # Iniciar o servidor TCP
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
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

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python name.py <IP> <PORT>")
        sys.exit(1)

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