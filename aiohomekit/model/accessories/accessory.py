from typing import Self
from aiohomekit.model import typed_dicts
from aiohomekit.model.characteristics import Characteristics, CharacteristicsTypes, NEEDS_POLLINGS_CHARS
from aiohomekit.model.services import Service, Services, ServicesTypes
from aiohomekit.uuid import normalize_uuid


class Accessory:
    """Represents a HomeKit accessory."""

    def __init__(self, aid: int):
        """Initialize a new accessory."""
        self.aid = aid
        self.services = Services()
        self._accessory_information: Service | None = None
        self._next_id = 0

    @property
    def characteristics(self) -> Characteristics:
        all_characteristics = Characteristics()
        for service in self.services:
            for characteristic in service.characteristics:
                all_characteristics.append(characteristic)
        return all_characteristics

    @classmethod
    def create_with_info(
        cls,
        aid: int,
        name: str,
        manufacturer: str,
        model: str,
        serial_number: str,
        firmware_revision: str,
    ) -> Self:
        """Create an accessory with the required services for HomeKit.

        This method should only be used for testing purposes as it assigns
        the next available ids to the accessory and services.
        """
        self = cls(aid)

        accessory_info = self.add_service(ServicesTypes.ACCESSORY_INFORMATION)
        accessory_info.add_char(CharacteristicsTypes.IDENTIFY, description="Identify")
        accessory_info.add_char(CharacteristicsTypes.NAME, value=name)
        accessory_info.add_char(CharacteristicsTypes.MANUFACTURER, value=manufacturer)
        accessory_info.add_char(CharacteristicsTypes.MODEL, value=model)
        accessory_info.add_char(CharacteristicsTypes.FIRMWARE_REVISION, value=firmware_revision)
        accessory_info.add_char(CharacteristicsTypes.SERIAL_NUMBER, value=serial_number)

        return self

    @classmethod
    def create_from_dict(cls, data: typed_dicts.Accessory) -> Self:
        """Create an accessory from a dict."""
        accessory = cls(data["aid"])

        for service_data in data["services"]:
            service = accessory.add_service(
                service_data["type"], iid=service_data["iid"], add_required=False
            )
            for char_data in service_data["characteristics"]:
                kwargs = dict()
                keys = {"perms", "format", "description", "min_value", "max_value", "valid_values", "unit", "min_step", "max_len", "handle", "broadcast_events", "disconnected_events", "value"}

                for key in keys:
                    camel_key = key.split('_')[0] + ''.join(word.title() for word in key.split('_')[1:])
                    if camel_key in char_data:
                        kwargs[key] = char_data[camel_key]

                assert "type" in char_data, f"Characteristic type is missing in {char_data}"
                assert "iid" in char_data, f"Characteristic iid is missing in {char_data}"

                service.add_char(
                    normalize_uuid(char_data["type"]), iid=char_data["iid"], **kwargs
                )

        for service_data in data["services"]:
            for linked_service in service_data.get("linked", []):
                # https://github.com/home-assistant/core/issues/100160
                # The Schlage Encode Plus can contain a 0 in this list which we have to ignore
                if linked_service:
                    accessory.services.iid(service_data["iid"]).add_linked_service(
                        accessory.services.iid(linked_service)
                    )

        return accessory

    @property
    def accessory_information(self) -> Service:
        """Returns the ACCESSORY_INFORMATION service for this accessory."""
        if self._accessory_information is None:
            self._accessory_information = self.services.first(
                service_type=ServicesTypes.ACCESSORY_INFORMATION
            )
        assert self._accessory_information is not None, 'No ACCESSORY_INFORMATION service found'
        return self._accessory_information

    @property
    def name(self) -> str:
        """Return the name of the accessory."""
        return self.accessory_information.value(CharacteristicsTypes.NAME, "")

    @property
    def manufacturer(self) -> str:
        """Return the manufacturer of the accessory."""
        return self.accessory_information.value(CharacteristicsTypes.MANUFACTURER, "")

    @property
    def model(self) -> str | None:
        """Return the model of the accessory."""
        return self.accessory_information.value(CharacteristicsTypes.MODEL, "")

    @property
    def serial_number(self) -> str:
        """Return the serial number of the accessory."""
        return self.accessory_information.value(CharacteristicsTypes.SERIAL_NUMBER, "")

    @property
    def firmware_revision(self) -> str:
        """Return the firmware revision of the accessory."""
        return self.accessory_information.value(
            CharacteristicsTypes.FIRMWARE_REVISION, ""
        )

    @property
    def hardware_revision(self) -> str:
        """Return the hardware revision of the accessory."""
        return self.accessory_information.value(
            CharacteristicsTypes.HARDWARE_REVISION, ""
        )

    @property
    def available(self) -> bool:
        """Return True if the accessory is available."""
        return all(s.available for s in self.services)

    @property
    def needs_polling(self) -> bool:
        """Check if there are any chars that need polling.

        Currently this is only used for BLE devices that have
        energy consumption characteristics.
        """
        for s in self.services:
            for c in s.characteristics:
                if c.type in NEEDS_POLLINGS_CHARS:
                    return True
        return False

    def get_next_id(self) -> int:
        """Return the next available id for a service."""
        self._next_id += 1
        return self._next_id

    def add_service(
        self,
        service_type: str,
        name: str | None = None,
        add_required: bool = False,
        iid: int | None = None,
    ) -> Service:
        """Add a service to the accessory."""
        service = Service(
            self, service_type, name=name, add_required=add_required, iid=iid
        )
        self.services.append(service)
        return service

    def as_dict(self) -> typed_dicts.Accessory:
        """Serialize the accessory to a dict."""
        return {
            "aid": self.aid,
            "services": [s.as_dict() for s in self.services],
        }
