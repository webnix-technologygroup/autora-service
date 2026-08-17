import signal
import time
import uuid

from django.core.management.base import BaseCommand

from service.notifications import process_batch


class Command(BaseCommand):
    help = "Обрабатывает transactional outbox"

    def add_arguments(self, p):
        p.add_argument("--limit", type=int, default=100)
        p.add_argument("--loop", action="store_true")
        p.add_argument("--sleep", type=float, default=10)

    def handle(self, *args, **o):
        stopped = False

        def stop(*_):
            nonlocal stopped
            stopped = True

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        worker = f"cmd-{uuid.uuid4()}"
        while not stopped:
            count = process_batch(o["limit"], worker)
            self.stdout.write(f"processed={count}")
            if not o["loop"]:
                break
            time.sleep(o["sleep"] if count == 0 else 0.1)
