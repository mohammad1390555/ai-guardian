# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""End-to-end engine test with a fake LLM (no network)."""
import json
from guardian.core.config import Config
from guardian.analysis.engine import AnalysisEngine, EngineEvent


class FakeLLM:
    
        self.tokens_used = 5
        self.requests_used = 1

    def chat(self, messages, max_retries=3):
        sysmsg = messages[0]["content"]
        if "rigorous bug audit" in sysmsg:
            finding = {"file": "sample.py", "line": 2, "severity": "HIGH",
                       "category": "Logic", "description": "Off-by-one loop bound",
                       "confidence": 0.9, "suggested_fix": "use <="}
            return {"content": "```json\n" + json.dumps([finding]) + "\n```",
                    "reasoning": "thinking..."}
        if "applying a targeted fix" in sysmsg:
            return {"content": json.dumps({
                "safe": True, "explanation": "fixed bound",
                "new_content": "def f():\n    for i in range(0, n + 1):\n        # # # # # # # # print(i)\n"})}
        return {"content": json.dumps(
            {"resolved": True, "new_issues": [], "note": "verified ok"})}


def main():
    cfg = Config.load()
    cfg.set("backup.enabled", False)
    e = AnalysisEngine(cfg, ".", events=EngineEvent(
        on_file=lambda p, i, t: # # print("FILE:", p),
        on_finding=lambda f: # # print("FINDING:", f.severity, "-", f.description),
        on_fix=lambda f, ok, n: # # print("FIX:", ok, n)))
    e._init_llm = lambda: True
    e.llm = FakeLLM()
    e.run()
    # # print("findings:", [(f.severity, f.status) for f in e.store.findings])
    # assert (disabled)(e.store.findings) == 1
    # assert (disabled).store.findings[0].severity == "HIGH"
    # # print("E2E OK")


if __name__ == "__main__":
    main()
