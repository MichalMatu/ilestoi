"""Offline policy tests for the Termux healthwatch without starting its infinite loop."""

import ast
import subprocess
import unittest
from pathlib import Path

WATCHER = Path(__file__).resolve().parents[1] / "deploy/termux/ilestoi-healthwatch.py"


def load_policy():
    tree = ast.parse(WATCHER.read_text(encoding="utf-8"))
    nodes = []
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "PUBLIC_TUNNEL_ERRORS" for target in node.targets)
            or isinstance(node, ast.FunctionDef)
            and node.name == "eligible_tunnel_failure"
        ):
            nodes.append(node)
    if len(nodes) != 2:
        raise AssertionError("Missing healthwatch policy declaration")
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    ns = {"frozenset": frozenset}
    exec(compile(module, str(WATCHER), "exec"), ns)
    return ns["eligible_tunnel_failure"]


class TunnelHealthwatchPolicyTests(unittest.TestCase):
    def test_530_recovers_only_when_backend_and_network_healthy(self):
        eligible = load_policy()
        self.assertTrue(eligible("200", "530", "ok", False))
        self.assertFalse(eligible("503", "530", "ok", False))
        self.assertFalse(eligible("200", "530", "TimeoutError", False))

    def test_explicit_down_marker_fences_restarts(self):
        eligible = load_policy()
        self.assertFalse(eligible("200", "530", "ok", True))
        self.assertFalse(eligible("200", "502", "ok", True))

    def test_legacy_cloudflare_errors_still_qualify(self):
        eligible = load_policy()
        for status in ("502", "503", "504", "520", "521", "522", "523", "524"):
            with self.subTest(status=status):
                self.assertTrue(eligible("200", status, "ok", False))

    def test_expected_non_tunnel_results_do_not_restart(self):
        eligible = load_policy()
        for status in ("200", "301", "403", "404", "429", "TimeoutError", "URLError"):
            with self.subTest(status=status):
                self.assertFalse(eligible("200", status, "ok", False))


class CloudflaredRunnerContractTests(unittest.TestCase):
    def test_uses_validated_named_config_without_token_file(self):
        script = (WATCHER.parent / "cloudflared.run").read_text(encoding="utf-8")
        self.assertIn("export HOME=/data/data/com.termux/files/home", script)
        self.assertIn('cloudflared --config "$HOME/.cloudflared/config.yml" tunnel run', script)
        self.assertNotIn("--token", script)

    def test_shell_syntax(self):
        script = WATCHER.parent / "cloudflared.run"
        proc = subprocess.run(["sh", "-n", str(script)], capture_output=True, text=True, timeout=5, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
