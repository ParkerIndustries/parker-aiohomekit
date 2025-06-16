from enum import Enum


class TransportType(str, Enum):
    IP = "IP"
    COAP = "COAP"
    BLE = "BLE"

class IpTransportType(str, Enum):
    TCP = "tcp"
    UDP = "udp"

class HAPZeroconfType(str, Enum):
    TCP = "_hap._tcp.local."
    UDP = "_hap._udp.local."
