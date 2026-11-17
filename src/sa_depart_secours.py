"""
sa_depart_secours.py  --  planning de départ "de dépannage".

Le VRAI planning de départ doit venir du glouton (src/greedy.py, tâche d'un autre membre).
Ce fichier ne sert que si greedy.py est absent ou échoue : il construit un planning valide
(sans chercher à être bon) pour que le recuit puisse tourner et être testé dès maintenant.

Méthode : "le plus contraint d'abord" + tirages au hasard.
  - on traite d'abord les étudiants qui ont le moins de créneaux possibles ;
  - pour chacun : on essaie des duos (en commençant par ceux déjà utilisés -> peu de duos
    distincts), et pour chaque duo on cherche une finale puis une pré-soutenance libres ;
  - si un étudiant ne peut pas être placé, on recommence avec un autre ordre (jusqu'à la limite de temps).
"""
import time
from sa_etat import Etat


def _placer(etat, sid, rng):
    duos = list(etat.duos_domaine(etat.domaine[sid]))
    rng.shuffle(duos)
    # duos déjà utilisés en premier (tri stable : l'aléatoire reste à l'intérieur de chaque groupe)
    duos.sort(key=lambda d: 0 if d in etat.compte_duo else 1)
    pos_pre = list(etat.cand_pre[sid])
    rng.shuffle(pos_pre)
    if etat.eligible[sid]:
        pos_fin = [(j, s, r) for (j, s) in etat.cand_fin[sid] for r in etat.salles_ids]
        rng.shuffle(pos_fin)
    essais = 0
    for duo in duos:
        if not etat.duo_valide(sid, duo):
            continue
        essais += 1
        if essais > 150:
            break
        fin = None
        if etat.eligible[sid]:
            fin = next((p for p in pos_fin if etat.ok_fin(sid, duo, *p)), None)
            if fin is None:
                continue
        pre = next((p for p in pos_pre if etat.ok_pre(sid, duo, *p)), None)
        if pre is None:
            continue
        etat.duo[sid] = duo
        etat.poser_pre(sid, *pre)
        if fin is not None:
            etat.poser_fin(sid, *fin)
        return True
    return False


def construire(instance, rng, echeance):
    """Renvoie un Etat complet et valide, ou None si l'échéance (time.perf_counter) est dépassée."""
    etat = Etat(instance)
    tentative = 0
    while time.perf_counter() < echeance:
        etat.vider()
        ordre = sorted(etat.etu_ids,
                       key=lambda s: (0 if etat.eligible[s] else 1,
                                      len(etat.cand_pre[s]) + len(etat.cand_fin.get(s, ())),
                                      rng.random()))
        if tentative > 0:                       # après un échec : on mélange un peu l'ordre
            for i in range(len(ordre) - 1):
                if rng.random() < 0.15:
                    ordre[i], ordre[i + 1] = ordre[i + 1], ordre[i]
        if all(_placer(etat, sid, rng) for sid in ordre):
            return etat
        tentative += 1
    return None
