"""Base classes for RPC services"""

from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Type

from .models import APIRequest, APIResponse


__all__ = [
    "RPCError",
    "RPCServiceBase",
    "RPCClientBase",
    "RPCServerBase",
    "RQ",
    "RS",
]


class RPCError(Exception):
    """Base class for RPC Exceptions"""


RQ = TypeVar('RQ', bound=APIRequest)
RS = TypeVar('RS', bound=APIResponse)


class RPCServiceBase(ABC, Generic[RQ, RS]):
    """
    Common base class for RPC services
    """
    _req_cls: Type[RQ] = NotImplemented
    _resp_cls: Type[RS] = NotImplemented


class RPCClientBase(RPCServiceBase[RQ, RS], ABC):
    """
    Base abstract class for RPC client classes
    """

    @abstractmethod
    def _rpc(self, req_data: RQ, **kwargs) -> RS:
        """
        Abstract method to send a request and await for a response
        :param req_data: the request data as an instance of the bound request class
        :param kwargs: additional keyword arguments for the underlying method implementation
        :return: the response data as an instance of the bound response class
        """


class RPCServerBase(RPCServiceBase[RQ, RS], ABC):
    """
    Base abstract class for RPC server classes
    """

    @abstractmethod
    def start(self, **kwargs) -> None:
        """
        Starts the server for RPC requests handling.
        :param kwargs: additional keyword arguments for the underlying method implementation
        """

    def stop(self) -> None:
        """
        Stops the server
        """
        raise NotImplementedError

    @abstractmethod
    def rpc_callback(self, req_data: RQ) -> RS:
        """
        Callback for a received request to produce a response
        :param req_data: the received RPCRequest object
        :return: an RPCResponse object
        """
