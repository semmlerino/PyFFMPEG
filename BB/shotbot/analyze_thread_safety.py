#!/usr/bin/env python3
"""Analyze thread safety overhead in the codebase."""

import ast
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple


class ThreadSafetyAnalyzer(ast.NodeVisitor):
    """AST visitor to analyze thread safety patterns."""
    
    def __init__(self):
        self.locks_found: List[str] = []
        self.lock_acquisitions: int = 0
        self.thread_classes: List[str] = []
        self.qt_signals: int = 0
        self.atomics: int = 0
        self.thread_locals: int = 0
        
    def visit_Import(self, node):
        """Track threading-related imports."""
        for alias in node.names:
            if 'thread' in alias.name.lower() or 'lock' in alias.name.lower():
                self.thread_classes.append(alias.name)
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node):
        """Track threading-related imports."""
        if node.module and ('thread' in node.module.lower() or 'lock' in node.module.lower()):
            for alias in node.names:
                self.thread_classes.append(f"{node.module}.{alias.name}")
        self.generic_visit(node)
    
    def visit_Call(self, node):
        """Track lock acquisitions and thread operations."""
        if isinstance(node.func, ast.Attribute):
            # Check for lock operations
            if node.func.attr in ['acquire', 'release', '__enter__', '__exit__']:
                self.lock_acquisitions += 1
            # Check for Qt signals
            elif node.func.attr in ['emit', 'connect', 'disconnect']:
                self.qt_signals += 1
        self.generic_visit(node)
    
    def visit_With(self, node):
        """Track context manager lock usage."""
        for item in node.items:
            if isinstance(item.context_expr, ast.Call):
                if hasattr(item.context_expr.func, 'id'):
                    if 'lock' in item.context_expr.func.id.lower():
                        self.lock_acquisitions += 1
            elif isinstance(item.context_expr, ast.Name):
                if 'lock' in item.context_expr.id.lower():
                    self.lock_acquisitions += 1
        self.generic_visit(node)
    
    def visit_Assign(self, node):
        """Track lock and thread-local creation."""
        if isinstance(node.value, ast.Call):
            if hasattr(node.value.func, 'id'):
                func_name = node.value.func.id
                if 'Lock' in func_name or 'RLock' in func_name:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            self.locks_found.append(target.id)
                elif 'local' in func_name.lower():
                    self.thread_locals += 1
        self.generic_visit(node)


def analyze_file(file_path: Path) -> Dict:
    """Analyze a single Python file for thread safety overhead."""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        tree = ast.parse(content)
        analyzer = ThreadSafetyAnalyzer()
        analyzer.visit(tree)
        
        # Count actual lock usage in code
        lock_with_patterns = len(re.findall(r'with\s+\w*[Ll]ock', content))
        lock_acquire_patterns = len(re.findall(r'\.acquire\(\)', content))
        lock_release_patterns = len(re.findall(r'\.release\(\)', content))
        
        return {
            'locks': len(analyzer.locks_found),
            'acquisitions': analyzer.lock_acquisitions,
            'with_locks': lock_with_patterns,
            'explicit_acquire': lock_acquire_patterns,
            'explicit_release': lock_release_patterns,
            'qt_signals': analyzer.qt_signals,
            'thread_locals': analyzer.thread_locals,
            'thread_imports': len(analyzer.thread_classes),
        }
    except Exception as e:
        return {'error': str(e)}


def calculate_overhead(stats: Dict) -> float:
    """Calculate estimated overhead from thread safety mechanisms."""
    # Rough estimates of overhead in microseconds
    LOCK_ACQUIRE_OVERHEAD = 0.5  # µs per acquisition
    SIGNAL_EMIT_OVERHEAD = 1.0   # µs per signal
    WITH_LOCK_OVERHEAD = 1.5     # µs per with statement
    
    total_overhead = (
        stats['acquisitions'] * LOCK_ACQUIRE_OVERHEAD +
        stats['qt_signals'] * SIGNAL_EMIT_OVERHEAD +
        stats['with_locks'] * WITH_LOCK_OVERHEAD
    )
    
    return total_overhead


