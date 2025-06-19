from conftest import _get_mock_service_info, _install_mock_service_info
import pytest
from zeroconf.asyncio import AsyncZeroconf

from aiohomekit.controller.zeroconf.ip.controller import IpController
from aiohomekit.exceptions import AccessoryNotFoundError
from aiohomekit.model.categories import Category
from aiohomekit.model.status_flags import StatusFlags
from aiohomekit.storage.characteristics_storage import CharacteristicsStorageMemory
from aiohomekit.storage.pairing_data_storage import PairingDataStorageMemory


async def test_discover_find_one(mock_asynczeroconf: AsyncZeroconf):
    controller = IpController(
        zeroconf_instance=mock_asynczeroconf, pairing_data_storage=PairingDataStorageMemory(), char_cache_storage=CharacteristicsStorageMemory()
    )

    with _install_mock_service_info(mock_asynczeroconf, _get_mock_service_info()):
        async with controller:
            result = await controller.find("00:00:01:00:00:02", timeout_sec=0.001)

    assert result is not None
    assert result.description.id == "00:00:01:00:00:02"
    assert result.description.category == Category.LIGHTBULB
    assert result.description.config_num == 1
    assert result.description.state_num == 1
    assert result.description.model == "unittest"
    assert result.description.status_flags == StatusFlags(0)
    assert result.paired is True


async def test_async_reachable(mock_asynczeroconf: AsyncZeroconf):
    controller = IpController(
        zeroconf_instance=mock_asynczeroconf, pairing_data_storage=PairingDataStorageMemory(), char_cache_storage=CharacteristicsStorageMemory()
    )

    with _install_mock_service_info(mock_asynczeroconf, _get_mock_service_info()):
        async with controller:
            result = await controller.is_reachable("00:00:01:00:00:02", timeout_sec=0.001)

    assert result is True


async def test_async_reachable_not_reachable(mock_asynczeroconf: AsyncZeroconf):
    controller = IpController(
        zeroconf_instance=mock_asynczeroconf, pairing_data_storage=PairingDataStorageMemory(), char_cache_storage=CharacteristicsStorageMemory()
    )

    async with controller:
        result = await controller.is_reachable(
            "00:00:01:00:00:02", timeout_sec=0.001
        )

    assert result is False


async def test_discover_find_one_unpaired(mock_asynczeroconf: AsyncZeroconf):
    controller = IpController(
        zeroconf_instance=mock_asynczeroconf, pairing_data_storage=PairingDataStorageMemory(), char_cache_storage=CharacteristicsStorageMemory()
    )

    svc = _get_mock_service_info()
    svc.properties[b"sf"] = b"1"
    svc._set_properties(svc.properties) # type: ignore

    with _install_mock_service_info(mock_asynczeroconf, svc):
        async with controller:
            result = await controller.find("00:00:01:00:00:02", timeout_sec=0.001)

    assert result is not None
    assert result.description.id == "00:00:01:00:00:02"
    assert result.description.status_flags == StatusFlags.UNPAIRED
    assert result.paired is False


async def test_discover_find_none(mock_asynczeroconf):
    controller = IpController(
        zeroconf_instance=mock_asynczeroconf, pairing_data_storage=PairingDataStorageMemory(), char_cache_storage=CharacteristicsStorageMemory()
    )

    async with controller:
        with pytest.raises(AccessoryNotFoundError):
            await controller.find("00:00:00:00:00:00", timeout_sec=0.001)


async def test_find_device_id_case_lower(mock_asynczeroconf: AsyncZeroconf):
    controller = IpController(
        zeroconf_instance=mock_asynczeroconf, pairing_data_storage=PairingDataStorageMemory(), char_cache_storage=CharacteristicsStorageMemory()
    )

    svc_info_1 = _get_mock_service_info()
    svc_info_1.properties[b"id"] = b"aa:aa:aa:aa:aa:aa"
    svc_info_1._set_properties(svc_info_1.properties) # type: ignore

    with _install_mock_service_info(mock_asynczeroconf, svc_info_1):
        async with controller:
            res = await controller.find("AA:AA:AA:AA:AA:AA", timeout_sec=0.001)
            assert res and res.description.id == "aa:aa:aa:aa:aa:aa"

    svc_info_2 = _get_mock_service_info()
    svc_info_2.properties[b"id"] = b"aa:aa:aa:aa:aa:aa"
    svc_info_2._set_properties(svc_info_2.properties) # type: ignore

    with _install_mock_service_info(mock_asynczeroconf, svc_info_2):
        svc_info_2.properties[b"id"] = b"aa:aa:aa:aa:aa:aa"

        async with controller:
            res = await controller.find("aa:aa:aa:aa:aa:aa", timeout_sec=0.001)
            assert res and res.description.id == "aa:aa:aa:aa:aa:aa"


