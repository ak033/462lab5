
import sys
import socket
import threading
import time
from collections import defaultdict
import json

# Constants
INFINITY = 999
BROADCAST_INTERVAL = 1  
DIJKSTRA_INTERVAL = 10 
TTL_LIMIT = 10  

class Router:
    def __init__(self, router_id, port, config_file):
        self.router_id = router_id
        self.port = port
        self.neighbors = {}  # neighbor_id: (label, cost, port)
        self.total_nodes = 0
        self.link_state = []  # 2D list for link costs
        self.received_link_states = set()  # To track received link states
        self.lock = threading.Lock()
        self.forwarding_table = {}
        
        self.load_config(config_file)
        self.initialize_link_state()

    def load_config(self, config_file):
        with open(config_file, 'r') as file:
            lines = file.readlines()
            self.total_nodes = int(lines[0].strip())  # First line: total number of nodes
            for line_no, line in enumerate(lines[1:], start=2):
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) != 4:
                    print(f"Warning: Malformed line {line_no} in config file: '{line}'")
                    continue
                neighbor_label, neighbor_id, cost, neighbor_port = parts
                neighbor_id = int(neighbor_id)
                cost = int(cost)
                neighbor_port = int(neighbor_port)
                self.neighbors[neighbor_id] = (neighbor_label, cost, neighbor_port)

    def initialize_link_state(self):
        # Initialize the link_state as a 2D list with INFINITY
        self.link_state = [[INFINITY for _ in range(self.total_nodes)] for _ in range(self.total_nodes)]
        # Set self-link to 0
        self.link_state[self.router_id][self.router_id] = 0
        # Set link costs to neighbors
        for neighbor_id, (label, cost, port) in self.neighbors.items():
            self.link_state[self.router_id][neighbor_id] = cost
        # Mark own link state as received
        self.received_link_states.add(self.router_id)

    def broadcast_link_state_periodically(self):
        while True:
            message = {
                'router_id': self.router_id,
                'link_state': self.link_state[self.router_id],
                'ttl': TTL_LIMIT
            }
            message_bytes = json.dumps(message).encode()
            with self.lock:
                for neighbor_id, (label, cost, neighbor_port) in self.neighbors.items():
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                        sock.sendto(message_bytes, ('127.0.0.1', neighbor_port))
            time.sleep(BROADCAST_INTERVAL)

    def receive_link_state(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(('127.0.0.1', self.port))
            while True:
                data, addr = sock.recvfrom(4096)
                message = json.loads(data.decode())
                self.process_received_message(message)

    def process_received_message(self, message):
        sender_id = message['router_id']
        received_link_state = message['link_state']
        ttl = message.get('ttl', 0)

        if ttl <= 0:
            return  # Do not process messages with non-positive TTL

        with self.lock:
            if sender_id not in self.received_link_states:
                self.received_link_states.add(sender_id)
            # Check if this is new or updated link state
            if self.link_state[sender_id] != received_link_state:
                self.link_state[sender_id] = received_link_state
                # Forward the message with decremented TTL
                if ttl - 1 > 0:
                    forwarded_message = {
                        'router_id': sender_id,
                        'link_state': received_link_state,
                        'ttl': ttl - 1
                    }
                    forwarded_bytes = json.dumps(forwarded_message).encode()
                    for neighbor_id, (label, cost, neighbor_port) in self.neighbors.items():
                        if neighbor_id != sender_id:  # Avoid sending back to the sender
                            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                                sock.sendto(forwarded_bytes, ('127.0.0.1', neighbor_port))

    def compute_dijkstra(self):
        while True:
            time.sleep(DIJKSTRA_INTERVAL)
            with self.lock:
                if len(self.received_link_states) < self.total_nodes:
                    print(f"Router {self.router_id}: Waiting for all link states. Computation deferred.")
                    continue  # Defer computation until all link states are received

                # Initialize Dijkstra's algorithm
                dist = [INFINITY] * self.total_nodes
                prev = [None] * self.total_nodes
                visited = [False] * self.total_nodes
                dist[self.router_id] = 0

                for _ in range(self.total_nodes):
                    # Find the unvisited node with the smallest distance
                    min_distance = INFINITY
                    u = None
                    for v in range(self.total_nodes):
                        if not visited[v] and dist[v] < min_distance:
                            min_distance = dist[v]
                            u = v
                    if u is None:
                        break
                    visited[u] = True

                    # Update distances to neighbors
                    for v in range(self.total_nodes):
                        if self.link_state[u][v] < INFINITY and not visited[v]:
                            alt = dist[u] + self.link_state[u][v]
                            if alt < dist[v]:
                                dist[v] = alt
                                prev[v] = u

                # Build forwarding table
                self.forwarding_table = {}
                for dest in range(self.total_nodes):
                    if dest == self.router_id:
                        continue
                    # Determine the next hop
                    next_hop = dest
                    while prev[next_hop] is not None and prev[next_hop] != self.router_id:
                        next_hop = prev[next_hop]
                    if prev[next_hop] is None:
                        next_hop = None  # No path found
                    self.forwarding_table[dest] = next_hop

                # Print Dijkstra's results
                print("\nDestination_Routerid\tDistance\tPrevious_node_id")
                for node in range(self.total_nodes):
                    print(f"{node}\t\t\t{dist[node]}\t\t{prev[node] if prev[node] is not None else '-'}")

                # Print Forwarding Table
                print("\nForwarding Table:")
                print("Destination_Routerid\tNext_hop_routerlabel")
                for dest, next_hop in self.forwarding_table.items():
                    if next_hop is None:
                        next_label = "-"
                    elif next_hop in self.neighbors:
                        next_label = self.neighbors[next_hop][0]
                    else:
                        # Find the label from the received link states
                        next_label = f"R{next_hop}"
                    print(f"{dest}\t\t\t{next_label}")
                print("\n" + "-"*50)

    def start(self):
        # Start broadcasting thread
        threading.Thread(target=self.broadcast_link_state_periodically, daemon=True).start()
        # Start receiving thread
        threading.Thread(target=self.receive_link_state, daemon=True).start()
        # Start Dijkstra computation thread
        threading.Thread(target=self.compute_dijkstra, daemon=True).start()
        # Keep the main thread alive
        while True:
            time.sleep(1)

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python Router.py <routerid> <routerport> <configfile>")
        sys.exit(1)

    try:
        router_id = int(sys.argv[1])
        router_port = int(sys.argv[2])
        config_file = sys.argv[3]
    except ValueError:
        print("Error: routerid and routerport must be integers.")
        sys.exit(1)

    router = Router(router_id, router_port, config_file)
    router.start()
