"""
sa_parametres.py  --  L8 : TOUS les réglages du recuit simulé au même endroit.

Règle du protocole : on règle ces valeurs avec des graines de réglage (100, 101, ...),
puis on les GÈLE (on n'y touche plus) avant la campagne officielle (graines 0 à 4).
Une seule version gelée est utilisée pour toutes les instances.
"""

PARAMS = {
    # --- score pondéré : 5 poids (f1..f5), somme = 1.  Départ : poids égaux. ---
    "poids": (0.2, 0.2, 0.2, 0.2, 0.2),

    # --- température ---
    # T0 est calibrée automatiquement : on choisit T0 pour qu'une dégradation "moyenne"
    # soit acceptée avec la probabilité p0 au début.
    "p0": 0.5,
    # À la fin, la température vaut T0 * ratio_final (quasi-descente pure).
    "ratio_final": 1e-3,
    "nb_calibration": 300,        # nb de mouvements d'essai pour calibrer T0

    # --- budget de temps (secondes) ---
    "part_glouton": 0.25,         # part max du budget donnée au glouton pour fournir le départ
    "marge_fin": 0.5,             # marge de sécurité avant la limite de temps du runner

    # --- archive des solutions non dominées ---
    "taille_archive": 100,
    "bande_archive": 0.15,        # on ne propose à l'archive que les états proches du meilleur score
}
