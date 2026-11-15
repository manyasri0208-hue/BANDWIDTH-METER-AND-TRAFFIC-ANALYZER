import socket
import struct
import time
import argparse

HEADER = struct.Struct("!Id")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="10.0.0.2")
    parser.add_argument("--port", type=int, default=9999)
    parser.add_argument("--rate", type=float, default=5)
    parser.add_argument("--duration", type=float, default=10)
    parser.add_argument("--size", type=int, default=1024)
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    packet_size = max(args.size, HEADER.size)
    payload_size = packet_size - HEADER.size
    interval = packet_size * 8 / (args.rate * 1_000_000)

    count = 0
    start = time.time()

    while time.time() - start < args.duration:
        packet = HEADER.pack(count, time.time()) + b"x" * payload_size
        sock.sendto(packet, (args.host, args.port))
        count += 1

        delay = start + count * interval - time.time()
        if delay > 0:
            time.sleep(delay)

    fin = b"FIN" + struct.pack("!I", count)

    for _ in range(3):
        sock.sendto(fin, (args.host, args.port))
        time.sleep(0.02)

    print("\nUDP SENDER REPORT")
    print("Packets sent:", count)
    print("Packet size:", packet_size, "bytes")
    print("Target rate:", args.rate, "Mbps")
    print("Duration:", args.duration, "seconds")

    sock.close()


if __name__ == "__main__":
    main()
