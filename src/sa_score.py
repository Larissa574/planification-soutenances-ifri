"""
sa_score.py  --  L8 : transformer les 5 critères en UN score, et garder les solutions non dominées.

1) Score pondéré normalisé
       score = somme_i  poids_i * f_i / echelle_i
   `echelle_i` = valeur du critère i sur le planning de DÉPART (plancher 1) : après division,
   chaque critère vaut 1.0 au départ, donc "améliorer f3 de 10 %" pèse comme "améliorer f1 de 10 %".
   Sans cette normalisation, le critère aux plus grands nombres écraserait les autres.
   Le recuit MINIMISE ce score.

2) Archive de Pareto
   a "domine" b si a est <= b sur les 5 critères et strictement < sur au moins un.
   L'archive garde les plannings qu'aucun autre planning trouvé ne domine.
"""


class Evaluateur:
    def __init__(self, poids, f_depart):
        self.poids = tuple(poids)
        self.echelles = tuple(max(1, x) for x in f_depart)
        self._coef = tuple(w / e for w, e in zip(self.poids, self.echelles))

    def score(self, f):
        c = self._coef
        return c[0] * f[0] + c[1] * f[1] + c[2] * f[2] + c[3] * f[3] + c[4] * f[4]


def domine(a, b):
    """a domine b : a n'est jamais pire et est meilleur quelque part (minimisation)."""
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


class ArchivePareto:
    def __init__(self, taille_max=100):
        self.taille_max = taille_max
        self.elements = []        # liste de (vecteur f, snapshot du planning)

    def proposer(self, f, snapshot_fn, evaluateur=None):
        """
        Propose un vecteur f. `snapshot_fn` n'est appelée (copie du planning) que si f est retenu.
        Renvoie True si f est entré dans l'archive.
        """
        for g, _ in self.elements:
            if g == f or domine(g, f):
                return False
        self.elements = [(g, s) for g, s in self.elements if not domine(f, g)]
        self.elements.append((f, snapshot_fn()))
        if len(self.elements) > self.taille_max and evaluateur is not None:
            # trop plein : on retire l'élément au plus mauvais score pondéré
            pire = max(range(len(self.elements)), key=lambda i: evaluateur.score(self.elements[i][0]))
            del self.elements[pire]
        return True

    def vecteurs(self):
        return sorted(f for f, _ in self.elements)
