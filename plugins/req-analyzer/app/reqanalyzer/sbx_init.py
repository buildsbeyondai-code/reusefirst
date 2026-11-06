#!/usr/bin/env python3
"""Runs INSIDE the sandbox (stdlib only, no package imports).

The sandbox has its own network namespace with loopback only. This init:
- relays 127.0.0.1:<egress-port> to a Unix socket served by the host's allowlisting egress proxy (so HTTPS_PROXY works),
- relays a Unix socket to 127.0.0.1:<inbound-port> (so the host can reach a launched app),
then runs the command, forwards SIGTERM/SIGINT to it, and exits with its exit code.
"""
from __future__ import annotations

import argparse
import os
import selectors
import signal
import socket
import subprocess
import sys
import threading


def pipe(a: socket.socket, b: socket.socket, idle_s: float = 900) -> None:
    """Copy bytes both ways until either side closes or nothing moves for idle_s."""
    sel = selectors.DefaultSelector()
    sel.register(a, selectors.EVENT_READ, b)
    sel.register(b, selectors.EVENT_READ, a)
    try:
        while True:
            events = sel.select(idle_s)
            if not events:
                return
            for key, _ in events:
                try:
                    data = key.fileobj.recv(65536)
                    if not data:
                        return
                    key.data.sendall(data)
                except OSError:
                    return
    finally:
        sel.close()
        for s in (a, b):
            try:
                s.close()
            except OSError:
                pass


def serve(listener: socket.socket, connect) -> None:
    while True:
        try:
            c, _ = listener.accept()
        except OSError:
            return

        def handle(c=c):
            try:
                u = connect()
            except OSError:
                c.close()
                return
            pipe(c, u)
        threading.Thread(target=handle, daemon=True).start()


def unix_connector(path: str):
    def f():
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(path)
        return s
    return f


def tcp_connector(port: int):
    def f():
        s = socket.create_connection(("127.0.0.1", port), timeout=10)
        s.settimeout(None)
        return s
    return f


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--egress-sock")
    ap.add_argument("--egress-port", type=int, default=3128)
    ap.add_argument("--inbound-sock")
    ap.add_argument("--inbound-port", type=int)
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd
    if not cmd:
        print("sbx_init: no command", file=sys.stderr)
        return 2
    if a.egress_sock:
        ls = socket.socket()
        ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ls.bind(("127.0.0.1", a.egress_port))
        ls.listen(64)
        threading.Thread(target=serve, args=(ls, unix_connector(a.egress_sock)), daemon=True).start()
    if a.inbound_sock and a.inbound_port:
        try:
            os.unlink(a.inbound_sock)
        except FileNotFoundError:
            pass
        us = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        us.bind(a.inbound_sock)
        us.listen(64)
        threading.Thread(target=serve, args=(us, tcp_connector(a.inbound_port)), daemon=True).start()
    try:
        p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL)
    except OSError as e:
        print(f"sbx_init: cannot start {cmd[0]}: {e}", file=sys.stderr)
        return 127

    def forward(sig, _frame):
        try:
            p.send_signal(sig)
        except ProcessLookupError:
            pass
    signal.signal(signal.SIGTERM, forward)
    signal.signal(signal.SIGINT, forward)
    return p.wait()


if __name__ == "__main__":
    sys.exit(main())