async def test_find_device_id_case_upper(mock_asynczeroconf: AsyncZeroconf):
    controller = IpController(
        zeroconf_instance=mock_asynczeroconf, pairing_data_storage=PairingDataStorageMemory(), char_cache_storage=CharacteristicsStorageMemory()
    )

    svc_info = _get_mock_service_info()
    svc_info.properties[b"id"] = b"AA:AA:aa:aa:AA:AA"
    svc_info._set_properties(svc_info.properties) # type: ignore

    with _install_mock_service_info(mock_asynczeroconf, svc_info):
        async with controller:
            res = await controller.find("AA:AA:AA:AA:AA:AA", timeout_sec=0.001)
            assert res and res.description.id == "aa:aa:aa:aa:aa:aa"

    svc_info = _get_mock_service_info()
    svc_info.properties[b"id"] = b"AA:AA:aa:aa:AA:AA"
    svc_info._set_properties(svc_info.properties) # type: ignore

    with _install_mock_service_info(mock_asynczeroconf, svc_info):
        async with controller:
            res = await controller.find("aa:aa:aa:aa:aa:aa", timeout_sec=0.001)
            assert res and res.description.id == "aa:aa:aa:aa:aa:aa"


async def test_discover_discover_one(mock_asynczeroconf: AsyncZeroconf):
    controller = IpController(
        zeroconf_instance=mock_asynczeroconf, pairing_data_storage=PairingDataStorageMemory(), char_cache_storage=CharacteristicsStorageMemory()
    )

    with _install_mock_service_info(mock_asynczeroconf, _get_mock_service_info()):
        async with controller:
            results = [d async for d in controller.discover(timeout_sec=0.001)]

    assert results[0].description.id == "00:00:01:00:00:02"
    assert results[0].description.category == Category.LIGHTBULB
    assert results[0].description.config_num == 1
    assert results[0].description.state_num == 1
    assert results[0].description.model == "unittest"
    assert results[0].description.status_flags == StatusFlags(0)
    assert results[0].paired is True


async def test_discover_none(mock_asynczeroconf):
    controller = IpController(
        zeroconf_instance=mock_asynczeroconf, pairing_data_storage=PairingDataStorageMemory(), char_cache_storage=CharacteristicsStorageMemory()
    )

    results = [d async for d in controller.discover(timeout_sec=0.001)]
    assert results == []


async def test_discover_missing_csharp(mock_asynczeroconf: AsyncZeroconf):
    controller = IpController(
        zeroconf_instance=mock_asynczeroconf, pairing_data_storage=PairingDataStorageMemory(), char_cache_storage=CharacteristicsStorageMemory()
    )

    svc_info = _get_mock_service_info()
    del svc_info.properties[b"c#"]
    svc_info._set_properties(svc_info.properties) # type: ignore

    with _install_mock_service_info(mock_asynczeroconf, svc_info):
        async with controller:
            results = [d async for d in controller.discover(timeout_sec=0.001)]

    assert results[0].description.id == "00:00:01:00:00:02"
    assert results[0].description.config_num == 0


async def test_discover_csharp_case(mock_asynczeroconf: AsyncZeroconf):
    controller = IpController(
        zeroconf_instance=mock_asynczeroconf, pairing_data_storage=PairingDataStorageMemory(), char_cache_storage=CharacteristicsStorageMemory()
    )

    svc_info = _get_mock_service_info()
    del svc_info.properties[b"c#"]
    svc_info.properties[b"C#"] = b"1"
    svc_info._set_properties(svc_info.properties) # type: ignore

    with _install_mock_service_info(mock_asynczeroconf, svc_info):
        async with controller:
            results = [d async for d in controller.discover(timeout_sec=0.001)]

    assert results[0].description.config_num == 1


async def test_discover_device_id_case_lower(mock_asynczeroconf: AsyncZeroconf):
    controller = IpController(
        zeroconf_instance=mock_asynczeroconf, pairing_data_storage=PairingDataStorageMemory(), char_cache_storage=CharacteristicsStorageMemory()
    )

    svc_info = _get_mock_service_info()
    svc_info.properties[b"id"] = b"aa:aa:aa:aa:aa:aa"
    svc_info._set_properties(svc_info.properties) # type: ignore

    with _install_mock_service_info(mock_asynczeroconf, svc_info):
        async with controller:

            results = [d async for d in controller.discover(timeout_sec=0.001)]

    assert results[0].description.id == "aa:aa:aa:aa:aa:aa"


async def test_discover_device_id_case_upper(mock_asynczeroconf: AsyncZeroconf):
    controller = IpController(
        zeroconf_instance=mock_asynczeroconf, pairing_data_storage=PairingDataStorageMemory(), char_cache_storage=CharacteristicsStorageMemory()
    )

    svc_info = _get_mock_service_info()
    svc_info.properties[b"id"] = b"AA:AA:aa:aa:AA:AA"
    svc_info._set_properties(svc_info.properties) # type: ignore

    with _install_mock_service_info(mock_asynczeroconf, svc_info):
        async with controller:

            results = [d async for d in controller.discover(timeout_sec=0.001)]

    assert results[0].description.id == "aa:aa:aa:aa:aa:aa"
