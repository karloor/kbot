#!/usr/bin/env python
# Naoko - A prototype synchtube bot
# Based on Denshi written in 2011 by Falaina falaina@falaina.net
#
# This software is released under the 2-clause BSD License.
# A copy of this license should have been provided with this
# software. If not see
# <http://www.freebsd.org/copyright/freebsd-license.html>.

import ConfigParser
import json
import logging
import math
import os
import random
import re
import requests
import socket
import sys
import threading
import time
import urllib2
from  collections      import  namedtuple, deque
from  datetime         import  datetime
from  multiprocessing  import  Pipe, Process
from  settings         import  *

import sioclient

# Package arguments for later use.
# Due to the way python handles scopes this needs to be used to avoid race
# conditions.
def package(fn, *args, **kwargs):
    def action():
        fn(*args, **kwargs)
    return action

# Simple Record Types for variable synchtube constructs
CytubeUser = namedtuple("CytubeUser",
                        ["name", "rank", "leader", "meta", "profile", "msgs"])


# Generic object that can be assigned attributes
class Object(object):
    pass

# Synchtube  "client" built on top of a socket.io socket
# Synchtube messages are generally of the form:
#   ["TYPE", DATA]
# e.g., The self message (describes current client)
#   ["self" ["bbc2c922",22262,true,"jpg",false,true,21]]
# Which describes a particular connection for the user Naoko
# (uid 22262). The first field is the session identifier,
# second is uid, third is whether or not client is authenticated
# fourth is avatar type, and so on.
class Naoko(object):
    def __init__(self, pipe=None):
        # Initialize all loggers
        self.logger = logging.getLogger("stclient")
        self.logger.setLevel(LOG_LEVEL)
        self.chat_logger = logging.getLogger("stclient.chat")
        self.chat_logger.setLevel(LOG_LEVEL)

        # Seem to have some kind of role in os.terminate() from the watchdog
        self.thread = threading.currentThread()
        self.thread.st = self
        self.thread.close = self.close
        self.closeLock = threading.Lock()
        self.closing = threading.Event()

        self._getConfig()

        self.st_message_handlers = {
            "chatMsg"             :  self.chat,
            "addUser"             :  self.addUser,
            "login"               :  self.login,
            "userlist"            :  self.users,
            "setPermissions"      :  self.ignore,
            "setEmoteList"        :  self.ignore,
            "setMotd"             :  self.ignore,
            "emoteList"           :  self.ignore,
            "drinkCount"          :  self.ignore,
            "channelOpts"         :  self.ignore,
            "channelCSSJS"        :  self.ignore,
            "userLeave"           :  self.ignore,
            "setCurrent"          :  self.ignore,
            "setPlaylistMeta"     :  self.ignore,
            "queue"               :  self.ignore,
            "playlist"            :  self.ignore,
            "delete"              :  self.ignore,
            "moveVideo"           :  self.ignore,
            "chatFilters"         :  self.ignore,
            "rank"                :  self.ignore,
            "closePoll"           :  self.ignore,
            "newPoll"             :  self.ignore,
            "updatePoll"          :  self.ignore,
            "queueFail"           :  self.ignore,
            "mediaUpdate"         :  self.ignore,
            "changeMedia"         :  self.ignore,
            "setTemp"             :  self.ignore,
            "acl"                 :  self.ignore,
            "usercount"           :  self.ignore,
            "setPlaylistLocked"   :  self.ignore,
            "setAFK"              :  self.ignore,
        }
        self.command_handlers = {
            "help"    :  self.command_help,
            "giphy"   :  self.command_giphy,
            "giphyr"  :  self.command_giphyrand,
        }
        self.room_info = {}
        self.doneInit = False
        self.userlist = {}

        self.logger.debug("Retrieving IO_URL")
        try:
            io_url = urllib2.urlopen(
                "http://%s/assets/js/iourl.js" %
                (self.domain)).read()
            self.io_url = io_url[io_url.rfind("var IO_URL"):].split('"')[1]
        except Exception:
            self.logger.warning(
                "Unable to load iourl.js, using default io_url if available.")
            self.io_url = self.default_io_url

        # Assume HTTP because Naoko can't handle other protocols anyway
        socket_ip, socket_port = self.io_url[7:].split(':')

        self.logger.info("Starting SocketIO Client")
        self.client = sioclient.SocketIOClient(
            socket_ip, int(socket_port), "socket.io", {
                "t": int(
                    round(
                        time.time() * 1000))})

        # Various queues and events used to sychronize actions in separate threads
        # Some are initialized with maxlen = 0 so they will silently discard
        # actions meant for non-existent threads
        self.st_queue = deque()
        self.api_queue = deque()
        self.st_action_queue = deque()
        self.add_queue = deque()
        # Events are used to prevent busy-waiting
        self.stAction = threading.Event()

        self.apiAction = threading.Event()
        self.addAction = threading.Event()

        self.client.connect()

        # Set a default selfUser with admin permissions, it will be updated
        # later
        self.selfUser = CytubeUser(
            self.name, 3, False, {
                "afk": False}, {
                "text": "", "image": ""}, deque(
                maxlen=3))

        # Connect to the room
        self.send("joinChannel", {"name": self.room})

        # Log In
        self.send("login", {"name": self.name, "pw": self.pw})

        # Start the threads that are required for all normal operation
        self.chatthread = threading.Thread(target=Naoko._chatloop, args=[self])
        self.chatthread.start()

        self.stthread = threading.Thread(target=Naoko._stloop, args=[self])
        self.stthread.start()

        self.stlistenthread = threading.Thread(target=Naoko._stlistenloop, args=[self])
        self.stlistenthread.start()

        # Healthcheck loop, reports to the watchdog timer every 5 seconds
        while not self.closing.wait(5):
            # Sleeping first lets everything get initialized
            # The parent process will wait
            try:
                status = True
                #status = status and self.stthread.isAlive() 
                #status = status and self.stlistenthread.isAlive()
                #status = status and self.chatthread.isAlive()
                # Catch the case where the client is still connecting after 5
                # seconds
                #status = status and (not self.client.heartBeatEvent or
                #        self.client.hbthread.isAlive())
            except Exception as e:
                self.logger.error(e)
                status = False
            if status and pipe:
                pipe.send("HEALTHY")
            if not status:
                self.close()
        else:
            if pipe:
                self.logger.warn("Restarting")
                pipe.send("RESTART")

    # Responsible for listening to communication from Synchtube
    def _stlistenloop(self):
        client = self.client
        while not self.closing.isSet():
            data = client.recvMessage()
            try:
                data = json.loads(data)
            except ValueError as e:
                self.logger.warn("Failed to parse" + data)
                raise e
            if not data or len(data) == 0:
                continue
            st_type = data["name"]
            try:
                if "args" in data:
                    arg = data["args"][0]
                else:
                    arg = ''
                self.logger.debug("st_message: %s [%s]", st_type, arg)
                fn = self.st_message_handlers[st_type]
            except KeyError:
                self.logger.warn("No handler for st_message %s", st_type)
            else:
                self.stExecute(package(fn, st_type, arg))
        else:
            self.logger.info("Synchtube Listening Loop Closed")
            self.close()

    # Responsible for handling messages from Synchtube
    def _stloop(self):
        client = self.client
        while self.stAction.wait():
            self.stAction.clear()
            if self.closing.isSet(): break
            while self.st_action_queue:
                self.st_action_queue.popleft()()
        self.logger.info("Synchtube Loop Closed")

    # Responsible for sending chat messages to IRC and Synchtube.
    # Only the $status command and error messages should send a chat message
    # to Synchtube or IRC outside this thread.
    def _chatloop(self):
        while not self.closing.isSet():
            # Detect when far too many messages are being sent and clear the
            # queue
            if len(self.st_queue) > 20:
                time.sleep(5)
                self.st_queue.clear()
                continue
            if self.st_queue:
                self.sendChat(self.st_queue.popleft())
            time.sleep(self.spam_interval)
        else:

            self.logger.info("Chat Loop Closed")

    def command_help(self, command, user, data):
        self.enqueueMsg(
                "I know the following commands: " +  
                ", ".join(self.command_handlers.keys()))

    def command_giphy(self, command, user, data):
        self.logger.debug("giphy: query=%s", data) 
        if not data: 
            self.command_giphyrand(command, user, data)
            return 

        url_template = "http://api.giphy.com/v1/gifs/search?q={}&api_key=dc6zaTOxFJmzC"

        r = requests.get(url_template.format(data))
        if r.status_code != 200: return
        self.logger.debug("giphy: json=%s", r.json()) 
        image = r.json()['data'][0]['images']['fixed_height']['url']
        self.enqueueMsg("{}.pic".format(image))

    def command_giphyrand(self, command, user, data):
        self.logger.debug("giphy: query=%s", data) 
        url = "http://api.giphy.com/v1/gifs/random?api_key=dc6zaTOxFJmzC"

        if data: 
            url = url + "&tag={}".format(data)
        r = requests.get(url)
        if r.status_code != 200: return

        image = r.json()['data']['image_url']
        self.logger.debug("giphy: imageurl=%s json=%s", image, r.json()) 
        self.enqueueMsg("{}.pic".format(image))

    # Handle chat commands from Synchtube
    def chatCommand(self, user, msg):
        if not msg or msg[0] != '$': return
        line = msg[1:].split(' ', 1)
        command = line[0].lower()
        try:
            if len(line) > 1:
                arg = line[1].strip()
            else:
                arg = ''
            fn = self.command_handlers[command]
        except KeyError:
            self.logger.debug("No handler for %s [%s]", command, arg)
        else:
            fn(command, user, arg)

    # Executes a function in the main Synchtube thread
    def stExecute(self, action):
        self.st_action_queue.append(action)
        self.stAction.set()

    def addExecute(self, action):
        self.add_queue.append(action)
        self.addAction.set()

    # Enqueues a message for sending to both IRC and Synchtube
    # This should not be used for bridging chat between IRC and Synchtube
    def enqueueMsg(self, msg):
        self.st_queue.append(msg)

    def close(self):
        self.closeLock.acquire()
        if self.closing.isSet():
            self.closeLock.release()
            return
        self.closing.set()
        self.closeLock.release()
        # self.client.close()
        self.stAction.set()
        self.addAction.set()

    def sendChat(self, msg):
        self.send("chatMsg", {"msg": msg})

    def send(self, tag='', data=''):
        buf = {"name": tag}
        if data != '':
            buf["args"] = [data]
        try:
            buf = json.dumps(buf, encoding="utf-8")
        except UnicodeDecodeError:
            buf = json.dumps(buf, encoding="iso-8859-15")
        self.client.send(5, data=buf)


    # Handlers for Cytube message types
    # All of them receive input in the form (tag, data)
    def ignore(self, tag, data):
        self.logger.debug("Ignoring %s", tag)

    def login(self, tag, data):
        if not data["success"] or "error" in data:
            if "error" in data:
                raise Exception(data["error"])
            else:
                raise Exception("Failed to login.")
        # Set AFK on join
        self.sendChat("/afk")

    def addUser(self, tag, data, isSelf=False):
        self._addUser(data, data["name"] == self.name)

    def users(self, tag, data):
        for u in data:
            self._addUser(u)

    def chat(self, tag, data):
        if not self.doneInit: return
        if not data["username"] in self.userlist: return

        user = self.userlist[data["username"]]
        msg = self._fixChat(data["msg"])
        self.chat_logger.debug("%s: %r", user.name, msg)

        if not data["meta"].get("addClass"):
            self.chatCommand(user, msg)

    def _addUser(self, u_dict, isSelf=False):
        userinfo = u_dict.copy()
        #userinfo['nick'] = self.filterString(userinfo['nick'], True)[1]
        userinfo['msgs'] = deque(maxlen=3)
        #userinfo['nickChanges'] = 0
        userinfo["leader"] = False
        assert set(
            userinfo.keys()) == set(
            CytubeUser._fields), "User information has changed formats. Tell Desuwa."
        user = CytubeUser(**userinfo)
        self.userlist[user.name] = user
        if isSelf:
            self.selfUser = user
            self.doneInit = True

    # Filters a string, removing invalid characters
    # Used to sanitize nicks or video titles for printing
    # Returns a boolean describing whether invalid characters were found
    # As well as the filtered string

    def filterString(self, input, isNick=False, replace=True):
        if input is None:
            return (False, "")
        output = []
        value = input
        if not isinstance(value, str) and not isinstance(value, unicode):
            value = str(value)
        if not isinstance(value, unicode):
            try:
                value = value.decode('utf-8')
            except UnicodeDecodeError:
                value = value.decode('iso-8859-15')
        valid = True
        for c in value:
            o = ord(c)
            # Locale independent ascii alphanumeric check
            if isNick and ((o >= 48 and o <= 57) or (
                    o >= 97 and o <= 122) or (o >= 65 and o <= 90) or o == 95):
                output.append(c)
                continue
            validChar = o > 31 and o != 127 and not (
                o >= 0xd800 and o <= 0xdfff) and o <= 0xffff
            if (not isNick) and validChar:
                output.append(c)
                continue
            valid = False
            if replace:
                output.append(unichr(0xfffd))
        return (valid, "".join(output))

    # Undoes the changes cytube applies to chat messages
    def _fixChat(self, input):
        if input is None:
            return ""
        value = input
        if not isinstance(value, str) and not isinstance(value, unicode):
            value = str(value)
        if not isinstance(value, unicode):
            try:
                value = value.decode('utf-8')
            except UnicodeDecodeError:
                value = value.decode('iso-8859-15')

        output = value

        # Replace html tags with whatever they replaced
        output = re.sub(r"</?strong>", "*", output)
        output = re.sub(r"</?em>", "_", output)
        output = re.sub(r"</?code>", "`", output)
        output = re.sub(r"</?s>", "~~", output)

        # Remove any other html tags that were added
        output = output.split("<")
        for i, val in enumerate(output):
            if ">" in val:
                output[i] = val.split(">", 1)[1]
        output = "".join(output)

        # Unescape &gt; and &lt;
        output = output.replace("&gt;", ">")
        output = output.replace("&lt;", "<")
        output = output.replace("&quot;", "\"")
        output = output.replace("&amp;", "&")

        return output

    def _getConfig(self):
        config = ConfigParser.RawConfigParser()
        config.read("naoko.conf")
        self.room = config.get("naoko", "room")
        self.room_pw = config.get("naoko", "room_pw")
        self.name = config.get("naoko", "nick")
        self.pw = config.get("naoko", "pass")
        self.domain = config.get("naoko", "domain")
        self.default_io_url = config.get("naoko", "default_io_url")
        self.spam_interval = float(config.get("naoko", "spam_interval"))
        self.skip_interval = float(config.get("naoko", "skip_interval"))
        self.server = config.get("naoko", "irc_server")
        self.channel = config.get("naoko", "irc_channel")
        self.irc_nick = config.get("naoko", "irc_nick")
        self.ircpw = config.get("naoko", "irc_pass")
        self.dbfile = config.get("naoko", "db_file")





