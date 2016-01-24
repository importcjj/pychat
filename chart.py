# -*- coding: utf-8 -*-

import struct
import cPickle
import sys
import select
import socket
import logging
import signal
import argparse

logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
logger.addHandler(handler)
logger.setLevel(logging.INFO)


DEFAULT_HOST = '127.0.0.1'
DEFAULT_port = '9999'


class ChatClient(object):

    def __init__(self, name, host, port):
        self.name = name
        self.connected = 0
        try:
            self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client.connect((host, port))
            logger.info(
                '[LOCAL]: Connected to server@{} successfully.'.format(host))
            send(self.client, 'NAME: {}'.format(self.name))
            data = receive(self.client)
            self.host = data.strip('CLIENT: ')
            self.connected = 1
        except socket.error as e:
            logger.info('[LOCAL]: {}'.format(e))
            sys.exit(1)

    def shutdown(self):
        send(self.client, '')
        logger.info('[LOCAL]: Shutdown.')

    def run(self):
        while self.connected:
            try:
                readable, writeable, exceptional = select.select(
                    [sys.stdin, self.client], [], [])
                for sock in readable:
                    if sock == sys.stdin:
                        data = sys.stdin.readline().strip()
                        if data:
                            send(self.client, data)
                    else:
                        data = receive(self.client)
                        if data:
                            sys.stdout.write('{}\n'.format(data))
                            sys.stdout.flush()
                        else:
                            logger.info('[SERVER]: Crashed.')
                            self.connected = 0
            except select.error as e:
                logger.info('[LOCAL]: {}'.format(e))
                self.shutdown()
            except KeyboardInterrupt as e:
                self.shutdown()
                sys.exit(1)


class ChatServer(object):

    def __init__(self, host, port):
        self.clients = 0
        self.clientmap = {}
        self.outputs = []
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((host, port))
        logger.info('[SERVER][{}]: Listen to port {}.'.format(
            self.clients, host))
        self.server.listen(20)
        signal.signal(signal.SIGINT, self.shutdown)

    def shutdown(self, signum=None, frame=None):
        for output in self.outputs:
            output.close()
        self.server.close()
        logger.info('[SERVER][{}]: Shutdown.'.format(self.clients))

    def client_name(self, client):
        info = self.clientmap[client]
        host, cname = info[0][0], info[1]
        return '{}@{}'.format(cname, host)

    def run(self):
        inputs = [self.server, sys.stdin]
        self.outputs = []
        self.running = 1
        while self.running:
            try:
                readable, writeable, exceptional = select.select(
                    inputs, self.outputs, [])
            except Exception:
                self.running = 0
                self.shutdown()
            for sock in readable:
                if sock == self.server:
                    client, address = self.server.accept()
                    self.clients += 1
                    logger.info('[SERVER][{}]: Got connection {} from {}.'.
                                format(self.clients, client.fileno(), address))
                    cname = receive(client).strip('NAME: ')
                    send(client, 'CLIENT: {}'.format(address[0]))
                    inputs.append(client)
                    self.clientmap[client] = (address, cname)
                    notification = '[SERVER]: {} has joined. Count = {}.'.format(
                        self.client_name(client), self.clients)
                    for output in self.outputs:
                        send(output, notification)
                    self.outputs.append(client)
                elif sock == sys.stdin:
                    junk = sys.stdin.readline()
                    logger.info('[SERVER][{}]: {}.'.format(self.clients, junk))
                    self.running = 0
                else:
                    try:
                        data = receive(sock)
                        if data:
                            message = '[{}]>> {}'.format(
                                self.client_name(sock), data)
                            for output in self.outputs:
                                send(output, message)
                        else:
                            self.clients -= 1
                            logger.info('[SERVER][{}]: {} hung up.'.format(
                                self.clients, sock.fileno()))
                            sock.close()
                            inputs.remove(sock)
                            self.outputs.remove(sock)
                            message = '[SERVER]: {} has left. Count = {}.'.format(
                                self.client_name(sock), self.clients)
                            for output in self.outputs:
                                send(output, message)
                    except socket.error:
                        inputs.remove(sock)
                        self.outputs.remove(sock)
        self.shutdown()


def send(channel, *args):
    buffer = cPickle.dumps(args)
    value = socket.htonl(len(buffer))
    size = struct.pack('L', value)
    channel.send(size)
    channel.send(buffer)


def receive(channel):
    size = struct.calcsize('L')
    size = channel.recv(size)
    try:
        size = socket.ntohl(struct.unpack('L', size)[0])
    except struct.error:
        return ''
    buf = ''
    while len(buf) < size:
        buf = channel.recv(size - len(buf))
    return cPickle.loads(buf)[0]

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Socket Chat Room.')
    parser.add_argument('--name', action='store',
                        dest='name', type=str, required=True)
    parser.add_argument('--host', action='store',
                        dest='host', type=str, default=DEFAULT_HOST)
    parser.add_argument('--port', action='store',
                        dest='port', type=int, default=DEFAULT_port)
    args = parser.parse_args()
    name = args.name
    host = args.host
    port = args.port
    if name == 'server':
        server = ChatServer(host, port)
        server.run()
    else:
        client = ChatClient(name, host, port)
        client.run()
