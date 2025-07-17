import logging
import pathlib
from asyncio.protocols import Protocol

from lark.exceptions import UnexpectedToken

from aiohomekit import hkjson

logger = logging.getLogger(__name__)

# MARK: - Protocols

# class StructStorageProtocol[StorageLayout](Protocol):

#     async def get(self) -> StorageLayout | None: ...

#     async def save(self, data: StorageLayout): ...

#     async def delete(self) -> None: ...


class DictStorageProtocol[ID, StorageLayoutItem](Protocol):

    async def get_all(self) -> dict[ID, StorageLayoutItem]: ...

    async def get(self, id: ID) -> StorageLayoutItem | None: ...

    async def save(self, id: ID, item: StorageLayoutItem): ...

    async def delete(self, id: ID) -> None: ...


# MARK: - Generic Implementations


class DictStorageMemory[ID, StorageLayoutItem](DictStorageProtocol):
    _storage_data: dict[ID, StorageLayoutItem]

    def __init__(self):
        self._storage_data = dict()

    # Protocol Implementation

    async def get_all(self) -> dict[ID, StorageLayoutItem]:
        return self._storage_data

    async def get(self, id: ID) -> StorageLayoutItem | None:
        return self._storage_data.get(id)

    async def save(self, id: ID, item: StorageLayoutItem):
        self._storage_data[id] = item

    async def delete(self, id: ID):
        if id in self._storage_data:
            self._storage_data.pop(id)


class DictStorageFile[ID, StorageLayoutItem](
    DictStorageMemory
):  # TODO: Codable protocol
    """ID and StorageLayoutItem must be JSON serializable and supported by aiohomekit.hkjson"""

    def __init__(self, location: pathlib.Path):
        """Create a new entity map store."""
        super().__init__()

        self._location = location

        if not location.exists():
            # create the file if it does not exist
            location.parent.mkdir(parents=True, exist_ok=True)
            location.touch()

        with open(location, encoding="utf-8") as fp:
            try:
                file = fp.read()
                self._storage_data = hkjson.loads(file)
                # print('CLI | Loaded characteristics: ', self.storage_data)
            except hkjson.JSON_DECODE_EXCEPTIONS as e:
                self._do_save()  # write a correct empty schema to replace the corrupted cache
                logger.debug(
                    f"Characteristic cache was corrupted, proceeding with cold cache. Rewriting cache file with in-memory snapshot: {self._storage_data}. Error: {e}. File content: {file}"
                )
            except (UnexpectedToken, TypeError, KeyError) as e:
                self._do_save()  # write a correct schema to replace the corrupted cache
                logger.debug(
                    f"Characteristic cache was corrupted, proceeding with cold cache. Rewriting cache file with in-memory snapshot: {self._storage_data}. Error: {e}. File content: {file}"
                )

    async def save(self, id: ID, item: StorageLayoutItem):
        self._storage_data[id] = item
        self._do_save()

    async def delete(self, id: ID):
        if id in self._storage_data:
            self._storage_data.pop(id)
        self._do_save()

    def _do_save(self):
        with open(self._location, mode="w", encoding="utf-8") as fp:
            fp.write(hkjson.dumps(self._storage_data))
