from time import time


class wiredMessages:
    def __init__(self):
        self.types = {
        200: True,
        201: False,  # Login Succeeded
        202: True,
        203: True,

        300: True,
        301: True,
        302: True,
        303: True,
        304: True,
        305: True,
        306: True,
        307: True,
        308: False,  # User Info
        309: True,
        310: False,  # userlist item
        311: False,  # userlist done
        320: True,
        321: True,
        322: True,
        330: False,  # private chat created
        331: True,
        332: True,
        340: True,
        341: True,  # Chat Topic

        400: True,
        401: True,
        402: True,
        410: True,
        411: True,
        420: True,
        421: True,

        500: True,
        501: True,
        502: True,
        503: True,
        510: True,
        511: True,
        512: True,
        513: True,
        514: True,
        515: True,
        516: True,
        520: True,
        521: True,
        522: True,
        523: True,

        600: True,
        601: True,
        602: True,
        610: True,
        611: True,
        620: True,
        621: True
        }

    def askhandle(self, msg):
        try:
            check = self.types[msg]
        except KeyError:  # unkown command - this is probably not going to be handled internally
            return False
        return check


class message:
    def __init__(self, type, id, msg):
        self.type = type
        self.id = id
        self.time = time()
        self.msg = msg


class user:
    def __init__(self):
        self.chats = []  # active chats for this user
        self.userid = None
        self.idle = None
        self.admin = None
        self.icon = None
        self.nick = None
        self.login = None
        self.ip = None
        self.host = None
        self.status = None
        self.image = None
        ## these will be updated once you obtain info on a user
        self.clientVersion = None
        self.cipherName = None
        self.cipherBits = None
        self.loginTime = None
        self.idleTime = None
        self.downloads = None
        self.uploads = None

    def initFromDict(self, data):
        if len(data) != 11:
            return 0  # invalid length
        if not int(data[0]) in self.chats:
            self.chats.append(int(data[0]))
        self.userid = int(data[1])
        self.idle = data[2]
        self.admin = data[3]
        self.icon = data[4]
        self.nick = data[5]
        self.login = data[6]
        self.ip = data[7]
        self.host = data[8]
        self.status = data[9]
        self.image = data[10]
        return 1

    def updateFromUserInfo(self, info):
        try:
            self.idle = info['idle']
            self.admin = info['admin']
            self.icon = info['icon']
            self.nick = info['nick']
            self.login = info['login']
            self.ip = info['ip']
            self.host = info['host']
            self.status = info['status']
            self.image = info['image']
            self.clientVersion = info['client-version']
            self.cipherName = info['cipher-name']
            self.cipherBits = info['cipher-bits']
            self.loginTime = info['login-time']
            self.idleTime = info['idle-time']
            self.downloads = info['downloads']
            self.uploads = info['uploads']
        except KeyError, IndexError:
            print "Error: updateFromUserInfo"
            return 0
        return 1
