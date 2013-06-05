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
            306: True,   # Kick
            307: True,   # Ban
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

            400: True, # Transfer Ready
            401: True, # Transfer Qeued
            402: False, # File Information
            410: False, # File Listing
            411: False, #File Listing done
            420: True,
            421: True,
            500: True,
            501: True,
            502: True,
            503: True,
            510: False,  # Login Failed
            511: False,  # Banned
            512: True,
            513: False,  # Account Not Found
            514: False, # User exists
            515: True,
            516: False, # Permission denied
            520: False, # File or Directory Not Found
            521: False,  # File exists
            522: True,
            523: True,
            600: False,  # User account item
            601: False,  # Group account item
            602: True,
            610: False,  # User account list item
            611: False,  # User account list done
            620: False,  # Group account list item
            621: False  # Group account list done
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
            return 0
        return 1


class privileges():
    def __init__(self):
        self.getUserInfo = 0
        self.broadcast = 0
        self.postNews = 1
        self.clearNews = 0
        self.download = 1
        self.upload = 1
        self.uploadAnywhere = 0
        self.createFolders = 0
        self.alterFiles = 0
        self.deleteFiles = 0
        self.viewDropboxes = 0
        self.createAccounts = 0
        self.editAccounts = 0
        self.deleteAccounts = 0
        self.elevatePrivileges = 0
        self.kickUsers = 0
        self.banUsers = 0
        self.cannotBeKicked = 0
        self.downloadSpeed = 0
        self.uploadSpeed = 0
        self.downloadLimit = 0
        self.uploadLimit = 0
        self.changeTopic = 0

    def parsePrivileges(self, values):
        if len(values) != 23:
            return 0
        parsed = {}
        try:
            self.getUserInfo = int(values[0])
            self.broadcast = int(values[1])
            self.postNews = int(values[2])
            self.clearNews = int(values[3])
            self.download = int(values[4])
            self.upload = int(values[5])
            self.uploadAnywhere = int(values[6])
            self.createFolders = int(values[7])
            self.alterFiles = int(values[8])
            self.deleteFiles = int(values[9])
            self.viewDropboxes = int(values[10])
            self.createAccounts = int(values[11])
            self.editAccounts = int(values[12])
            self.deleteAccounts = int(values[13])
            self.elevatePrivileges = int(values[14])
            self.kickUsers = int(values[15])
            self.banUsers = int(values[16])
            self.cannotBeKicked = int(values[17])
            self.downloadSpeed = int(values[18])
            self.uploadSpeed = int(values[19])
            self.downloadLimit = int(values[20])
            self.uploadLimit = int(values[21])
            self.changeTopic = int(values[22])
        except (KeyError, IndexError) as e:
            print "parsePrivileges: %s" % e
            return 0
        return parsed

    def toString(self):
        privmask = str(self.getUserInfo) + chr(28)
        privmask += str(self.broadcast) + chr(28)
        privmask += str(self.postNews) + chr(28)
        privmask += str(self.clearNews) + chr(28)
        privmask += str(self.download) + chr(28)
        privmask += str(self.upload) + chr(28)
        privmask += str(self.uploadAnywhere) + chr(28)
        privmask += str(self.createFolders) + chr(28)
        privmask += str(self.alterFiles) + chr(28)
        privmask += str(self.deleteFiles) + chr(28)
        privmask += str(self.viewDropboxes) + chr(28)
        privmask += str(self.createAccounts) + chr(28)
        privmask += str(self.editAccounts) + chr(28)
        privmask += str(self.deleteAccounts) + chr(28)
        privmask += str(self.elevatePrivileges) + chr(28)
        privmask += str(self.kickUsers) + chr(28)
        privmask += str(self.banUsers) + chr(28)
        privmask += str(self.cannotBeKicked) + chr(28)
        privmask += str(self.downloadSpeed) + chr(28)
        privmask += str(self.uploadSpeed) + chr(28)
        privmask += str(self.downloadLimit) + chr(28)
        privmask += str(self.uploadLimit) + chr(28)
        privmask += str(self.changeTopic)
        return privmask

