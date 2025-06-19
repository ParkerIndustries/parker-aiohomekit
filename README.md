# aiohomekit by Parker Industries

**This library is still in development. No guarantees are made. Features may be incomplete or buggy, and might change over time.**

This library implements the HomeKit protocol for controlling Homekit accessories using asyncio.

This library is a fork of [Jc2k/aiohomekit](https://github.com/Jc2k/aiohomekit) with major refactoring. It is not backwards compatible with the original library and can't be used as a drop-in replacement.

It's primary use is for [MajorDom](https://majordom.io), so python version and code standards are the same as at MajorDom.

## Changes

### Notes to adapt the new API:

- storage mechanisms (for pairing data and characteristics cache) have been completed to automatically load and save all data, and delegated from controllers to separate injected Storage classes, which provide interface for CRUD operations and manage data persistence
- Pairings and Discoveries no longer have a reference to the controller
- finish_pairing returns PairingData, which can be used to instantiate a Pairing
- async methods marked with `async` keyword no longer have `async_` prefix
- some methods have been renamed for clarity
- arguments for some methods have been changed to correspond to the abstract classes
- redundant methods and arguments have been removed
- files have been restructured to improve organization and maintainability, which may require changes in imports
- to try the library or view the examples, check the renewed `__main__.py`
- for other details, check the declaration of the classes and methods, it's pretty self-explanatory now

### Other changes include:
- added more type hints, comments, and more clear names
- fixed bugs related to data persistence and storage management
- fixed saving of updated pairing data when DHCP changes the IP address of the accessory

## Roadmap

Currently only ip discovery, pairing, and control is tested.

Next steps to implement are:
- BLE discovery
- BLE pairing and provisioning of WiFi and Thread credentials
- Device control over BLE and COAP (Thread))
- Tests for the features above
- Fix all errors and warnings from linters and type checkers. (most of them due to ignoring optional types)
- Fix all docstrings since they became deprecated before this fork was even created

## Code Quality Analysis (TODO)

This projects uses tool stack by astra.sh:
- `uv` project manager instead of `poetry`
- `ruff` linter+formatter instead of `black`, `isort`, and `flake8`
- `ty` static type checker instead of `mypy`

## Contributing (legacy)

Lots of users are using this library with devices from a wide array of vendors. As a community open source project we do not have the hardware or time resources to certify every device with multiple vendors projects. We may be conservative about larger changes or changes that are low level. We do ask where possible that any changes should be tested with a certified HomeKit implementations of shipping products, not just against emulators or other uncertified implementations.

Please bear in mind that some shipping devices interpret the HAP specification loosely. In general we prefer to match the behaviour of real HAP controllers even where their behaviour is not strictly specified. Here are just some of the kinds of problems we've had to work around:

* Despite the precise formatting of JSON being unspecified, there are devices in the wild that cannot handle spaces when parsing JSON. For example, `{"foo": "bar"}` vs `{"foo":"bar"}`. This means we never use a "pretty" encoding of JSON.
* Despite a boolean being explicitly defined as `0`, `1`, `true` or `false` in the spec, some devices only support 3 of the 4. This means booleans must be encoded as `0` or `1`.
* Some devices have shown themselves to be sensitive to headers being missing, in the wrong order or if there are extra headers. So we ensure that only the headers iOS sends are present, and that the casing and ordering is the same.
* Some devices are sensitive to a HTTP message being split into separate TCP packets. So we take care to only write a full message to the network stack.

And so on. As a rule we need to be strict about what we send and loose about what we receive.

## Device compatibility (legacy)

`aiohomekit` is primarily tested with a Phillips Hue bridge and an Eve Extend bridge. It is known to work to some extent with many more devices though these are not currently explicitly documented anywhere at the moment.

You can look at the problems your device has faced in the home-assistant [issues list](https://github.com/home-assistant/core/issues?q=is%3Aopen+is%3Aissue+label%3A%22integration%3A+homekit_controller%22).

## FAQ (legacy, TODO)

### How do I use this?

Check the __main__.py file for examples.


### Does this support BLE accessories?

No. Eventually we hope to via [aioble](https://github.com/detectlabs/aioble) which provides an asyncio bluetooth abstraction that works on Linux, macOS and Windows.

### Can i use this to make a homekit accessory?

No, this is just the client part. You should use one the of other implementations:

 * [homekit_python](https://github.com/jlusiardi/homekit_python/) (this is used a lot during aiohomekit development)
 * [HAP-python](https://github.com/ikalchev/HAP-python)

### Why doesn't aiohomekit use library X instead?

Where possible aiohomekit uses libraries that are easy to install with pip, are ready available as wheels (including on Raspberry Pi via piwheels), are cross platform (including Windows) and are already used by Home Assistant. They should not introduce hard dependencies on uncommon system libraries. The intention here is to avoid any difficulty in the Home Assistant build process.

People are often alarmed at the hand rolled HTTP code and suggest using an existing HTTP library like `aiohttp`. High level HTTP libraries are pretty much a non-starter because:

* Of the difficulty of adding in HAP session security without monkey patches.
* They don't expect responses without requests (i.e. events).
* As mentioned above, some of these devices are very sensitive. We don't care if your change is compliant with every spec if it still makes a real world device cry. We are not in a position to demand these devices be fixed. So instead we strive for byte-for-byte accuracy on our write path. Any library would need to give us that flexibility.
* Some parts of the responses are actually not HTTP, even though they look it.

We are also just reluctant to make a change that large for something that is working with a lot of devices. There is a big chance of introducing a regression.

Of course a working proof of concept (using a popular well maintained library) that has been tested with something like a Tado internet bridge (including events) would be interesting.

## Thanks

This library wouldn't have been possible without homekit_python, a synchronous implementation of both the client and server parts of HAP.
