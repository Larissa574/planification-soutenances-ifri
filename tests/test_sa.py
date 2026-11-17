"""Tests du recuit simulé (L7 + L8). Lancer depuis la racine du dépôt :  python -m pytest tests/test_sa.py"""
import json
import random
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import validator  # noqa: E402
from sa_depart_secours import construire  # noqa: E402
from sa_etat import Etat, PlanningInvalide  # noqa: E402
from sa_score import ArchivePareto, Evaluateur, domine  # noqa: E402
from sa_voisinages import tirer_mouvement  # noqa: E402
import simulated_annealing as sa  # noqa: E402

CLES = ("teacher_presence_days", "teacher_idle_slots", "teacher_load_range",
        "supervisor_group_breaks", "distinct_jury_pairs")


def charger(chemin):
    return json.loads((ROOT / chemin).read_text(encoding="utf-8"))


def f_validateur(instance, solution):
    """Les 5 critères selon le validateur officiel (None si planning invalide)."""
    res = validator.validate_solution(instance, solution)
    if not res["valid"]:
        return None
    return tuple(res["metrics"][k] for k in CLES)


@pytest.fixture(scope="module")
def demo():
    return charger("examples/demo_instance.json"), charger("examples/demo_solution.json")


@pytest.fixture(scope="module")
def small():
    return charger("data/small_01.json")


#L7 : état
def test_charger_demo_donne_les_criteres_du_validateur(demo):
    inst, sol = demo
    etat = Etat(inst).charger_solution(sol)
    assert etat.criteres() == (6, 6, 5, 2, 2)
    assert etat.complet()


def test_aller_retour_json_est_valide(demo):
    inst, sol = demo
    sortie = Etat(inst).charger_solution(sol).en_solution()
    assert f_validateur(inst, sortie) == (6, 6, 5, 2, 2)


def test_planning_incomplet_refuse(demo):
    inst, _ = demo
    with pytest.raises(PlanningInvalide):
        Etat(inst).charger_solution(charger("examples/empty_solution.json"))


def test_planning_avec_conflit_refuse(demo):
    inst, sol = demo
    mauvais = json.loads(json.dumps(sol))
    # on met deux séances au même créneau avec le même jury
    mauvais["sessions"][1]["slot"] = mauvais["sessions"][0]["slot"]
    with pytest.raises(PlanningInvalide):
        Etat(inst).charger_solution(mauvais)


def test_reposer_annule_un_mouvement(small):
    rng = random.Random(1)
    etat = construire(small, rng, float("inf"))
    avant, snap = etat.criteres(), etat.snapshot()
    for _ in range(300):
        photo = tirer_mouvement(rng)(etat, rng)
        if photo is not None:
            etat.reposer(photo)
            assert etat.criteres() == avant
            assert etat.snapshot() == snap


#L7 : mouvements gardent la validité
@pytest.mark.parametrize("nom", ["small_01", "small_04", "medium_01"])
def test_mouvements_valides_et_criteres_incrementaux_exacts(nom):
    inst = charger(f"data/{nom}.json")
    rng = random.Random(7)
    etat = construire(inst, rng, float("inf"))
    for i in range(1500):
        photo = tirer_mouvement(rng)(etat, rng)
        if photo is not None and rng.random() < 0.4:
            etat.reposer(photo)                      # on mélange accepté / refusé
        if i % 150 == 0:
            sol = etat.en_solution()
            assert f_validateur(inst, sol) == etat.criteres(), f"écart à l'itération {i}"
    assert f_validateur(inst, etat.en_solution()) == etat.criteres()


#L8 : score, archive
def test_score_vaut_1_au_depart_avec_poids_somme_1():
    ev = Evaluateur((0.2,) * 5, (10, 20, 5, 8, 3))
    assert ev.score((10, 20, 5, 8, 3)) == pytest.approx(1.0)
    assert ev.score((5, 20, 5, 8, 3)) < 1.0


