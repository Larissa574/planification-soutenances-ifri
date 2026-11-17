
import csv
import os
from pathlib import Path

# ============================================================
# CONFIGURATION
# ============================================================

DOSSIER_PROJET = Path(__file__).resolve().parent

FICHIER_RESULTATS = os.path.join(
    str(DOSSIER_PROJET),
    "results",
    "resultats.csv"
)

DOSSIER_SORTIE = DOSSIER_PROJET / "analyses_membre4"

FICHIER_VALIDES = DOSSIER_SORTIE / "resultats_valides.csv"
FICHIER_PARETO = DOSSIER_SORTIE / "fronts_pareto.csv"
FICHIER_RAPPORT = DOSSIER_SORTIE / "rapport_analyse.txt"

CRITERES = [
    "teacher_presence_days",
    "teacher_idle_slots",
    "teacher_load_range",
    "supervisor_group_breaks",
    "distinct_jury_pairs",
]

COLONNES_OBLIGATOIRES = [
    "instance_id",
    "method",
    "seed",
    "stop_status",
    "valid",
]

COLONNES_ENTETE = (
    COLONNES_OBLIGATOIRES
    + ["solution_file", "validation_file"]
    + CRITERES
)


# ============================================================
# OUTILS
# ============================================================

def est_valide(valeur):
    """Interprète la valeur de la colonne valid."""
    return str(valeur).strip().lower() in {
        "true", "1", "yes", "oui"
    }


def est_booleen(valeur):
    """Vérifie que la valeur représente un booléen."""
    return str(valeur).strip().lower() in {
        "true", "false", "1", "0",
        "yes", "no", "oui", "non"
    }


def convertir_criteres(ligne):
    """Convertit les cinq critères en nombres."""
    valeurs = {}

    for critere in CRITERES:
        valeurs[critere] = float(ligne[critere])

    return valeurs


# ============================================================
# LECTURE DES RESULTATS
# ============================================================

