import threading
import ssl
import types
import logging
import socket as pysocket
from time import sleep, time


class socket(threading.Thread):
    def __init__(self, parent):
        threading.Thread.__init__(self)
        self.lock = threading.Lock()
        self.parent = parent
        self.logger = logging.getLogger('lib:re:wired')
        self.event = threading.Event()
        self.socket = pysocket.socket(pysocket.AF_INET, pysocket.SOCK_STREAM)
        if pysocket.has_ipv6:
            try:
                self.socket = pysocket.socket(pysocket.AF_INET6, pysocket.SOCK_STREAM)
            except:
                pass
        self.queue = {}
        self.msgid = 0
        self.tlssocket = 0
        self.connected = 0
        self.keepalive = 1
        self.address = 0
        self.port = 0
        self.peercert = 0

    def run(self):
        while self.keepalive:
            if self.connected:
                data = ""
                try:
                    byte = self.tlssocket.read(1)
                except pysocket.error:
                    self.keepalive = 0
                    self.connected = 0
                while byte != chr(4):
                    if not self.keepalive:
                        break
                    try:
                        data += byte
                        byte = self.tlssocket.read(1)
                        if byte == "":
                            raise pysocket.error
                    except pysocket.error:
                        self.logger.debug("receive: socket error")
                        self.keepalive = 0
                        self.connected = 0
                        break
                data += byte
                self.lock.acquire()
                if self.queueMsg(data):
                    self.event.set()
                self.lock.release()
            else:
                sleep(0.5)
        # connection closed
        self.disconnect()
        # Exit thread
        self.logger.debug("EXIT")
        raise SystemExit

    def connect(self, address, port):
        self.address = address
        self.port = port
        host = 0
        try:
            self.socket = makeconn(self.address, self.port)
        except pysocket.error:
            self.logger.debug("Failed to connect!")
            self.keepalive = 0
            return 0
        try:
            self.tlssocket = ssl.wrap_socket(self.socket, server_side=False, ssl_version=ssl.PROTOCOL_TLSv1)
            self.peercert = self.tlssocket.getpeercert(binary_form=True)
        except:
            return 0
        self.connected = 1
        return 1

    def disconnect(self):
        self.logger.debug("IN DISCONNECT")
        self.connected = 0
        try:
            self.socket.close()
        except pysocket.error, ssl.error:
            self.logger.debug("Socket Error on disconnect")
            return 0
        return 1

    def send(self, data):
        if not self.connected:
            return 0
        try:
            self.tlssocket.send(str(data) + chr(4))
        except pysocket.error:
            self.logger.debug("send: socket error")
            return 0
        return 1

    def queueMsg(self, data):
        # parses the server msg and appends it to the msg queue
        if not self.connected:
            return 0
        if not data:
            return 0
        if data.count(chr(4)) < 1:
            self.logger.debug("invalid msg to parse: " + repr(data))
            return 0
        if data[3:4] != ' ':
            self.logger.debug("invalid respone in parse:%s.", data[0:3])
            return 0
        response = int(data[0:3])
        data = data[4:]
        data = data.rstrip(chr(4))
        parsed = data.split(chr(28))
        msg = types.message(response, self.msgid, parsed)
        self.queue[self.msgid] = msg
        self.msgid += 1
        return 1


def makeconn(host, port):
    for r in pysocket.getaddrinfo(host, port,
                                0, pysocket.SOCK_STREAM):
        af, st, pr, _, sa = r
        s = pysocket.socket(af, st, pr)
        try:
            s.connect(sa)
            return s
        except pysocket.error, msg:
            s.close()
    raise msg
