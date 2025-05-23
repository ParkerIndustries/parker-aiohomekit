@dataclass
class AbstractDiscoveryInfo:
    id: str
    name: str
    status_flags: StatusFlags
    config_num: int
    category: Categories
