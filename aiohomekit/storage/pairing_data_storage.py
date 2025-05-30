from aiohomekit.storage.storage import DictStorageProtocol
from aiohomekit.model.typed_dicts import HKDeviceID, PairingData
from .storage import (
    DictStorageMemory,
    DictStorageFile,
)


class PairingDataStorageProtocol(DictStorageProtocol[HKDeviceID, PairingData]): ...

class PairingDataStorageMemory(DictStorageMemory[HKDeviceID, PairingData], PairingDataStorageProtocol): ...

class PairingDataStorageFile(DictStorageFile[HKDeviceID, PairingData], PairingDataStorageProtocol): ...
