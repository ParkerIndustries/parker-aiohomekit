
class PairingData(TypedDict, total=True): # TODO: replace typed dicts with normal models
    # TODO: recheck keys: has AccessoryIP vs AccessoryAddress
    AccessoryPairingID: str
    AccessoryLTPK: str
    iOSPairingId: str
    iOSDeviceLTSK: str
    iOSDeviceLTPK: str
    AccessoryIP: str
    Connection: str
