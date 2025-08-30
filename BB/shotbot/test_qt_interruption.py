import sys

from PySide6.QtCore import QCoreApplication, QThread

app = (
    QCoreApplication(sys.argv)
    if not QCoreApplication.instance()
    else QCoreApplication.instance()
)


class TestThread(QThread):
    def run(self):
        print(f"In run, interruption requested: {self.isInterruptionRequested()}")


thread = TestThread()

# Test 1: Request interruption before starting
thread.requestInterruption()
print(f"After requestInterruption (before start): {thread.isInterruptionRequested()}")

# Start and check
thread.start()
thread.wait(100)
print(f"After start and wait: {thread.isInterruptionRequested()}")

# Test 2: New thread, start first then request interruption
thread2 = TestThread()
thread2.start()
thread2.requestInterruption()
print(
    f"Thread2 after start then requestInterruption: {thread2.isInterruptionRequested()}"
)
thread2.wait(100)
