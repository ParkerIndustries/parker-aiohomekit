from asyncio.protocols import Protocol


# MARK: - Protocols

# class StructStorageProtocol[StorageLayout](Protocol):

#     async def get(self) -> StorageLayout | None: ...

#     async def create_or_update(self, data: StorageLayout): ...

#     async def delete(self) -> None: ...

class DictStorageProtocol[ID, StorageLayoutItem](Protocol):

    async def get_all(self) -> dict[ID, StorageLayoutItem]: ...

    async def get(self, id: ID) -> StorageLayoutItem | None: ...

    async def create_or_update(self, id: ID, item: StorageLayoutItem): ...

    async def delete(self, id: ID) -> None: ...

# MARK: - Generic Implementations

class DictStorageMemory[ID, StorageLayoutItem]:

    _storage_data: dict[ID, StorageLayoutItem]

    def __init__(self):
        self._storage_data = dict()

    # Protocol Implementation

    async def get_all(self) -> dict[ID, StorageLayoutItem]:
        return self._storage_data

    async def get(self, id: ID) -> StorageLayoutItem | None:
        return self._storage_data.get(id)

    async def create_or_update_map(self, id: ID, item: StorageLayoutItem):
        self._storage_data[id] = item

    async def delete(self, id: ID):
        if id in self._storage_data:
            self._storage_data.pop(id)

class DictStorageFile[ID: Codable, StorageLayoutItem: Codable](DictStorageMemory):

    def __init__(self, location: pathlib.Path):
        """Create a new entity map store."""
        super().__init__()

        self._location = location

        if not location.exists():
            # create the file if it does not exist
            location.parent.mkdir(parents=True, exist_ok=True)

        with open(location, encoding="utf-8") as fp:
            try:
                self._storage_data = hkjson.loads(fp.read())
                # print('CLI | Loaded characteristics: ', self.storage_data)
            except hkjson.JSON_DECODE_EXCEPTIONS as e:
                self._do_save() # write a correct empty schema to replace the corrupted cache
                logger.debug(
                    f"Characteristic cache was corrupted, proceeding with cold cache: {e}. Rewriting cache file with in-memory snapshot: {self.storage_data}"
                )
            except (UnexpectedToken, TypeError, KeyError) as e:
                self._do_save() # write a correct schema to replace the corrupted cache
                logger.debug(
                    f"Characteristic cache was corrupted, proceeding with cold cache: {e}. Rewriting cache file with in-memory snapshot: {self.storage_data}"
                )

    async def create_or_update(self, id: ID, item: StorageLayoutItem):
        self._storage_data[id] = item
        self._do_save()

    async def delete(self, id: ID):
        if id in self._storage_data:
            self._storage_data.pop(id)
        self._do_save()

    def _do_save(self):
        with open(self.location, mode="w", encoding="utf-8") as fp:
            fp.write(hkjson.dumps(self._storage_data))
