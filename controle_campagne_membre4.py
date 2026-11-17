
from pathlib import Path
import csv
import json
from collections import Counter, defaultdict

# ============================================================
# CONFIGURATION
# ============================================================

DOSSIER_PROJET = Path(__file__).resolve().parent
DOSSIER_DATA = DOSSIER_PROJET / "data"
FICHIER_RESULTATS = DOSSIER_PROJET / "results" / "resultats.csv"
DOSSIER_SORTIE = DOSSIER_PROJET / "analyses_membre4"

METHODE_DETERMINISTE = "greedy"
METHODE_STOCHASTIQUE = "sa"

GRAINES_ATTENDUES = {"0", "1", "2", "3", "4"}

CRITERES = [
    "teacher_presence_days",
    "teacher_idle_slots",
    "teacher_load_range",
    "supervisor_group_breaks",
    "distinct_jury_pairs",
]

COLONNES_ATTENDUES = [
    "instance_id",
    "method",
    "seed",
    "build_seconds",
    "search_seconds",
    "total_seconds",
    "first_feasible_seconds",
    "stop_status",
    "valid",
    *CRITERES,
    "solution_file",
    "validation_file",
]


# ============================================================
# OUTILS
# ============================================================

def est_valide(valeur):
    """Interprète les différentes représentations d'une valeur booléenne."""
    return str(valeur).strip().lower() in {
        "true", "1", "yes", "oui"
    }


def lire_instances():
    """Récupère les identifiants des 30 instances JSON."""
    if not DOSSIER_DATA.exists():
        print(f"ERREUR : dossier introuvable : {DOSSIER_DATA}")
        return []

    instances = []

    for fichier in DOSSIER_DATA.glob("*.json"):
        nom = fichier.stem

        if nom.startswith(("small_", "medium_", "large_")):
            instances.append(nom)

    return sorted(instances)


def lire_resultats():
    """Lit le fichier CSV produit par le runner."""
    if not FICHIER_RESULTATS.exists():
        print(f"ERREUR : fichier de résultats introuvable : {FICHIER_RESULTATS}")
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
            colonne for colonne in COLONNES_ATTENDUES
            if colonne not in colonnes
        ]

        if colonnes_absentes:
            print("ERREUR : colonnes absentes dans resultats.csv :")
            for colonne in colonnes_absentes:
                print(f"- {colonne}")
            return None

        return list(lecteur)


def verifier_nombre(valeur):
    """Vérifie qu'une valeur est numérique et finie."""
    try:
        nombre = float(valeur)
        return nombre >= 0 and nombre != float("inf") and nombre == nombre
    except (TypeError, ValueError):
        return False


# ============================================================
# CONTROLE DES LIGNES
# ============================================================

def controler_structure(lignes):
    erreurs = []
    avertissements = []

    for numero, ligne in enumerate(lignes, start=2):
        for colonne in COLONNES_ATTENDUES:
            if colonne not in ligne:
                erreurs.append(
                    f"Ligne {numero} : colonne '{colonne}' absente."
                )

        if not ligne.get("instance_id", "").strip():
            erreurs.append(f"Ligne {numero} : instance_id manquant.")

        if not ligne.get("method", "").strip():
            erreurs.append(f"Ligne {numero} : method manquant.")

        if not ligne.get("stop_status", "").strip():
            erreurs.append(f"Ligne {numero} : stop_status manquant.")

        if ligne.get("valid", "").strip().lower() not in {
            "true", "false", "1", "0", "yes", "no", "oui", "non"
        }:
            erreurs.append(
                f"Ligne {numero} : valeur valid incorrecte."
            )
            continue

        if est_valide(ligne.get("valid", "")):
            for colonne in ("solution_file", "validation_file"):
                if not ligne.get(colonne, "").strip():
                    erreurs.append(
                        f"Ligne {numero} : champ '{colonne}' manquant."
                    )

            for critere in CRITERES:
                valeur = ligne.get(critere, "").strip()

                if not valeur:
                    erreurs.append(
                        f"Ligne {numero} : critère '{critere}' manquant "
                        "pour une solution valide."
                    )
                elif not verifier_nombre(valeur):
                    erreurs.append(
                        f"Ligne {numero} : critère '{critere}' "
                        "non numérique ou négatif."
                    )
        else:
            valeurs_presentes = [
                critere for critere in CRITERES
                if ligne.get(critere, "").strip()
            ]

            if valeurs_presentes:
                avertissements.append(
                    f"Ligne {numero} : solution invalide avec des "
                    f"critères renseignés : {', '.join(valeurs_presentes)}."
                )

    return erreurs, avertissements


