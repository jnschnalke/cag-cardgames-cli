from threading import Barrier
import socketio
import urllib3
import json

sio = socketio.Client()


class Command(object):

    def __init__(self, name, func, description='') -> None:
        self.name = name
        self.func = func
        self.description = description

    def __call__(self, *args, **kwds):
        return self.func(*args, **kwds)

    def __str__(self) -> str:
        return f'{self.name} - {self.description}'


commands = {}
http = urllib3.PoolManager()

run = True
token = None
sid = None


def require_connection(func):

    def wrapper(*args, **kwargs):
        global sio

        if not sio.connected:
            print('A valid connection is required, run "connect" first')
            return

        func(*args, **kwargs)

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


def command(cmd_name=None, description=None):
    def inner(func):
        name = func.__name__
        desc = description
        if cmd_name:
            name = cmd_name
        if not description and func.__doc__:
            desc = func.__doc__

        commands[name] = Command(name, func, desc)

        def wrapper(*args, **kwargs):

            func(*args, **kwargs)

        return wrapper

    return inner


def execute_command(cmd):
    params = cmd.split(' ')

    if params and params[0] in commands:
        commands[params[0]](*params[1:])
    else:
        print('Command not found')


def authenticated_request(uri, method, data):
    payload = json.dumps(data).encode('utf-8')

    req = http.request(
        method, f'http://localhost:8080/api{uri}',
        body=payload,
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'})

    if req.status >= 200 and req.status < 300:
        if req.data:
            return json.loads(req.data)
        else:
            return True
    else:
        print(req.status)
        return False


@command()
def help(cmd=None):
    '''Prints helpful information'''
    global commands
    if not cmd:
        print('Available commands:')
        for cmd in commands.values():
            print(cmd)
    else:
        if cmd in commands:
            print(commands[cmd])
        else:
            print('Command not found')
            help()


@command()
def login(player=None):
    '''Performs login for a player'''
    players = {
        'momo': '1234',
        'jan': '1234'
    }
    if not player:
        print('Please provide player name')
        return

    credentials = {"player_name": player, "password": players[player]}
    req = http.request(
        'POST', 'http://localhost:8080/api/auth/login',
        body=json.dumps(credentials).encode('utf-8'),
        headers={'Content-Type': 'application/json'})

    if req.status != 200:
        raise RuntimeError('Could not login to api')
    else:
        rsp_data = json.loads(req.data)
        print(f'Logged in to api')
        global token
        token = rsp_data['token']
        return rsp_data['token']


@command()
def connect():
    '''Connects to the server via websockets'''
    global token

    if not token:
        print('Need to login first, use: login <player>')
        return

    try:
        sio.connect('http://localhost:8080',
                    headers={'Authorization': f'Bearer {token}'}, transports=['websocket'])
    except socketio.exceptions.ConnectionError as err:
        print('Connection was refused')
        print(err)
        exit(-1)

    print(f'connected... sid: {sio.sid}')
    global sid
    sid = sio.sid


@command()
@require_connection
def kill():
    '''Exits connection without proper disconnect'''

    quit(0)


@command()
def setup(player=None):
    '''Equivalent to running login followed by connect'''
    login(player)
    connect()


@sio.event
def ping(data):
    print(f'Received: {data["message"]}')


class WSCallback:

    def __init__(self) -> None:
        self.barrier = Barrier(2)
        self.data = None
        self.result = None
        self.message = None

    def __call__(self, *args, **kwds):
        if args:
            response = args[0]
            if 'result' in response:
                self.result = response['result']

                if self.result == 'SUCCESS':
                    self.result = True
                elif self.result == 'ERROR':
                    self.result = False

            if 'data' in response:
                self.data = response['data']
            else:
                self.data = args[0]

            if 'message' in response:
                self.message = response['message']

        self.barrier.wait()

    def wait(self):
        self.barrier.wait()


@command()
@require_connection
def scores():
    callback = WSCallback()

    '''Retrieves the current scores from the server'''
    sio.emit('get_scores', callback=callback)

    callback.wait()
    print(f'Scores: {callback.data}')


@command('exit')
def stop_running():
    '''Causes the program to exit'''
    global run
    run = False


@command()
@require_connection
def test_event(data=None):
    sio.emit('test_event', data)


def subscribe_match(match_id):
    callback = WSCallback()

    sio.emit('subscribe', data={'match_id': match_id}, callback=callback)
    callback.wait()
    if callback.result:
        print('Successfully joined')
    else:
        print(f'Failed to join: {callback.message}')


@command()
@require_connection
def create_match(player_count=2):
    params = {
        "isPublic": True,
        "maxPlayers": 4
    }

    match = authenticated_request('/matches', 'POST', params)

    print(f'Created game {match["id"]}')
    subscribe_match(match['id'])


print("For a list of commands type 'help'")
while run:
    print('> ', end='')
    message = input()
    execute_command(message)

if sid:
    sio.disconnect()
    print('disconnected')
