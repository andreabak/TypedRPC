import json
import socket
from abc import ABC, abstractmethod
from typing import TypedDict, TypeVar, Type, ClassVar, Optional, Tuple


__all__ = [
    'RPCError',
    'RPCPacket',
    'RPCRequest',
    'RPCResponse',
    'RPCService',
    'RPCClientBase',
    'RPCServerBase',
]


class RPCError(Exception):
    pass


class RPCPacket(TypedDict):
    """Base class for RPC requests and responses"""


class RPCRequest(RPCPacket):
    """Base class for RPC requests"""


class RPCResponse(RPCPacket):
    """Base class for RPC requests"""


Rq = TypeVar('Rq', bound=RPCRequest)
Rs = TypeVar('Rs', bound=RPCResponse)


class RPCService(ABC):
    """
    Common base class for JSON RPC over TCP servers and clients classes
    """
    _req_cls: Type[Rq] = NotImplemented
    _resp_cls: Type[Rs] = NotImplemented

    _ping_resp: ClassVar[bytes] = b'pong'
    _ping_req: ClassVar[bytes] = b'ping'
    _socket_timeout: ClassVar[float] = 10.0
    _buffer_size: ClassVar[int] = 4096
    _eof: bytes = b'\0'

    def _setup_socket(self, timeout: Optional[float] = None) -> socket.socket:
        sock: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout if timeout is not None else self._socket_timeout)
        return sock

    def _recv_data(self, sock: socket.socket) -> bytes:
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


class RPCClientBase(RPCService, ABC):
    """
    Base class for client classes that implement JSON RPC over TCP clients
    """
    def _create_socket(self, **create_setup_kwargs) -> socket.socket:
        sock = self._setup_socket(**create_setup_kwargs)
        sock.connect(self._socket_address)
        return sock

    def _send_and_receive(self, req_data_raw: bytes, skip_receive: bool = False,
                          **create_socket_kwargs) -> bytes:
        try:
            with self._create_socket(**create_socket_kwargs) as sock:
                sock.send(req_data_raw + self._eof)
                resp_data_raw = self._recv_data(sock) if not skip_receive else b''
        except (OSError, socket.error) as exc:
            raise RPCError(f'Socket error: {exc}') from exc
        return resp_data_raw

    def _ping(self, **create_socket_kwargs) -> bool:
        try:
            resp: bytes = self._send_and_receive(self._ping_req, **create_socket_kwargs)
            if resp != self._ping_resp:
                raise RPCError('Invalid ping response')
        except RPCError:
            return False
        return True

    def _rpc(self, req_data: Rq, **create_socket_kwargs) -> Rs:
        # TODO: Validate request

        req_data_raw: bytes = json.dumps(req_data).encode()
        resp_data_raw: bytes = self._send_and_receive(req_data_raw, **create_socket_kwargs)

        try:
            resp_data: Rs = self._resp_cls(**json.loads(resp_data_raw))
        except json.JSONDecodeError as exc:
            raise RPCError(f'Failed decoding json response: {exc}') from exc
        # TODO: Validate response
        return resp_data


class RPCServerBase(RPCService, ABC):
    """
    Base class for client classes that implement JSON RPC over TCP servers
    """
    _socket_timeout: ClassVar[float] = 1.0

    def _create_socket(self, **create_setup_kwargs) -> socket.socket:
        sock = self._setup_socket(**create_setup_kwargs)
        sock.bind(self._socket_address)
        sock.listen()
        return sock

    def _listen(self, **create_socket_kwargs):
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
                        req_data: Rq = self._req_cls(**json.loads(req_data_raw))
                        resp_data: Rs = self.rpc_callback(req_data)
                        resp_data_raw: bytes = json.dumps(resp_data).encode()
                        conn.sendall(resp_data_raw)

    start = _listen

    @abstractmethod
    def rpc_callback(self, req_data: Rq) -> Rs:
        """
        Callback for a received request to produce a response
        :param req_data: the received RPCRequest object
        :return: an RPCResponse object
        """

    # noinspection PyMethodMayBeStatic
    def stop_callback(self) -> bool:
        """
        Callback to stop the server
        :return: True if the server must be stopped else False
        """
        return True

    def _no_clients_timeout_callback(self) -> None:
        """
        If no clients are connected call this every timeout seconds
        """