# ============================================================
# CONTROLE DE LA CAMPAGNE
# ============================================================

def controler_campagne(instances, lignes):
    erreurs, avertissements = controler_structure(lignes)

    executions = defaultdict(list)
    methodes_connues = {
        METHODE_DETERMINISTE,
        METHODE_STOCHASTIQUE
    }

    instances_connues = set(instances)

    for numero, ligne in enumerate(lignes, start=2):
        instance = ligne.get("instance_id", "").strip()
        methode = ligne.get("method", "").strip()
        graine = ligne.get("seed", "").strip()

        if instance not in instances_connues:
            erreurs.append(
                f"Ligne {numero} : instance inconnue '{instance}'."
            )
            continue

        if methode not in methodes_connues:
            erreurs.append(
                f"Ligne {numero} : méthode non prévue '{methode}'. "
                "Méthodes attendues : greedy et sa."
            )
            continue

        if methode == METHODE_DETERMINISTE:
            if graine not in ("", "0"):
                avertissements.append(
                    f"Ligne {numero} : graine inattendue pour greedy : {graine}."
                )
            cle = (instance, methode, "unique")

        else:
            if graine not in GRAINES_ATTENDUES:
                erreurs.append(
                    f"Ligne {numero} : graine inattendue pour sa : {graine}."
                )
                continue
            cle = (instance, methode, graine)

        executions[cle].append(numero)

    # Détection des doublons
    doublons = []

    for cle, numeros in executions.items():
        if len(numeros) > 1:
            doublons.append((cle, numeros))

    # Vérification des exécutions attendues
    executions_manquantes = []

    for instance in instances:
        cle_greedy = (instance, METHODE_DETERMINISTE, "unique")

        if cle_greedy not in executions:
            executions_manquantes.append(
                f"{instance} : exécution greedy absente."
            )

        for graine in sorted(GRAINES_ATTENDUES):
            cle_sa = (instance, METHODE_STOCHASTIQUE, graine)

            if cle_sa not in executions:
                executions_manquantes.append(
                    f"{instance} : graine {graine} absente pour sa."
                )

    # Statistiques
    nombre_greedy = sum(
        1 for cle in executions
        if cle[1] == METHODE_DETERMINISTE
    )

    nombre_sa = sum(
        1 for cle in executions
        if cle[1] == METHODE_STOCHASTIQUE
    )

    nombre_valides = sum(
        1 for ligne in lignes
        if est_valide(ligne.get("valid", ""))
    )

    nombre_invalides = sum(
        1 for ligne in lignes
        if ligne.get("valid", "").strip().lower()
        in {"false", "0", "no", "non"}
    )

    return {
        "erreurs": erreurs,
        "avertissements": avertissements,
        "doublons": doublons,
        "manquantes": executions_manquantes,
        "nombre_greedy": nombre_greedy,
        "nombre_sa": nombre_sa,
        "nombre_valides": nombre_valides,
        "nombre_invalides": nombre_invalides,
    }


# ============================================================
# GENERATION DU RAPPORT
# ============================================================

