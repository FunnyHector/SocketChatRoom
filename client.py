import sys
import socket
import select

# Specify where the server is to connect to
SERVER_ADDRESS = '127.0.0.1'
SERVER_PORT = 5001


def run_client():
    """sockfd
    Run the client. This should listen for input text from the user
    and send messages to the server. Responses from the server should
    be printed to the console.
    """

    # Create a socket and connect to the server
    client_socket = socket.socket()
    client_socket.connect((SERVER_ADDRESS, SERVER_PORT))
    socket_list = [sys.stdin, client_socket]

    # Log that it has connected to the server
    print('[Log] Connected to chat server. Type "/HELP" for help.')
    print('[Log] Or type to send messages:')

    # Start listening for input and messages from the server
    while True:
        # Listen to the sockets (and command line input) until something happens
        ready_to_read, ready_to_write, in_error = select.select(socket_list, [], [], 0)

        # When one of the inputs are ready, process the message
        for sock in ready_to_read:
            # The server has sent a message
            if sock == client_socket:
                # decode the data coming from the socket and print it out to the console
                msg = sock.recv(1024).decode().strip()

                # to prevent the server broadcast a lot of crap
                if not msg:
                    continue
                elif msg is not '' or msg is not '\n':
                    print(msg)

            else:
                # The user entered a message
                msg = sys.stdin.readline()
                if msg == '/HELP':
                    print_help()
                elif msg == '/QUIT':
                    sys.exit()
                else:
                    # Send the message to the server
                    client_socket.send(msg.encode())


def print_help():
    print('/NICK <name>\n\tEnter a unique nickname which is then displayed in front of your messages.')
    print('/WHO\n\tList all the users in current chat room.')
    print('/MSG <name> <message>\n\tPrivate message to a specific user. The message will not be shown to others')
    print('/JOIN <chat_room_name>\n\tJoin into the specified chat room.')
    print('/ROOM\n\tShow which chat room you are in.')
    print('/QUIT\n\tQuit')


if __name__ == '__main__':
    run_client()
