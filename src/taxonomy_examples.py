"""
Few-shot examples for the ConceptRadar taxonomy classifier.
Each topic maps to 1-2 prototypical paper/concept titles that clearly represent the topic.
Parking topics have empty lists (no examples needed).
"""

TAXONOMY_EXAMPLES = {
    # ══════════════════════════════════════════════════════════════
    # DOMAIN: AI
    # ══════════════════════════════════════════════════════════════

    # --- Foundations ---
    "topic_ai_mathematics_for_ai": [
        "Convergence Analysis of Stochastic Gradient Descent with Momentum",
        "Random Matrix Theory for Deep Learning Weight Initialization",
    ],
    "topic_ai_statistics_and_probabilistic_models": [
        "Variational Inference with Normalizing Flows",
        "Bayesian Deep Learning via Stochastic Gradient MCMC",
    ],
    "topic_ai_optimization_algorithms": [
        "Adam: A Method for Stochastic Optimization",
        "Sharpness-Aware Minimization for Efficiently Improving Generalization",
    ],
    "topic_ai_information_theory_and_causal_inference": [
        "Causal Discovery from Observational Data Using Score Matching",
        "Mutual Information Neural Estimation for Representation Learning",
    ],
    "topic_ai_learning_theory": [
        "PAC-Bayesian Bounds for Deep Neural Networks",
        "Generalization in Deep Learning: The Role of Implicit Regularization",
    ],
    "topic_ai_knowledge_representation": [
        "Frame-Based Knowledge Representation for Common Sense Reasoning",
        "Neural-Symbolic Knowledge Graphs for Structured Prediction",
    ],
    "topic_ai_formal_reasoning": [
        "Automated Theorem Proving with Large Language Models",
        "Formal Verification of Neural Network Properties Using SMT Solvers",
    ],
    "topic_ai_evaluation_and_benchmarking": [
        "MMLU: Measuring Massive Multitask Language Understanding",
        "HumanEval: Hand-Written Evaluation Set for Code Generation",
    ],
    "topic_ai_interpretability_and_explainability": [
        "SHAP Values for Model-Agnostic Feature Attribution",
        "Mechanistic Interpretability of Transformer Circuits",
    ],
    "topic_ai_neuro_symbolic_ai": [
        "Combining Neural Perception with Symbolic Planning in Hybrid AI",
        "Logic Tensor Networks: Integrating Differentiable Reasoning",
    ],

    # --- Models & Architectures ---
    "topic_ai_neural_networks": [
        "Deep Residual Learning for Image Recognition",
        "Universal Approximation with Deep Narrow Networks",
    ],
    "topic_ai_transformers": [
        "Attention Is All You Need: The Transformer Architecture",
        "FlashAttention: Fast and Memory-Efficient Exact Attention",
    ],
    "topic_ai_large_language_models": [
        "GPT-4 Technical Report: Capabilities and Limitations",
        "Scaling Laws for Neural Language Models",
    ],
    "topic_ai_multimodal_models": [
        "Gemini: A Family of Highly Capable Multimodal Models",
        "CLIP: Connecting Text and Images via Contrastive Learning",
    ],
    "topic_ai_diffusion_models": [
        "Denoising Diffusion Probabilistic Models for Image Generation",
        "Stable Diffusion: High-Resolution Image Synthesis with Latent Diffusion",
    ],
    "topic_ai_graph_neural_networks": [
        "Message Passing Neural Networks for Molecular Property Prediction",
        "Graph Attention Networks for Semi-Supervised Classification",
    ],
    "topic_ai_efficient_ai_models": [
        "TinyLlama: An Open-Source Small Language Model",
        "Knowledge Distillation from Large to Small Models",
    ],
    "topic_ai_agent_architectures": [
        "ReAct: Synergizing Reasoning and Acting in Language Models",
        "Cognitive Architectures for Language Agents",
    ],
    "topic_ai_world_models": [
        "Learning World Models for Autonomous Driving Simulation",
        "Dreamer: Model-Based Reinforcement Learning with World Models",
    ],
    "topic_ai_model_adaptation_and_merging": [
        "Model Merging by Task Arithmetic in Weight Space",
        "LoRA: Low-Rank Adaptation of Large Language Models",
    ],

    # --- Learning & Training ---
    "topic_ai_supervised_learning": [
        "Label-Efficient Supervised Learning with Data Augmentation",
        "ImageNet Classification with Deep Convolutional Neural Networks",
    ],
    "topic_ai_unsupervised_and_self_supervised_learning": [
        "SimCLR: A Simple Framework for Contrastive Self-Supervised Learning",
        "DINO: Self-Supervised Vision Transformers Without Labels",
    ],
    "topic_ai_reinforcement_learning": [
        "Proximal Policy Optimization for Game Playing Agents",
        "Mastering Atari Games with Deep Reinforcement Learning",
    ],
    "topic_ai_transfer_learning": [
        "Domain Adaptation via Feature Alignment for Medical Imaging",
        "How Transferable are Features in Deep Neural Networks",
    ],
    "topic_ai_continual_learning": [
        "Overcoming Catastrophic Forgetting in Neural Networks",
        "Progressive Neural Networks for Lifelong Learning",
    ],
    "topic_ai_federated_learning": [
        "Communication-Efficient Learning of Deep Networks from Decentralized Data",
        "Federated Learning with Differential Privacy Guarantees",
    ],
    "topic_ai_data_augmentation_and_synthesis": [
        "Synthetic Data Generation with Generative Adversarial Networks",
        "MixUp: Beyond Empirical Risk Minimization via Data Interpolation",
    ],
    "topic_ai_prompt_engineering": [
        "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models",
        "Systematic Prompt Design for Improved Zero-Shot Performance",
    ],
    "topic_ai_fine_tuning_and_adaptation": [
        "Parameter-Efficient Fine-Tuning with Adapters",
        "QLoRA: Efficient Finetuning of Quantized Language Models",
    ],
    "topic_ai_alignment_and_rlhf": [
        "Training Language Models to Follow Instructions with Human Feedback",
        "Constitutional AI: Harmlessness from AI Feedback",
    ],

    # --- Agents & Cognition ---
    "topic_ai_ai_agents": [
        "AutoGPT: Autonomous GPT-4 Agent for Complex Task Completion",
        "A Survey on Large Language Model based Autonomous Agents",
    ],
    "topic_ai_multi_agent_systems": [
        "Multi-Agent Debate Improves LLM Reasoning and Factuality",
        "Cooperative Multi-Agent Reinforcement Learning for Traffic Control",
    ],
    "topic_ai_planning_and_search": [
        "Monte Carlo Tree Search for LLM Reasoning",
        "AlphaProof: AI System for Mathematical Theorem Proving via Search",
    ],
    "topic_ai_reasoning_systems": [
        "Chain-of-Thought Reasoning in Large Language Models",
        "Logical Reasoning Over Natural Language as Knowledge Representation",
    ],
    "topic_ai_memory_systems": [
        "MemGPT: Towards LLMs as Operating Systems with Virtual Memory",
        "Retrieval-Augmented Memory for Long-Context Language Models",
    ],
    "topic_ai_tool_use": [
        "Toolformer: Language Models Can Teach Themselves to Use Tools",
        "Function Calling in Large Language Models for API Integration",
    ],
    "topic_ai_autonomous_systems": [
        "End-to-End Autonomous Driving with Vision Transformers",
        "Self-Driving Laboratory for Accelerated Materials Discovery",
    ],
    "topic_ai_human_ai_collaboration": [
        "AI-Assisted Code Review: Human-AI Pair Programming",
        "Interactive Machine Learning with Human-in-the-Loop Feedback",
    ],
    "topic_ai_decision_making": [
        "Sequential Decision Making Under Uncertainty with LLMs",
        "Bayesian Optimization for Automated Machine Learning",
    ],
    "topic_ai_embodied_ai": [
        "Sim-to-Real Transfer for Robotic Manipulation via Reinforcement Learning",
        "PaLM-E: An Embodied Multimodal Language Model",
    ],

    # --- Data & Knowledge ---
    "topic_ai_data_engineering": [
        "Scalable Data Pipelines for Machine Learning at Scale",
        "Data-Centric AI: Best Practices for Data Quality in ML",
    ],
    "topic_ai_knowledge_graphs": [
        "Wikidata: A Free Collaborative Knowledge Base",
        "Embedding Knowledge Graphs for Link Prediction and Entity Classification",
    ],
    "topic_ai_vector_databases": [
        "FAISS: Billion-Scale Similarity Search with GPU Acceleration",
        "Milvus: A Purpose-Built Vector Database for AI Applications",
    ],
    "topic_ai_retrieval_systems": [
        "Dense Passage Retrieval for Open-Domain Question Answering",
        "ColBERT: Efficient and Effective Passage Search via Late Interaction",
    ],
    "topic_ai_retrieval_augmented_generation": [
        "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        "REALM: Retrieval-Enhanced Autoregressive Language Model Pre-Training",
    ],
    "topic_ai_ontology_engineering": [
        "Automated Ontology Construction from Unstructured Text",
        "OWL-Based Ontology Alignment for Semantic Interoperability",
    ],
    "topic_ai_information_extraction": [
        "Named Entity Recognition with Transformer-Based Models",
        "Relation Extraction from Scientific Literature Using LLMs",
    ],
    "topic_ai_data_quality_and_curation": [
        "Detecting Label Errors in Large-Scale Datasets with Confident Learning",
        "Data Quality Frameworks for Production Machine Learning Systems",
    ],
    "topic_ai_data_labeling_and_annotation": [
        "Active Learning Strategies for Efficient Data Annotation",
        "Weak Supervision: Creating Training Labels Programmatically",
    ],
    "topic_ai_semantic_search": [
        "Sentence-BERT: Sentence Embeddings for Semantic Textual Similarity",
        "Neural Information Retrieval with Cross-Encoder Reranking",
    ],

    # --- Infrastructure & Systems ---
    "topic_ai_ai_hardware": [
        "TPU v4: Designing Hardware for Large-Scale Machine Learning",
        "GPU Architecture Innovations for Deep Learning Workloads",
    ],
    "topic_ai_distributed_ml_systems": [
        "Megatron-LM: Training Multi-Billion Parameter Language Models at Scale",
        "Data Parallelism and Model Parallelism for Distributed Training",
    ],
    "topic_ai_mlops": [
        "MLflow: A Platform for the Machine Learning Lifecycle",
        "Continuous Integration and Delivery for Machine Learning Pipelines",
    ],
    "topic_ai_model_deployment_and_serving": [
        "TensorRT: High-Performance Inference Engine for Deep Learning",
        "Model Serving at Scale: Low-Latency Inference with vLLM",
    ],
    "topic_ai_model_compression": [
        "Quantization-Aware Training for Efficient Model Deployment",
        "Pruning Neural Networks at Initialization for Efficient Inference",
    ],
    "topic_ai_edge_ai": [
        "On-Device Machine Learning for Mobile Applications",
        "TinyML: Machine Learning on Microcontrollers",
    ],
    "topic_ai_cloud_ai": [
        "Serverless Machine Learning Inference on Cloud Platforms",
        "Auto-Scaling GPU Clusters for On-Demand Model Training",
    ],
    "topic_ai_scalability_and_performance": [
        "ZeRO: Memory Optimizations Toward Training Trillion Parameter Models",
        "Ring AllReduce for Efficient Large-Scale Distributed Training",
    ],
    "topic_ai_ml_system_optimization": [
        "Compiler Optimizations for Deep Learning Graph Execution",
        "Kernel Fusion Techniques for GPU-Accelerated Neural Networks",
    ],
    "topic_ai_model_monitoring_and_observability": [
        "Detecting Data Drift in Production ML Systems",
        "Real-Time Model Performance Monitoring and Alerting",
    ],

    # --- Security & Safety ---
    "topic_ai_ai_safety": [
        "Concrete Problems in AI Safety: Avoiding Side Effects",
        "Alignment of Superhuman AI Systems: An Open Research Agenda",
    ],
    "topic_ai_ai_security": [
        "Prompt Injection Attacks on Large Language Models",
        "Securing Machine Learning Models Against Data Poisoning",
    ],
    "topic_ai_adversarial_machine_learning": [
        "Adversarial Examples in the Physical World",
        "Certified Defenses Against Adversarial Perturbations",
    ],
    "topic_ai_robustness_and_resilience": [
        "Benchmarking Neural Network Robustness to Distribution Shifts",
        "Out-of-Distribution Detection with Energy-Based Models",
    ],
    "topic_ai_red_teaming": [
        "Red Teaming Language Models to Reduce Harms",
        "Automated Red-Teaming with Attack Prompts for LLM Evaluation",
    ],
    "topic_ai_risk_management": [
        "Risk Assessment Frameworks for Deploying AI in Critical Systems",
        "Quantifying Uncertainty in Machine Learning Predictions for Risk",
    ],
    "topic_ai_trustworthy_ai_principles": [
        "Trustworthy AI: From Principles to Practices",
        "A Framework for Building Trust in AI Through Transparency",
    ],
    "topic_ai_privacy_preserving_ai": [
        "Differential Privacy in Deep Learning Training",
        "Secure Multi-Party Computation for Privacy-Preserving ML",
    ],
    "topic_ai_fairness_and_bias_detection": [
        "Fairness Constraints in Machine Learning: Algorithms and Metrics",
        "Auditing Large Language Models for Demographic Bias",
    ],
    "topic_ai_ethical_ai_development": [
        "Responsible AI Development: A Practitioner's Guide",
        "Ethics by Design: Embedding Values in AI System Development",
    ],

    # --- Applications ---
    "topic_ai_ai_for_software_engineering": [
        "Copilot Evaluation: Measuring AI Code Generation Productivity",
        "LLM-Based Automated Bug Detection and Program Repair",
    ],
    "topic_ai_ai_for_cybersecurity": [
        "Deep Learning for Malware Detection and Classification",
        "AI-Powered Threat Intelligence for Network Intrusion Detection",
    ],
    "topic_ai_ai_for_healthcare": [
        "Med-PaLM: Large Language Model for Medical Question Answering",
        "AI-Assisted Radiology: Deep Learning for Chest X-Ray Diagnosis",
    ],
    "topic_ai_ai_for_science_and_discovery": [
        "AlphaFold: Protein Structure Prediction with Deep Learning",
        "AI-Driven Drug Discovery: Molecular Generation with Graph Networks",
    ],
    "topic_ai_ai_for_education": [
        "Intelligent Tutoring Systems with Adaptive Learning Paths",
        "Automated Essay Scoring with Transformer Models",
    ],
    "topic_ai_ai_for_finance": [
        "Deep Reinforcement Learning for Algorithmic Trading",
        "Fraud Detection with Graph Neural Networks in Financial Systems",
    ],
    "topic_ai_ai_for_manufacturing": [
        "Predictive Maintenance with Machine Learning in Smart Factories",
        "AI-Driven Quality Inspection Using Computer Vision",
    ],
    "topic_ai_creative_ai": [
        "Text-to-Image Generation with Diffusion Models",
        "AI Music Composition: Neural Network-Based Score Generation",
    ],
    "topic_ai_enterprise_ai": [
        "Document Understanding for Enterprise Knowledge Management",
        "AI-Powered Customer Service Automation with LLMs",
    ],
    "topic_ai_robotics_and_automation": [
        "AI-Driven Process Automation for Warehouse Logistics",
        "Vision-Language Models for Industrial Robot Task Planning",
    ],

    # --- Society & Governance ---
    "topic_ai_ai_ethics_and_philosophy": [
        "The Ethics of Artificial Intelligence: Key Issues and Debates",
        "Machine Consciousness: Philosophical Arguments and Counterarguments",
    ],
    "topic_ai_policy_and_regulation": [
        "The EU AI Act: Regulatory Framework for Artificial Intelligence",
        "National AI Strategies: A Comparative Policy Analysis",
    ],
    "topic_ai_ai_economics": [
        "The Economic Impact of Generative AI on Productivity Growth",
        "AI and Market Structure: Concentration Effects in the Tech Industry",
    ],
    "topic_ai_labor_and_workforce_impact": [
        "Automation and the Future of Work: Job Displacement Projections",
        "Upskilling Workers for the AI Economy: Policy Recommendations",
    ],
    "topic_ai_social_impact_and_equity": [
        "Digital Divide and AI Access: Equity in the Age of Automation",
        "AI for Social Good: Applications in Developing Countries",
    ],
    "topic_ai_legal_and_liability": [
        "Legal Liability for AI-Generated Decisions: A Framework",
        "Intellectual Property Rights in AI-Generated Content",
    ],
    "topic_ai_international_ai_governance": [
        "Global AI Governance: International Cooperation and Standards",
        "AI Arms Race: Geopolitics of Artificial Intelligence Development",
    ],
    "topic_ai_responsible_ai_frameworks": [
        "Google's Responsible AI Practices: Principles to Implementation",
        "NIST AI Risk Management Framework: Guidelines and Assessment",
    ],
    "topic_ai_data_governance": [
        "Data Governance for AI: Privacy, Security, and Compliance",
        "Federated Data Governance Across Organizational Boundaries",
    ],
    "topic_ai_public_perception_and_trust": [
        "Public Attitudes Toward Artificial Intelligence: A Global Survey",
        "Building Public Trust in AI: Transparency and Communication",
    ],

    # --- Parking ---
    "topic_ai_topic_evaluation_parking": [],
    "topic_ai_domain_evaluation_parking": [],
    "topic_ai_hitl_review_required": [],

    # ══════════════════════════════════════════════════════════════
    # DOMAIN: PHYSICS
    # ══════════════════════════════════════════════════════════════

    # --- Classical & Fluid Mechanics ---
    "topic_physics_newtonian_mechanics": [
        "Analytical Solutions to the Three-Body Problem with Perturbation Methods",
    ],
    "topic_physics_lagrangian_and_hamiltonian_mechanics": [
        "Symplectic Integrators for Hamiltonian Systems in Celestial Mechanics",
    ],
    "topic_physics_oscillations_and_waves": [
        "Nonlinear Wave Interactions in Elastic Media",
    ],
    "topic_physics_acoustics": [
        "Acoustic Metamaterials for Sound Absorption and Noise Control",
    ],
    "topic_physics_fluid_dynamics": [
        "Turbulence Modeling with Direct Numerical Simulation at High Reynolds Numbers",
        "Navier-Stokes Existence and Smoothness: Computational Approaches",
    ],
    "topic_physics_continuum_mechanics": [
        "Finite Element Analysis of Nonlinear Deformation in Soft Materials",
    ],
    "topic_physics_nonlinear_dynamics_and_chaos": [
        "Lyapunov Exponents and Strange Attractors in Dissipative Systems",
    ],
    "topic_physics_computational_mechanics": [
        "Mesh-Free Methods for Multiscale Computational Mechanics",
    ],

    # --- Electromagnetism & Optics ---
    "topic_physics_electrostatics": ["Electrostatic Self-Assembly of Colloidal Particles at Interfaces"],
    "topic_physics_magnetostatics": ["Magnetic Domain Imaging with Nitrogen-Vacancy Magnetometry"],
    "topic_physics_electrodynamics": ["Radiation Reaction in Classical Electrodynamics: Abraham-Lorentz Force"],
    "topic_physics_electromagnetic_waves": ["Terahertz Electromagnetic Wave Propagation in Complex Media"],
    "topic_physics_geometrical_optics": ["Ray Tracing Methods for Gravitational Lensing Simulations"],
    "topic_physics_physical_optics": ["Diffraction-Limited Imaging with Structured Illumination Microscopy"],
    "topic_physics_photonics_and_lasers": ["Ultrafast Fiber Lasers for Precision Spectroscopy"],
    "topic_physics_plasma_physics": ["Magnetic Confinement Plasma Instabilities in Tokamak Reactors"],
    "topic_physics_metamaterials_and_plasmonics": ["Negative Refractive Index Materials for Electromagnetic Cloaking"],

    # --- Thermodynamics & Statistical Physics ---
    "topic_physics_classical_thermodynamics": ["Carnot Efficiency Bounds in Nanoscale Heat Engines"],
    "topic_physics_statistical_mechanics": ["Renormalization Group Methods for Critical Phenomena"],
    "topic_physics_kinetic_theory": ["Boltzmann Transport Equation for Electron Dynamics in Solids"],
    "topic_physics_phase_transitions": ["Kosterlitz-Thouless Transition in Two-Dimensional Systems"],
    "topic_physics_critical_phenomena": ["Universality Classes and Scaling Laws Near Critical Points"],
    "topic_physics_non_equilibrium_thermodynamics": ["Fluctuation Theorems and Entropy Production in Driven Systems"],
    "topic_physics_complex_systems_physics": ["Emergence of Collective Behavior in Active Matter Systems"],
    "topic_physics_information_theory_and_physics": ["Thermodynamic Cost of Information Processing: Landauer's Principle"],

    # --- Quantum Mechanics ---
    "topic_physics_quantum_foundations": ["Bell Inequality Violations and Quantum Nonlocality Experiments"],
    "topic_physics_schroedinger_equation": ["Exact Solutions of the Time-Dependent Schrödinger Equation for Driven Systems"],
    "topic_physics_angular_momentum_and_spin": ["Spin-Orbit Coupling Effects in Quantum Dot Systems"],
    "topic_physics_perturbation_theory": ["Higher-Order Perturbation Theory for Anharmonic Oscillators"],
    "topic_physics_scattering_theory": ["Partial Wave Analysis in Quantum Mechanical Scattering"],
    "topic_physics_relativistic_quantum_mechanics": ["Dirac Equation Solutions in Curved Spacetime"],
    "topic_physics_quantum_information": ["Quantum Error Correction with Surface Codes"],
    "topic_physics_quantum_measurement": ["Weak Measurement and Post-Selection in Quantum Optics"],

    # --- Relativity & Gravitation ---
    "topic_physics_special_relativity": ["Lorentz Invariance Tests with Ultra-High-Energy Cosmic Rays"],
    "topic_physics_general_relativity": ["Numerical Solutions of Einstein Field Equations for Binary Mergers"],
    "topic_physics_relativistic_electrodynamics": ["Radiation from Relativistic Charged Particles in Accelerators"],
    "topic_physics_black_holes": ["Information Paradox and Black Hole Complementarity"],
    "topic_physics_gravitational_waves": ["LIGO Detection of Gravitational Waves from Binary Neutron Star Mergers"],
    "topic_physics_quantum_gravity_theories": ["Loop Quantum Gravity: Spin Foam Models and Semiclassical Limits"],
    "topic_physics_gravitational_lensing": ["Strong Gravitational Lensing as a Probe of Dark Matter Substructure"],
    "topic_physics_experimental_gravity": ["Precision Tests of the Equivalence Principle with Atom Interferometry"],

    # --- Condensed Matter ---
    "topic_physics_solid_state_physics": ["Electronic Band Structure Calculations with Density Functional Theory"],
    "topic_physics_semiconductor_physics": ["Carrier Transport in Two-Dimensional Semiconductor Heterostructures"],
    "topic_physics_superconductivity": ["High-Temperature Superconductivity in Nickelate Compounds"],
    "topic_physics_magnetism_in_solids": ["Skyrmion Dynamics in Chiral Magnetic Materials"],
    "topic_physics_soft_matter_physics": ["Self-Assembly of Block Copolymers for Nanopatterning"],
    "topic_physics_low_dimensional_systems": ["Quantum Hall Effect in Graphene Bilayers"],
    "topic_physics_topological_materials": ["Topological Insulators: Surface States and Spin-Momentum Locking"],
    "topic_physics_quantum_many_body_physics": ["Tensor Network Methods for Strongly Correlated Quantum Systems"],
    "topic_physics_disordered_systems": ["Anderson Localization in Three-Dimensional Disordered Media"],

    # --- AMO ---
    "topic_physics_atomic_structure": ["Precision Spectroscopy of Hydrogen for Fundamental Constants"],
    "topic_physics_molecular_structure": ["Ab Initio Calculation of Molecular Potential Energy Surfaces"],
    "topic_physics_quantum_optics": ["Single-Photon Sources for Quantum Communication Networks"],
    "topic_physics_laser_cooling_and_trapping": ["Magneto-Optical Traps for Ultracold Atomic Ensembles"],
    "topic_physics_ultrafast_phenomena": ["Attosecond Pulse Generation for Electron Dynamics Imaging"],
    "topic_physics_nonlinear_optics": ["Four-Wave Mixing in Photonic Crystal Fibers"],
    "topic_physics_cold_atoms_and_bec": ["Bose-Einstein Condensation in Ultracold Atomic Gases"],
    "topic_physics_precision_measurements": ["Optical Atomic Clocks for Gravitational Redshift Detection"],

    # --- Nuclear & Particle ---
    "topic_physics_nuclear_structure": ["Shell Model Calculations for Neutron-Rich Nuclei"],
    "topic_physics_nuclear_reactions": ["Heavy-Ion Fusion Reactions at Sub-Barrier Energies"],
    "topic_physics_particle_accelerators": ["Design of Next-Generation Proton Colliders at 100 TeV"],
    "topic_physics_standard_model": ["Precision Electroweak Measurements at the LHC"],
    "topic_physics_qcd": ["Lattice QCD Calculations of Hadron Masses and Form Factors"],
    "topic_physics_electroweak_interactions": ["W Boson Mass Measurement and Standard Model Tensions"],
    "topic_physics_beyond_standard_model": ["Supersymmetry Searches at the Large Hadron Collider"],
    "topic_physics_astroparticle_physics": ["Dark Matter Direct Detection with Xenon Time Projection Chambers"],
    "topic_physics_neutrino_physics": ["Neutrino Mass Ordering from Long-Baseline Oscillation Experiments"],
    "topic_physics_qft": ["Renormalization of Gauge Theories in Curved Spacetime"],

    # --- Astrophysics & Cosmology ---
    "topic_physics_stellar_structure_and_evolution": ["Core-Collapse Supernova Simulations with Neutrino Transport"],
    "topic_physics_galaxy_formation_and_evolution": ["IllustrisTNG: Cosmological Simulations of Galaxy Formation"],
    "topic_physics_observational_astronomy": ["James Webb Space Telescope Observations of High-Redshift Galaxies"],
    "topic_physics_planetary_science": ["Atmospheric Characterization of Exoplanets via Transit Spectroscopy"],
    "topic_physics_high_energy_astrophysics": ["Multi-Messenger Astronomy: Combining Gravitational Waves and Gamma Rays"],
    "topic_physics_cosmology": ["CMB Anisotropy Measurements and Constraints on Inflationary Models"],
    "topic_physics_gravitational_astronomy": ["Pulsar Timing Arrays for Nanohertz Gravitational Wave Detection"],
    "topic_physics_compact_objects": ["Equation of State of Neutron Star Matter from GW Observations"],
    "topic_physics_early_universe_physics": ["Primordial Nucleosynthesis and Light Element Abundances"],

    # --- Emerging & Other ---
    "topic_physics_computational_physics": ["High-Performance Computing for Molecular Dynamics Simulations"],
    "topic_physics_experimental_techniques": ["Cryogenic Detector Development for Rare Event Searches"],
    "topic_physics_metrology_and_standards": ["Redefinition of the Kilogram via the Kibble Balance"],
    "topic_physics_mathematical_physics": ["Riemann Zeta Function Zeros and Quantum Chaos Connections"],
    "topic_physics_physics_education_research": ["Active Learning Methods in Introductory Physics Courses"],
    "topic_physics_philosophy_of_physics": ["The Measurement Problem in Quantum Mechanics: Interpretations"],
    "topic_physics_biophysics": ["Single-Molecule Force Spectroscopy of Protein Folding"],
    "topic_physics_materials_physics": ["First-Principles Design of Novel Thermoelectric Materials"],
    "topic_physics_energy_physics": ["Next-Generation Solar Cell Efficiency via Perovskite Tandem Architectures"],
    "topic_physics_quantum_technologies": ["Quantum Key Distribution Networks for Secure Communication"],
    "topic_physics_ml_for_physics": ["Neural Network Potentials for Ab Initio Molecular Dynamics"],
    "topic_physics_open_problems_and_frontiers": ["Dark Energy and the Accelerating Universe: Current Puzzles"],
    "topic_physics_topic_evaluation_parking": [],
    "topic_physics_domain_evaluation_parking": [],
    "topic_physics_hitl_review_required": [],

    # ══════════════════════════════════════════════════════════════
    # DOMAIN: ROBOTICS
    # ══════════════════════════════════════════════════════════════

    # --- Robot Mechanics & Design ---
    "topic_robotics_actuation_systems": ["Variable Stiffness Actuators for Safe Human-Robot Interaction"],
    "topic_robotics_sensor_technologies": ["MEMS Inertial Sensors for Mobile Robot Navigation"],
    "topic_robotics_mechanical_design": ["Topology Optimization for Lightweight Robot Structural Components"],
    "topic_robotics_materials_and_fabrication": ["3D-Printed Soft Pneumatic Actuators for Robotic Grippers"],
    "topic_robotics_robot_system_design": ["Modular Reconfigurable Robot Design for Multi-Task Deployment"],
    "topic_robotics_locomotion_systems": ["Dynamic Legged Locomotion Over Rough Terrain"],
    "topic_robotics_soft_robotics": ["Continuum Robots for Minimally Invasive Surgical Applications"],
    "topic_robotics_exoskeletons_and_wearables": ["Powered Exoskeleton for Lower-Limb Rehabilitation"],

    # --- Robot Perception ---
    "topic_robotics_robot_vision": ["Real-Time Object Detection for Autonomous Mobile Robots"],
    "topic_robotics_3d_reconstruction": ["Neural Radiance Fields for Robot Scene Understanding"],
    "topic_robotics_sensor_fusion": ["LiDAR-Camera Fusion for Autonomous Driving Perception"],
    "topic_robotics_localization_and_mapping_slam": ["Visual-Inertial SLAM for GPS-Denied Environments"],
    "topic_robotics_object_recognition": ["Category-Level Object Pose Estimation for Manipulation"],
    "topic_robotics_tactile_sensing": ["GelSight Tactile Sensors for Fine Manipulation Tasks"],
    "topic_robotics_proprioception": ["Proprioceptive State Estimation for Legged Robots"],
    "topic_robotics_semantic_mapping": ["3D Semantic Scene Graphs for Robot Task Planning"],
    "topic_robotics_auditory_sensing": ["Sound Source Localization for Social Robot Interaction"],

    # --- Control Systems ---
    "topic_robotics_motion_control": ["Model Predictive Control for Agile Quadrotor Flight"],
    "topic_robotics_force_control": ["Force-Torque Control for Precision Assembly Tasks"],
    "topic_robotics_impedance_control": ["Variable Impedance Control for Safe Physical Interaction"],
    "topic_robotics_adaptive_control": ["Online Adaptive Control for Robots with Unknown Dynamics"],
    "topic_robotics_hybrid_control": ["Hybrid Automata for Contact-Rich Manipulation Planning"],
    "topic_robotics_trajectory_generation": ["Minimum-Snap Trajectory Generation for Multirotor UAVs"],
    "topic_robotics_real_time_control": ["FPGA-Based Real-Time Control at Microsecond Latencies"],
    "topic_robotics_compliance_control": ["Passive Compliance Design for Safe Collaborative Robots"],
    "topic_robotics_distributed_control": ["Consensus-Based Distributed Control for Robot Swarms"],

    # --- Planning & Navigation ---
    "topic_robotics_path_planning": ["RRT*: Asymptotically Optimal Sampling-Based Path Planning"],
    "topic_robotics_motion_planning": ["Constrained Motion Planning for High-DOF Manipulators"],
    "topic_robotics_task_planning": ["PDDL-Based Task Planning for Long-Horizon Robot Manipulation"],
    "topic_robotics_navigation_algorithms": ["Deep Reinforcement Learning for Indoor Robot Navigation"],
    "topic_robotics_exploration_strategies": ["Frontier-Based Exploration for Unknown Environment Mapping"],
    "topic_robotics_multi_robot_planning": ["Decentralized Multi-Robot Task Allocation and Scheduling"],
    "topic_robotics_decision_making": ["POMDP-Based Decision Making Under Uncertainty for Mobile Robots"],
    "topic_robotics_behavior_generation": ["Diffusion Policy: Visuomotor Policy Learning via Action Diffusion"],
    "topic_robotics_predictive_planning": ["Predictive Motion Planning Using Learned Human Intent Models"],

    # --- Manipulation & Grasping ---
    "topic_robotics_grasping_strategies": ["Learning 6-DOF Grasp Poses from Point Clouds"],
    "topic_robotics_dexterous_manipulation": ["In-Hand Object Reorientation with a Dexterous Robot Hand"],
    "topic_robotics_object_interaction": ["Contact-Rich Manipulation of Deformable Objects"],
    "topic_robotics_manipulation_planning": ["Task and Motion Planning for Sequential Manipulation"],
    "topic_robotics_tool_use": ["Autonomous Tool Selection and Use by Robotic Manipulators"],
    "topic_robotics_force_guided_assembly": ["Peg-in-Hole Assembly with Force-Guided Insertion Strategies"],
    "topic_robotics_robot_hands_and_grippers": ["Underactuated Gripper Design for Robust Grasping"],
    "topic_robotics_soft_manipulation": ["Soft Robotic Grippers for Delicate Object Handling"],
    "topic_robotics_collaborative_manipulation": ["Dual-Arm Collaborative Manipulation for Large Object Transport"],

    # --- Human-Robot Interaction ---
    "topic_robotics_human_robot_communication": ["Natural Language Grounding for Robot Instruction Following"],
    "topic_robotics_social_robotics": ["Emotion Recognition for Socially Assistive Companion Robots"],
    "topic_robotics_shared_autonomy": ["Shared Control Teleoperation with Intent Prediction"],
    "topic_robotics_user_interfaces": ["Augmented Reality Interfaces for Robot Programming"],
    "topic_robotics_trust_and_acceptance": ["Factors Influencing Human Trust in Autonomous Robots"],
    "topic_robotics_human_factors": ["Ergonomic Assessment of Human-Robot Collaborative Workstations"],
    "topic_robotics_collaborative_robotics": ["Safety-Certified Collaborative Robots for Shared Workspaces"],
    "topic_robotics_affective_robotics": ["Affective Computing for Emotionally Responsive Robots"],
    "topic_robotics_haptic_interaction": ["Haptic Feedback Systems for Teleoperated Surgical Robots"],

    # --- Robot Learning & Cognition ---
    "topic_robotics_reinforcement_learning": ["Sample-Efficient Reinforcement Learning for Robotic Locomotion"],
    "topic_robotics_imitation_learning": ["One-Shot Imitation Learning from Human Video Demonstrations"],
    "topic_robotics_robot_skill_learning": ["Learning Reusable Robot Skills from Play Data"],
    "topic_robotics_learning_from_demonstration": ["Interactive Learning from Demonstration with Corrective Feedback"],
    "topic_robotics_generative_models": ["Generative Models for Robot Trajectory Prediction and Planning"],
    "topic_robotics_adaptation_and_transfer_learning": ["Sim-to-Real Transfer with Domain Randomization for Manipulation"],
    "topic_robotics_robot_cognition": ["Cognitive Architecture for Autonomous Robot Decision-Making"],
    "topic_robotics_world_modeling": ["Learned World Models for Model-Based Robot Control"],
    "topic_robotics_explainable_ai_for_robotics": ["Explainable Robot Policies via Natural Language Justification"],

    # --- Robotics Software & Systems ---
    "topic_robotics_robot_operating_systems_ros": ["ROS 2: Architecture for Real-Time Robotic Systems"],
    "topic_robotics_software_architectures": ["Microservice Architecture for Scalable Robot Software"],
    "topic_robotics_distributed_robotics": ["Middleware for Distributed Multi-Robot System Coordination"],
    "topic_robotics_system_integration": ["End-to-End System Integration for Autonomous Mobile Manipulators"],
    "topic_robotics_simulation_and_modeling": ["Isaac Sim: Physics-Based Simulation for Robot Learning"],
    "topic_robotics_cloud_robotics": ["Cloud-Based Object Recognition Services for Mobile Robots"],
    "topic_robotics_embedded_systems": ["Real-Time Embedded Control Software for Quadruped Robots"],
    "topic_robotics_robot_programming": ["Visual Programming Languages for Non-Expert Robot Users"],
    "topic_robotics_cyber_physical_systems": ["Digital Twin Frameworks for Industrial Robot Monitoring"],

    # --- Robotic Applications ---
    "topic_robotics_industrial_robotics": ["Flexible Manufacturing Cells with Dual-Arm Industrial Robots"],
    "topic_robotics_service_robotics": ["Autonomous Room Service Delivery Robots in Hotel Environments"],
    "topic_robotics_medical_robotics": ["Da Vinci Surgical System: Advances in Robot-Assisted Surgery"],
    "topic_robotics_field_robotics": ["Autonomous Underwater Vehicles for Ocean Floor Mapping"],
    "topic_robotics_space_robotics": ["Mars Rover Autonomy: Navigation in Unstructured Terrain"],
    "topic_robotics_agricultural_robotics": ["Autonomous Fruit Harvesting with Vision-Guided Manipulation"],
    "topic_robotics_logistics_robotics": ["Autonomous Mobile Robots for Warehouse Order Fulfillment"],
    "topic_robotics_defense_robotics": ["Autonomous Drone Swarms for Search and Rescue Operations"],
    "topic_robotics_rehabilitation_robotics": ["Robot-Assisted Upper Limb Rehabilitation After Stroke"],
    "topic_robotics_construction_robotics": ["Autonomous Bricklaying Robots for Construction Automation"],

    # --- Foundations of Robotics ---
    "topic_robotics_robot_kinematics": ["Inverse Kinematics Solutions for Redundant Manipulators"],
    "topic_robotics_robot_dynamics": ["Recursive Newton-Euler Algorithm for Multi-Body Robot Dynamics"],
    "topic_robotics_control_theory": ["Lyapunov Stability Analysis for Nonlinear Robot Controllers"],
    "topic_robotics_geometric_methods": ["Lie Group Methods for Robot Motion Representation"],
    "topic_robotics_optimization_for_robotics": ["Convex Optimization for Real-Time Robot Motion Planning"],
    "topic_robotics_probability_and_statistics": ["Probabilistic Roadmaps for Robot Path Planning Under Uncertainty"],
    "topic_robotics_information_theory": ["Information-Theoretic Exploration for Active Perception"],
    "topic_robotics_differential_geometry": ["Riemannian Geometry for Robot Configuration Space Analysis"],

    # --- Robot Safety, Ethics & Society ---
    "topic_robotics_ethical_robotics": ["Ethical Decision-Making Frameworks for Autonomous Vehicles"],
    "topic_robotics_robot_safety_standards": ["ISO 15066: Safety Requirements for Collaborative Robots"],
    "topic_robotics_legal_and_policy": ["Legal Frameworks for Autonomous Robot Liability"],
    "topic_robotics_socio_economic_impact": ["Economic Impact of Industrial Robot Adoption on Employment"],
    "topic_robotics_trustworthy_robotics": ["Verification and Validation for Safety-Critical Robot Systems"],
    "topic_robotics_robot_security": ["Cybersecurity Vulnerabilities in Connected Robot Systems"],
    "topic_robotics_privacy_in_robotics": ["Privacy-Preserving Perception for Domestic Service Robots"],
    "topic_robotics_robot_governance": ["Governance Frameworks for Autonomous Delivery Robots in Cities"],
    "topic_robotics_risk_management_for_robotics": ["Probabilistic Risk Assessment for Autonomous Robot Operations"],

    # --- Emerging & Cross-Cutting ---
    "topic_robotics_swarm_robotics": ["Emergent Collective Behavior in Decentralized Robot Swarms"],
    "topic_robotics_bio_inspired_robotics": ["Insect-Scale Flying Robots with Flapping-Wing Mechanisms"],
    "topic_robotics_quantum_robotics": ["Quantum Computing Applications for Robot Path Optimization"],
    "topic_robotics_benchmarking_and_evaluation": ["Standardized Benchmarks for Robotic Manipulation Tasks"],
    "topic_robotics_hardware_software_co_design": ["Co-Design of Morphology and Controller for Soft Robots"],
    "topic_robotics_neuro_robotics": ["Neural Interfaces for Direct Brain-Robot Control"],
    "topic_robotics_experimental_robotics": ["Reproducible Experimental Protocols for Robot Learning Research"],
    "topic_robotics_topic_evaluation_parking": [],
    "topic_robotics_domain_evaluation_parking": [],
    "topic_robotics_hitl_review_required": [],

    # ══════════════════════════════════════════════════════════════
    # DOMAIN: PSYCHOLOGY
    # ══════════════════════════════════════════════════════════════

    # --- Cognitive Psychology ---
    "topic_psychology_sensation_and_perception": ["Multisensory Integration in Visual-Auditory Perception"],
    "topic_psychology_attention_and_consciousness": ["Neural Correlates of Selective Attention in Visual Search"],
    "topic_psychology_memory_systems": ["Consolidation of Episodic Memory During Sleep"],
    "topic_psychology_language_processing": ["Predictive Processing in Sentence Comprehension"],
    "topic_psychology_problem_solving": ["Insight Problem Solving: Neural Mechanisms of the Aha Moment"],
    "topic_psychology_decision_making": ["Prospect Theory and Loss Aversion in Risky Decision Making"],
    "topic_psychology_cognitive_control": ["Executive Function Development in Children and Adolescents"],
    "topic_psychology_categorization_and_concepts": ["Prototype vs. Exemplar Models of Category Representation"],
    "topic_psychology_cognitive_neuroscience": ["Default Mode Network Activity and Mind Wandering"],

    # --- Biological & Evolutionary ---
    "topic_psychology_neuroanatomy_and_function": ["Prefrontal Cortex Contributions to Working Memory"],
    "topic_psychology_neurotransmitters_and_hormones": ["Serotonin System Dysregulation in Major Depression"],
    "topic_psychology_behavioral_genetics": ["Twin Studies of Heritability of Intelligence"],
    "topic_psychology_psychophysiology": ["Heart Rate Variability as an Index of Emotional Regulation"],
    "topic_psychology_evolutionary_psychology": ["Parental Investment Theory and Mate Selection Preferences"],
    "topic_psychology_sensory_and_motor_systems": ["Mirror Neuron System and Action Understanding"],
    "topic_psychology_sleep_and_circadian_rhythms": ["Circadian Rhythm Disruption and Mental Health Outcomes"],
    "topic_psychology_behavioral_neuroscience": ["Reward Circuitry and Dopaminergic Pathways in Addiction"],

    # --- Developmental Psychology ---
    "topic_psychology_child_development": ["Theory of Mind Development in Preschool Children"],
    "topic_psychology_adolescent_development": ["Adolescent Brain Development and Risk-Taking Behavior"],
    "topic_psychology_adult_development": ["Midlife Career Transitions and Identity Reformulation"],
    "topic_psychology_aging_and_gerontology": ["Cognitive Reserve and Resilience to Age-Related Decline"],
    "topic_psychology_attachment_and_bonding": ["Attachment Security and Romantic Relationship Quality"],
    "topic_psychology_moral_reasoning": ["Kohlberg's Stages of Moral Development: Cross-Cultural Evidence"],
    "topic_psychology_social_emotional_growth": ["Emotional Competence Development Through Social Learning"],
    "topic_psychology_cognitive_development": ["Piaget's Stages: Contemporary Evidence and Revisions"],
    "topic_psychology_developmental_psychopathology": ["Early Adversity and Trajectories of Developmental Psychopathology"],

    # --- Social Psychology ---
    "topic_psychology_social_cognition": ["Implicit Bias and Automatic Stereotype Activation"],
    "topic_psychology_attitudes_and_persuasion": ["Elaboration Likelihood Model of Attitude Change"],
    "topic_psychology_group_dynamics": ["Social Loafing and Motivation Losses in Group Tasks"],
    "topic_psychology_interpersonal_relationships": ["Gottman's Theory of Marital Stability and Dissolution"],
    "topic_psychology_prejudice_and_discrimination": ["Microaggressions and Their Psychological Impact on Minorities"],
    "topic_psychology_aggression_and_altruism": ["Prosocial Behavior and the Bystander Effect Revisited"],
    "topic_psychology_cultural_psychology": ["Cultural Dimensions of Self-Construal: Independent vs Interdependent"],
    "topic_psychology_social_influence": ["Conformity and Obedience: Replication of Milgram's Paradigm"],
    "topic_psychology_self_and_identity": ["Self-Determination Theory and Intrinsic Motivation"],
    "topic_psychology_intergroup_relations": ["Contact Hypothesis and Prejudice Reduction Interventions"],

    # --- Personality & Individual Differences ---
    "topic_psychology_personality_theories": ["Big Five Personality Traits: Structure and Stability Across Cultures"],
    "topic_psychology_personality_traits": ["Dark Triad Traits and Workplace Behavior"],
    "topic_psychology_intelligence_and_abilities": ["General Intelligence Factor g: Psychometric and Neuroscience Evidence"],
    "topic_psychology_emotion_and_affect": ["Appraisal Theory of Emotion: Cognitive Determinants of Affect"],
    "topic_psychology_motivation_and_drives": ["Self-Determination Theory: Autonomy, Competence, and Relatedness"],
    "topic_psychology_self_concept": ["Self-Efficacy Beliefs and Academic Achievement"],
    "topic_psychology_temperament_studies": ["Infant Temperament and Later Personality Development"],
    "topic_psychology_psychological_assessment": ["Reliability and Validity of the MMPI-3 Personality Inventory"],
    "topic_psychology_creativity_research": ["Divergent Thinking and Creative Problem Solving"],

    # --- Clinical Psychopathology & Assessment ---
    "topic_psychology_foundations_of_psychopathology_and_diagnostic_systems": [
        "DSM-5-TR Diagnostic Classification: Reliability and Clinical Utility",
    ],
    "topic_psychology_neurodevelopmental_disorders": [
        "Autism Spectrum Disorder: Early Identification and Intervention",
        "ADHD Subtypes and Executive Function Deficits in Children",
    ],
    "topic_psychology_psychotic_and_schizophrenia_spectrum": [
        "Cognitive Remediation Therapy for Schizophrenia Spectrum Disorders",
    ],
    "topic_psychology_mood_disorders": [
        "Major Depressive Disorder: Neurobiological Mechanisms and Treatment",
        "Bipolar Disorder Cycling Patterns and Pharmacological Management",
    ],
    "topic_psychology_anxiety_ocd_and_trauma_related": [
        "Exposure Therapy Mechanisms in Anxiety and PTSD Treatment",
    ],
    "topic_psychology_personality_disorders": [
        "Borderline Personality Disorder: Dialectical Behavior Therapy Outcomes",
    ],
    "topic_psychology_substance_related_and_addictive_disorders": [
        "Motivational Interviewing for Substance Use Disorder Treatment",
    ],
    "topic_psychology_eating_somatic_and_dissociative_disorders": [
        "Anorexia Nervosa Treatment Outcomes: Family-Based vs Individual Therapy",
    ],
    "topic_psychology_clinical_assessment_and_diagnostic_methods": [
        "Structured Clinical Interview for DSM-5: Administration and Scoring",
    ],

    # --- Psychotherapeutic Interventions & Prevention ---
    "topic_psychology_foundations_of_psychotherapy_and_treatment_planning": [
        "Common Factors in Psychotherapy: Therapeutic Alliance and Outcomes",
    ],
    "topic_psychology_cognitive_behavioral_and_third_wave_therapies": [
        "Acceptance and Commitment Therapy for Chronic Pain",
    ],
    "topic_psychology_psychodynamic_and_psychoanalytic_therapies": [
        "Short-Term Psychodynamic Psychotherapy for Depression: RCT Results",
    ],
    "topic_psychology_humanistic_existential_and_experiential_therapies": [
        "Person-Centered Therapy: Rogerian Conditions and Outcome Research",
    ],
    "topic_psychology_family_couples_and_group_therapies": [
        "Emotionally Focused Couples Therapy: Effectiveness Meta-Analysis",
    ],
    "topic_psychology_crisis_intervention_and_trauma_informed_care": [
        "Trauma-Informed Care in Emergency Mental Health Services",
    ],
    "topic_psychology_prevention_science_and_public_mental_health": [
        "School-Based Mental Health Prevention Programs: Effectiveness Review",
    ],

    # --- Health Psychology & Well-being ---
    "topic_psychology_stress_and_coping": ["Transactional Model of Stress and Coping: Current Applications"],
    "topic_psychology_health_behaviors": ["Behavior Change Techniques for Physical Activity Promotion"],
    "topic_psychology_chronic_illness_management": ["Psychological Adjustment to Type 2 Diabetes Diagnosis"],
    "topic_psychology_pain_psychology": ["Central Sensitization and Psychological Factors in Chronic Pain"],
    "topic_psychology_psychoneuroimmunology": ["Stress-Immune Interactions and Inflammatory Disease Risk"],
    "topic_psychology_health_promotion": ["Health Literacy Interventions for Underserved Populations"],
    "topic_psychology_behavioral_medicine": ["Biofeedback Training for Hypertension Management"],
    "topic_psychology_positive_psychology": ["Character Strengths and Flourishing: Empirical Evidence"],
    "topic_psychology_subjective_well_being": ["Life Satisfaction Predictors Across the Lifespan"],
    "topic_psychology_mindfulness_interventions": ["Mindfulness-Based Stress Reduction for Anxiety Disorders"],

    # --- Applied Psychology ---
    "topic_psychology_industrial_organizational": ["Employee Engagement and Organizational Performance"],
    "topic_psychology_educational_psychology": ["Self-Regulated Learning Strategies in Higher Education"],
    "topic_psychology_forensic_psychology": ["Eyewitness Testimony Reliability and Memory Distortion"],
    "topic_psychology_sports_psychology": ["Mental Imagery and Performance Enhancement in Athletes"],
    "topic_psychology_human_factors": ["Cognitive Workload Assessment in Air Traffic Control"],
    "topic_psychology_environmental_psychology": ["Environmental Design and Restorative Attention Theory"],
    "topic_psychology_consumer_psychology": ["Nudge Theory and Consumer Decision Architecture"],
    "topic_psychology_community_psychology": ["Community-Based Participatory Research in Mental Health"],
    "topic_psychology_political_psychology": ["Moral Foundations Theory and Political Ideology"],
    "topic_psychology_media_psychology": ["Social Media Use and Adolescent Mental Health Outcomes"],

    # --- Psychology & Society ---
    "topic_psychology_public_policy_and_advocacy": ["Evidence-Based Policy Advocacy for Mental Health Services"],
    "topic_psychology_social_inequality_and_justice": ["Socioeconomic Status and Mental Health Disparities"],
    "topic_psychology_global_and_cross_cultural_issues": ["Cross-Cultural Validation of Psychological Assessment Tools"],
    "topic_psychology_psychological_aspects_of_law": ["Psychological Factors in Jury Decision Making"],
    "topic_psychology_science_communication": ["Public Understanding of Psychology: Science Communication Strategies"],
    "topic_psychology_stigma_and_discrimination": ["Mental Illness Stigma Reduction Through Contact-Based Education"],
    "topic_psychology_psychology_of_sustainability": ["Pro-Environmental Behavior and Identity-Based Motivation"],
    "topic_psychology_psychology_and_human_rights": ["Psychological Impact of Forced Migration and Refugee Experience"],
    "topic_psychology_digital_society_and_technology": ["Internet Addiction: Diagnostic Criteria and Prevalence Studies"],

    # --- History, Philosophy & Ethics ---
    "topic_psychology_history_of_psychology": ["Wilhelm Wundt and the Founding of Experimental Psychology"],
    "topic_psychology_schools_of_thought": ["Behaviorism to Cognitive Revolution: Paradigm Shifts in Psychology"],
    "topic_psychology_philosophical_foundations": ["Free Will and Determinism: Implications for Psychological Theory"],
    "topic_psychology_critical_psychology": ["Power Relations and Social Constructionism in Psychology"],
    "topic_psychology_indigenous_psychologies": ["Indigenous Healing Practices and Western Psychological Models"],
    "topic_psychology_research_ethics": ["Informed Consent and Deception in Psychological Research"],
    "topic_psychology_professional_ethics": ["APA Ethics Code: Principles for Professional Practice"],
    "topic_psychology_philosophy_of_mind": ["Consciousness and the Hard Problem: Philosophical Perspectives"],

    # --- Research Methods & Emerging ---
    "topic_psychology_research_design": ["Randomized Controlled Trial Design for Psychotherapy Research"],
    "topic_psychology_statistical_modeling": ["Structural Equation Modeling in Psychological Research"],
    "topic_psychology_psychometrics": ["Item Response Theory for Adaptive Psychological Testing"],
    "topic_psychology_qualitative_methods": ["Interpretive Phenomenological Analysis in Health Psychology"],
    "topic_psychology_quantitative_methods": ["Multilevel Modeling for Nested Psychological Data"],
    "topic_psychology_computational_psychology": ["Computational Models of Decision Making: Drift Diffusion Model"],
    "topic_psychology_neuroimaging_techniques": ["fMRI Connectivity Analysis for Cognitive Network Mapping"],
    "topic_psychology_big_data_analytics": ["Machine Learning Applied to Large-Scale Psychological Surveys"],
    "topic_psychology_open_science_practices": ["Pre-Registration and Transparency in Psychological Research"],
    "topic_psychology_replication_and_reproducibility": ["Replication Crisis in Psychology: Large-Scale Replication Projects"],
    "topic_psychology_topic_evaluation_parking": [],
    "topic_psychology_domain_evaluation_parking": [],
    "topic_psychology_hitl_review_required": [],
}