def main():
    """Analyze thread safety overhead in the codebase."""
    print("=" * 70)
    print("THREAD SAFETY OVERHEAD ANALYSIS")
    print("=" * 70)
    print()
    
    # Key files to analyze
    target_files = [
        'cache_manager.py',
        'process_pool_manager.py',
        'launcher_manager.py',
        'shot_model.py',
        'main_window.py',
        'cache/storage_backend.py',
        'cache/failure_tracker.py',
        'cache/memory_manager.py',
        'cache/thumbnail_processor.py',
        'previous_shots_worker.py',
        'threede_scene_worker.py',
    ]
    
    total_stats = {
        'locks': 0,
        'acquisitions': 0,
        'with_locks': 0,
        'explicit_acquire': 0,
        'explicit_release': 0,
        'qt_signals': 0,
        'thread_locals': 0,
        'thread_imports': 0,
    }
    
    file_overheads = []
    
    print("Per-File Analysis:")
    print("-" * 70)
    
    for file_name in target_files:
        file_path = Path(file_name)
        if not file_path.exists():
            file_path = Path('cache') / file_name.replace('cache/', '')
        
        if file_path.exists():
            stats = analyze_file(file_path)
            if 'error' not in stats:
                overhead = calculate_overhead(stats)
                file_overheads.append((file_name, overhead, stats))
                
                # Aggregate stats
                for key in total_stats:
                    total_stats[key] += stats.get(key, 0)
                
                print(f"\n{file_name}:")
                print(f"  Locks defined:      {stats['locks']}")
                print(f"  Lock acquisitions:  {stats['acquisitions']}")
                print(f"  With-lock blocks:   {stats['with_locks']}")
                print(f"  Qt signals:         {stats['qt_signals']}")
                print(f"  Estimated overhead: {overhead:.2f} µs")
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    print(f"\nTotal Counts:")
    print(f"  Lock objects:        {total_stats['locks']}")
    print(f"  Lock acquisitions:   {total_stats['acquisitions']}")
    print(f"  With-lock blocks:    {total_stats['with_locks']}")
    print(f"  Explicit acquires:   {total_stats['explicit_acquire']}")
    print(f"  Explicit releases:   {total_stats['explicit_release']}")
    print(f"  Qt signal ops:       {total_stats['qt_signals']}")
    print(f"  Thread locals:       {total_stats['thread_locals']}")
    
    total_overhead = sum(o for _, o, _ in file_overheads)
    print(f"\nTotal estimated overhead: {total_overhead:.2f} µs")
    
    # Sort by overhead
    print(f"\nTop overhead contributors:")
    for file_name, overhead, stats in sorted(file_overheads, key=lambda x: x[1], reverse=True)[:5]:
        if overhead > 0:
            print(f"  {file_name:<30} {overhead:>8.2f} µs")
    
    # Calculate the "883% overhead" claim
    print("\n" + "=" * 70)
    print("OVERHEAD ANALYSIS")
    print("=" * 70)
    
    # Assume baseline operation is 10µs (rough estimate)
    baseline_operation = 10.0
    overhead_ratio = (total_overhead / baseline_operation) * 100
    
    print(f"\nAssuming baseline operation time: {baseline_operation} µs")
    print(f"Thread safety overhead:            {total_overhead:.2f} µs")
    print(f"Overhead ratio:                    {overhead_ratio:.1f}%")
    
    if overhead_ratio > 100:
        print(f"\n⚠️  EXCESSIVE OVERHEAD DETECTED: {overhead_ratio:.1f}%")
        print("   Thread safety mechanisms are taking more time than actual operations!")
    
    # Recommendations
    print("\n" + "=" * 70)
    print("OPTIMIZATION OPPORTUNITIES")
    print("=" * 70)
    
    if total_stats['locks'] > 5:
        print("\n1. Lock Consolidation:")
        print(f"   - {total_stats['locks']} separate locks found")
        print("   - Consider using a single lock per module")
        print("   - Use threading.RLock() for recursive needs")
    
    if total_stats['acquisitions'] > 20:
        print("\n2. Reduce Lock Frequency:")
        print(f"   - {total_stats['acquisitions']} lock acquisitions detected")
        print("   - Batch operations under single lock acquisition")
        print("   - Use lock-free data structures where possible")
    
    if total_stats['qt_signals'] > 50:
        print("\n3. Signal Optimization:")
        print(f"   - {total_stats['qt_signals']} Qt signal operations")
        print("   - Consider batching signals")
        print("   - Use direct method calls for same-thread communication")
    
    print("\n4. Alternative Approaches:")
    print("   - Use Queue for thread communication (lock-free)")
    print("   - Implement actor model with message passing")
    print("   - Use asyncio for I/O-bound operations")
    print("   - Consider ProcessPoolExecutor for CPU-bound tasks")
    

if __name__ == '__main__':
    main()