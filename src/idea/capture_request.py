"""Forward desktop capture requests to the instance holding the database lock."""
import hashlib
import time
from pathlib import Path
from PySide6.QtCore import QObject, QTimer, QThread
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def endpoint(database: Path) -> str:
    database = database.resolve()
    identity = hashlib.sha256(str(database).encode()).hexdigest()[:16]
    return str(database.parent / f".idea-{identity}-capture.sock")


def request_capture(database: Path) -> bool:
    socket = QLocalSocket()
    try:
        deadline = time.monotonic() + 1.5
        while True:
            socket.connectToServer(endpoint(database))
            if socket.waitForConnected(max(1, int((deadline - time.monotonic()) * 1000))):
                break
            socket.abort()
            if time.monotonic() >= deadline:
                return False
            # Another launch may own the lock but still be initializing its UI.
            QThread.msleep(25)
        socket.write(b"capture\n")
        if socket.bytesToWrite() and not socket.waitForBytesWritten(1500):
            return False
        response = bytearray()
        while b"\n" not in response and len(response) < 16:
            if not socket.waitForReadyRead(1500):
                return False
            response.extend(socket.readAll().data())
        return response == b"ok\n"
    finally:
        socket.abort()


class CaptureServer(QObject):
    def __init__(self, database: Path, callback, parent=None):
        super().__init__(parent)
        self.callback = callback
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        name = endpoint(database)
        path = Path(name)
        # The caller must hold the database lock before removing a stale socket.
        if path.is_symlink() or (path.exists() and not path.is_socket()):
            raise OSError("Capture socket path is occupied by another file.")
        if path.exists() and not QLocalServer.removeServer(name):
            raise OSError("Could not remove a stale capture socket.")
        self.server.newConnection.connect(self.accept)
        if not self.server.listen(name):
            raise OSError(self.server.errorString())

    def accept(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            pending = bytearray()
            timer = QTimer(socket)
            timer.setSingleShot(True)
            timer.timeout.connect(socket.abort)
            timer.start(3000)
            def receive(socket=socket, pending=pending, timer=timer):
                pending.extend(socket.readAll().data())
                if b"\n" not in pending and len(pending) <= 32:
                    return
                timer.stop()
                if pending == b"capture\n":
                    socket.write(b"ok\n")
                    socket.disconnectFromServer()
                    QTimer.singleShot(0, self.callback)
                else:
                    socket.abort()
            socket.readyRead.connect(receive)
            socket.disconnected.connect(socket.deleteLater)
            if socket.bytesAvailable():
                receive()

    def close(self):
        self.server.close()