def lire_resultats():
    if not os.path.exists(FICHIER_RESULTATS):
        print(
            "ERREUR : fichier de résultats introuvable : "
            f"{FICHIER_RESULTATS}"
        )
        return None

    with open(
        FICHIER_RESULTATS,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as fichier:

        lecteur = csv.DictReader(fichier)

        colonnes = lecteur.fieldnames or []

        colonnes_absentes = [
            colonne
            for colonne in COLONNES_ENTETE
            if colonne not in colonnes
        ]

        if colonnes_absentes:
            print("ERREUR : colonnes absentes dans resultats.csv :")

            for colonne in colonnes_absentes:
                print(f"- {colonne}")

            return None

        return list(lecteur)


# ============================================================
# CONTROLE DES RESULTATS
# ============================================================

def controler_resultats(lignes):
    erreurs = []
    resultats_valides = []
    resultats_invalides = []

    for numero, ligne in enumerate(lignes, start=2):

        # Vérification des champs obligatoires
        for colonne in COLONNES_OBLIGATOIRES:
            if not ligne.get(colonne, "").strip():
                erreurs.append(
                    f"Ligne {numero} : champ '{colonne}' manquant."
                )

        # Vérification de la valeur booléenne
        valeur_valid = ligne.get("valid", "")

        if not est_booleen(valeur_valid):
            erreurs.append(
                f"Ligne {numero} : valeur de 'valid' incorrecte."
            )
            continue

        # Traitement d'une solution valide
        if est_valide(ligne.get("valid", "")):

            for colonne in ("solution_file", "validation_file"):
                if not ligne.get(colonne, "").strip():
                    erreurs.append(
                        f"Ligne {numero} : champ '{colonne}' manquant."
                    )

            criteres_corrects = True

            for critere in CRITERES:
                valeur = ligne.get(critere, "").strip()

                if not valeur:
                    erreurs.append(
                        f"Ligne {numero} : critère '{critere}' manquant."
                    )
                    criteres_corrects = False
                    continue

                try:
                    nombre = float(valeur)

                    if nombre < 0 or nombre != nombre:
                        raise ValueError

                except (ValueError, TypeError):
                    erreurs.append(
                        f"Ligne {numero} : critère '{critere}' "
                        "non numérique ou négatif."
                    )
                    criteres_corrects = False

            if criteres_corrects:
                resultats_valides.append(ligne)

        # Traitement d'une solution invalide
        else:
            resultats_invalides.append(ligne)

            # Une exécution invalide peut ne pas avoir de fichiers
            # ni de métriques : cela est autorisé.
            criteres_renseignes = [
                critere
                for critere in CRITERES
                if ligne.get(critere, "").strip()
            ]

            if criteres_renseignes:
                erreurs.append(
                    f"Ligne {numero} : une solution invalide "
                    "contient des métriques renseignées."
                )

    return resultats_valides, resultats_invalides, erreurs


# ============================================================
# DOMINANCE DE PARETO
# ============================================================

def domine(solution_a, solution_b):
    """
    A domine B si :
    - A n'est moins bonne sur aucun critère ;
    - A est strictement meilleure sur au moins un critère.
    Tous les critères sont à minimiser.
    """
    valeurs_a = convertir_criteres(solution_a)
    valeurs_b = convertir_criteres(solution_b)

    pas_pire = all(
        valeurs_a[c] <= valeurs_b[c]
        for c in CRITERES
    )

    strictement_meilleure = any(
        valeurs_a[c] < valeurs_b[c]
        for c in CRITERES
    )

    return pas_pire and strictement_meilleure


def extraire_front_pareto(solutions):
    """Conserve les solutions valides non dominées."""
    front = []

    for solution in solutions:
        est_dominee = False

        for autre_solution in solutions:
            if autre_solution is solution:
                continue

            if domine(autre_solution, solution):
                est_dominee = True
                break

        if not est_dominee:
            front.append(solution)

    return front


def calculer_pareto_par_instance(solutions):
    """Calcule un front de Pareto séparé pour chaque instance."""
    groupes = {}

    for solution in solutions:
        instance = solution.get("instance_id", "")
        groupes.setdefault(instance, []).append(solution)

    fronts = []

    for instance, solutions_instance in groupes.items():
        front = extraire_front_pareto(solutions_instance)
        fronts.extend(front)

    return fronts


# ============================================================
# EXPORT CSV
# ============================================================

def exporter_csv(chemin, lignes, colonnes):
    """Crée toujours le fichier CSV, même si aucune ligne n'existe."""
    chemin.parent.mkdir(parents=True, exist_ok=True)

    with open(
        chemin,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as fichier:

        ecrivain = csv.DictWriter(
            fichier,
            fieldnames=colonnes,
            extrasaction="ignore"
        )

        ecrivain.writeheader()
        ecrivain.writerows(lignes)


# ============================================================
# RAPPORT
# ============================================================

def enregistrer_rapport(
    total,
    valides,
    invalides,
    erreurs,
    fronts
):
    DOSSIER_SORTIE.mkdir(parents=True, exist_ok=True)

    lignes = [
        "========================================",
        "ANALYSE DES RESULTATS - MEMBRE 4",
        "========================================",
        "",
        f"Nombre total d'executions : {total}",
        f"Nombre de solutions valides : {len(valides)}",
        f"Nombre de solutions invalides : {len(invalides)}",
        f"Nombre de solutions Pareto : {len(fronts)}",
        "",
        "--- CONTROLE DES RESULTATS ---",
    ]

    if erreurs:
        lignes.extend(erreurs)
    else:
        lignes.append("Aucune incoherence detectee.")

    lignes.extend([
        "",
        "--- ETUDE DE PARETO ---",
    ])

    if fronts:
        lignes.append(
            f"{len(fronts)} solution(s) non dominee(s) identifiee(s)."
        )
    else:
        lignes.append(
            "Aucune solution valide disponible pour Pareto."
        )

    lignes.extend([
        "",
        "--- FICHIERS GENERES ---",
        str(FICHIER_VALIDES),
        str(FICHIER_PARETO),
        "",
        "Analyse terminee.",
    ])

    FICHIER_RAPPORT.write_text(
        "\n".join(lignes),
        encoding="utf-8"
    )


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

def main():
    print("=" * 45)
    print("ANALYSE DES RESULTATS - MEMBRE 4")
    print("=" * 45)

    DOSSIER_SORTIE.mkdir(parents=True, exist_ok=True)

    lignes = lire_resultats()

    if lignes is None:
        return

    print(f"\nNombre total d'executions : {len(lignes)}")

    valides, invalides, erreurs = controler_resultats(lignes)

    print(f"Nombre de solutions valides : {len(valides)}")
    print(f"Nombre de solutions invalides : {len(invalides)}")

    print("\n--- CONTROLE DES RESULTATS ---")

    if erreurs:
        for erreur in erreurs:
            print("-", erreur)
    else:
        print("Aucune incoherence detectee.")

    exporter_csv(
        FICHIER_VALIDES,
        valides,
        COLONNES_ENTETE
    )

    print(f"\nResultats valides exportes : {FICHIER_VALIDES}")

    # Calcul du front uniquement si les données sont cohérentes
    # et que des solutions valides sont disponibles.
    if valides and not erreurs:
        fronts = calculer_pareto_par_instance(valides)
    else:
        fronts = []

    if fronts:
        print(
            f"\nNombre de solutions non dominees : {len(fronts)}"
        )
    else:
        print("\nAucune solution valide disponible pour Pareto.")

    exporter_csv(
        FICHIER_PARETO,
        fronts,
        COLONNES_ENTETE
    )

    print(f"Fronts Pareto exportes : {FICHIER_PARETO}")

    enregistrer_rapport(
        len(lignes),
        valides,
        invalides,
        erreurs,
        fronts
    )

    print(f"Rapport d'analyse enregistre : {FICHIER_RAPPORT}")
    print("\nAnalyse terminee.")


if __name__ == "__main__":
    main()
