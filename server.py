import socket
import select
import sqlite3

# Define where the server is running. 127.0.0.1 is the loopback address,
# meaning it is running on the local machine.
HOST = "127.0.0.1"
PORT = 5001


def run_server():
    """
    Start a server to facilitate the chat between clients.
    The server uses a single socket to accept incoming connections
    which are then added to a list (socket_list) and are listened to
    to receive incoming messages. Messages are then stored in a database
    and are transmitted back out to the clients.
    """

    # Initialise a sqlite3 database connection and its cursor
    c, conn = initialise_sqlite()

    # Create a socket for the server to listen for connecting clients
    server_socket = socket.socket()
    server_socket.bind((HOST, PORT))
    server_socket.listen(10)

    # Create a list to manage all of the sockets and add the server socket to this list
    socket_list = [server_socket]

    # create a dict to keep record of all client sockets and their ids
    socket_dict = dict()

    # some welcome message
    print('[Log] Server is running successfully. Listening.')

    # Start listening for input from both the server socket and the clients
    while True:

        # Monitor all of the sockets in socket_list until something happens
        ready_to_read, ready_to_write, in_error = select.select(socket_list, [], [], 0)

        # When something happens, check each of the ready_to_read sockets
        for sock in ready_to_read:
            # A new connection request received
            if sock == server_socket:
                accept_new_connection(c, conn, server_socket, socket_dict, socket_list)

            # A message from a client has been received
            else:
                # Extract the data from the socket
                data = sock.recv(1024).decode().strip()

                # to prevent the server broadcast a lot of crap
                if not data or data == '' or data == '\n':
                    continue

                # get the client's socket_id, nickname and chat room
                client_sock_id = sock.getpeername()[1]
                c.execute('SELECT nkname, room FROM user_rooms WHERE socket_id = \'%s\'' % client_sock_id)
                conn.commit()
                client = c.fetchone()
                client_nkname = client[0]
                client_room = client[1]
                print("[Log] message received from (%s): %s" % (client_sock_id, data))  # log

                # '/NICK': the client want to change his/her nickname
                if data.startswith('/NICK'):
                    nickname(c, client_room, client_sock_id, conn, data, sock)

                # '/WHO': the client want a list of all currently connected users
                elif data == '/WHO':
                    who(c, client_nkname, client_room, sock)

                # '/MSG': the client has sent a private(direct) message
                elif data.startswith('/MSG'):
                    message(c, client_nkname, client_room, conn, data, sock, socket_dict)

                # '/JOIN': join the client into specified chat room
                elif data.startswith('/JOIN'):
                    join_room(c, client_nkname, client_sock_id, conn, data, sock)

                # '/ROOM': tell the user which room he/she is in
                elif data.startswith('/ROOM'):
                    room(c, client_nkname, client_sock_id, conn, sock)

                # broadcast the message to all clients
                else:
                    broadcast(c, client_nkname, client_room, data, server_socket, socket_list)


def message(c, client_nkname, client_room, conn, data, sock, socket_dict):
    """
    Directly massage to the specified user in the same chat room (instead of broadcast to all)

    :param c: the cursor of database connection
    :param client_nkname: a str of the client's nickname
    :param client_room: a str of the client's chat room name
    :param conn: the database connection
    :param data: the data sent from the client
    :param sock: the socket from where data came
    :param socket_dict: a dict to keep track of socket and its corresponding id
    :return: None
    """

    index = data[5:].find(' ')
    # the client didn't specify whom to message to
    if index == -1:
        msg = '[SEVER] Please specify who you want to message to. Use /MSG followed by a nickname.'
        sock.send(msg.encode())
        print("[Log] the client didn't specify whom to message to")  # log
        return None

    # fetch the matching entry in database
    name = data[5:index + 5]
    c.execute('SELECT socket_id, nkname, room FROM user_rooms WHERE nkname = \'%s\' AND room = \'%s\''
              % (name, client_room))
    conn.commit()
    target = c.fetchone()

    # should only directly message to another client in the same chat room
    if target is None:
        msg = '[SEVER] Nickname {0} in chat room {1} does not exist'.format(name, client_room)
        sock.send(msg.encode())
        print('[Log] ' + msg)  # log
        return None

    # the nickname that the message goes to
    target_socket_id = int(target[0])
    taeget_nkname = target[1]

    # find the target and send the message
    for k, v in socket_dict.items():
        if k == target_socket_id:
            msg = '[PRIVATE from {0}]: '.format(client_nkname) + data[index + 5:]
            v.send(msg.encode())
            sock.send('[SERVER] Private message sent.'.encode())
            print("[Log] private message sent from %s to %s" % (client_nkname, taeget_nkname))  # log
            return None
    return None


def who(c, client_nkname, client_room, sock):
    """
    List all currently connected users in current chat room, and respond to the client

    :param c: the cursor of database connection
    :param client_nkname: a str of the client's nickname
    :param client_room: a str of the client's chat room name
    :param sock: the socket from where data came
    :return: None
    """

    names = '[SEVER] clients in this chat room:\n'
    for row in c.execute('SELECT nkname FROM user_rooms WHERE room = \'%s\'' % client_room):
        names = names + row[0] + '\n'
    sock.send(names.encode())
    print("[Log] returning all correctly connected users to %s" % client_nkname)  # log
    return None


