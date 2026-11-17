"""
sa_etat.py  --  L7 : représentation d'un planning pour le recuit simulé.

Un `Etat` est un planning "vivant" : on peut POSER ou RETIRER une séance, et
l'objet met à jour tout seul
  * les agendas des enseignants et des salles (pour tester les conflits),
  * les 5 critères f1..f5 (sans jamais tout recalculer).

Principe de sécurité : on ne pose une séance que si `ok_pre` / `ok_fin` dit OUI.
Donc un Etat construit uniquement par ces méthodes est TOUJOURS valide.

Représentation (3 dictionnaires, indexés par l'identifiant de l'étudiant) :
    duo[sid]  = (id_président, id_examinateur)      <- le même pour les 2 phases
    pre[sid]  = (jour, créneau)                      <- pré-soutenance (en ligne)
    fin[sid]  = (jour, créneau, salle)               <- finale (seulement si éligible)
"""
from collections import Counter


class PlanningInvalide(ValueError):
    """Levée quand un planning chargé ne respecte pas les règles."""


# --------------------------------------------------------------------------
# Petites fonctions utilitaires
# --------------------------------------------------------------------------
def ensemble_dispos(availability):
    """[{"day":0,"slots":[0,1]}, ...]  ->  {(0,0), (0,1), ...}  (test d'appartenance instantané)."""
    return {(bloc["day"], s) for bloc in availability for s in bloc["slots"]}


def _trous(slots):
    """Créneaux 'perdus' entre le premier et le dernier d'une journée (critère f2 pour 1 jour)."""
    return max(slots) - min(slots) + 1 - len(slots)


def _nb_groupes(slots):
    """Nombre de blocs de créneaux consécutifs dans un ensemble d'entiers. {1,2,3,6,7} -> 2."""
    return sum(1 for s in slots if (s - 1) not in slots)


