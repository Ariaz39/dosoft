# Dofus Scene Guard pour OBS

Plugin OBS Studio Windows destiné à ne diffuser que la source correspondant à
l'instance de jeu active. La scène de programme est `Stream`, qui inclut la
scène imbriquée gérée par le moteur actif. Lorsqu'une autre application prend le premier
plan, la dernière source Dofus reste affichée : le navigateur, le bureau et
les autres applications ne sont jamais sélectionnés comme source de diffusion.

## État du projet

Le plugin et le connecteur DOSOFT sont implémentés et compilés pour OBS 32.
Depuis la version 0.2, le canal local est bidirectionnel : DOSOFT peut détecter
les scènes et sources, créer la scène Dofus puis recevoir la confirmation OBS.

## Captures par moteur

- Unity : `game_capture`, scène `Jeu_Dofus_Unity`. Une capture encore à sa
  transformation par défaut est automatiquement centrée et ajustée aux
  dimensions du canevas OBS, proportions conservées. Les cadrages déjà
  déplacés, rognés ou redimensionnés manuellement restent inchangés.
- Dofus Rétro : `window_capture` en Windows Graphics Capture, scène par défaut
  `Jeu_Dofus_Rétro`.
- Wakfu : `window_capture` en Windows Graphics Capture, scène `Jeu_Wakfu`
  (évite le hook Java/OpenGL très saccadé).

Les scènes et préfixes de sources sont enregistrés séparément. Changer de
moteur dans DOSOFT ne détruit donc pas le cadrage préparé pour un autre jeu.

## Modes de sélection prévus

- `foreground` : le plugin lit la fenêtre Windows au premier plan et trouve
  la scène configurée pour son `hwnd`.
- `dosoft` : DOSOFT publie l'instance qu'il vient de sélectionner via un
  canal local. Ce mode suit sa boucle, même pendant une transition de focus.
- `hybrid` : DOSOFT est prioritaire et la détection du premier plan sert de
  secours.

Voir [l'architecture](docs/architecture.md) et le [contrat DOSOFT](docs/dosoft-bridge.md).

## Utilisation avec DOSOFT 1.3.8

Le setup DOSOFT peut installer automatiquement la DLL dans le dossier commun
des plugins OBS. Après avoir relancé OBS, ouvrir l'assistant OBS de DOSOFT et
suivre ses trois étapes. Il détecte l'installation, crée si nécessaire les
scènes `Jeu_Dofus_Unity`, `Jeu_Dofus_Rétro` et `Jeu_Wakfu`, puis synchronise
les fenêtres détectées. Les noms de la scène de stream, de la scène de secours,
du micro, de la caméra et de la pause restent configurables dans l'assistant.

Un Alt-Tab ne change jamais de scène et conserve la dernière capture Dofus.
Si toutes les fenêtres de jeu synchronisées ferment ou plantent, OBS affiche
la scène de secours configurée. Lorsqu'une fenêtre revient, le connecteur
reprend la sélection sans exposer les autres applications.
