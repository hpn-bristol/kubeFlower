from typing import List, Tuple

import flwr as fl
from flwr.common import Metrics
import argparse


# Define metric aggregation function
def weighted_average(metrics: List[Tuple[int, Metrics]]) -> Metrics:
    # Multiply accuracy of each client by number of examples used
    accuracies = [num_examples * m["accuracy"] for num_examples, m in metrics]
    examples = [num_examples for num_examples, _ in metrics]

    # Aggregate and return custom metric (weighted average)
    return {"accuracy": sum(accuracies) / sum(examples)}

#Parse inputs
parser = argparse.ArgumentParser(description="Launches FL clients.")
parser.add_argument('-clients',"--clients", type=int, default=2, help="Define the number of clients to be part of he FL process",)
parser.add_argument('-min',"--min", type=int, default=2, help="Minimum number of available clients",)
parser.add_argument('-rounds',"--rounds", type=int, default=5, help="Number of FL rounds",)
args = vars(parser.parse_args())
num_clients = args['clients']
min_clients = args['min']
rounds = args['rounds']

# Define strategy
strategy = fl.server.strategy.FedAvg(evaluate_metrics_aggregation_fn=weighted_average, min_fit_clients = num_clients, min_available_clients=min_clients)

# Start Flower server
fl.server.start_server(
    server_address="0.0.0.0:8080",
    config=fl.server.ServerConfig(num_rounds=rounds),
    strategy=strategy,
)