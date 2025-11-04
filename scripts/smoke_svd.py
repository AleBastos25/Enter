"""Smoke test for SVD acceleration in embedding similarity search."""

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.embedding.index import CosineIndex


def generate_random_embeddings(n: int, dim: int = 384) -> np.ndarray:
    """Generate random unit-norm embeddings for testing."""
    vecs = np.random.randn(n, dim).astype(np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vecs / norms


def test_svd_acceleration():
    """Test SVD acceleration with different index sizes."""
    print("=" * 60)
    print("SVD Acceleration Test")
    print("=" * 60)
    
    dim = 384
    test_sizes = [50, 100, 200, 500, 1000]
    n_queries = 10
    top_k = 5
    
    print(f"\nConfiguration:")
    print(f"  Embedding dimension: {dim}")
    print(f"  Number of queries: {n_queries}")
    print(f"  Top-K: {top_k}")
    print(f"\nTesting index sizes: {test_sizes}")
    print()
    
    results = []
    
    for size in test_sizes:
        print(f"Testing size={size}:")
        
        # Generate embeddings
        embeddings = generate_random_embeddings(size, dim)
        ids = list(range(size))
        queries = generate_random_embeddings(n_queries, dim)
        
        # Test without SVD
        index_no_svd = CosineIndex(dim=dim, svd_enabled=False)
        index_no_svd.add(ids, embeddings)
        
        start = time.perf_counter()
        top_ids_no_svd, top_scores_no_svd = index_no_svd.search(queries, top_k)
        time_no_svd = time.perf_counter() - start
        
        # Test with SVD (auto-select components)
        index_svd = CosineIndex(
            dim=dim,
            svd_enabled=True,
            svd_n_components=None,  # Auto-select
            svd_min_size=100,
            svd_variance_threshold=0.95,
        )
        index_svd.add(ids, embeddings)
        
        start = time.perf_counter()
        top_ids_svd, top_scores_svd = index_svd.search(queries, top_k)
        time_svd = time.perf_counter() - start
        
        # Check if SVD was actually used
        svd_used = size >= 100 and index_svd._svd_fitted
        if svd_used:
            reduced_dim = index_svd._svd_reduced_dim
            speedup = time_no_svd / time_svd if time_svd > 0 else 0
        else:
            reduced_dim = None
            speedup = 1.0
        
        # Compare results (check if top-1 matches)
        top1_matches = 0
        for q_idx in range(n_queries):
            if top_ids_no_svd[q_idx, 0] == top_ids_svd[q_idx, 0]:
                top1_matches += 1
        
        results.append({
            "size": size,
            "time_no_svd": time_no_svd,
            "time_svd": time_svd,
            "svd_used": svd_used,
            "reduced_dim": reduced_dim,
            "speedup": speedup,
            "top1_accuracy": top1_matches / n_queries,
        })
        
        print(f"  Without SVD: {time_no_svd*1000:.2f} ms")
        print(f"  With SVD:    {time_svd*1000:.2f} ms")
        if svd_used:
            print(f"  Reduced dim: {reduced_dim} (from {dim})")
            print(f"  Speedup:      {speedup:.2f}x")
            print(f"  Top-1 accuracy: {top1_matches}/{n_queries} ({top1_matches/n_queries*100:.1f}%)")
        else:
            print(f"  SVD not applied (size < min_size=100)")
        print()
    
    # Summary
    print("=" * 60)
    print("Summary:")
    print("=" * 60)
    print(f"{'Size':<10} {'No SVD (ms)':<15} {'SVD (ms)':<15} {'Speedup':<10} {'Top-1 Acc':<10}")
    print("-" * 60)
    for r in results:
        svd_status = "Yes" if r["svd_used"] else "No"
        speedup_str = f"{r['speedup']:.2f}x" if r["svd_used"] else "N/A"
        acc_str = f"{r['top1_accuracy']*100:.1f}%" if r["svd_used"] else "N/A"
        print(
            f"{r['size']:<10} "
            f"{r['time_no_svd']*1000:<15.2f} "
            f"{r['time_svd']*1000:<15.2f} "
            f"{speedup_str:<10} "
            f"{acc_str:<10}"
        )
    
    print("\nNotes:")
    print("  - SVD is only applied when index size >= min_size (default: 100)")
    print("  - Speedup is more noticeable with larger indices")
    print("  - Top-1 accuracy should be close to 100% (SVD is approximate but precise)")
    print("  - SVD uses variance_threshold=0.95 to auto-select components")


def test_svd_with_fixed_components():
    """Test SVD with fixed number of components."""
    print("\n" + "=" * 60)
    print("SVD with Fixed Components Test")
    print("=" * 60)
    
    dim = 384
    size = 500
    n_queries = 20
    top_k = 5
    
    embeddings = generate_random_embeddings(size, dim)
    ids = list(range(size))
    queries = generate_random_embeddings(n_queries, dim)
    
    component_counts = [32, 64, 128, 192]
    
    print(f"\nTesting with size={size}, fixed component counts: {component_counts}\n")
    
    # Baseline (no SVD)
    index_baseline = CosineIndex(dim=dim, svd_enabled=False)
    index_baseline.add(ids, embeddings)
    start = time.perf_counter()
    top_ids_baseline, top_scores_baseline = index_baseline.search(queries, top_k)
    time_baseline = time.perf_counter() - start
    
    print(f"Baseline (no SVD): {time_baseline*1000:.2f} ms\n")
    
    for n_comp in component_counts:
        index_svd = CosineIndex(
            dim=dim,
            svd_enabled=True,
            svd_n_components=n_comp,
            svd_min_size=100,
        )
        index_svd.add(ids, embeddings)
        
        start = time.perf_counter()
        top_ids_svd, top_scores_svd = index_svd.search(queries, top_k)
        time_svd = time.perf_counter() - start
        
        speedup = time_baseline / time_svd if time_svd > 0 else 0
        
        # Check accuracy
        top1_matches = sum(
            1 for q_idx in range(n_queries)
            if top_ids_baseline[q_idx, 0] == top_ids_svd[q_idx, 0]
        )
        
        print(f"Components={n_comp:3d}: {time_svd*1000:.2f} ms, speedup={speedup:.2f}x, "
              f"top-1 accuracy={top1_matches}/{n_queries} ({top1_matches/n_queries*100:.1f}%)")
    
    print("\nNote: More components = better accuracy but slower")


def main():
    """Run SVD tests."""
    try:
        test_svd_acceleration()
        test_svd_with_fixed_components()
        
        print("\n" + "=" * 60)
        print("All tests completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

