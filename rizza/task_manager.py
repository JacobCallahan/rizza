"""A task handler to import, export, and run test tasks."""
import asyncio
from contextlib import suppress
import json
from pathlib import Path

import attr
from logzero import logger

from rizza.entity_tester import EntityTestTask
from rizza.helpers.misc import json_serial


@attr.s()
class TaskManager:
    """A simple class to create, import, export and run tasks."""

    @staticmethod
    def import_tasks(path):
        """Import saved tasks from a file.

        :params path: Path to the tasks file.
        """
        infile = Path(path).read_text()
        for line in infile.splitlines():
            logger.debug(f"Importing: {line}")
            yield EntityTestTask(**json.loads(line))
        logger.info("Finished importing.")

    @staticmethod
    def export_tasks(path, tasks=None):
        """Export current tasks to a file.

        :params path: Path to the save file. If none, a name will be created.
        :params tasks: Can either be a list of tasks, or a task generator.
        """
        output = []
        for task in tasks:
            logger.debug(f"Exporting: {task}")
            output.append(attr.asdict(task, filter=lambda attr, value: attr.name != "config"))
        Path(path).write_text(json.dumps(output, default=json_serial))
        logger.info("Finished exporting.")

    @staticmethod
    def run_tests(tests=None, mock=False):
        """Run the tests passed in."""
        for test in tests:
            logger.info(
                "{}~{}~{}\n".format(
                    json.dumps(attr.asdict(test), default=json_serial),
                    json.dumps(test.execute(mock), default=json_serial),
                    json.dumps(attr.asdict(test), default=json_serial),
                )
            )


@attr.s()
class AsyncTaskManager(TaskManager):
    """An asynchronous version of the TaskManager class."""

    task_generator = attr.ib()
    max_running = attr.ib(default=25)

    def __attrs_post_init__(self):
        """Setup our remaining helpers"""
        self.loop = asyncio.get_event_loop()
        self.max_running = asyncio.Semaphore(self.max_running)
        if isinstance(self.task_generator, str):
            self.task_generator = super().import_tasks(self.task_generator)

    async def _run_test(self, test, mock=False):
        before = attr.assoc(test)
        async with self.max_running:
            try:
                result = await self.loop.run_in_executor(None, test.execute, mock)
            except Exception as err:
                logger.error(err)
                result = "Unhandled Exception"
        logger.info(
            "{}~{}~{}\n".format(
                json.dumps(attr.asdict(before), default=json_serial),
                json.dumps(test.execute(result), default=json_serial),
                json.dumps(attr.asdict(test), default=json_serial),
            )
        )

    async def _async_loop(self, mock=False):
        """Run the tests passed in and return the log file"""
        tasks = [asyncio.ensure_future(self._run_test(task, mock)) for task in self.task_generator]
        await asyncio.wait(tasks)

    def run_tests(self, mock=False):
        """Run the tests passed in."""
        self.loop.run_until_complete(self._async_loop(mock))
        with suppress(IndexError):
            return logger.handlers[1].baseFilename
