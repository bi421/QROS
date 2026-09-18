# main.py
import io
import os
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def run_script(name):
    print(f"\n🚀 Ажиллуулж байна: {name}")
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run([sys.executable, f"scripts/{name}"], env=env)
    if result.returncode != 0:
        print(f"⚠️ {name} алдаатай дууслаа.")


if __name__ == "__main__":
    print("=" * 70)
    print("📊 ResearchOS – Нэгдсэн шинжилгээ")
    print("=" * 70)
    run_script("run_first_backtest.py")
    run_script("run_full_analysis_fixed4.py")
    run_script("trading_signal.py")
    print("\n✅ Бүх шинжилгээ дууссан.")
