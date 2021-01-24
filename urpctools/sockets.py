"""RPC service using raw socket"""

import json
import socket
from abc import ABC, abstractmethod
from typing import ClassVar, Optional, Tuple

from .service import RPCError, RQ, RS, RPCService, RPCClientBase, RPCServerBase


__all__ = [
    'RPCSocketService',
    'RPCSocketClientBase',
    'RPCSocketServerBase',
]


# pylint: disable=not-callable,missing-function-docstring
class RPCSocketService(RPCService[RQ, RS], ABC):
    """
    Common base class for JSON RPC over TCP servers and clients classes
    """

    _ping_resp: ClassVar[bytes] = b'pong'
    _ping_req: ClassVar[bytes] = b'ping'
    _socket_timeout: ClassVar[float] = 10.0
    _buffer_size: ClassVar[int] = 4096
    _eof: bytes = b'\0'

    def _setup_socket(self, timeout: Optional[float] = None) -> socket.socket:
        """
        Sets up and configures a socket
        :param timeout: the timeout to use for the socket.
                        If None or omitted the default class `_socket_timeout` value is used
        :return: the prepared socket instance
        """
        sock: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout if timeout is not None else self._socket_timeout)
        return sock

    def _recv_data(self, sock: socket.socket) -> bytes:
        """
        Receives raw data from a socket
        :param sock: the socket
        :return: the raw data in bytes (stripped of \0 and leading/trailing whitespace)
        """
        resp_data_raw: bytes = b""
        while True:
            data_chunk: bytes = sock.recv(self._buffer_size)
            resp_data_raw += data_chunk
            if self._eof in data_chunk or not data_chunk:
                break
        return resp_data_raw.rstrip(b'\0').strip()

    @property
    @abstractmethod
    def _socket_address(self) -> Tuple[str, int]:
        """
        Returns a tuple of (address, port) suitable to open a socket connection
        """


# pylint: disable=missing-function-docstring
class RPCSocketClientBase(RPCClientBase[RQ, RS], RPCSocketService[RQ, RS], ABC):
    """
    Base class for client classes that implement JSON RPC over TCP clients
    """
    def _create_socket(self, **setup_socket_kwargs) -> socket.socket:
        """
        Creates the socket and connects to the server address
        :param setup_socket_kwargs: additional keyword arguments for socket setup
        :return: the connected socket
        """
        sock = self._setup_socket(**setup_socket_kwargs)
        sock.connect(self._socket_address)
        return sock

    def _send_and_receive(self, req_data_raw: bytes, skip_receive: bool = False,
                          **create_socket_kwargs) -> bytes:
        """
        Sends a raw request and awaits for a raw response
        :param req_data_raw: the raw request data in bytes
        :param skip_receive: don't wait for a response, return immediately after sending the request
        :param create_socket_kwargs: additional keyword arguments for socket creation
        :raise RPCError: if any socket error happen while sending or receiving data
        :return: the raw response bytes or, if `skip_receive` is True, an empty bytes string
        """
        try:
            with self._create_socket(**create_socket_kwargs) as sock:
                sock.send(req_data_raw + self._eof)
                resp_data_raw = self._recv_data(sock) if not skip_receive else b''
        except (OSError, socket.error) as exc:
            raise RPCError(f'Socket error: {exc}') from exc
        return resp_data_raw

    def _ping(self, **create_socket_kwargs) -> bool:  # TODO: implement proper ping request-response
        """
        Pings the server for connectivity testing
        :param create_socket_kwargs: additional keyword arguments for socket creation
        :return: True if the ping was successful else False
        """
        try:
            resp: bytes = self._send_and_receive(self._ping_req, **create_socket_kwargs)
            if resp != self._ping_resp:
                raise RPCError('Invalid ping response')
        except RPCError:
            return False
        return True

    def _rpc(self, req_data: RQ, **create_socket_kwargs) -> RS:
        """
        Sends a request and awaits for a response
        :param req_data: the request data as an instance of the bound request class
        :param create_socket_kwargs: additional keyword arguments for socket creation
        :raise RPCError: if any socket or response data errors happen
        :return: the response data as an instance of the bound response class
        """
        # TODO: Validate request

        req_data_raw: bytes = json.dumps(req_data).encode()
        resp_data_raw: bytes = self._send_and_receive(req_data_raw, **create_socket_kwargs)

        try:
            resp_data: RS = self._resp_cls(**json.loads(resp_data_raw))
        except json.JSONDecodeError as exc:
            raise RPCError(f'Failed decoding json response: {exc}') from exc
        # TODO: Validate response
        return resp_data


# pylint: disable=missing-function-docstring
class RPCSocketServerBase(RPCServerBase[RQ, RS], RPCSocketService[RQ, RS], ABC):
    """
    Base class for client classes that implement JSON RPC over TCP servers
    """
    _socket_timeout: ClassVar[float] = 1.0

    def _create_socket(self, **setup_socket_kwargs) -> socket.socket:
        """
        Creates the socket and binds the server to it
        :param setup_socket_kwargs: additional keyword arguments for socket setup
        :return: the connected socket
        """
        sock = self._setup_socket(**setup_socket_kwargs)
        sock.bind(self._socket_address)
        sock.listen()
        return sock

    def _listen(self, **create_socket_kwargs) -> None:
        """
        Listens indefinitely for clients connections and handles requests.
        :param create_socket_kwargs: additional keyword arguments for socket creation
        """
        with self._create_socket(**create_socket_kwargs) as sock:
            print(f'RPC server listening on {self._socket_address}')
            while True:
                try:
                    conn, addr = sock.accept()
                except socket.timeout:
                    self._no_clients_timeout_callback()
                    continue
                with conn:
                    print(f'New RPC connection from {addr}')
                    req_data_raw: bytes = self._recv_data(conn)
                    if req_data_raw == self._ping_req:
                        conn.sendall(self._ping_resp + self._eof)
                    else:
                        req_data: RQ = self._req_cls(**json.loads(req_data_raw))
                        resp_data: RS = self.rpc_callback(req_data)
                        resp_data_raw: bytes = json.dumps(resp_data).encode()
                        conn.sendall(resp_data_raw)

    def start(self, **kwargs) -> None:
        self._listen(**kwargs)

    def _no_clients_timeout_callback(self) -> None:
        """
        If no clients are connected call this every timeout seconds
        """
