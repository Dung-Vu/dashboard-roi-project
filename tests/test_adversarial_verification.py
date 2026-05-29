from __future__ import annotations

import unittest
import subprocess
import sys
from pathlib import Path

class AdversarialVerificationTest(unittest.TestCase):
    def test_run_javascript_stress_test(self):
        """Runs verify_stress.js with Node to verify front-end components' robustness."""
        test_js_path = Path(__file__).parent / "verify_stress.js"
        self.assertTrue(test_js_path.exists(), "verify_stress.js does not exist!")
        
        # Run node on verify_stress.js
        try:
            result = subprocess.run(
                ["node", str(test_js_path)],
                capture_output=True,
                text=True,
                check=True
            )
            # Ensure the output has "--- Stress Testing Complete ---"
            self.assertIn("--- Stress Testing Complete ---", result.stdout)
            self.assertNotIn("[FAIL]", result.stdout, "JS stress test reported failures!")
            
            # Print the output in the test log
            print("\nJS Stress Test Output:\n", result.stdout)
            
        except subprocess.CalledProcessError as e:
            self.fail(f"JS stress test failed to run or exited with error. stdout: {e.stdout}, stderr: {e.stderr}")
        except FileNotFoundError:
            self.skipTest("Node.js is not installed on this system. Skipping JS integration test.")

if __name__ == "__main__":
    unittest.main()