# --------------------------------------------------------------------------
# La classe principale
# --------------------------------------------------------------------------
class Etat:
    def __init__(self, instance):
        self.instance = instance
        self.jours_pre = set(instance["predefence_days"])
        self.jours_fin = set(instance["final_defence_days"])

        # ---- données statiques sur les enseignants -------------------------
        ens = instance["teachers"]
        self.ens_ids = [t["id"] for t in ens]
        self.dispo_ens = {t["id"]: ensemble_dispos(t["availability"]) for t in ens}
        self.cap_ens = {t["id"]: t["max_sessions_per_day"] for t in ens}
        self.peut_presider = {t["id"] for t in ens if "president" in t["eligible_roles"]}
        self.peut_examiner = {t["id"] for t in ens if "examiner" in t["eligible_roles"]}
        self.domaines_ens = {t["id"]: set(t["domains"]) for t in ens}

        # ---- salles -------------------------------------------------------
        self.salles_ids = [r["id"] for r in instance["rooms"]]
        self.dispo_salle = {r["id"]: ensemble_dispos(r["availability"]) for r in instance["rooms"]}
        self.cap_salle = {r["id"]: r["max_sessions_per_day"] for r in instance["rooms"]}

        # ---- étudiants ----------------------------------------------------
        etus = instance["students"]
        self.etu_ids = [e["id"] for e in etus]
        self.eligible = {e["id"]: e["eligible_final"] for e in etus}
        self.eligibles_ids = [e["id"] for e in etus if e["eligible_final"]]
        self.encadrant = {e["id"]: e["supervisor_id"] for e in etus}
        self.domaine = {e["id"]: e["domain"] for e in etus}
        self.dispo_etu = {e["id"]: ensemble_dispos(e["availability"]) for e in etus}
        # Positions (jour, créneau) où l'étudiant est libre ET qui sont dans la bonne période
        self.cand_pre = {sid: sorted(p for p in self.dispo_etu[sid] if p[0] in self.jours_pre)
                         for sid in self.etu_ids}
        self.cand_fin = {sid: sorted(p for p in self.dispo_etu[sid] if p[0] in self.jours_fin)
                         for sid in self.eligibles_ids}

        self._duos_par_domaine = {}   # cache : domaine -> tous les duos (p, e) possibles
        self.vider()

    # ======================================================================
    # État dynamique
    # ======================================================================
    def vider(self):
        """Planning vide : aucune séance posée."""
        self.duo, self.pre, self.fin = {}, {}, {}
        self.ens_jour = {}        # (enseignant, jour) -> ensemble de créneaux occupés
        self.flux = {}            # (salle, jour)      -> {créneau: encadrant}  (occupation des salles)
        self.charge = {t: 0 for t in self.ens_ids}   # nb de séances par enseignant (f3)
        self.compte_duo = {}      # (p, e) -> nb de pré-soutenances qui l'utilisent (f5)
        self.nb_duos = 0
        self.f1 = 0
        self.f2 = 0
        # --- pour f4 (ruptures d'encadrant) ---
        self.pre_cnt = {}         # (encadrant, jour, créneau) -> nb de pré-soutenances
        self.pre_slots = {}       # (encadrant, jour) -> ensemble de créneaux (distincts)
        self.flux_contrib = {}    # (salle, jour) -> Counter(encadrant -> nb de groupes)
        self.groupes = {}         # (encadrant, phase) -> nb de groupes
        self.total_groupes = 0
        self.nb_cles_groupes = 0  # nb de (encadrant, phase) ayant au moins 1 groupe

    # ---------------- les 5 critères ----------------
    def criteres(self):
        """(f1, f2, f3, f4, f5) -- exactement ceux du validateur."""
        c = self.charge.values()
        f3 = max(c) - min(c)
        f4 = self.total_groupes - self.nb_cles_groupes
        return (self.f1, self.f2, f3, f4, self.nb_duos)

    # ---------------- mise à jour interne des agendas ----------------
    def _ens_ajouter(self, t, jour, slot):
        cle = (t, jour)
        s = self.ens_jour.get(cle)
        if s is None:
            s = self.ens_jour[cle] = set()
            self.f1 += 1                       # nouvelle présence (enseignant, jour)
        else:
            self.f2 -= _trous(s)
        s.add(slot)
        self.f2 += _trous(s)
        self.charge[t] += 1

    def _ens_retirer(self, t, jour, slot):
        cle = (t, jour)
        s = self.ens_jour[cle]
        self.f2 -= _trous(s)
        s.remove(slot)
        if s:
            self.f2 += _trous(s)
        else:
            del self.ens_jour[cle]
            self.f1 -= 1
        self.charge[t] -= 1

    def _ajuster_groupes(self, sup, phase, delta):
        cle = (sup, phase)
        avant = self.groupes.get(cle, 0)
        apres = avant + delta
        self.groupes[cle] = apres
        self.total_groupes += delta
        if avant == 0 and apres > 0:
            self.nb_cles_groupes += 1
        elif avant > 0 and apres == 0:
            self.nb_cles_groupes -= 1

    def _pre_sup_ajouter(self, sup, jour, slot):
        k = (sup, jour, slot)
        self.pre_cnt[k] = self.pre_cnt.get(k, 0) + 1
        if self.pre_cnt[k] == 1:               # premier étudiant de cet encadrant à ce créneau
            s = self.pre_slots.setdefault((sup, jour), set())
            avant = _nb_groupes(s)
            s.add(slot)
            self._ajuster_groupes(sup, "predefence", _nb_groupes(s) - avant)

    def _pre_sup_retirer(self, sup, jour, slot):
        k = (sup, jour, slot)
        self.pre_cnt[k] -= 1
        if self.pre_cnt[k] == 0:
            del self.pre_cnt[k]
            s = self.pre_slots[(sup, jour)]
            avant = _nb_groupes(s)
            s.remove(slot)
            self._ajuster_groupes(sup, "predefence", _nb_groupes(s) - avant)
            if not s:
                del self.pre_slots[(sup, jour)]

    def _flux_maj(self, salle, jour, slot, sup, ajout):
        cle = (salle, jour)
        flux = self.flux.setdefault(cle, {})
        if ajout:
            flux[slot] = sup
        else:
            del flux[slot]
        # on recalcule les groupes de CE flux (salle, jour) seulement : au plus ~10 créneaux
        nouveau = Counter()
        prev_sup, prev_fin = None, None
        for s in sorted(flux):
            if prev_sup != flux[s] or prev_fin != s:
                nouveau[flux[s]] += 1
            prev_sup, prev_fin = flux[s], s + 1
        for sup_, n in self.flux_contrib.get(cle, {}).items():
            self._ajuster_groupes(sup_, "final", -n)
        for sup_, n in nouveau.items():
            self._ajuster_groupes(sup_, "final", n)
        if flux:
            self.flux_contrib[cle] = nouveau
        else:
            del self.flux[cle]
            self.flux_contrib.pop(cle, None)

    # ======================================================================
    # POSER / RETIRER une séance  (opérations de base, sans aucun test)
    # ======================================================================
    def poser_pre(self, sid, jour, slot):
        p, e = self.duo[sid]
        self.pre[sid] = (jour, slot)
        self._ens_ajouter(p, jour, slot)
        self._ens_ajouter(e, jour, slot)
        n = self.compte_duo.get((p, e), 0)
        self.compte_duo[(p, e)] = n + 1
        if n == 0:
            self.nb_duos += 1
        self._pre_sup_ajouter(self.encadrant[sid], jour, slot)

    def retirer_pre(self, sid):
        jour, slot = self.pre.pop(sid)
        p, e = self.duo[sid]
        self._ens_retirer(p, jour, slot)
        self._ens_retirer(e, jour, slot)
        self.compte_duo[(p, e)] -= 1
        if self.compte_duo[(p, e)] == 0:
            del self.compte_duo[(p, e)]
            self.nb_duos -= 1
        self._pre_sup_retirer(self.encadrant[sid], jour, slot)

    def poser_fin(self, sid, jour, slot, salle):
        p, e = self.duo[sid]
        sup = self.encadrant[sid]
        self.fin[sid] = (jour, slot, salle)
        for t in (p, e, sup):
            self._ens_ajouter(t, jour, slot)
        self._flux_maj(salle, jour, slot, sup, True)

    def retirer_fin(self, sid):
        jour, slot, salle = self.fin.pop(sid)
        p, e = self.duo[sid]
        sup = self.encadrant[sid]
        for t in (p, e, sup):
            self._ens_retirer(t, jour, slot)
        self._flux_maj(salle, jour, slot, sup, False)

    # ======================================================================
    # TESTS DE VALIDITÉ  (ne modifient rien)
    # ======================================================================
    def duo_valide(self, sid, duo):
        """Le duo (p, e) est-il admissible pour cet étudiant ? (rôles, domaine, distincts, encadrant)"""
        p, e = duo
        if p == e or p not in self.peut_presider or e not in self.peut_examiner:
            return False
        if self.domaine[sid] not in self.domaines_ens[e]:
            return False
        if self.eligible[sid] and self.encadrant[sid] in duo:
            return False          # l'encadrant est rapporteur en finale : il ne peut pas être p ou e
        return True

    def _enseignant_libre(self, t, jour, slot):
        if (jour, slot) not in self.dispo_ens[t]:
            return False
        s = self.ens_jour.get((t, jour))
        return s is None or (slot not in s and len(s) < self.cap_ens[t])

    def ok_pre(self, sid, duo, jour, slot):
        """Peut-on poser la pré-soutenance de `sid` avec ce duo à (jour, slot) ?"""
        if jour not in self.jours_pre or (jour, slot) not in self.dispo_etu[sid]:
            return False
        return (self._enseignant_libre(duo[0], jour, slot)
                and self._enseignant_libre(duo[1], jour, slot))

    def ok_fin(self, sid, duo, jour, slot, salle):
        """Peut-on poser la finale de `sid` avec ce duo à (jour, slot, salle) ?"""
        if jour not in self.jours_fin or (jour, slot) not in self.dispo_etu[sid]:
            return False
        if (jour, slot) not in self.dispo_salle[salle]:
            return False
        occ = self.flux.get((salle, jour))
        if occ is not None and (slot in occ or len(occ) >= self.cap_salle[salle]):
            return False
        return (self._enseignant_libre(duo[0], jour, slot)
                and self._enseignant_libre(duo[1], jour, slot)
                and self._enseignant_libre(self.encadrant[sid], jour, slot))

    # ======================================================================
    # Duos possibles
    # ======================================================================
    def duos_domaine(self, domaine):
        """Tous les duos (p, e) où e couvre le domaine (sans tenir compte de l'encadrant)."""
        if domaine not in self._duos_par_domaine:
            pres = [t for t in self.ens_ids if t in self.peut_presider]
            exas = [t for t in self.ens_ids if t in self.peut_examiner and domaine in self.domaines_ens[t]]
            self._duos_par_domaine[domaine] = [(p, e) for p in pres for e in exas if p != e]
        return self._duos_par_domaine[domaine]

    def duo_au_hasard(self, sid, rng):
        """Un duo admissible tiré au hasard (None si aucun n'existe)."""
        liste = self.duos_domaine(self.domaine[sid])
        if not liste:
            return None
        for _ in range(20):
            d = rng.choice(liste)
            if self.duo_valide(sid, d):
                return d
        valides = [d for d in liste if self.duo_valide(sid, d)]
        return rng.choice(valides) if valides else None

    # ======================================================================
    # Photos (pour annuler un mouvement) et copies
    # ======================================================================
    def releve(self, sids):
        """Photo de l'état de quelques étudiants : [(sid, duo, pre, fin_ou_None), ...]."""
        return [(sid, self.duo[sid], self.pre[sid], self.fin.get(sid)) for sid in sids]

    def reposer(self, photo):
        """Remet ces étudiants EXACTEMENT comme dans la photo (annule un mouvement)."""
        for sid, _, _, _ in photo:
            if sid in self.pre:
                self.retirer_pre(sid)
            if sid in self.fin:
                self.retirer_fin(sid)
        for sid, duo, pre, fin in photo:
            self.duo[sid] = duo
            self.poser_pre(sid, *pre)
            if fin is not None:
                self.poser_fin(sid, *fin)

    def snapshot(self):
        """Copie légère du planning entier (les tuples sont immuables : copie de dict suffit)."""
        return (dict(self.duo), dict(self.pre), dict(self.fin))

    # ======================================================================
    # Conversion  JSON <-> Etat
    # ======================================================================
    def charger_solution(self, solution):
        """
        Remplit l'état à partir d'une solution JSON (ex : celle du glouton).
        Lève PlanningInvalide si une règle est violée -> on ne reçoit jamais de planning faux.
        """
        self.vider()
        pre_s, fin_s = {}, {}
        for s in solution.get("sessions", []):
            if s["student_id"] not in self.eligible:
                raise PlanningInvalide(f"étudiant inconnu : {s['student_id']}")
            cible = pre_s if s["phase"] == "predefence" else fin_s
            if s["student_id"] in cible:
                raise PlanningInvalide(f"{s['student_id']} : deux séances en phase {s['phase']}")
            cible[s["student_id"]] = s
        for sid in self.etu_ids:
            if sid not in pre_s:
                raise PlanningInvalide(f"{sid} : pas de pré-soutenance")
            if (sid in fin_s) != self.eligible[sid]:
                raise PlanningInvalide(f"{sid} : finale manquante ou interdite")
            a = pre_s[sid]
            duo = (a["president_id"], a["examiner_id"])
            if sid in fin_s and (fin_s[sid]["president_id"], fin_s[sid]["examiner_id"]) != duo:
                raise PlanningInvalide(f"{sid} : continuité président/examinateur violée")
            if not self.duo_valide(sid, duo):
                raise PlanningInvalide(f"{sid} : duo non admissible {duo}")
            self.duo[sid] = duo
            if not self.ok_pre(sid, duo, a["day"], a["slot"]):
                raise PlanningInvalide(f"{sid} : pré-soutenance impossible à ({a['day']},{a['slot']})")
            self.poser_pre(sid, a["day"], a["slot"])
            if sid in fin_s:
                b = fin_s[sid]
                if b["room_id"] is None or b["room_id"] not in self.dispo_salle:
                    raise PlanningInvalide(f"{sid} : salle inconnue")
                if not self.ok_fin(sid, duo, b["day"], b["slot"], b["room_id"]):
                    raise PlanningInvalide(f"{sid} : finale impossible à ({b['day']},{b['slot']},{b['room_id']})")
                self.poser_fin(sid, b["day"], b["slot"], b["room_id"])
        return self

    def en_solution(self, snapshot=None):
        """Construit le dictionnaire JSON (schéma 4.0). Sans argument : l'état courant."""
        duo, pre, fin = snapshot if snapshot is not None else (self.duo, self.pre, self.fin)
        sessions = []
        for sid, (j, s) in pre.items():
            sessions.append({"student_id": sid, "phase": "predefence", "day": j, "slot": s,
                             "room_id": None, "president_id": duo[sid][0], "examiner_id": duo[sid][1]})
        for sid, (j, s, salle) in fin.items():
            sessions.append({"student_id": sid, "phase": "final", "day": j, "slot": s,
                             "room_id": salle, "president_id": duo[sid][0], "examiner_id": duo[sid][1]})
        sessions.sort(key=lambda x: (x["phase"] != "predefence", x["day"], x["slot"], x["student_id"]))
        return {"schema_version": self.instance["schema_version"],
                "instance_id": self.instance["instance_id"],
                "sessions": sessions}

    def complet(self):
        """Tous les étudiants ont-ils leurs séances ?"""
        return len(self.pre) == len(self.etu_ids) and len(self.fin) == len(self.eligibles_ids)