def test_echelle_plancher_1():
    ev = Evaluateur((0.2,) * 5, (0, 0, 0, 0, 0))
    assert ev.echelles == (1, 1, 1, 1, 1)


def test_dominance():
    assert domine((1, 2, 3, 4, 5), (1, 2, 3, 4, 6))
    assert not domine((1, 2, 3, 4, 5), (1, 2, 3, 4, 5))
    assert not domine((1, 9, 3, 4, 5), (2, 2, 3, 4, 5))


def test_archive_ne_garde_que_les_non_domines():
    arch = ArchivePareto(10)
    assert arch.proposer((5, 5, 5, 5, 5), lambda: "A")
    assert arch.proposer((4, 6, 5, 5, 5), lambda: "B")        # incomparable
    assert not arch.proposer((6, 6, 6, 6, 6), lambda: "C")    # dominé par A
    assert arch.proposer((4, 4, 4, 4, 4), lambda: "D")        # domine A et B
    assert arch.vecteurs() == [(4, 4, 4, 4, 4)]


#solve : bout en bout
def test_solve_demo_valide_et_ne_degrade_pas(demo):
    inst, _ = demo
    res = sa.solve(inst, time_limit=2.0, seed=0)
    assert f_validateur(inst, res["solution"]) == tuple(res["criteres_final"])
    assert res["stop_status"] == "FEASIBLE"


def test_solve_small_ameliore_le_depart(small):
    res = sa.solve(small, time_limit=3.0, seed=0)
    assert f_validateur(small, res["solution"]) == tuple(res["criteres_final"])
    ev = Evaluateur(sa.PARAMS["poids"], res["criteres_depart"])
    assert ev.score(res["criteres_final"]) < 1.0


def test_solve_reproductible_avec_la_meme_graine(small):
    # même graine + même nombre d'itérations => même résultat ; on compare à budget identique
    a = sa.solve(small, time_limit=1.5, seed=3)
    b = sa.solve(small, time_limit=1.5, seed=3)
    assert a["criteres_depart"] == b["criteres_depart"]


def test_respect_du_budget_de_temps(small):
    import time
    t = time.perf_counter()
    sa.solve(small, time_limit=2.0, seed=0)
    assert time.perf_counter() - t < 2.0


# branchement du glouton (faux glouton)
def _faux_glouton(monkeypatch, fonction):
    module = types.ModuleType("greedy")
    module.solve = fonction
    monkeypatch.setitem(sys.modules, "greedy", module)


def test_utilise_le_glouton_quand_il_existe(demo, monkeypatch):
    inst, sol = demo
    _faux_glouton(monkeypatch, lambda instance, time_limit, seed: {"solution": sol})
    res = sa.solve(inst, time_limit=1.0, seed=0)
    assert res["origine_depart"] == "glouton"
    assert res["criteres_depart"] == (6, 6, 5, 2, 2)


def test_glouton_au_format_tuple(demo, monkeypatch):
    inst, sol = demo
    _faux_glouton(monkeypatch, lambda instance, time_limit, seed: (sol, "FEASIBLE"))
    assert sa.solve(inst, time_limit=1.0, seed=0)["origine_depart"] == "glouton"


def test_glouton_qui_plante_ou_triche_ne_bloque_pas(demo, monkeypatch):
    inst, sol = demo

    def plante(instance, time_limit, seed):
        raise RuntimeError("bug")
    _faux_glouton(monkeypatch, plante)
    assert sa.solve(inst, time_limit=1.0, seed=0)["origine_depart"] == "secours"

    mauvais = json.loads(json.dumps(sol))
    mauvais["sessions"][1]["slot"] = mauvais["sessions"][0]["slot"]
    _faux_glouton(monkeypatch, lambda instance, time_limit, seed: {"solution": mauvais})
    res = sa.solve(inst, time_limit=1.0, seed=0)
    assert res["origine_depart"] == "secours"
    assert f_validateur(inst, res["solution"]) is not None
