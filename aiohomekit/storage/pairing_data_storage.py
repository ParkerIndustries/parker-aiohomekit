from aiohomekit.model.typed_dicts import HKDeviceID, PairingData
from aiohomekit.storage.storage import DictStorageProtocol

from .storage import DictStorageFile, DictStorageMemory


class PairingDataStorageProtocol(DictStorageProtocol[HKDeviceID, PairingData]): ...


class PairingDataStorageMemory(
    DictStorageMemory[HKDeviceID, PairingData], PairingDataStorageProtocol
): ...


class PairingDataStorageFile(
    DictStorageFile[HKDeviceID, PairingData], PairingDataStorageProtocol
): ...
