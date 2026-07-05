import sys
import os

# Try to load environment variables from a .env file if python-dotenv is installed
try:
    import dotenv
    dotenv.load_dotenv(override=True)
except ImportError:
    pass

# 1. Apply the MCP module monkeypatches to fix Google ADK import issues
import mcp
from mcp.types import SamplingCapability
mcp.SamplingCapability = SamplingCapability

from mcp import ClientSession
original_init = ClientSession.__init__
def patched_init(self, *args, **kwargs):
    kwargs.pop('sampling_capabilities', None)
    return original_init(self, *args, **kwargs)
ClientSession.__init__ = patched_init

print("[ConceptRadar] Applied mcp monkeypatches: SUCCESS.")

import uvicorn
from src.db import init_db, insert_node, insert_cluster, insert_edge, get_all_nodes

def seed_database():
    """Seeds the database with classic AI nodes so the dashboard has initial visual elements."""
    nodes = get_all_nodes()
    if len(nodes) > 0:
        print("[ConceptRadar] Database already contains data. Skipping seeding.")
        return
        
    print("[ConceptRadar] Seeding database with initial concepts...")
    
    # Define clusters
    insert_cluster("cluster_agentic", "Agentic AI", "Autonomous LLM workflows and interactive systems", None)
    insert_cluster("cluster_interpretability", "Mechanistic Interpretability", "Reverse-engineering neural networks and mapping weights", None)
    insert_cluster("cluster_rlhf", "Alignment & RLHF", "Direct preference optimization and model alignment", None)
    insert_cluster("cluster_neuromorphic", "Neuromorphic Computing", "Brain-inspired analog computing hardware and algorithms", None)
    
    # Ingest Seed Nodes
    
    # 1. Generative Agents Paper (Established/Frontier boundary)
    insert_node(
        node_id="arxiv:2304.03442",
        title="Generative Agents: Interactive Simulacra of Human Behavior",
        summary="Introduces generative agents that simulate believable human behavior in a sandbox environment, using architectures that store, retrieve, and reflect on memory.",
        url="https://arxiv.org/abs/2304.03442",
        source_type="arxiv",
        embedding=None,
        novelty_score=0.45,
        validation_score=0.85,
        momentum_score=0.80,
        cluster_id="cluster_agentic"
    )
    
    # 2. DPO Paper (Established/Frontier boundary)
    insert_node(
        node_id="arxiv:2305.18290",
        title="Direct Preference Optimization: Your Language Model is Secretly a Reward Model",
        summary="A stable, simple, and computationally lightweight algorithm to align language models to human preferences without training a separate reward model or using RL.",
        url="https://arxiv.org/abs/2305.18290",
        source_type="arxiv",
        embedding=None,
        novelty_score=0.35,
        validation_score=0.88,
        momentum_score=0.85,
        cluster_id="cluster_rlhf"
    )
    
    # 3. Google ADK GitHub (Established implementation)
    insert_node(
        node_id="github:google/adk",
        title="google/adk - Agent Development Kit",
        summary="The Google Agent Development Kit is a python SDK to build robust, multi-agent frameworks, supporting workflows, tools, and MCP servers.",
        url="https://github.com/google/adk",
        source_type="github",
        embedding=None,
        novelty_score=0.40,
        validation_score=0.55,
        momentum_score=0.75,
        cluster_id="cluster_agentic"
    )
    
    # 4. Spiking Neural Networks Paper (Speculative/Emerging)
    insert_node(
        node_id="arxiv:2401.00001",
        title="Analog Spiking Neurons for Ultra-Low Power Embodiment",
        summary="Proposes a neuromorphic analog chip architecture that runs spiking neural networks (SNNs) for robots acting in real-time, high-stakes dynamic environments.",
        url="https://arxiv.org/abs/2401.00001",
        source_type="arxiv",
        embedding=None,
        novelty_score=0.85,
        validation_score=0.75,
        momentum_score=0.40,
        cluster_id="cluster_neuromorphic"
    )
    
    # 5. Interpretability YouTube Video (Speculative/Noise)
    insert_node(
        node_id="youtube:reverse_engineering_llm",
        title="How We Reverse Engineered a 70B Parameter Model",
        summary="A detailed walkthrough of mechanistic interpretability, tracing neurons to map how features like spelling and coding are stored in LLM weights.",
        url="https://youtube.com/watch?v=mock123",
        source_type="youtube",
        embedding=None,
        novelty_score=0.75,
        validation_score=0.20,
        momentum_score=0.60,
        cluster_id="cluster_interpretability"
    )
    
    # Insert relationships
    insert_edge("github:google/adk", "arxiv:2304.03442", "implements", 0.65)
    
    print("[ConceptRadar] Database seeding complete.")

if __name__ == "__main__":
    # Ensure database is set up
    init_db()
    
    # Seed it
    seed_database()
    
    # Run FastAPI Server
    print("[ConceptRadar] Launching server on http://localhost:8000...")
    uvicorn.run("src.main:app", host="127.0.0.1", port=8000, reload=True)
