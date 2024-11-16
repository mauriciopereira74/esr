import socket
import sys
import json
import threading
import logging

# Setup logging
logging.basicConfig(
    filename='client.log',
    filemode='a',  # Append to the existing log file
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def connect_to_bootstrapper(host, port):
    try:
        # Create a socket object
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            # Connect to the bootstrapper
            s.connect((host, port))
            logging.info(f"Connected to bootstrapper at {host}:{port}")
            
            
    
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    finally:
        logging.info("Disconnected from bootstrapper")

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

    # Connect to the bootstrapper in a separate thread to handle communication
    connection_thread = threading.Thread(target=connect_to_bootstrapper, args=(bootstrapper_host, bootstrapper_port))
    connection_thread.start()

    # Keep the main thread running
    try:
        while True:
            pass
    except KeyboardInterrupt:
        logging.info("Shutting down...")
        connection_thread.join()  # Ensure the connection thread has cleaned up properly
