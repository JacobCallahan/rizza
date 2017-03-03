# -*- encoding: utf-8 -*-
"""A task handler to import, export, and run test tasks."""
import json
from collections import deque
from multiprocessing.pool import ThreadPool as Pool
import attr
from rizza.entity_tester import EntityTestTask
# joblib (run on multiple cores)
# pykafka (share info between parallel python processes)
# spark (run on multiple machines)


def coroutine(func):
    """Helper generator created by David Beazley."""
    def start(*args, **kwargs):
        """Call next on the function and returns the value."""
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
        with open(path) as infile:
            for line in infile:
                yield EntityTestTask(**json.loads(line))

    @staticmethod
    def export_tasks(path=None, tasks=None):
        """Export current tasks to a file.

        :params path: Path to the save file. If none, a name will be created.
        :params tasks: Can either be a list of tasks, or a task generator.
        """
        with open(path, "w") as outfile:
            for task in tasks:
                json.dump(attr.asdict(task), outfile)
                outfile.write("\n")

    @staticmethod
    def log_tests(path=None, tests=None):
        """Run and log the tests passed in."""
        with open(path, "w") as log:
            print ("Writing to log file: {0}".format(path))
            for test in tests:
                json.dump(test, log)
                log.write("~{}\n".format(test.execute()))

    @coroutine
    def run_tasks(self, limit=None, threads=1):
        """Run the tasks currently in the deque.

        :params limit: The maximum number of tasks to run.
        :params threads: Number of threads to run tasks on (default is 1).
        """
        # pool = Pool(10)
        # for result in pool.imap_unordered(execute, tasks)
        #     print (result)
        # try:
        #     self.tasks.popleft().execute()
        # except GeneratorExit:
        #     return "No more tasks in the queue."
        pass
