"""Module with API models base classes"""

import enum
import json
from abc import ABC
from base64 import b64encode, b64decode
from datetime import datetime
from dataclasses import (
    dataclass,
    is_dataclass,
    asdict as dataclass_asdict,
    fields as dataclass_fields,
)
from typing import (
    ClassVar,
    Container,
    MutableMapping,
    Type,
    Set,
    Any,
    Optional,
    Iterable,
    Tuple,
    Union,
)
from uuid import uuid4

import dacite


__all__ = [
    "APIMessage",
    "APIRequest",
    "APIResponse",
    "APISuccessResponse",
    "APIErrorResponse",
    "APIBadRequestError",
    "APIInternalError",
    "StrEnum",
]


def is_optional_type(typ: Any) -> bool:
    """
    Checks whether the given type annotation is `Optional[...]` or `Union[..., None]`
    :param typ: the type annotation to check
    :return: True if optional else False
    """
    args = getattr(typ, "__args__", None)
    origin = getattr(typ, "__origin__", None)
    return origin is Union and args is not None and type(None) in args


def dict_skip_none_factory(
    keyvalue_pairs: Iterable[Tuple[str, Any]]
) -> MutableMapping[str, Any]:
    """Returns a dict of only non-None values from an iterable of (key, value) pairs"""
    return {k: v for k, v in keyvalue_pairs if v is not None}


# pylint: disable=too-many-return-statements,arguments-differ
class JSONExtendedEncoder(json.JSONEncoder):
    """
    `JSONEncoder` class that supports additional base types:
    - bytes are ascii-decoded to str
    - set are converted to list
    - datetime are cast to str with `.isoformat()`
    - Enum are stored by their value
    - StrEnum are stored by their name
    - dataclasses are converted to dicts
    """

    def default(self, obj: Any) -> Any:
        if isinstance(obj, bytes):
            return b64encode(obj).decode("ascii")
        if isinstance(obj, set):
            return list(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, StrEnum):
            return obj.name
        if isinstance(obj, enum.Enum):
            return obj.value
        if is_dataclass(obj):
            return dataclass_asdict(obj)
        return super().default(obj)


class JSONSkipNoneEncoder(JSONExtendedEncoder):
    """
    Same as `JSONExtendedEncoder` but skips dataclasses fields values that are `None`
    """

    def default(self, obj: Any) -> Any:
        if is_dataclass(obj):
            return dataclass_asdict(obj, dict_factory=dict_skip_none_factory)
        return super().default(obj)


class StrEnumMeta(enum.EnumMeta):
    """Metaclass for StrEnum"""

    # pylint: disable=signature-differs
    def __call__(
        cls, enum_name: Any, *args: Any, **kwargs: Any
    ) -> Union[Type["StrEnum"], "StrEnum"]:
        """
        Overrides `enum.EnumMeta.__call__` to allow referencing enums by name.
        If any `*args` or `**kwargs` are passed, or `enum_name` is not a member
        of the enum class, will default to `enum.EnumMeta.__call__`.
        :param enum_name: the name of the enum member to reference
        :param args: additional positional arguments for `enum.EnumMeta.__call__`
        :param kwargs: additional keyword arguments for `enum.EnumMeta.__call__`
        :return: the enum instance if found, or the output of `enum.EnumMeta.__call__`
        """
        if not args and not kwargs:
            member: StrEnum = cls._member_map_.get(enum_name)
            if member:
                return member
        return super().__call__(enum_name, *args, **kwargs)


class StrEnum(enum.Enum, metaclass=StrEnumMeta):
    """
    `enum.Enum` subclass that allows enumeration members to be referenced by name.
    i.e. for a "Color" enum class with member `red = 3`,
         `Color("red")` and `Color(3)` are both valid.
    """


