#!/usr/bin/env python3
"""Small JSON Lines client for the iCar APP bridge test scripts.

It intentionally sends only requests supplied by the local operator.  It is
useful for checking APP protocol v2 and managed map saves without exposing an
arbitrary ROS topic publisher.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from typing import Any, Dict, Iterable, Optional, Sequence


def parse_request(text: str) -> Dict[str, Any]:
    try:
        request = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f'invalid JSON request: {exc.msg}') from exc
    if not isinstance(request, dict) or not isinstance(request.get('cmd'), str):
        raise ValueError('request must be a JSON object containing string field cmd')
    return request


class BridgeClient:
    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.socket = socket.create_connection((host, port), timeout=timeout)
        self.reader = self.socket.makefile('r', encoding='utf-8', newline='\n')

    def close(self) -> None:
        self.reader.close()
        self.socket.close()

    def receive(self) -> Dict[str, Any]:
        line = self.reader.readline()
        if not line:
            raise ConnectionError('bridge closed the connection')
        response = json.loads(line)
        if not isinstance(response, dict):
            raise ValueError('bridge returned a non-object JSON line')
        return response

    def request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.socket.sendall((json.dumps(payload, ensure_ascii=False) + '\n').encode('utf-8'))
        return self.receive()


def print_response(response: Dict[str, Any]) -> bool:
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return bool(response.get('ok', True))


def run_requests(client: BridgeClient, requests: Iterable[Dict[str, Any]]) -> int:
    ok = True
    for request in requests:
        ok = print_response(client.request(request)) and ok
    return 0 if ok else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='iCar APP bridge JSON Lines client')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--token', default='', help='optional APP bridge auth token')
    parser.add_argument('--timeout', type=float, default=3.0)
    parser.add_argument('--request', action='append', default=[], help='JSON request; may be repeated')
    parser.add_argument('--interactive', action='store_true', help='keep one session open and read JSON lines')
    args = parser.parse_args(argv)

    if args.port <= 0 or args.port > 65535 or args.timeout <= 0:
        parser.error('port must be 1..65535 and timeout must be positive')
    try:
        requests = [parse_request(item) for item in args.request]
        client = BridgeClient(args.host, args.port, args.timeout)
        try:
            print_response(client.receive())  # JSON Lines hello envelope
            if args.token:
                if not print_response(client.request({'cmd': 'auth', 'token': args.token})):
                    return 1
            status = run_requests(client, requests)
            if not args.interactive:
                return status
            print('Enter one JSON request per line; type quit or exit to close.')
            while True:
                try:
                    line = input('app> ').strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    return status
                if line.lower() in {'quit', 'exit'}:
                    return status
                if not line:
                    continue
                status = max(status, run_requests(client, [parse_request(line)]))
        finally:
            client.close()
    except (ConnectionError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f'APP bridge client error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
