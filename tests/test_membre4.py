
import sys
import unittest
from pathlib import Path

# Chemin du dossier principal du projet
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from validator import load_json, validate_solution


class TestsMembre4(unittest.TestCase):

    def setUp(self):
        """
        Charger une nouvelle instance et une nouvelle solution
        avant chaque test pour éviter les modifications cumulées.
        """
        self.instance = load_json(
            ROOT / "examples" / "demo_instance.json"
        )
        self.solution = load_json(
            ROOT / "examples" / "demo_solution.json"
        )

    # --------------------------------------------------
    # TEST 1 : Rôle incompatible
    # --------------------------------------------------
    def test_role_incompatible(self):
        session = self.solution["sessions"][0]

        examinateur_id = session["examiner_id"]

        examinateur = next(
            t for t in self.instance["teachers"]
            if t["id"] == examinateur_id
        )

        # L'enseignant est uniquement habilité comme président
        examinateur["eligible_roles"] = ["president"]

        resultat = validate_solution(self.instance, self.solution)

        self.assertFalse(resultat["valid"])
        self.assertTrue(
            any("is not eligible as examiner" in e
                for e in resultat["errors"]),
            resultat["errors"]
        )

    # --------------------------------------------------
    # TEST 2 : Encadrant également membre du jury
    # --------------------------------------------------
    def test_jury_membres_non_distincts(self):
        session = next(
            s for s in self.solution["sessions"]
            if s["phase"] == "final"
        )

        etudiant = next(
            e for e in self.instance["students"]
            if e["id"] == session["student_id"]
        )

        # L'encadrant devient aussi examinateur
        session["examiner_id"] = etudiant["supervisor_id"]

        resultat = validate_solution(self.instance, self.solution)

        self.assertFalse(resultat["valid"])
        self.assertTrue(
            any("jury members must be distinct" in e
                for e in resultat["errors"]),
            resultat["errors"]
        )

    # --------------------------------------------------
    # TEST 3 : Chevauchement de deux soutenances
    # --------------------------------------------------
    def test_chevauchement(self):
        finales = [
            s for s in self.solution["sessions"]
            if s["phase"] == "final"
        ]

        self.assertGreaterEqual(len(finales), 2)

        premiere = finales[0]
        deuxieme = finales[1]

        # Placer les deux finales au même créneau
        deuxieme["day"] = premiere["day"]
        deuxieme["slot"] = premiere["slot"]

        resultat = validate_solution(self.instance, self.solution)

        self.assertFalse(resultat["valid"])
        self.assertTrue(
            any("overlap" in e for e in resultat["errors"]),
            resultat["errors"]
        )

    # --------------------------------------------------
    # TEST 4 : Salle attribuée à une pré-soutenance
    # --------------------------------------------------
    def test_salle_interdite_predefence(self):
        session = next(
            s for s in self.solution["sessions"]
            if s["phase"] == "predefence"
        )

        session["room_id"] = self.instance["rooms"][0]["id"]

        resultat = validate_solution(self.instance, self.solution)

        self.assertFalse(resultat["valid"])
        self.assertTrue(
            any("must be null for online predefence" in e
                for e in resultat["errors"]),
            resultat["errors"]
        )

    # --------------------------------------------------
    # TEST 5 : Domaine incorrect de l'examinateur
    # --------------------------------------------------
    def test_domaine_examinateur_incorrect(self):
        # Ajouter un nouveau domaine à l'instance
        self.instance["domains"].append("AUTRE")

        # Modifier le domaine du premier étudiant
        self.instance["students"][0]["domain"] = "AUTRE"

        resultat = validate_solution(self.instance, self.solution)

        self.assertFalse(resultat["valid"])
        self.assertTrue(
            any("examiner does not cover student domain" in e
                for e in resultat["errors"]),
            resultat["errors"]
        )

    # --------------------------------------------------
    # TEST 6 : Enseignant indisponible
    # --------------------------------------------------
    def test_indisponibilite_enseignant(self):
        session = self.solution["sessions"][0]

        enseignant_id = session["president_id"]

        enseignant = next(
            t for t in self.instance["teachers"]
            if t["id"] == enseignant_id
        )

        # Rendre cet enseignant indisponible
        enseignant["availability"] = []

        resultat = validate_solution(self.instance, self.solution)

        self.assertFalse(resultat["valid"])
        self.assertTrue(
            any("unavailable for whole session" in e
                for e in resultat["errors"]),
            resultat["errors"]
        )

    # --------------------------------------------------
    # TEST 7 : Dépassement du plafond journalier
    # --------------------------------------------------
    def test_plafond_journalier_depasse(self):
        # ENS-A intervient plusieurs fois dans la démonstration
        enseignant = next(
            t for t in self.instance["teachers"]
            if t["id"] == "ENS-A"
        )

        # Limiter son nombre de séances à une par jour
        enseignant["max_sessions_per_day"] = 1

        resultat = validate_solution(self.instance, self.solution)

        self.assertFalse(resultat["valid"])
        self.assertTrue(
            any("daily cap exceeded" in e
                for e in resultat["errors"]),
            resultat["errors"]
        )

    # --------------------------------------------------
    # TEST 8 : Jour hors période autorisée
    # --------------------------------------------------
    def test_jour_hors_periode(self):
        session = next(
            s for s in self.solution["sessions"]
            if s["phase"] == "predefence"
        )

        # Les pré-soutenances sont autorisées uniquement au jour 0
        session["day"] = 1

        resultat = validate_solution(self.instance, self.solution)

        self.assertFalse(resultat["valid"])
        self.assertTrue(
            any("outside its common phase period" in e
                for e in resultat["errors"]),
            resultat["errors"]
        )

    # --------------------------------------------------
    # TEST 9 : Rupture de continuité du jury
    # --------------------------------------------------
    def test_rupture_continuite_jury(self):
        session = next(
            s for s in self.solution["sessions"]
            if s["phase"] == "final"
        )

        # Modifier le président de la soutenance finale
        session["president_id"] = "ENS-D"

        resultat = validate_solution(self.instance, self.solution)

        self.assertFalse(resultat["valid"])
        self.assertTrue(
            any("president/examiner continuity violated" in e
                for e in resultat["errors"]),
            resultat["errors"]
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