class accountlist():
    def __init__(self, parent):
        self.parent = parent
        self.logger = self.parent.logger
        self.users = {}
        self.groups = {}
        self.lastupdated = 0

    def loadUser(self, account):
        if not self.parent.privileges['editAccounts']:
            self.logger.error("loadUser: not allowed to read accounts")
            return 0
        if not account in self.users:
            self.logger.error("loadUser: Can't find %s in userlist.", account)
            return 0
        self.parent.socketthread.send("READUSER %s" % account)
        data = self.parent.getMsg(600, 5)
        if data:
            if len(data.msg) != 26:
                self.logger.error("loadAccount: invalid field count %s instead of 26", len(data.msg))
            privlist = data.msg[3:]
            privs = privileges()
            privs.parsePrivileges(privlist)
            if not privs:
                self.logger.error("loadAccount: Failed to parse privileges")
                return 0
            group = data.msg[2]
            password = data.msg[1]
            if not data.msg[0] == account:
                self.logger.error("loadAccount: expected account %s but got account %s!!!", account, data.msg[0])
            self.users[account].privs = privs
            self.users[account].password = password
            if group:
                if group in self.groups:  # add this user to the membership list
                    if not account in self.groups[group].members:
                        self.groups[group].members.append(account)
                self.users[account].group = group
                self.users[account].privs = self.groups[group].privs  # Push group privs onto user
            self.users[account].isloaded = 1
            self.users[account].lastupdated = time()
        else:
            self.logger.error("loadUser: timeout waiting for response")
            return 0
        return self.users[account]

    def loadGroup(self, account):
        if not self.parent.privileges['editAccounts']:
            self.logger.error("loadGroup: not allowed to read accounts")
            return 0
        if not account in self.groups:
            self.logger.error("loadGroup: Can't find %s in grouplist.", account)
            return 0
        self.parent.socketthread.send("READGROUP %s" % account)
        data = self.parent.getMsg(601, 5)
        if data:
            if len(data.msg) != 24:
                self.logger.error("loadGroup: invalid field count %s instead of 24", len(data.msg))
            privlist = data.msg[1:]
            privs = privileges()
            privs.parsePrivileges(privlist)
            if not privs:
                self.logger.error("loadAccount: Failed to parse privileges")
                return 0
            group = data.msg[0]
            if not group == account:
                self.logger.error("loadGroup: expected group %s but got %s!!!", account, group)
                return 0
            self.groups[account].privs = privs
            self.groups[account].isloaded = 1
            self.groups[account].lastupdated = time()
        else:
            self.logger.error("loadGroup: Timeout waiting for response")
            return 0
        return  self.groups[account]

    def updateUsers(self, userlist):
        for key, auser in userlist.items():
            try:
                auser = auser.msg[0]
                if not auser in self.users:
                    self.users[auser] = useraccount(auser)
            except (IndexError, KeyError) as e:
                self.logger.error("updateUsers: Failed to parse list: %s", e)
                return 0
        return 1

    def updateGroups(self, grouplist):
        for key, agroup in grouplist.items():
            try:
                agroup = agroup.msg[0]
                if not agroup in self.groups:
                    self.groups[agroup] = groupaccount(agroup)
            except (IndexError, KeyError) as e:
                self.logger.error("updateGroups: Failed to parse list: %s", e)
                return 0
        return 1


class useraccount():
    def __init__(self, username, privs=False):
        self.username = username
        self.group = 0
        self.privs = 0
        self.isloaded = 0
        self.lastupdated = 0
        if privs:
            pass


class groupaccount():
    def __init__(self, groupname, privs=False):
        self.groupname = groupname
        self.members = []
        self.privs = 0
        self.isloaded = 0
        self.lastupdated = 0
        if privs:
            pass
