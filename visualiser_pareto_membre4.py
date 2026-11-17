
import csv
import os
from itertools import combinations

import matplotlib.pyplot as plt


# ============================================================
# CONFIGURATION
# ============================================================

FICHIER_PARETO = os.path.join(
    "analyses_membre4",
    "fronts_pareto.csv"
)

DOSSIER_GRAPHIQUES = os.path.join(
    "analyses_membre4",
    "graphiques_pareto"
)

CRITERES = {
    "teacher_presence_days": "Jours de présence des enseignants",
    "teacher_idle_slots": "Créneaux d'attente des enseignants",
    "teacher_load_range": "Écart de charge des enseignants",
    "supervisor_group_breaks": "Ruptures des groupes de superviseurs",
    "distinct_jury_pairs": "Paires de jurys distinctes"
}


# ============================================================
# LECTURE DU FRONT DE PARETO
# ============================================================

def lire_front_pareto():

    if not os.path.exists(FICHIER_PARETO):
        raise FileNotFoundError(
            f"Fichier introuvable : {FICHIER_PARETO}"
        )

    with open(
        FICHIER_PARETO,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as fichier:

        lecteur = csv.DictReader(fichier)
        donnees = list(lecteur)

    if not donnees:
        print(
            "Aucune solution Pareto disponible. "
            "Les graphiques seront produits lorsque "
            "les résultats expérimentaux seront présents."
        )
        return []

    for critere in CRITERES:
        if critere not in lecteur.fieldnames:
            raise ValueError(
                f"Colonne manquante dans le CSV : {critere}"
            )

    return donnees


# ============================================================
# PREPARATION DES DONNEES
# ============================================================

def convertir_donnees(donnees):

    donnees_converties = []

    for ligne in donnees:

        try:
            solution = {
                "instance_id": ligne["instance_id"],
                "method": ligne["method"],
                "seed": ligne["seed"]
            }

            for critere in CRITERES:
                solution[critere] = float(ligne[critere])

            donnees_converties.append(solution)

        except (ValueError, KeyError, TypeError):
            print(
                "Une ligne incorrecte a été ignorée :",
                ligne
            )

    return donnees_converties


# ============================================================
# CREATION DES GRAPHIQUES
# ============================================================

def creer_graphiques(donnees):

    os.makedirs(
        DOSSIER_GRAPHIQUES,
        exist_ok=True
    )

    # Cinq critères donnent dix combinaisons possibles.
    combinaisons = list(
        combinations(CRITERES.keys(), 2)
    )

    instances = sorted({
        ligne["instance_id"]
        for ligne in donnees
    })

    for instance in instances:

        solutions = [
            ligne for ligne in donnees
            if ligne["instance_id"] == instance
        ]

        print(
            f"\nCréation des graphiques pour {instance}..."
        )

        for critere_x, critere_y in combinaisons:

            valeurs_x = [
                solution[critere_x]
                for solution in solutions
            ]

            valeurs_y = [
                solution[critere_y]
                for solution in solutions
            ]

            plt.figure(figsize=(9, 6))

            plt.scatter(
                valeurs_x,
                valeurs_y,
                s=80,
                alpha=0.8
            )

            # Identification des solutions
            for solution in solutions:

                etiquette = (
                    f"{solution['method']}"
                    f" / seed {solution['seed']}"
                )

                plt.annotate(
                    etiquette,
                    (
                        solution[critere_x],
                        solution[critere_y]
                    ),
                    fontsize=7,
                    xytext=(5, 5),
                    textcoords="offset points"
                )

            plt.xlabel(CRITERES[critere_x])
            plt.ylabel(CRITERES[critere_y])

            plt.title(
                f"Front de Pareto - {instance}\n"
                f"{CRITERES[critere_x]} "
                f"et {CRITERES[critere_y]}"
            )

            plt.grid(True, alpha=0.3)
            plt.tight_layout()

            nom_fichier = (
                f"{instance}_{critere_x}_{critere_y}.png"
            )

            chemin = os.path.join(
                DOSSIER_GRAPHIQUES,
                nom_fichier
            )

            plt.savefig(
                chemin,
                dpi=300,
                bbox_inches="tight"
            )

            plt.close()

            print(f"Graphique enregistré : {chemin}")


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

def main():

    print("\n===== VISUALISATION DU FRONT DE PARETO =====")

    donnees = lire_front_pareto()

    if not donnees:
        return

    donnees = convertir_donnees(donnees)

    if not donnees:
        print("Aucune donnée numérique exploitable.")
        return

    creer_graphiques(donnees)

    print("\nVisualisation terminée.")


if __name__ == "__main__":
    main()
