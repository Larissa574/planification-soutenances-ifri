"""
sa_voisinages.py  --  L7 : les "petits pas" du recuit simulé.

Un voisinage est une fonction  mouvement(etat, rng)  qui essaie de modifier légèrement le planning.

  * Si le nouveau planning est VALIDE : le mouvement est appliqué et la fonction renvoie
    une "photo" de l'état d'AVANT (pour pouvoir annuler si le recuit refuse le mouvement).
  * Sinon : l'état est laissé exactement comme avant et la fonction renvoie None.

Technique utilisée dans tous les mouvements :  RETIRER -> TESTER -> POSER (ou REMETTRE).
On retire d'abord la séance (sinon elle se bloquerait elle-même), on teste la nouvelle
position, puis on la pose si c'est permis ; sinon on remet l'ancienne.
"""


# ---------------------------------------------------------------------------
# 1. Déplacer une séance (même jury, autre jour/créneau/salle)
# ---------------------------------------------------------------------------
def deplacer(etat, rng):
    sid = rng.choice(etat.etu_ids)
    if etat.eligible[sid] and rng.random() < 0.5:                      # --- une finale ---
        jour, slot = rng.choice(etat.cand_fin[sid])
        salle = rng.choice(etat.salles_ids)
        ancien = etat.fin[sid]
        if (jour, slot, salle) == ancien:
            return None
        photo = etat.releve([sid])
        etat.retirer_fin(sid)
        if etat.ok_fin(sid, etat.duo[sid], jour, slot, salle):
            etat.poser_fin(sid, jour, slot, salle)
            return photo
        etat.poser_fin(sid, *ancien)
        return None
    # --- une pré-soutenance ---
    jour, slot = rng.choice(etat.cand_pre[sid])
    ancien = etat.pre[sid]
    if (jour, slot) == ancien:
        return None
    photo = etat.releve([sid])
    etat.retirer_pre(sid)
    if etat.ok_pre(sid, etat.duo[sid], jour, slot):
        etat.poser_pre(sid, jour, slot)
        return photo
    etat.poser_pre(sid, *ancien)
    return None


# ---------------------------------------------------------------------------
# 2. Échanger les positions de deux étudiants (même phase)
# ---------------------------------------------------------------------------
def echanger(etat, rng):
    en_finale = len(etat.eligibles_ids) >= 2 and rng.random() < 0.5
    a, b = rng.sample(etat.eligibles_ids if en_finale else etat.etu_ids, 2)
    photo = etat.releve([a, b])

    if en_finale:
        pa, pb = etat.fin[a], etat.fin[b]
        # test rapide : chacun doit être libre à la place de l'autre
        if (pb[0], pb[1]) not in etat.dispo_etu[a] or (pa[0], pa[1]) not in etat.dispo_etu[b]:
            return None
        etat.retirer_fin(a)
        etat.retirer_fin(b)
        if etat.ok_fin(a, etat.duo[a], *pb):
            etat.poser_fin(a, *pb)
            if etat.ok_fin(b, etat.duo[b], *pa):     # b est testé APRÈS la pose de a
                etat.poser_fin(b, *pa)
                return photo
            etat.retirer_fin(a)
        etat.poser_fin(a, *pa)
        etat.poser_fin(b, *pb)
        return None

    pa, pb = etat.pre[a], etat.pre[b]
    if pa == pb or pb not in etat.dispo_etu[a] or pa not in etat.dispo_etu[b]:
        return None
    etat.retirer_pre(a)
    etat.retirer_pre(b)
    if etat.ok_pre(a, etat.duo[a], *pb):
        etat.poser_pre(a, *pb)
        if etat.ok_pre(b, etat.duo[b], *pa):
            etat.poser_pre(b, *pa)
            return photo
        etat.retirer_pre(a)
    etat.poser_pre(a, *pa)
    etat.poser_pre(b, *pb)
    return None


# ---------------------------------------------------------------------------
# 3. Changer le duo (président, examinateur) d'un étudiant -- pour LES DEUX phases
# ---------------------------------------------------------------------------
def changer_duo(etat, rng):
    sid = rng.choice(etat.etu_ids)
    ancien = etat.duo[sid]
    mode = rng.random()
    if mode < 0.4:                       # copier le duo d'un autre étudiant -> moins de duos distincts (f5)
        nouveau = etat.duo[rng.choice(etat.etu_ids)]
    elif mode < 0.8:                     # ne changer qu'UN membre du duo
        autre = etat.duo_au_hasard(sid, rng)
        if autre is None:
            return None
        nouveau = (autre[0], ancien[1]) if rng.random() < 0.5 else (ancien[0], autre[1])
    else:                                # duo entièrement nouveau
        nouveau = etat.duo_au_hasard(sid, rng)
        if nouveau is None:
            return None
    if nouveau == ancien or not etat.duo_valide(sid, nouveau):
        return None

    photo = etat.releve([sid])
    pre, fin = etat.pre[sid], etat.fin.get(sid)
    etat.retirer_pre(sid)
    if fin is not None:
        etat.retirer_fin(sid)
    # pré et finale sont sur des jours différents : on peut tester les deux avant de poser
    if etat.ok_pre(sid, nouveau, *pre) and (fin is None or etat.ok_fin(sid, nouveau, *fin)):
        etat.duo[sid] = nouveau
        etat.poser_pre(sid, *pre)
        if fin is not None:
            etat.poser_fin(sid, *fin)
        return photo
    etat.poser_pre(sid, *pre)            # duo[sid] n'a pas changé : on remet comme avant
    if fin is not None:
        etat.poser_fin(sid, *fin)
    return None


# ---------------------------------------------------------------------------
# 4. Changer la salle d'une finale (même jour, même créneau)
# ---------------------------------------------------------------------------
def changer_salle(etat, rng):
    if not etat.eligibles_ids or len(etat.salles_ids) < 2:
        return None
    sid = rng.choice(etat.eligibles_ids)
    jour, slot, ancienne = etat.fin[sid]
    salle = rng.choice(etat.salles_ids)
    if salle == ancienne:
        return None
    photo = etat.releve([sid])
    etat.retirer_fin(sid)
    if etat.ok_fin(sid, etat.duo[sid], jour, slot, salle):
        etat.poser_fin(sid, jour, slot, salle)
        return photo
    etat.poser_fin(sid, jour, slot, ancienne)
    return None


# (mouvement, poids de tirage)
MOUVEMENTS = [(deplacer, 35), (echanger, 20), (changer_duo, 30), (changer_salle, 15)]


def tirer_mouvement(rng, mouvements=None):
    mouvements = mouvements or MOUVEMENTS
    fonctions = [m[0] for m in mouvements]
    poids = [m[1] for m in mouvements]
    return rng.choices(fonctions, weights=poids, k=1)[0]
