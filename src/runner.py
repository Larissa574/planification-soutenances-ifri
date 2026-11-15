import argparse
import csv
import logging
import random
import time
from pathlib import Path
from typing import Callable

from io_utils import (
    list_instances,
    load_instance,
    save_solution,
    validate_solution,
)

# En-tête exact de templates/resultats.csv
CSV_COLUMNS = [
    "instance_id",
    "method",
    "seed",
    "build_seconds",
    "search_seconds",
    "total_seconds",
    "first_feasible_seconds",
    "stop_status",
    "valid",
    "teacher_presence_days",
    "teacher_idle_slots",
    "teacher_load_range",
    "supervisor_group_breaks",
    "distinct_jury_pairs",
    "solution_file",
    "validation_file",
]


def setup_logger(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("campaign_runner")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        fh = logging.FileHandler(log_dir / "campaign.log", encoding="utf-8")
        fh.setFormatter(fmt)
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(fh)
        logger.addHandler(ch)
    return logger


def ensure_csv_header(csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()


def append_csv_row(csv_path: Path, row: dict) -> None:
    ensure_csv_header(csv_path)
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writerow(row)


def run_single(
    instance_path: Path,
    method_name: str,
    solve_fn: Callable,
    seed: int,
    time_limit: float = 60.0,
    results_dir: Path = Path("results"),
    csv_path: Path = Path("results/resultats.csv"),
    logger: logging.Logger | None = None,
) -> dict:
    """
    Exécute une méthode sur une instance avec une graine donnée,
    chronomètre, sauvegarde le JSON, valide et enregistre la ligne CSV.
    """
    instance_id = instance_path.stem
    instance_data = load_instance(instance_path)

    # Fixe la graine globale avant l'appel
    random.seed(seed)

    # Chronomètre temps mural (hors chargement/export/validation)
    t_start = time.perf_counter()
    try:
        raw_result = solve_fn(instance_data, time_limit=time_limit, seed=seed)
    except Exception as exc:
        total_sec = round(time.perf_counter() - t_start, 4)
        if logger:
            logger.exception(f"Erreur sur {instance_id} ({method_name}, seed={seed}): {exc}")
        row = {
            "instance_id": instance_id,
            "method": method_name,
            "seed": seed,
            "build_seconds": 0.0,
            "search_seconds": total_sec,
            "total_seconds": total_sec,
            "first_feasible_seconds": "",
            "stop_status": f"ERROR: {type(exc).__name__}",
            "valid": False,
            "teacher_presence_days": "",
            "teacher_idle_slots": "",
            "teacher_load_range": "",
            "supervisor_group_breaks": "",
            "distinct_jury_pairs": "",
            "solution_file": "",
            "validation_file": "",
        }
        append_csv_row(csv_path, row)
        return row

    total_sec = round(time.perf_counter() - t_start, 4)

    # Normalisation du retour de solve_fn (accepte un dict détaillé ou un tuple (sol, status))
    if isinstance(raw_result, dict) and "solution" in raw_result:
        solution = raw_result["solution"]
        stop_status = raw_result.get("stop_status", "UNKNOWN")
        build_sec = round(float(raw_result.get("build_seconds", 0.0)), 4)
        search_sec = round(float(raw_result.get("search_seconds", total_sec - build_sec)), 4)
        first_feas = raw_result.get("first_feasible_seconds", "")
        if first_feas != "" and first_feas is not None:
            first_feas = round(float(first_feas), 4)
    else:
        solution, stop_status = raw_result
        build_sec = 0.0
        search_sec = total_sec
        first_feas = total_sec if solution is not None else ""

    if total_sec > time_limit and stop_status not in ("TIMEOUT", "OPTIMAL"):
        stop_status = "TIMEOUT"

    # Si aucune solution produite
    if solution is None:
        row = {
            "instance_id": instance_id,
            "method": method_name,
            "seed": seed,
            "build_seconds": build_sec,
            "search_seconds": search_sec,
            "total_seconds": total_sec,
            "first_feasible_seconds": "",
            "stop_status": stop_status,
            "valid": False,
            "teacher_presence_days": "",
            "teacher_idle_slots": "",
            "teacher_load_range": "",
            "supervisor_group_breaks": "",
            "distinct_jury_pairs": "",
            "solution_file": "",
            "validation_file": "",
        }
        append_csv_row(csv_path, row)
        if logger:
            logger.warning(f"{instance_id} | {method_name} | seed={seed} -> AUCUNE SOLUTION ({stop_status}) en {total_sec}s")
        return row

    # Export JSON et validation officielle
    method_dir = results_dir / method_name
    sol_path = method_dir / f"{instance_id}_seed{seed}.json"
    val_path = method_dir / f"{instance_id}_seed{seed}_val.json"

    save_solution(solution, sol_path)
    val_res = validate_solution(instance_path, sol_path, report_path=val_path)
    is_valid = val_res["valid"]
    row = {
        "instance_id": instance_id,
        "method": method_name,
        "seed": seed,
        "build_seconds": build_sec,
        "search_seconds": search_sec,
        "total_seconds": total_sec,
        "first_feasible_seconds": first_feas if is_valid else "",
        "stop_status": stop_status,
        "valid": is_valid,
        "teacher_presence_days": val_res["f1"] if is_valid else "",
        "teacher_idle_slots": val_res["f2"] if is_valid else "",
        "teacher_load_range": val_res["f3"] if is_valid else "",
        "supervisor_group_breaks": val_res["f4"] if is_valid else "",
        "distinct_jury_pairs": val_res["f5"] if is_valid else "",
        "solution_file": sol_path.as_posix(),
        "validation_file": val_path.as_posix(),
    }
    append_csv_row(csv_path, row)

    if logger:
        scores = (
            f"({val_res['f1']}, {val_res['f2']}, {val_res['f3']}, {val_res['f4']}, {val_res['f5']})"
            if is_valid
            else f"INVALIDE: {val_res['errors']}"
        )
        logger.info(
            f"{instance_id} | {method_name} | seed={seed} | valid={is_valid} | {total_sec}s | {scores}"
        )
    return row


def run_campaign(
    method_name: str,
    solve_fn: Callable,
    seeds: list[int],
    data_dir: str = "data",
    time_limit: float = 60.0,
    results_dir: str = "results",
) -> None:
    res_path = Path(results_dir)
    csv_path = res_path / "resultats.csv"
    logger = setup_logger(res_path / "logs")
    instances = list_instances(data_dir)

    logger.info(
        f"=== Début campagne '{method_name}' : {len(instances)} instances x {len(seeds)} graines (budget={time_limit}s) ==="
    )
    for inst_path in instances:
        for seed in seeds:
            run_single(
                instance_path=inst_path,
                method_name=method_name,
                solve_fn=solve_fn,
                seed=seed,
                time_limit=time_limit,
                results_dir=res_path,
                csv_path=csv_path,
                logger=logger,
            )
    logger.info(f"=== Fin campagne '{method_name}'. Résultats dans {csv_path} ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lanceur de campagne soutenances")
    parser.add_argument(
        "--method",
        choices=["demo", "greedy", "sa"],
        default="demo",
        help="Méthode à exécuter (demo pour tester le pipeline)",
    )
    parser.add_argument("--time-limit", type=float, default=60.0, help="Temps max par run (s)")
    args = parser.parse_args()

    if args.method == "demo":
        # Test autonome du lanceur avec le fichier demo fourni
        demo_sol = load_instance("examples/demo_solution.json")

        def dummy_solver(instance: dict, time_limit: float = 60.0, seed: int = 0):
            return {
                "solution": demo_sol,
                "stop_status": "FEASIBLE",
                "build_seconds": 0.001,
                "search_seconds": 0.002,
                "first_feasible_seconds": 0.001,
            }

        logger = setup_logger(Path("results/logs"))
        run_single(
            instance_path=Path("examples/demo_instance.json"),
            method_name="demo",
            solve_fn=dummy_solver,
            seed=0,
            time_limit=args.time_limit,
            logger=logger,
        )
    elif args.method == "greedy":
        from greedy import solve as greedy_solve
        # Déterministe : 1 seule exécution (seed 0)
        run_campaign("greedy", greedy_solve, seeds=[0], time_limit=args.time_limit)
    elif args.method == "sa":
        from simulated_annealing import solve as sa_solve
        # Stochastique : graines 0 à 4
        run_campaign("sa", sa_solve, seeds=[0, 1, 2, 3, 4], time_limit=args.time_limit)