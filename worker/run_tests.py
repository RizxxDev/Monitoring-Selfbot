"""
Master Test Runner: Menjalankan seluruh test suite Growcord Selfbot (67 test).
Dapat dijalankan kapan saja tanpa token Discord (100% offline).

Penggunaan:
    python run_tests.py
"""

import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from tests.selftest import main as run_selftest


def main():
    print("=" * 60)
    print(" MENJALANKAN SELURUH TEST SUITE GROWCORD SELFBOT")
    print("=" * 60)

    # 1. Jalankan selftest offline simulation
    print("\n[1/2] Menjalankan Simulasi Engine Lengkap (tests/selftest.py)...")
    try:
        run_selftest()
    except SystemExit as exc:
        if exc.code not in (0, None):
            print("FAILED: selftest.py gagal!")
            sys.exit(exc.code)

    # 2. Jalankan Unittest Suite di direktori tests/
    print("\n[2/2] Menjalankan Unit & Integration Tests (tests/)...")
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    from tests import (
        test_24_7_fixes,
        test_phase1_fixes,
        test_phase2_optimizations,
        test_robustness_24_7,
    )

    for mod in (
        test_phase1_fixes,
        test_24_7_fixes,
        test_robustness_24_7,
        test_phase2_optimizations,
    ):
        suite.addTests(loader.loadTestsFromModule(mod))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print(f" SEMUA TEST LULUS! (Total: {17 + result.testsRun} test)")
        print("=" * 60)
        sys.exit(0)
    else:
        print(f" ADA TEST GAGAL: {len(result.failures)} failure(s), {len(result.errors)} error(s)")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()

