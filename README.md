# Notebook to Kedro

> Transformer progressivement un notebook Data Science relativement propre en un projet Kedro structuré, reproductible et facile à valider humainement.

## Contexte

Les workflows de Machine Learning commencent souvent dans un notebook Jupyter utilisé comme environnement d'expérimentation :

```text
chargement des données
    → preprocessing
    → feature engineering
    → séparation train/test
    → entraînement
    → prédiction
    → évaluation
```

Lorsqu'une expérimentation doit devenir un projet maintenable, une grande partie du travail consiste à restructurer manuellement ce notebook :

- extraire des fonctions ;
- identifier les entrées et sorties de chaque étape ;
- construire des nodes et une pipeline Kedro ;
- déplacer les paramètres vers la configuration ;
- déclarer les jeux de données ;
- organiser le code et séparer les responsabilités ;
- rendre le workflow reproductible et testable.

Ce travail est utile, mais répétitif. **Notebook to Kedro** cherche à en automatiser la partie mécanique tout en rendant visibles les ambiguïtés qui nécessitent une décision humaine.

## Objectif

L'interface cible de la bibliothèque est volontairement simple :

```python
from notebook_to_kedro import convert

report = convert(
    input_path="notebooks/model.ipynb",
    output_path="generated/my_kedro_project",
)
```

À terme, le dossier généré devra être un projet Kedro cohérent dont le workflow peut être lancé avec :

```bash
cd generated/my_kedro_project
kedro run
```

La réussite ne se limite pas à produire du code syntaxiquement valide : les sorties observables du projet généré devront être comparables à celles du notebook source.

## Positionnement

Le projet ne promet pas de transformer automatiquement n'importe quel notebook chaotique en code prêt pour la production.

Il vise plutôt à :

> automatiser une grande partie du refactoring répétitif d'un notebook ML séquentiel et relativement propre vers une pipeline Kedro structurée, avec diagnostics explicites et validation humaine.

L'outil devra savoir distinguer trois situations :

1. la conversion est supportée ;
2. la conversion est possible mais comporte des avertissements ;
3. la conversion est refusée avec une explication actionnable.

## Périmètre initial

Le MVP ciblera des notebooks :

- écrits en Python ;
- syntaxiquement valides ;
- exécutables dans l'ordre des cellules ;
- sans dépendance à un état interactif antérieur ;
- utilisant principalement des variables nommées pour transmettre les résultats entre étapes ;
- composés de transformations de données et d'étapes ML relativement explicites.

Le MVP ne cherchera pas à gérer :

- les cellules exécutées dans un ordre incohérent ;
- les magies Jupyter et les commandes shell ;
- `exec`, `eval` et les imports dynamiques ;
- les mutations et effets de bord impossibles à déterminer statiquement ;
- les dépendances externes complexes ou leur version exacte ;
- tous les frameworks de Machine Learning ;
- le déploiement, le serving, le monitoring ou l'infrastructure cloud.

Quand une construction n'est pas supportée, l'outil devra la signaler plutôt que générer silencieusement un résultat douteux.

## Architecture envisagée

```text
Notebook .ipynb
      ↓
Loader et validation
      ↓
Analyse AST des cellules
      ↓
Résolution des symboles et dépendances
      ↓
Représentation intermédiaire + diagnostics
      ↓
Générateur Kedro versionné
      ↓
Écriture transactionnelle des fichiers
      ↓
Projet généré + rapport de conversion
```

### Loader

Le loader ouvre le notebook, valide son format et restitue ses cellules dans l'ordre source. Il ne réalise aucune analyse métier.

### Analyseur

L'analyseur s'appuie autant que possible sur l'AST Python pour identifier :

- les imports ;
- les symboles définis et utilisés ;
- les fonctions et classes ;
- les dépendances entre cellules ;
- les mutations ou effets de bord suspects ;
- les constructions non supportées.

L'analyse statique ne pouvant pas garantir seule l'équivalence sémantique, ses limites devront apparaître dans les diagnostics.

### Représentation intermédiaire

L'analyse du notebook ne produira pas directement du code Kedro. Une représentation intermédiaire décrira les tâches, leurs entrées et sorties, leur provenance et les paramètres reconnus.

Exemple conceptuel :

```python
Task(
    name="train_model",
    source_cells=(5,),
    inputs=("X_train", "y_train"),
    outputs=("model",),
    parameters=("learning_rate",),
    source_code="...",
)
```

Cette séparation permettra de faire évoluer l'analyse et la génération indépendamment.

### Générateur Kedro

Le générateur transformera uniquement la représentation intermédiaire. Il créera une structure Kedro compatible avec une version explicitement ciblée, notamment :

- les fonctions de nodes ;
- la définition de la pipeline ;
- son enregistrement ;
- la configuration des paramètres ;
- le catalogue des entrées et sorties persistantes ;
- les fichiers minimaux permettant l'exécution du projet.

## Principes de conception

- **Déterminisme d'abord** : parsing, graphe de dépendances, génération et validation ne dépendent pas d'un LLM.
- **Traçabilité** : toute tâche générée reste reliée à ses cellules sources.
- **Échec explicite** : une ambiguïté importante bloque la conversion ou produit un avertissement visible.
- **Pas d'écrasement silencieux** : une destination existante est protégée par défaut.
- **Simplicité** : fonctions, dataclasses et modules ciblés avant toute abstraction plus générale.
- **Testabilité** : les décisions d'analyse et le projet généré doivent pouvoir être testés séparément.
- **Validation humaine** : le rapport de conversion fait partie du produit.

## Place éventuelle d'un LLM

Le cœur du MVP restera déterministe. Un LLM pourra éventuellement assister, dans une phase ultérieure :

- le nommage métier des nodes ;
- la classification des blocs ;
- le regroupement de plusieurs cellules ;
- l'extraction de paramètres ambigus ;
- le refactoring de code impératif complexe ;
- la proposition de tests.

Ces suggestions devront toujours passer par les validations déterministes et être présentées à l'utilisateur avant adoption.

## État du projet

Le projet est en phase de cadrage. Aucun convertisseur n'est encore implémenté.

La première étape technique prévue consiste à construire un analyseur de notebook capable de produire une représentation intermédiaire inspectable, sans générer de projet Kedro.

L'avancement et les décisions sont consignés chronologiquement dans [JOURNAL.md](JOURNAL.md).

## Roadmap initiale

1. Formaliser le sous-ensemble de notebooks supporté.
2. Initialiser le package Python et son outillage qualité.
3. Charger et valider les notebooks.
4. Analyser les cellules avec l'AST Python.
5. Résoudre les dépendances et produire la représentation intermédiaire.
6. Générer un projet Kedro minimal pour des fixtures contrôlées.
7. Vérifier l'équivalence sur des sorties observables.
8. Ajouter progressivement les paramètres, catalogues et diagnostics avancés.

## Contributions

Le projet débute. Les conventions de développement, commandes d'installation et règles de contribution seront ajoutées avec le premier squelette Python.

## Nom du projet

**Notebook to Kedro** est un nom provisoire. Le nom du package Python envisagé est `notebook_to_kedro`.