def nickname(c, client_room, client_sock_id, conn, data, sock):
    """
    check the validity of this '/NICK' command, and if it's valid, update the database, give this client a new nickname

    :param c: the cursor of database connection
    :param client_room: a str of the client's chat room name
    :param client_sock_id: a str of the client's socket id
    :param conn: the database connection
    :param data: the data sent from the client
    :param sock: the socket from where data came
    :return: None
    """

    # nickname cannot contain white space
    if data[6:].find(' ') != -1:
        msg = '[SEVER] Nickname cannot contain white space, try another one.'
        sock.send(msg.encode())
        print("[Log] failed because nickname contains whitespace: %s" % data[6:])  # log
        return None

    # nickname cannot be empty
    if not data[6:]:
        msg = '[SEVER] Nickname cannot be empty, try again.'
        sock.send(msg.encode())
        print("[Log] failed because nickname is empty")  # log
        return None

    # search the database
    c.execute('SELECT nkname, room FROM user_rooms WHERE nkname = \'%s\' AND room = \'%s\'' % (data[6:], client_room))
    conn.commit()

    # the specified nickname is taken
    if c.fetchone() is not None:
        msg = '[SEVER] Nickname {0} in chat room {1} is already used, try another one.' \
            .format(data[6:], client_room)
        sock.send(msg.encode())
        print("[Log] updating users failed with existing name: %s" % data[6:])  # log
        return None

    # update the database, and log it.
    c.execute('UPDATE user_rooms SET nkname = \'%s\' WHERE socket_id = \'%s\''
              % (data[6:], client_sock_id))
    conn.commit()
    sock.send('[SEVER] Setting nickname done.'.encode())
    print("[Log] updating users succeeded with new nickname: %s" % data[6:])  # log
    return None


def broadcast(c, client_nkname, client_room, data, server_socket, socket_list):
    """
    Broadcast the message to all users in the same chat room

    :param c: the cursor of database connection
    :param client_nkname: a str of the client's nickname
    :param client_room: a str of the client's chat room name
    :param data: the data sent from the client
    :param server_socket: the server socket
    :param socket_list: a list of all running sockets
    :return: None
    """

    # concatenate a string to broadcast in format: "socket_id: data"
    data_broadcast = '' + client_nkname + ': ' + data
    # only select users in current chat room
    targetlist = []
    for row in c.execute('SELECT socket_id FROM user_rooms WHERE room = \'%s\'' % client_room):
        targetlist.extend(row)

    # log
    print('[Log] broadcasting to all clients in chat room %s: %s' % (client_room, data_broadcast))

    # broadcast
    for send_sock in socket_list:
        # check it isn’t the recv socket, and in the same chat room.
        if send_sock is not server_socket and str(send_sock.getpeername()[1]) in targetlist:
            send_sock.send(data_broadcast.encode())

    return None


def room(c, client_nkname, client_sock_id, conn, sock):
    """
    Respond this client with which chat room he/she is in.

    :param c: the cursor of database connection
    :param client_nkname: a str of the client's nickname
    :param client_sock_id: a str of the client's socket id
    :param conn: the database connection
    :param sock: the socket from where data came
    :return: None
    """

    # search
    c.execute('SELECT room FROM user_rooms WHERE socket_id = \'%s\'' % client_sock_id)
    conn.commit()
    # respond
    msg = '[SEVER] You are in chat room: {0}'.format(c.fetchone()[0])
    sock.send(msg.encode())
    print("[Log] the client %s has request that which room he belongs in." % client_nkname)  # log

    return None


def join_room(c, client_nkname, client_sock_id, conn, data, sock):
    """
    Join this client into the specified chat room, and update the database

    :param c: the cursor of database connection
    :param client_nkname: a str of the client's nickname
    :param client_sock_id: a str of the client's socket id
    :param conn: the database connection
    :param data: the data sent from the client
    :param sock: the socket from where data came
    :return: None
    """

    # update the database
    c.execute('UPDATE user_rooms SET room = \'%s\' WHERE socket_id = \'%s\'' % (data[6:], client_sock_id))
    conn.commit()
    # respond back to the client
    msg = '[SEVER] You have joined into chat room {0}'.format(data[6:])
    sock.send(msg.encode())
    print("[Log] the client %s has joined chat room %s" % (client_nkname, data[6:]))  # log

    return None


def accept_new_connection(c, conn, server_socket, socket_dict, socket_list):
    """
    Accept a new socket request, update the database, and log the new connection

    :param c: the cursor of database connection
    :param conn: the database connection
    :param server_socket: the server socket
    :param socket_dict: a dict to keep track of socket and its corresponding id
    :param socket_list: a list of all running sockets
    :return: None
    """

    # Accept the new socket request
    sockfd, addr = server_socket.accept()
    # Add the socket to the list of sockets to monitor
    socket_list.append(sockfd)
    # put this client into the default global chat room and update the database & dict
    sockfd_id = sockfd.getpeername()[1]
    c.execute("INSERT INTO user_rooms (socket_id, nkname, room) VALUES ('%s', '%s', '%s')"
              % (sockfd_id, sockfd_id, 'global'))
    conn.commit()
    socket_dict[sockfd.getpeername()[1]] = sockfd
    print()
    # Log what has happened on the server
    print("[Log] Client (%s: %s) connected" % (addr[0], addr[1]))  # log
    print("[Log] put client %s into the default global chat room" % sockfd_id)  # log
    sockfd.send('[SERVER] Welcome to THE BEST Chat Room'.encode())
    return None


def initialise_sqlite():
    """
    Initialise a sqlite3 database connection and its cursor

    :return: a tuple (c, conn) where c is the cursor of database connection and conn is the connection itself
    """

    # Start a sqlite database connection
    conn = sqlite3.connect('server.db')
    c = conn.cursor()
    # drop the previous table if it exist
    c.execute('DROP TABLE IF EXISTS user_rooms')
    conn.commit()
    # Create table in the sqlite database
    c.execute('CREATE TABLE IF NOT EXISTS user_rooms (socket_id TEXT PRIMARY KEY, nkname TEXT, room TEXT)')
    conn.commit()
    return c, conn


if __name__ == '__main__':
    run_server()
