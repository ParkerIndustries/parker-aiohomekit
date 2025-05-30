from aiohomekit.model.accessories import AccessoriesState
from aiohomekit.storage.storage import DictStorageProtocol
from aiohomekit.model.typed_dicts import HKDeviceID
from .storage import (
    DictStorageMemory,
    DictStorageFile,
)


class CharacteristicsStorageProtocol(DictStorageProtocol[HKDeviceID, AccessoriesState]): ...

class CharacteristicsStorageMemory(DictStorageMemory[HKDeviceID, AccessoriesState]): ...

class CharacteristicsStorageFile(DictStorageFile[HKDeviceID, AccessoriesState]): ...
