from multiprocessing import Queue, Process
from queue import Empty
import os
from tqdm import tqdm
from typing import Callable, Iterable
import logging

# Set up logger
logger = logging.getLogger(__name__)

def worker(task_queue, task, catch_errors: bool = True):
    while True:
        try:
            args = task_queue.get(timeout=1)
            if args is None:
                break
            logger.debug(f"[PID {os.getpid()}] Processing task")
            task(*args)
        except Empty:
            continue
        except Exception as e:
            if catch_errors:
                logger.error(f"[PID {os.getpid()}] Worker error: {e}")
            else:
                raise e


def run_parallel(processor: Callable, tasks: Iterable, workers = None, catch_errors: bool = True, log_level: str | None = None, task_count: int | None = None):
    workers = workers or os.cpu_count() or 4
    
    # Configure logging based on whether we're running in parallel or not
    if log_level is None:
        log_level = 'INFO' if workers == 1 else 'WARNING'
    logging.basicConfig(
        level=log_level,
        format='[%(process)d] %(message)s'
    )
    
    logger.debug(f"Starting processing with {workers} workers")
    
    if workers > 1:
        task_queue = Queue(maxsize=100)
        
        # Start worker processes
        processes = []
        for _ in range(workers):
            p = Process(target=worker, args=(task_queue, processor, catch_errors))
            p.start()
            processes.append(p)

    # Load tasks into queue
    for task_item in tqdm(tasks, total=task_count):
        if workers > 1:
            task_queue.put(task_item)
        else:
            processor(*task_item)

    if workers > 1:
        # Signal workers to exit
        for _ in range(workers):
            task_queue.put(None)

        # Wait for all processes to complete
        for p in processes:
            p.join()