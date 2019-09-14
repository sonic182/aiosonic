

import json
import random
import socket

import threading

import h2.connection
import h2.events

import pytest


def send_response(conn, event):
    stream_id = event.stream_id
    response_data = json.dumps(dict(event.headers)).encode('utf-8')

    conn.send_headers(
        stream_id=stream_id,
        headers=[
            (':status', '200'),
            ('server', 'basic-h2-server/1.0'),
            ('content-length', str(len(response_data))),
            ('content-type', 'application/json'),
        ],
    )
    conn.send_data(
        stream_id=stream_id,
        data=response_data,
        end_stream=True
    )


def handle(sock):
    conn = h2.connection.H2Connection(client_side=False)
    conn.initiate_connection()
    sock.sendall(conn.data_to_send())

    while True:
        data = sock.recv(65535)
        if not data:
            break

        events = conn.receive_data(data)
        for event in events:
            if isinstance(event, h2.events.RequestReceived):
                send_response(conn, event)

        data_to_send = conn.data_to_send()
        if data_to_send:
            sock.sendall(data_to_send)


@pytest.fixture
def http2_server():
    """Http2 server fixture."""
    data = {}

    def _acceptor(sock):
        while True:
            print('accepting...')
            handle(sock.accept()[0])

    def _get_server():
        data['sock'] = sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        port = random.randint(1000, 9000)

        sock.bind(('0.0.0.0', port))
        sock.listen(5)

        server = threading.Thread(target=_acceptor, args=(sock, ))
        server.start()
        return 'http://0.0.0.0:%i' % port

    yield _get_server()
    sock = data.get('sock')

    if sock:
        sock.close()
