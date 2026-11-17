"""
sa_reglage.py  --  L8 : régler p0 et ratio_final AVANT la campagne officielle.

Règles du protocole respectées :
  * graines de réglage 100, 101, ... (JAMAIS 0 à 4, réservées à la campagne finale) ;
  * résultats écrits dans results_reglage/ (jamais dans results/) ;
  * les valeurs retenues sont ensuite recopiées dans sa_parametres.py et GELÉES.

Mesure de qualité commune à toutes les configurations : score à poids égaux, normalisé par le
planning de départ (1.0 = pas mieux que le départ ; plus petit = mieux).

Usage (depuis la racine du dépôt) :
    python src/sa_reglage.py --instances small_01 medium_01 --budget 10 --graines 100 101 102
"""
import argparse
import csv
import itertools
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from io_utils import load_instance          # noqa: E402
from sa_parametres import PARAMS            # noqa: E402
from sa_score import Evaluateur             # noqa: E402
import simulated_annealing as sa            # noqa: E402

GRILLE = {"p0": [0.2, 0.5, 0.8], "ratio_final": [1e-2, 1e-3, 1e-4]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instances", nargs="+", default=["small_01", "medium_01"])
    ap.add_argument("--budget", type=float, default=10.0, help="secondes par run")
    ap.add_argument("--graines", nargs="+", type=int, default=[100, 101, 102])
    ap.add_argument("--sortie", default="results_reglage/reglage.csv")
    args = ap.parse_args()
    assert all(g >= 100 for g in args.graines), "les graines 0-4 sont réservées à la campagne finale"

    sortie = Path(args.sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    lignes = []
    for p0, ratio in itertools.product(GRILLE["p0"], GRILLE["ratio_final"]):
        params = dict(PARAMS, p0=p0, ratio_final=ratio)
        scores = []
        for nom in args.instances:
            inst = load_instance(Path("data") / f"{nom}.json")
            for g in args.graines:
                r = sa.solve(inst, time_limit=args.budget, seed=g, params=params)
                if r["solution"] is None:
                    continue
                ev = Evaluateur((0.2,) * 5, r["criteres_depart"])
                s = ev.score(r["criteres_final"])
                scores.append(s)
                lignes.append({"p0": p0, "ratio_final": ratio, "instance": nom, "graine": g,
                               "score_relatif": round(s, 4), "criteres_final": r["criteres_final"]})
        moy = statistics.mean(scores) if scores else float("nan")
        print(f"p0={p0:<4} ratio_final={ratio:<7} score relatif moyen = {moy:.4f}  ({len(scores)} runs)")

    with sortie.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0].keys()))
        w.writeheader()
        w.writerows(lignes)
    print("Détails :", sortie)


if __name__ == "__main__":
    main()
