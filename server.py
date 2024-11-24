# pylint: disable=invalid-name
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
    
    # Enviar a lista de streams disponíveis
    response = ",".join(videos.keys())
    conn.send(response.encode('utf-8'))
    print(f"Sent available streams to {addr}: {response}")
    

def start_server(ip, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.bind((ip, port))
        server_socket.listen()
        print(f"Server started at {ip}:{port}, waiting for connections...")

        while True:
            conn, addr = server_socket.accept()
            print(f"Connection accepted from {addr}")
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