class SerializableDataclass(ABC):
    """
    Base class for dataclasses that enable serialization/deserialization
    from JSON strings or dict objects.
    Leverages the `dacite` package under the hood.
    """

    _dict_excluded_fields: ClassVar[Container[str]] = set()
    _serialization_excluded_fields: ClassVar[Container[str]] = set()
    _dict_factory: ClassVar[Type[MutableMapping]] = dict
    _from_dict_config: ClassVar[dacite.Config] = dacite.Config(
        type_hooks={bytes: b64decode, datetime: datetime.fromisoformat},
        cast=[Set, enum.Enum],
    )
    _json_encoder_cls: ClassVar[Type[json.JSONEncoder]] = JSONExtendedEncoder
    _json_decoder_cls: ClassVar[Type[json.JSONDecoder]] = json.JSONDecoder

    def to_dict(self) -> MutableMapping[str, Any]:
        """Converts the dataclass instance to dict"""
        assert is_dataclass(
            self
        )  # TODO: make into an exception and move to subclass init? after dataclass deco
        # noinspection PyDataclass
        data: MutableMapping[str, Any] = dataclass_asdict(
            self, dict_factory=self._dict_factory
        )
        data = {k: v for k, v in data.items() if k not in self._dict_excluded_fields}
        return data

    @classmethod
    def from_dict(cls, data: MutableMapping[str, Any]) -> "SerializableDataclass":
        """Creates a dataclass instance from a dict"""
        # noinspection PyTypeChecker
        return dacite.from_dict(data_class=cls, data=data, config=cls._from_dict_config)

    # FIXME: ugly override
    def to_json(self, override_data: Optional[MutableMapping[str, Any]] = None) -> str:
        """
        Converts the dataclass instance to a JSON string.
        :param override_data: use the given data (as dict) instead,
                              ignoring contents from the instance
        :return: the encoded JSON string
        """
        data: MutableMapping[str, Any]
        if override_data is not None:
            data = override_data
        else:
            data = self.to_dict()
        data = {
            k: v
            for k, v in data.items()
            if k not in self._serialization_excluded_fields
        }
        return json.dumps(data, cls=self._json_encoder_cls)

    @classmethod
    def from_json(cls, data_str: str) -> "SerializableDataclass":
        """Creates a dataclass instance from a JSON string"""
        return cls.from_dict(json.loads(data_str, cls=cls._json_decoder_cls))

    to_str = to_json
    from_str = from_json

    def __str__(self) -> str:
        return self.to_json()


@dataclass
class APIMessage(SerializableDataclass, ABC):
    """
    Base dataclass for API messages
    """

    _uid: int = None
    _type: str = None

    def __post_init__(self):
        """
        Initialization for dataclass instances.
        Checks that all required fields are populated.
        Also assigns a random `_uid` if not specified.
        """
        allowed_none = ("_uid",)
        for field in dataclass_fields(self):
            if field.name in allowed_none:
                continue
            if getattr(self, field.name, None) is None and not is_optional_type(
                field.type
            ):
                raise TypeError(
                    f"{field.name} must be specified for {self.__class__.__name__}"
                )
        if self._uid is None:
            self._uid = uuid4().int

    as_dict = SerializableDataclass.to_dict


@dataclass
class APIRequest(APIMessage, ABC):
    """
    Base dataclass for API requests
    """

    _type: str = "request"
    command: str = None


@dataclass
class APIResponse(APIMessage, ABC):
    """
    Base dataclass for API responses
    """

    _type: str = "response"
    _status: str = None


@dataclass
class APISuccessResponse(APIResponse):
    """
    Dataclass for successful API responses
    """

    _status: str = "success"


@dataclass
class APIErrorResponse(APIResponse):
    """
    Dataclass for error API responses
    """

    _status: str = "error"
    error_name: str = None
    error_msg: Optional[str] = None


@dataclass
class APIBadRequestError(APIErrorResponse):
    """
    Dataclass for bad request error API responses
    """

    _status: str = "error"
    error_name: str = "bad_request"


@dataclass
class APIInternalError(APIErrorResponse):
    """
    Dataclass for internal error API responses
    """

    error_name: str = "internal_error"
