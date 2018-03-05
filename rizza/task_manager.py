# -*- encoding: utf-8 -*-
"""A task handler to import, export, and run test tasks."""
import json
from collections import deque
from multiprocessing.pool import ThreadPool as Pool
import attr
from logzero import logger
from rizza.entity_tester import EntityTestTask
from rizza.helpers.misc import json_serial
# joblib (run on multiple cores)
# pykafka (share info between parallel python processes)
# spark (run on multiple machines)


def coroutine(func):
    """Helper generator created by David Beazley."""
    def start(*args, **kwargs):
        """Call next on the function and return the value."""
        g = func(*args, **kwargs)
        g.next()
        return g
    return start


@attr.s()
class TaskManager(object):
    """A simple class to create, import, export and run tasks."""

    tasks = attr.ib(default=attr.Factory(deque))

    @staticmethod
    def import_tasks(path=None):
        """Import saved tasks from a file.

        :params path: Path to the tasks file.
        """
        with open(path, 'r') as infile:
            for line in infile:
                logger.debug('Importing: {}'.format(line))
                yield EntityTestTask(**json.loads(line))
        logger.info('Finished importing.')

    @staticmethod
    def export_tasks(path=None, tasks=None):
        """Export current tasks to a file.

        :params path: Path to the save file. If none, a name will be created.
        :params tasks: Can either be a list of tasks, or a task generator.
        """
        with open(path, 'w') as outfile:
            for task in tasks:
                logger.debug('Exporting: {}'.format(task))
                json.dump(
                    attr.asdict(
                        task,
                        filter=lambda attr, value: attr.name != 'config'
                    ),
                    outfile
                )
                outfile.write("\n")
        logger.info('Finished exporting.')

    @staticmethod
    def run_tests(tests=None, mock=False):
        """Run the tests passed in."""
        for test in tests:
            logger.info("{0}~{1}~{2}\n".format(
                json.dumps(attr.asdict(test), default=json_serial),
                json.dumps(test.execute(mock), default=json_serial),
                json.dumps(attr.asdict(test), default=json_serial)
            ))

    @coroutine
    def run_tasks(self, limit=None, threads=1):
        """Run the tasks currently in the deque.

        :params limit: The maximum number of tasks to run.
        :params threads: Number of threads to run tasks on (default is 1).
        """
        # pool = Pool(10)
        # for result in pool.imap_unordered(execute, tasks)
        #     print(result)
        # try:
        #     self.tasks.popleft().execute()
        # except GeneratorExit:
        #     return "No more tasks in the queue."
        pass
