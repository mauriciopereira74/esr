import socket
import sys
import json
import threading
import time

def handle_connection(host, port, listen=False):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            # No UDP, o connect() define o endereço de destino para chamadas de send() e o endereço de origem esperado para recv()
            sock.connect((host, int(port)))
            print(f"UDP socket prepared for {host}:{port}")

            if listen:
                # Se listen for True, mantenha o socket ouvindo por dados
                print(f"Listening for data from {host}:{port}")
                while True:
                    data, _ = sock.recvfrom(1024)
                    if data:
                        print(f"Received data from {host}:{port}: {data.decode()}")
                    else:
                        print("Connection closed by remote host.")
                        break
            else:
                # Se não for para ouvir, apenas envie uma mensagem inicial
                initial_message = "Hello from UDP client"
                sock.send(initial_message.encode('utf-8'))
                print(f"Sent initial message to {host}:{port} via UDP")
    except Exception as e:
        print(f"Failed to communicate over UDP with {host}:{port}: {e}")

def request_streams(client_socket):
    try:
        request_message = json.dumps({"request": "streams"})
        client_socket.send(request_message.encode('utf-8'))

        # Aguarda a resposta do servidor
        response = client_socket.recv(4096)
        if response:
            streams = json.loads(response).get("streams", [])
            if streams:
                print("Available streams:")
                for index, stream in enumerate(streams):
                    print(f"{index + 1}. {stream}")
                return streams
            else:
                print("No streams available.")
                return []
        else:
            print("No response received for streams request.")
            return []
    except Exception as e:
        print(f"Error while requesting streams: {e}")
        return []

def choose_stream(client_socket, streams):
    try:
        while True:
            print("\nSelect a stream by number or type '0' to go back:")
            user_input = input("> ").strip()
            if user_input == "0":
                print("Returning to main menu...")
                break
            elif user_input.isdigit() and 1 <= int(user_input) <= len(streams):
                chosen_stream = streams[int(user_input) - 1]
                print(f"You chose the stream: {chosen_stream}")

                # Lógica para começar o streaming
            else:
                print("Invalid selection. Try again.")
    except Exception as e:
        print(f"Error while choosing a stream: {e}")

def connect_to_bootstrapper(host, port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.connect((host, port))
            print(f"Connected to bootstrapper at {host}:{port}")

            # Thread para escutar mensagens recebidas
            def listen_to_bootstrapper():
                while True:
                    try:
                        data_encoded = client_socket.recv(1024)
                        if data_encoded:
                            data = json.loads(data_encoded)
                            print(f"Received data: {data}")

                            message_code = data.get('code', -1)
                            if message_code == 0:
                                # Conexão direta disponível com vizinhos
                                for neighbor in data['data']:
                                    threading.Thread(target=handle_connection, args=(neighbor[0], neighbor[1])).start()
                            elif message_code == 1:
                                # Vizinhos disponíveis, mas ainda não conectados
                                for neighbor in data['data']:
                                    print("Neighbor available but not yet connected, setting up listening UDP socket.")
                                    threading.Thread(target=handle_connection, args=(neighbor[0], neighbor[1], True)).start()
                            elif message_code == 2:
                                # Vizinhos conectados sem interfaces válidas
                                print("Neighbors connected but with invalid interfaces.")
                            else:
                                print("Unknown message code received.")
                        else:
                            print("No data received, connection may be closed.")
                            break
                    except Exception as e:
                        print(f"Error while receiving data: {e}")
                        break

            listener_thread = threading.Thread(target=listen_to_bootstrapper, daemon=True)
            listener_thread.start()

            while True:
                print("\n'1' to request available streams ; '2' to choose a stream ; '0' to close the client:")
                user_input = input("> ").strip().lower()
                if user_input == "1":
                    available_streams = request_streams(client_socket)
                elif user_input == "2":
                    if 'available_streams' in locals() and available_streams:
                        choose_stream(client_socket, available_streams)
                    else:
                        print("No streams available. Please request streams first.")
                elif user_input == "0":
                    print("Closing the client...")
                    break
                else:
                    print("Unknown command. Try again.")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python client.py <BOOTSTRAPPER_IP> <BOOTSTRAPPER_PORT>")
        sys.exit(1)

    bootstrapper_host = sys.argv[1]
    bootstrapper_port = int(sys.argv[2])

    # Connect to the bootstrapper
    threading.Thread(target=connect_to_bootstrapper, args=(bootstrapper_host, bootstrapper_port)).start()