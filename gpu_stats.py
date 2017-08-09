import json
import time
import docker
import logging
logger = logging.getLogger(__name__)
import threading

docker_client = docker.from_env(version="auto", timeout=5)
current_threads = dict()

class ContainerMonitor(threading.Thread):
    
    def __init__(self, container_id, stats_queue):
        super(ContainerMonitor, self).__init__()
        self.container = docker_client.containers.get(container_id)
        self.stop = False
        self.stats_queue = stats_queue
        

    def run(self):
        logger.info("Start monitoring container %s" % self.container.id)
        stats = self.container.stats(decode=True, stream=True)
        previous_cpu = 0.0
        previous_system = 0.0
        for s in stats:
            if self.stop:
                logger.info("Stopped monitoring container %s" % self.container.id)
                break
            previous_cpu = s['precpu_stats']['cpu_usage']['total_usage']
            previous_system = s['precpu_stats']['system_cpu_usage']
            cpu_percent, percpu_percent = calculate_cpu_percent(previous_cpu, previous_system, s)
            memory_usage = s['memory_stats']['usage']
            memory_limit = s['memory_stats']['limit']
            logger.info("%s: %s %s %s %s" % (self.container.id, cpu_percent, memory_usage, memory_limit, percpu_percent))


# according to: https://github.com/moby/moby/blob/eb131c5383db8cac633919f82abad86c99bffbe5/cli/command/container/stats_helpers.go#L175-L188
def calculate_cpu_percent(previous_cpu, previous_system, s):
    cpu_percent = 0.0
    num_cpus = len(s['cpu_stats']['cpu_usage']['percpu_usage'])
    percpu_percent = [0.0 for _ in range(num_cpus)]
    total_usage = float(s['cpu_stats']['cpu_usage']['total_usage'])
    cpu_delta = total_usage - previous_cpu
    system_delta = float(s['cpu_stats']['system_cpu_usage']) - previous_system
    if system_delta > 0 and cpu_delta > 0:
        cpu_percent = (cpu_delta / system_delta) * float(num_cpus) * 100.0
        percpu_percent = [percpu / total_usage * cpu_percent for percpu in s['cpu_stats']['cpu_usage']['percpu_usage']]
    return cpu_percent, percpu_percent


def stop_container_monitors(container_ids):
    for c_id in container_ids:
        if c_id in current_threads:
            current_threads[c_id].stop = True
        else:
            logger.warn("Tried stopping non-existent container monitor: %s " % c_id)


def monitor_containers(container_ids, container_stats, stop_others=False):
    if stop_others:
        others = set(current_threads.keys()) - set(container_ids)
        for o in others:
            o.stop = True
        current_threads.clear()
    for c_id in container_ids:
        if c_id not in current_threads:
            monitor = ContainerMonitor(c_id, container_stats)
            monitor.start()
            current_threads[c_id] = monitor


if __name__ == '__main__':
    import queue
    import sys
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)
    container_stats = queue.Queue()
    print(len(sys.argv))
    if len(sys.argv) == 2:
        containers = [sys.argv[1]]
    else:
        containers = [docker_client.containers.list()[0].id]
    monitor_containers(containers, container_stats)
    time.sleep(10)
    stop_container_monitors(containers)
    time.sleep(2)