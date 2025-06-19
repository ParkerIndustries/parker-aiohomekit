from aiohomekit.model.accessories import AccessoriesState
from aiohomekit.model.typed_dicts import HKDeviceID
from aiohomekit.storage.storage import DictStorageProtocol

from .storage import DictStorageFile, DictStorageMemory


class CharacteristicsStorageProtocol(
    DictStorageProtocol[HKDeviceID, AccessoriesState]
): ...


class CharacteristicsStorageMemory(
    DictStorageMemory[HKDeviceID, AccessoriesState], CharacteristicsStorageProtocol
): ...


class CharacteristicsStorageFile(
    DictStorageFile[HKDeviceID, AccessoriesState], CharacteristicsStorageProtocol
): ...