name = "Launcher"
restarting = False
MIN_DUR = 2.5    # Don't fork too often

# Set up logging
logging.basicConfig(format='%(name)-10s:%(levelname)-8s - %(message)s', 
    stream=sys.__stderr__)
logger = logging.getLogger("socket.io client")
logger.setLevel(LOG_LEVEL)
(info, debug, warning, error) = (logger.info, logger.debug, logger.warning, logger.error)

class throttle:
    def __init__ (self, fn):
        self.fn = fn
        self.delay = MIN_DUR
        self.last_call = 0

    def __call__ (self, *args, **kwargs):
        if not restarting and time.time() - self.last_call < 60:
            self.delay *= 2
            self.delay = self.delay if self.delay < 60 * 10 else 60*10
        else:
            self.delay = MIN_DUR
        remaining = self.delay - time.time() + self.last_call
        if remaining > 0:
            time.sleep(remaining)
        self.last_call = time.time()
        self.fn(*args, **kwargs)

def spawn(script):
    (pipe_in, pipe_out) = Pipe(False)
    p = Process(target=script, args=(pipe_out,))
    p.daemon = True  
    p.start()
    pipe_out.close()
    return (pipe_in, p)

@throttle
def run(script):
    (child_pipe, child) = spawn (script)
    restarting = False
    print "[%s] Forked off (%d)\n" % (name, child.pid)
    try:
        while child_pipe.poll(TIMEOUT):
            buf = child_pipe.recv()
            if buf == "RESTART":
                time.sleep(5)
                break
            elif buf == "HEALTHY":
                restarting = True
                continue
            else:
                raise Exception("Received invalid message (%s)"% (buf))
    except EOFError:
        print "[%s] EOF on child pipe" % (name)
    except IOError:
        print "[%s] IOError on child pipe" % (name)
    except OSError as e:
        print "Received exception ", str(e)
    finally:
        child.terminate()

if __name__ == '__main__':
    try:
        while True:
            run(Naoko)
    except KeyboardInterrupt:
        print "\n Shutting Down"
