"""
simulated_annealing.py  --  boucle principale du recuit simulé (L7 + L8).

Interface attendue par runner.py :
    solve(instance, time_limit=60.0, seed=0)  ->  dict avec "solution", "stop_status", ...

Étapes :
  1. Planning de départ : celui du glouton (src/greedy.py, `solve(instance, time_limit, seed)`).
     S'il est absent ou invalide -> planning de dépannage (sa_depart_secours.py).
  2. Recuit : mouvements valides uniquement ; acceptation e^(-delta/T) ; température qui
     baisse avec le temps écoulé ; on garde le meilleur planning vu.
  3. Retour du meilleur planning + archive des solutions non dominées.

Le temps du glouton est compté dans le budget (protocole : 60 s au total).
"""
import copy
import logging
import math
import random
import time

from sa_etat import Etat, PlanningInvalide
from sa_parametres import PARAMS
from sa_score import Evaluateur, ArchivePareto
from sa_voisinages import tirer_mouvement

log = logging.getLogger("sa")


# ---------------------------------------------------------------------------
# 1. Départ
# ---------------------------------------------------------------------------
def _solution_du_glouton(instance, budget, seed):
    """Appelle greedy.solve s'il existe. Renvoie (solution_json ou None, message)."""
    try:
        from greedy import solve as glouton
    except ImportError:
        return None, "greedy.py absent"
    try:
        res = glouton(copy.deepcopy(instance), time_limit=budget, seed=seed)
    except Exception as exc:                       # un bug du glouton ne doit pas tuer le recuit
        return None, f"greedy a levé {type(exc).__name__}: {exc}"
    if isinstance(res, dict) and "solution" in res:
        sol = res["solution"]
    elif isinstance(res, tuple):
        sol = res[0]
    else:
        sol = res
    return (sol, "ok") if sol else (None, "greedy n'a produit aucune solution")


def _etat_de_depart(instance, t0, time_limit, seed, rng, params):
    """Renvoie (etat, origine) ; etat = None si rien de valide n'a pu être construit."""
    budget_glouton = params["part_glouton"] * time_limit
    sol, msg = _solution_du_glouton(instance, budget_glouton, seed)
    if sol is not None:
        try:
            return Etat(instance).charger_solution(sol), "glouton"
        except PlanningInvalide as exc:
            msg = f"planning du glouton refusé : {exc}"
    log.warning("Départ de dépannage utilisé (%s)", msg)
    from sa_depart_secours import construire
    etat = construire(instance, rng, t0 + 0.6 * time_limit)
    return etat, "secours"


# ---------------------------------------------------------------------------
# 2. Recuit
# ---------------------------------------------------------------------------
def _calibrer_T0(etat, ev, rng, params):
    """T0 tel qu'une dégradation moyenne soit acceptée avec probabilité p0. L'état est restauré."""
    s0 = ev.score(etat.criteres())
    pires = []
    for _ in range(params["nb_calibration"]):
        photo = tirer_mouvement(rng)(etat, rng)
        if photo is None:
            continue
        d = ev.score(etat.criteres()) - s0
        if d > 0:
            pires.append(d)
        etat.reposer(photo)                       # on annule toujours : simple mesure
    if not pires:
        return 0.01
    return (sum(pires) / len(pires)) / (-math.log(params["p0"]))


def recuit(etat, ev, rng, echeance, params, archive=None):
    """Boucle du recuit. Modifie `etat`. Renvoie (meilleur_snapshot, f_meilleur, statistiques)."""
    f = etat.criteres()
    s = ev.score(f)
    meilleur_s, meilleur_f, meilleur_snap = s, f, etat.snapshot()
    if archive is not None:
        archive.proposer(f, etat.snapshot, ev)

    T0 = _calibrer_T0(etat, ev, rng, params)
    ratio = params["ratio_final"]
    bande = 1.0 + params["bande_archive"]
    t_debut = time.perf_counter()
    duree = max(echeance - t_debut, 1e-6)
    T = T0
    essais = appliques = acceptes = 0
    exp = math.exp
    rnd = rng.random

    while True:
        if essais % 25 == 0:
            now = time.perf_counter()
            if now >= echeance:
                break
            T = T0 * ratio ** ((now - t_debut) / duree)        # refroidissement géométrique
        essais += 1
        photo = tirer_mouvement(rng)(etat, rng)
        if photo is None:
            continue
        appliques += 1
        f2 = etat.criteres()
        s2 = ev.score(f2)
        delta = s2 - s
        if delta <= 0 or rnd() < exp(-delta / T):
            acceptes += 1
            s, f = s2, f2
            if s < meilleur_s:
                meilleur_s, meilleur_f, meilleur_snap = s, f, etat.snapshot()
            if archive is not None and s <= meilleur_s * bande:
                archive.proposer(f, etat.snapshot, ev)
        else:
            etat.reposer(photo)                                # refus : on annule

    stats = {"T0": T0, "T_fin": T, "essais": essais, "mouvements_valides": appliques,
             "acceptes": acceptes}
    return meilleur_snap, meilleur_f, stats


# ---------------------------------------------------------------------------
# 3. Point d'entrée pour le runner
# ---------------------------------------------------------------------------
def solve(instance, time_limit=60.0, seed=0, params=None):
    t0 = time.perf_counter()
    params = dict(PARAMS if params is None else params)
    rng = random.Random(seed)                      # générateur local : reproductible, indépendant du reste
    marge = min(params["marge_fin"], 0.1 * time_limit)
    echeance = t0 + time_limit - marge

    etat, origine = _etat_de_depart(instance, t0, time_limit, seed, rng, params)
    if etat is None or not etat.complet():
        return {"solution": None, "stop_status": "NO_SOLUTION",
                "build_seconds": time.perf_counter() - t0,
                "search_seconds": 0.0, "first_feasible_seconds": ""}

    t_depart = time.perf_counter() - t0
    f_depart = etat.criteres()
    ev = Evaluateur(params["poids"], f_depart)
    archive = ArchivePareto(params["taille_archive"])

    snap, f_final, stats = recuit(etat, ev, rng, echeance, params, archive)

    solution = etat.en_solution(snap)
    total = time.perf_counter() - t0
    return {
        "solution": solution,
        "stop_status": "FEASIBLE",                 # valide ; arrêt à la limite de temps
        "build_seconds": t_depart,
        "search_seconds": total - t_depart,
        "first_feasible_seconds": t_depart,
        # --- informations supplémentaires (le runner les ignore ; utiles pour l'analyse) ---
        "origine_depart": origine,
        "criteres_depart": f_depart,
        "criteres_final": f_final,
        "stats": stats,
        "archive": archive.vecteurs(),
    }