def enregistrer_rapport(resultat, nombre_instances, nombre_lignes):
    DOSSIER_SORTIE.mkdir(parents=True, exist_ok=True)

    chemin = DOSSIER_SORTIE / "rapport_controle_campagne.txt"

    lignes_rapport = [
        "========================================",
        "RAPPORT DE CONTROLE DE CAMPAGNE",
        "MEMBRE 4",
        "========================================",
        "",
        f"Nombre d'instances : {nombre_instances}",
        f"Nombre de lignes CSV : {nombre_lignes}",
        f"Executions greedy detectees : {resultat['nombre_greedy']}",
        f"Executions sa detectees : {resultat['nombre_sa']}",
        f"Solutions valides : {resultat['nombre_valides']}",
        f"Solutions invalides : {resultat['nombre_invalides']}",
        "",
        "--- ERREURS ---",
    ]

    lignes_rapport.extend(
        resultat["erreurs"] or ["Aucune erreur de structure detectee."]
    )

    lignes_rapport.extend(["", "--- AVERTISSEMENTS ---"])
    lignes_rapport.extend(
        resultat["avertissements"] or ["Aucun avertissement."]
    )

    lignes_rapport.extend(["", "--- DOUBLONS ---"])

    if resultat["doublons"]:
        for cle, numeros in resultat["doublons"]:
            lignes_rapport.append(
                f"{cle} : lignes {numeros}"
            )
    else:
        lignes_rapport.append("Aucun doublon detecte.")

    lignes_rapport.extend(["", "--- EXECUTIONS MANQUANTES ---"])
    lignes_rapport.extend(
        resultat["manquantes"] or ["Aucune execution manquante."]
    )

    if (
        resultat["erreurs"]
        or resultat["doublons"]
        or resultat["manquantes"]
    ):
        lignes_rapport.extend([
            "",
            "CAMPAGNE A COMPLETER OU A VERIFIER"
        ])
    else:
        lignes_rapport.extend([
            "",
            "CONTROLE DE CAMPAGNE TERMINE"
        ])

    chemin.write_text(
        "\n".join(lignes_rapport),
        encoding="utf-8"
    )

    return chemin


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

def main():
    print("=" * 45)
    print("CONTROLE DE CAMPAGNE - MEMBRE 4")
    print("=" * 45)

    instances = lire_instances()

    if not instances:
        print("Aucune instance trouvee dans le dossier data.")
        return

    lignes = lire_resultats()

    if lignes is None:
        return

    resultat = controler_campagne(instances, lignes)

    print(f"\nNombre d'instances : {len(instances)}")
    print(f"Nombre de lignes CSV : {len(lignes)}")
    print(f"Executions greedy detectees : {resultat['nombre_greedy']}")
    print(f"Executions sa detectees : {resultat['nombre_sa']}")
    print(f"Solutions valides : {resultat['nombre_valides']}")
    print(f"Solutions invalides : {resultat['nombre_invalides']}")

    print("\n--- ERREURS ---")
    if resultat["erreurs"]:
        for erreur in resultat["erreurs"]:
            print("-", erreur)
    else:
        print("Aucune erreur de structure detectee.")

    print("\n--- AVERTISSEMENTS ---")
    if resultat["avertissements"]:
        for avertissement in resultat["avertissements"]:
            print("-", avertissement)
    else:
        print("Aucun avertissement.")

    print("\n--- DOUBLONS ---")
    if resultat["doublons"]:
        for cle, numeros in resultat["doublons"]:
            print(f"- {cle} : lignes {numeros}")
    else:
        print("Aucun doublon detecte.")

    print("\n--- EXECUTIONS MANQUANTES ---")
    if resultat["manquantes"]:
        for execution in resultat["manquantes"]:
            print("-", execution)
    else:
        print("Aucune execution manquante.")

    rapport = enregistrer_rapport(
        resultat,
        len(instances),
        len(lignes)
    )

    print("\n" + "=" * 45)
    if (
        resultat["erreurs"]
        or resultat["doublons"]
        or resultat["manquantes"]
    ):
        print("CAMPAGNE A COMPLETER OU A VERIFIER")
    else:
        print("CONTROLE DE CAMPAGNE TERMINE")
    print("=" * 45)

    print(f"\nRapport enregistre : {rapport}")


if __name__ == "__main__":
    main()
