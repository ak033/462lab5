import sys
import socket
import threading
import time
from collections import defaultdict
import json

# Constants
INFINITY = 999
BROADCAST_INTERVAL = 1  # seconds
DIJKSTRA_INTERVAL = 10  # seconds

# Initialize router state
class Router:
    def __init__(self, router_id, port, config_file):
        self.router_id = router_id
        self.port = port
        self.neighbors = {}
        self.link_state = defaultdict(lambda: [INFINITY] * 10)  # Support up to 10 nodes
        self.lock = threading.Lock()
        self.forwarding_table = {}

        self.load_config(config_file)
        self.link_state[self.router_id][self.router_id] = 0

    def load_config(self, config_file):
        with open(config_file, 'r') as file:
            lines = file.readlines()
            total_nodes = int(lines[0].strip())  # Read the first line for the total number of nodes
            for line_no, line in enumerate(lines[1:], start=2):  # Process from the second line onwards
                line = line.strip()  # Remove leading/trailing spaces
                if not line:  # Skip completely empty lines
                    continue
                parts = line.split()
                if len(parts) != 4:  # Ensure the line has exactly 4 parts
                    print(f"Warning: Malformed line {line_no} in config file: '{line}'")
                    continue
                neighbor_label, neighbor_id, cost, neighbor_port = parts
                self.neighbors[int(neighbor_id)] = (neighbor_label, int(cost), int(neighbor_port))
                self.link_state[self.router_id][int(neighbor_id)] = int(cost)

    def broadcast_link_state(self):
        message = json.dumps({'router_id': self.router_id, 'link_state': self.link_state[self.router_id]})
        for neighbor_id, (_, _, neighbor_port) in self.neighbors.items():
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.sendto(message.encode(), ('127.0.0.1', neighbor_port))

    def receive_link_state(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(('127.0.0.1', self.port))
            while True:
                data, _ = sock.recvfrom(4096)
                self.process_received_message(json.loads(data.decode()))

    def process_received_message(self, message):
        sender_id = message['router_id']
        received_link_state = message['link_state']

        with self.lock:
            if self.link_state[sender_id] != received_link_state:
                self.link_state[sender_id] = received_link_state
                self.broadcast_link_state()  # Re-broadcast updated state

    def compute_dijkstra(self):
        while True:
            time.sleep(DIJKSTRA_INTERVAL)

            with self.lock:
                num_nodes = len(self.link_state)
                dist = [INFINITY] * num_nodes
                prev = [None] * num_nodes
                visited = [False] * num_nodes
                dist[self.router_id] = 0

                for _ in range(num_nodes):
                    min_distance = INFINITY
                    u = None
                    for v in range(num_nodes):
                        if not visited[v] and dist[v] < min_distance:
                            min_distance = dist[v]
                            u = v
                    if u is None:
                        break
                    visited[u] = True

                    for v in range(num_nodes):
                        if self.link_state[u][v] < INFINITY and not visited[v]:
                            alt = dist[u] + self.link_state[u][v]
                            if alt < dist[v]:
                                dist[v] = alt
                                prev[v] = u

                # Build forwarding table
                self.forwarding_table = {}
                for dest in range(num_nodes):
                    if dest == self.router_id:
                        continue
                    next_hop = dest
                    while prev[next_hop] != self.router_id and prev[next_hop] is not None:
                        next_hop = prev[next_hop]
                    self.forwarding_table[dest] = next_hop

                # Print results
                print(f"Router {self.router_id} - Dijkstra Results")
                print("Destination\tDistance\tPrevious Node")
                for node in range(num_nodes):
                    print(f"{node}\t\t{dist[node]}\t\t{prev[node]}")
                print("Forwarding Table:")
                for dest, next_hop in self.forwarding_table.items():
                    print(f"Destination {dest} -> Next Hop {self.neighbors[next_hop][0] if next_hop in self.neighbors else next_hop}")

    def start(self):
        threading.Thread(target=self.broadcast_link_state).start()
        threading.Thread(target=self.receive_link_state).start()
        threading.Thread(target=self.compute_dijkstra).start()


# Main function to start the router
if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python Router.py <routerid> <routerport> <configfile>")
        sys.exit(1)

    router_id = int(sys.argv[1])
    router_port = int(sys.argv[2])
    config_file = sys.argv[3]

    router = Router(router_id, router_port, config_file)
    router.start()
