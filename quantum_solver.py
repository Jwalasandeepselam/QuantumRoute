"""Bounded QAOA TSP solver with a nearest-neighbor fallback."""

import json
from pathlib import Path
import subprocess
import sys

import numpy as np

QUANTUM_TIMEOUT_SECONDS = 30
MAX_QUANTUM_NODES = 4  # Tsp uses N**2 qubits; bound statevector memory.


def _solve_qaoa(distance_matrix):
    """Execute in a subprocess so the caller can enforce a hard time limit."""
    from importlib.metadata import version
    import networkx as nx
    from qiskit_algorithms import QAOA
    from qiskit_algorithms.optimizers import COBYLA
    from qiskit_optimization.algorithms import MinimumEigenOptimizer
    from qiskit_optimization.applications import Tsp

    # Algorithms 0.3 uses V1 primitives; 0.4+ uses V2 primitives.
    algorithm_version = tuple(int(part) for part in version("qiskit-algorithms").split(".")[:2])
    if algorithm_version >= (0, 4):
        from qiskit.primitives import StatevectorSampler
        sampler = StatevectorSampler(seed=42)
    else:
        from qiskit.primitives import Sampler
        sampler = Sampler(options={"shots": 1024, "seed": 42})

    # Tsp is undirected. Preserve directed road costs via the greedy fallback
    # instead of silently replacing them with symmetric costs.
    if not np.allclose(distance_matrix, distance_matrix.T):
        raise ValueError("Tsp requires a symmetric distance matrix")
    graph = nx.Graph()
    graph.add_nodes_from(range(len(distance_matrix)))
    for i in range(len(distance_matrix)):
        for j in range(i + 1, len(distance_matrix)):
            graph.add_edge(i, j, weight=float(distance_matrix[i, j]))
    tsp = Tsp(graph)
    quadratic_program = tsp.to_quadratic_program()
    qaoa = QAOA(sampler=sampler, optimizer=COBYLA(maxiter=50), reps=2)
    result = MinimumEigenOptimizer(qaoa).solve(quadratic_program)
    if not quadratic_program.is_feasible(result.x):
        raise ValueError("QAOA returned an infeasible tour")
    return [int(index) for index in tsp.interpret(result.x)]


def _greedy_route(matrix):
    route = [0]
    remaining = set(range(1, len(matrix)))
    while remaining:
        next_node = min(remaining, key=lambda node: (matrix[route[-1], node], node))
        route.append(next_node)
        remaining.remove(next_node)
    return route


def solve_route(distance_matrix):
    """Return each node once in visit order (the closing node is implicit).

    QAOA is approximate, so its feasible tour is not guaranteed globally optimal.
    Invalid input raises ValueError. Quantum errors, timeout, asymmetric input,
    or instances exceeding the simulation budget use greedy nearest-neighbor.
    """
    matrix = np.asarray(distance_matrix, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("distance_matrix must be an N x N matrix")
    if not np.isfinite(matrix).all() or (matrix < 0).any():
        raise ValueError("distances must be finite and nonnegative")
    count = len(matrix)
    if count <= 1:
        return list(range(count))
    try:
        if count > MAX_QUANTUM_NODES:
            raise ValueError("TSP exceeds the statevector simulation budget")
        if not np.allclose(matrix, matrix.T):
            raise ValueError("Tsp requires symmetric distances")
        worker = (
            "import json, sys, numpy as np; "
            "from quantum_solver import _solve_qaoa; "
            "print(json.dumps(_solve_qaoa(np.array(json.load(sys.stdin)))))"
        )
        completed = subprocess.run(
            [sys.executable, "-c", worker],
            input=json.dumps(matrix.tolist()),
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent),
            timeout=QUANTUM_TIMEOUT_SECONDS,
            check=True,
        )
        route = json.loads(completed.stdout.strip().splitlines()[-1])
        if sorted(route) != list(range(count)):
            raise ValueError("QAOA returned an invalid tour")
        # Rotate the cycle to start at node zero, matching the fallback.
        start = route.index(0)
        return route[start:] + route[:start]
    except Exception:
        print("[WARNING] Quantum timeout or error: Using Classical Fallback")
        return _greedy_route(matrix)
