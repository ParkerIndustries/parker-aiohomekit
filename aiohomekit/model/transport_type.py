from enum import Enum


class TransportType(str, Enum):
    IP = "ip"
    COAP = "coap"
    BLE = "ble"
