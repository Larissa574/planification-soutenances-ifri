import json
import subprocess
import sys
from pathlib import Path


def load_instance(instance_path: str | Path) -> dict:
    """Charge un fichier d'instance JSON (ex: data/small_01.json)."""
    path = Path(instance_path)
    if not path.exists():
        raise FileNotFoundError(f"Fichier d'instance introuvable : {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_solution(solution: dict, output_path: str | Path) -> Path:
    """Sauvegarde un planning au format JSON (UTF-8, indenté)."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(solution, f, indent=2, ensure_ascii=False)
    return path


def validate_solution(
    instance_path: str | Path,
    solution_path: str | Path,
    report_path: str | Path | None = None,
    validator_script: str | Path = "validator.py",
) -> dict:
    """
    Exécute validator.py, sauvegarde le rapport JSON si report_path est fourni,
    et retourne un dictionnaire standardisé avec la validité et les 5 critères.
    """
    cmd = [
        sys.executable,
        str(validator_script),
        str(instance_path),
        str(solution_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    stdout = proc.stdout.strip()

    if not stdout:
        report = {
            "valid": False,
            "errors": [proc.stderr.strip() or "Sortie vide du validateur"],
            "metrics": None,
        }
    else:
        report = json.loads(stdout)

    if report_path is not None:
        out_path = Path(report_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    is_valid = bool(report.get("valid", False))
    metrics = report.get("metrics") or {}

    return {
        "valid": is_valid,
        "errors": report.get("errors", []),
        "f1": metrics.get("teacher_presence_days") if is_valid else None,
        "f2": metrics.get("teacher_idle_slots") if is_valid else None,
        "f3": metrics.get("teacher_load_range") if is_valid else None,
        "f4": metrics.get("supervisor_group_breaks") if is_valid else None,
        "f5": metrics.get("distinct_jury_pairs") if is_valid else None,
    }


def list_instances(data_dir: str | Path = "data") -> list[Path]:
    """Retourne la liste triée des 30 instances (small_*, medium_*, large_*)."""
    order = {"small": 0, "medium": 1, "large": 2}
    files = list(Path(data_dir).glob("*.json"))
    instances = [f for f in files if f.stem.split("_")[0] in order]
    return sorted(
        instances,
        key=lambda p: (order[p.stem.split("_")[0]], p.stem),
    )


if __name__ == "__main__":
    inst = load_instance("examples/demo_instance.json")
    print(f"Instance chargée ({len(inst.get('students', []))} étudiants).")

    res = validate_solution("examples/demo_instance.json", "examples/demo_solution.json")
    print("Résultat validation :", res)

    print(f"Instances trouvées : {len(list_instances('data'))}")