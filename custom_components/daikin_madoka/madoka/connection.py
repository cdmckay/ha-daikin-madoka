import asyncio
import logging
from asyncio.exceptions import CancelledError
from enum import Enum
from typing import Callable, Dict, Optional

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

from .consts import NOTIFY_CHAR_UUID, SEND_MAX_TRIES, WRITE_CHAR_UUID
from .transport import Transport, TransportDelegate

logger = logging.getLogger(__name__)


class ConnectionException(Exception):
    """Exceptions are documented in the same way as classes.

    The __init__ method may be documented in either the class level
    docstring, or as a docstring on the __init__ method itself.

    Either form is acceptable, but the two should not be mixed. Choose one
    convention to document the __init__ method and be consistent with it.

    """

    pass


class ConnectionStatus(Enum):
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    ABORTED = 3


class Connection(TransportDelegate):
    """Bluetooth client"""

    client: BleakClient = None

    """This class implements the bluetooth connection to the device.

    It communicates with the device to send and receive data that is passed to the `Transport` to be rebuilt.
    all the features supported by the device and provides methods to operate globally on all the features.
    However, each feature can be queried/updated independently by accesing the feature attributes.

    Attributes:
        client (BleakClient): Bluetooth device client
        transport (`Transport`): Transport used for the protocol
        address (str): MAC address of the device
        name (str): Name of the device when available
        current_future (Future): Future of the current command being processed
        connected (ConnectionStatus): Status of the connection
        adapter (str): Bluetooth adapter used for the client

    """

    def __init__(
        self,
        address: str,
        adapter: str = None,
        reconnect: bool = True,
        ble_device: Optional[BLEDevice] = None,
        ble_device_provider: Optional[Callable[[], Optional[BLEDevice]]] = None,
    ):
        """Inits the connection with the device address.

        Args:
            address (str): MAC address of the device
            adapter (str): Unused; retained for backwards compatibility. Home
                Assistant selects the adapter via the injected BLEDevice.
            ble_device (BLEDevice): Pre-resolved device from Home Assistant's
                central scanner. Required inside HA — the library no longer runs
                its own BleakScanner (which collided with HA's scanner and
                wedged the link with org.bluez InProgress errors).
            ble_device_provider: Optional zero-arg callable returning the
                freshest BLEDevice for this address. Called before every
                (re)connect so reconnections always use a current device.
        """
        self.reconnect = reconnect
        self.adapter = adapter
        self.address = address
        self.name = self.address
        self.client = None
        self.ble_device = ble_device
        self.ble_device_provider = ble_device_provider
        self.connection_status = ConnectionStatus.DISCONNECTED
        self.last_info = None
        self.transport = Transport(self)
        self.current_future = None
        self.requests = {}
        self._closing = False

    def on_disconnect(self, client: BleakClient):
        self.connection_status = ConnectionStatus.DISCONNECTED
        logger.info(f"Disconnected {self.address}!")
        # Don't auto-reconnect while the entry is being unloaded/cleaned up,
        # otherwise the reconnect loop leaks across a reload.
        if self._closing or not self.reconnect:
            return
        asyncio.create_task(self.start())

    async def cleanup(self):
        self._closing = True
        if self.client:
            await self.client.stop_notify(NOTIFY_CHAR_UUID)
            await self.client.disconnect()
        self.connection_status = ConnectionStatus.DISCONNECTED

    async def start(self):
        """Starts the connection manager.

        The device is connected directly using the BLEDevice provided by Home
        Assistant's central scanner (resolved fresh via ``ble_device_provider``
        before each attempt). The library no longer runs its own BleakScanner —
        doing so collided with HA's scanner on the same adapter and wedged the
        link with org.bluez InProgress errors.
        """
        logger.debug(f"Starting connection manager on {self.address}")
        self.connection_status = ConnectionStatus.CONNECTING
        while (
            not self.connection_status == ConnectionStatus.CONNECTED
            and not self.connection_status == ConnectionStatus.ABORTED
        ):
            if self._closing:
                self.connection_status = ConnectionStatus.DISCONNECTED
                return
            try:
                await self._connect()
                await asyncio.sleep(2.0)
            except ConnectionAbortedError:
                self.connection_status = ConnectionStatus.ABORTED
            except CancelledError:
                # Propagate cancellation so asyncio.wait_for() and config-entry
                # unload can actually stop this reconnect loop. This used to be
                # swallowed, which made start() uncancellable and hung Home
                # Assistant's setup forever when the device was reachable (in
                # the BLE scan) but not connectable.
                self.connection_status = ConnectionStatus.DISCONNECTED
                raise
            except Exception:
                self.connection_status = ConnectionStatus.ABORTED

    async def _connect(self):
        # Always prefer the freshest BLEDevice from Home Assistant's central
        # scanner; an address-only fallback cannot be opened by bleak.
        if self.ble_device_provider is not None:
            fresh = self.ble_device_provider()
            if fresh is not None:
                self.ble_device = fresh
        if self.ble_device is None:
            self.connection_status = ConnectionStatus.ABORTED
            raise ConnectionAbortedError(
                f"No BLEDevice available for {self.address}; "
                "Home Assistant has not seen it advertise yet."
            )
        self.name = self.ble_device.name or self.address
        try:
            # Use bleak-retry-connector instead of a raw BleakClient.connect().
            # Inside Home Assistant this reserves a connection slot via the
            # central manager and serializes attempts, which avoids the
            # org.bluez InProgress / br-connection-canceled race that otherwise
            # wedges the link at ~1 failed connect/sec. It also retries with
            # backoff and works standalone (outside HA) against vanilla bleak.
            self.client = await establish_connection(
                BleakClient,
                self.ble_device,
                self.name,
                disconnected_callback=self.on_disconnect,
            )
        except Exception as e:
            if "Software caused connection abort" not in str(e):
                logger.error(e)
            if not self.reconnect:
                raise e
            logger.debug("Reconnecting...")
            return

        logger.info(f"Connected to {self.address}")
        self.connection_status = ConnectionStatus.CONNECTED
        await self.client.start_notify(
            NOTIFY_CHAR_UUID,
            self.notification_handler,
        )

    def notification_handler(self, sender: str, data: bytearray):
        """This callback is used to receive the data read from the device (chunks) and attempt to rebuild the message.

        Args:
            sender (str) : Client ID
            data (bytearray): Data to be rebuilt
        """
        self.transport.rebuild_chunk(data)

    def cmd_id_to_bytes(self, cmd_id: int):
        return bytearray([0x00]) + cmd_id.to_bytes(2, "big")

    def bytes_to_cmd_id(self, data: bytes):
        return int.from_bytes(data[2:4], "big")

    async def send(self, cmd_id: int, data: bytearray):
        """This method is used to send data to the device.
        The `transport` is used to split the data into chunks as required by the communication protocol and these chunks are sent in order to the device.

        Args:
            cmd_id (str) : Command ID to be sent
            data (bytearray): Data to be sent
        Returns:
            Future: Callers of this methods must await this Future to receive the result of the command execution
        """

        cmd_response = asyncio.get_event_loop().create_future()
        if cmd_id not in self.requests:
            self.requests[cmd_id] = []

        self.requests[cmd_id].append(cmd_response)

        if self.connection_status is not ConnectionStatus.CONNECTED:
            cmd_response.cancel()
            return cmd_response

        # length, 0x00, cmdid, payload
        payload = bytearray([0x00]) + self.cmd_id_to_bytes(cmd_id) + data

        payload[0] = len(payload)

        logger.debug(f"Sending cmd payload: {bytes(payload).hex()}")

        chunks = self.transport.split_in_chunks(payload)
        sent = 0

        self.current_cmd_id = cmd_id
        for chunknum, chunk in enumerate(chunks):
            for i in range(0, SEND_MAX_TRIES):
                try:
                    if self.connection_status is not ConnectionStatus.CONNECTED:
                        cmd_response.cancel()
                        return cmd_response

                    await self.client.write_gatt_char(WRITE_CHAR_UUID, chunk)
                    logger.debug(
                        f"CMD {cmd_id}. Chunk #{chunknum + 1}/{len(chunks)} sent with size {len(chunk)} bytes"
                    )
                    sent += 1
                    break
                except CancelledError as e:
                    logger.debug(
                        f"Send command failed. Retrying ({i}/{SEND_MAX_TRIES}) for chunk #{chunknum} : {str(e)}",
                        exc_info=e,
                    )
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.debug(
                        f"Send command failed. Retrying ({i}/{SEND_MAX_TRIES}) for chunk #{chunknum} : {str(e)}"
                    )
                    await asyncio.sleep(1)

        if sent != len(chunks) and self.connection_status == ConnectionStatus.CONNECTED:
            raise ConnectionException("Command chunks could not be sent")

        return cmd_response

    def response_rebuilt(self, data: bytearray):
        """This callback is used to receive messages rebuilt by the transport.

        The messages are used to resolve the future used when the command was sent.

        See base class `TransportDelegate`."""

        if len(data) <= 4:
            return

        cmd_id = self.bytes_to_cmd_id(data)

        if cmd_id not in self.requests:
            return
        if len(self.requests[cmd_id]) > 0:
            req = self.requests[cmd_id].pop(0)
            if req.done():
                return
            req.set_result(data)

    def response_failed(self, data: bytearray):
        """This callback is used to cancel the future used when the command was sent.

        See base class `TransportDelegate`."""

        if len(data) <= 4:
            return

        cmd_id = self.bytes_to_cmd_id(data)

        if cmd_id not in self.requests:
            return

        if len(self.requests[cmd_id]) > 0:
            req = self.requests[cmd_id].pop(0)
            if req.done():
                return
            req.cancel()

    async def read_info(self) -> Dict[str, str]:
        """This method is used to retrieve the information stored in the Bluetooth Services available in the device.

        This information is related to the Software Version, Hardware Version, Model Number and others.

        Returns:
            Dict[str,str]: Dictionary with all the info values
        """
        try:
            if self.last_info:
                return self.last_info

            if self.connection_status is not ConnectionStatus.CONNECTED:
                return {}

            values = {}

            for service in self.client.services:
                logger.debug(
                    "[Service] {0}: {1}".format(service.uuid, service.description)
                )
                for char in service.characteristics:
                    if "read" in char.properties:
                        try:
                            raw = await self.client.read_gatt_char(char.uuid)
                            value = None

                            try:
                                if char.description.endswith(" ID"):
                                    value = (
                                        raw.hex().replace("fe", "-").replace("ff", "")
                                    )
                                else:
                                    value = raw.decode()
                            except Exception:
                                value = str(raw)
                            values[char.description] = value
                            logger.debug(
                                "\t[Characteristic] {0}: (Handle: {1}) ({2}) | Name: {3}, Value: {4} ".format(
                                    char.uuid,
                                    char.handle,
                                    ",".join(char.properties),
                                    char.description,
                                    value,
                                )
                            )
                        except Exception as e:
                            logger.error(e)

            self.last_info = values
            return self.last_info
        except Exception as e:
            logger.error(e)
            raise e
