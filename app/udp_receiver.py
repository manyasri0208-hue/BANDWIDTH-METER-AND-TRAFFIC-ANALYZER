
import socket
import struct
import time
import csv
import os

HEADER = struct.Struct("!Id")
FIN = b"FIN"

HOST = "0.0.0.0"
PORT = 9999


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((HOST, PORT))
    sock.settimeout(2)

    received = set()
    total_bytes = 0
    expected_packets = None
    start_time = None
    last_packet_time = None
    last_sequence = -1
    out_of_order = 0
    delays = []

    print(f"UDP Receiver listening on port {PORT}")

    while True:
        try:
            data, address = sock.recvfrom(65535)
        except socket.timeout:
            if start_time is not None:
                break
            continue

        now = time.time()

        if data.startswith(FIN):
            if len(data) >= 7:
                expected_packets = struct.unpack("!I", data[3:7])[0]
            continue

        if len(data) < HEADER.size:
            continue

        sequence, timestamp = HEADER.unpack_from(data)

        if start_time is None:
            start_time = now

        if sequence not in received:
            received.add(sequence)
            total_bytes += len(data)

            if sequence < last_sequence:
                out_of_order += 1

            last_sequence = max(last_sequence, sequence)

            delays.append((now - timestamp) * 1000)

        last_packet_time = now

    sock.close()

    received_count = len(received)
    expected = expected_packets if expected_packets is not None else received_count
    lost = max(0, expected - received_count)

    duration = (
        last_packet_time - start_time
        if start_time is not None and last_packet_time is not None
        else 0
    )

    throughput = (
        total_bytes * 8 / duration / 1_000_000
        if duration > 0 else 0
    )

    average_delay = (
        sum(delays) / len(delays) if delays else 0
    )

    jitter = 0
    if len(delays) > 1:
        jitter = sum(
            abs(delays[i] - delays[i - 1])
            for i in range(1, len(delays))
        ) / (len(delays) - 1)

    loss_percentage = (
        lost / expected * 100 if expected else 0
    )

    print("\n========== UDP RECEIVER REPORT ==========")
    print("Expected packets :", expected)
    print("Received packets :", received_count)
    print("Lost packets     :", lost)
    print("Packet loss      : %.2f%%" % loss_percentage)
    print("Received bytes   :", total_bytes)
    print("Throughput       : %.3f Mbps" % throughput)
    print("Average delay    : %.3f ms" % average_delay)
    print("Average jitter   : %.3f ms" % jitter)
    print("Out-of-order     :", out_of_order)
    print("=========================================")

    os.makedirs("results", exist_ok=True)

    with open("results/udp_results.csv", "a", newline="") as file:
        writer = csv.writer(file)

        if file.tell() == 0:
            writer.writerow([
                "Expected", "Received", "Lost",
                "Loss_Percent", "Bytes", "Throughput_Mbps",
                "Average_Delay_ms", "Jitter_ms"
            ])

        writer.writerow([
            expected, received_count, lost,
            round(loss_percentage, 2), total_bytes,
            round(throughput, 3),
            round(average_delay, 3),
            round(jitter, 3)
        ])


if __name__ == "__main__":
    main()
