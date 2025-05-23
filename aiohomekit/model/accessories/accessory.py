
class Accessory:
    """Represents a HomeKit accessory."""

    def __init__(self, aid: int):
        """Initialize a new accessory."""
        self.aid = aid
        self._next_id = 0
        self.services = Services()
        self.characteristics = Characteristics()
        self._accessory_information: Service | None = None

    @classmethod
    def create_with_info(
        cls,
        aid: int,
        name: str,
        manufacturer: str,
        model: str,
        serial_number: str,
        firmware_revision: str,
    ) -> Accessory:
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

    @property
    def accessory_information(self) -> Service:
        """Returns the ACCESSORY_INFORMATION service for this accessory."""
        if self._accessory_information is None:
            self._accessory_information = self.services.first(
                service_type=ServicesTypes.ACCESSORY_INFORMATION
            )
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

    @classmethod
    def create_from_dict(cls, data: dict[str, Any]) -> Accessory: # TODO: refactor entity_map to normal Codable or pydantic protocol, or merge with typed dict
        """Create an accessory from a dict."""
        accessory = cls(data["aid"])

        for service_data in data["services"]:
            service = accessory.add_service(
                service_data["type"], iid=service_data["iid"], add_required=False
            )
            for char_data in service_data["characteristics"]:
                kwargs = {
                    "perms": char_data["perms"],
                }
                if "format" in char_data:
                    kwargs["format"] = char_data["format"]
                if "description" in char_data:
                    kwargs["description"] = char_data["description"]
                if "minValue" in char_data:
                    kwargs["min_value"] = char_data["minValue"]
                if "maxValue" in char_data:
                    kwargs["max_value"] = char_data["maxValue"]
                if "valid-values" in char_data:
                    kwargs["valid_values"] = char_data["valid-values"]
                if "unit" in char_data:
                    kwargs["unit"] = char_data["unit"]
                if "minStep" in char_data:
                    kwargs["min_step"] = char_data["minStep"]
                if "maxLen" in char_data:
                    kwargs["max_len"] = char_data["maxLen"]
                if "handle" in char_data:
                    kwargs["handle"] = char_data["handle"]
                if "broadcast_events" in char_data:
                    kwargs["broadcast_events"] = char_data["broadcast_events"]
                if "disconnected_events" in char_data:
                    kwargs["disconnected_events"] = char_data["disconnected_events"]

                char = service.add_char(
                    char_data["type"], iid=char_data["iid"], **kwargs
                )
                if char_data.get("value") is not None:
                    char.set_value(char_data["value"])

        for service_data in data["services"]:
            for linked_service in service_data.get("linked", []):
                # https://github.com/home-assistant/core/issues/100160
                # The Schlage Encode Plus can contain a 0 in this list which we have to ignore
                if linked_service:
                    accessory.services.iid(service_data["iid"]).add_linked_service(
                        accessory.services.iid(linked_service)
                    )

        return accessory

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

    def to_accessory_and_service_list(self) -> dict[str, Any]:
        """Serialize the accessory to a dict."""
        return {
            "aid": self.aid,
            "services": [s.to_accessory_and_service_list() for s in self.services],
        }
