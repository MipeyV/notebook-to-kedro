# Journal de développement

Ce fichier retrace chronologiquement l'évolution de **Notebook to Kedro**.

Il sert à conserver :

- ce qui a réellement été réalisé ;
- les décisions d'architecture et leur justification ;
- les limites découvertes ;
- les questions encore ouvertes ;
- la prochaine étape concrète.

Le journal n'est pas un changelog de version ni une simple backlog. Une entrée est ajoutée lorsqu'un travail est terminé ou lorsqu'une décision structurante est prise.

## Convention des entrées

Chaque nouvelle entrée suit autant que possible cette structure :

```markdown
## AAAA-MM-JJ — Titre court

### Réalisé

- ...

### Décisions

- ...

### Points ouverts

- ...

### Prochaine étape

- ...
```

Les entrées les plus récentes seront ajoutées en haut, juste après cette convention, afin que l'état actuel soit immédiatement visible.

---

## 2026-08-16 — Initialisation du projet

### Réalisé

- Clarification du problème ciblé : automatiser le passage d'un notebook Data Science relativement propre vers un projet Kedro structuré.
- Définition d'un premier périmètre fonctionnel et des limites du MVP.
- Proposition d'une architecture en étapes : chargement, analyse AST, résolution des dépendances, représentation intermédiaire, génération Kedro et écriture des fichiers.
- Identification des principaux risques : état implicite, mutations, effets de bord, scopes Python, inférence des paramètres et compatibilité Kedro.
- Création du `README.md` présentant le contexte, les objectifs, le périmètre et la roadmap initiale.
- Création de ce journal de développement.
- Initialisation du dépôt Git local avec une branche principale `main`.

### Décisions

- Le MVP ne dépendra pas d'un LLM.
- La représentation intermédiaire sera séparée du générateur Kedro.
- Une cellule de code convertible correspondra initialement à une tâche au maximum ; la fusion automatique de cellules est reportée.
- Les cas ambigus devront produire des diagnostics explicites et pourront bloquer la génération.
- La première étape d'implémentation portera sur l'analyse du notebook, pas sur la génération Kedro.
- Le projet Kedro produit ciblera une version explicitement définie et testée.

### Points ouverts

- Choisir les versions minimales de Python et Kedro.
- Définir précisément la matrice des constructions supportées, averties et interdites.
- Définir la forme finale des objets de la représentation intermédiaire.
- Choisir la convention d'extraction explicite des paramètres.
- Décider du nom définitif du projet et vérifier sa disponibilité avant publication éventuelle.

### Prochaine étape

- Initialiser le squelette Python en `src/` et spécifier les premiers notebooks fixtures avant d'implémenter le loader.
