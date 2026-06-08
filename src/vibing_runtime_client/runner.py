"""Run a RuntimeChannelClient until SIGTERM/SIGINT, then stop cleanly."""

import asyncio
import signal

from vibing_runtime_client.client import RuntimeChannelClient


def run_client(client: RuntimeChannelClient) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    main = loop.create_task(client.run())

    def _stop() -> None:
        client.stop()
        main.cancel()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _stop)

    try:
        loop.run_until_complete(main)
    except asyncio.CancelledError:
        pass
    finally:
        loop.close()
