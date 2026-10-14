"""Pi vital signs, read straight from the kernel's /proc and /sys files."""
import time


class SysStats:
    def __init__(self):
        self._prev = None
        self.cpu = 0.0

    def _cpu_times(self):
        with open("/proc/stat") as f:
            v = [int(x) for x in f.readline().split()[1:]]
        idle = v[3] + (v[4] if len(v) > 4 else 0)
        return sum(v), idle

    def sample(self):
        try:
            total, idle = self._cpu_times()
            if self._prev:
                dt, di = total - self._prev[0], idle - self._prev[1]
                self.cpu = 100.0 * (1 - di / dt) if dt else 0.0
            self._prev = (total, idle)
        except OSError:
            pass
        return {"cpu": self.cpu, "mem": self.mem(), "temp": self.temp(), "uptime": self.uptime()}

    @staticmethod
    def mem():
        try:
            info = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    k, v = line.split(":")
                    info[k] = int(v.split()[0])
            return 100.0 * (1 - info["MemAvailable"] / info["MemTotal"])
        except (OSError, KeyError, ValueError):
            return 0.0

    @staticmethod
    def temp():
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                return int(f.read()) / 1000.0
        except (OSError, ValueError):
            return 0.0

    @staticmethod
    def uptime():
        try:
            with open("/proc/uptime") as f:
                return float(f.read().split()[0])
        except (OSError, ValueError):
            return time.monotonic()
