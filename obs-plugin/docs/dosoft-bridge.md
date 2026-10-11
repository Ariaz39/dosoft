# Pont DOSOFT BETA → OBS

## Constat dans DOSOFT BETA

DOSOFT découvre les fenêtres Dofus dans `logic.py` et conserve, pour chaque
compte, son `name`, son `hwnd`, son équipe et son ordre. Dans `main.py`, son
`current_idx` est mis à jour lors des changements manuels de premier plan,
des raccourcis, du menu radial et de la barre de personnages. C'est une source
plus fiable que le seul polling Windows pour suivre sa boucle interne.

## Contrat proposé

DOSOFT émet un message JSON local à chaque sélection réussie :

```json
{
  "version": 2,
  "event": "dofus_account_selected",
  "client_id": "b340-c0816",
  "account": "NomDuPersonnage",
  "hwnd": 123456,
  "engine": "unity"
}
```

Pour `sync_team`, le plugin crée ou met à jour une capture par compte dans la
scène propre au moteur. `engine` vaut `unity`, `retro` ou `wakfu`. Unity et
Unity utilise la capture de jeu ; Rétro et Wakfu utilisent la capture de fenêtre
WGC. Pour Wakfu, ce choix évite l'injection dans `javaw.exe`, responsable d'une
capture très saccadée sur certaines configurations.
Pour les
événements de sélection, il associe en priorité `hwnd`, puis `account`, à
cette capture OBS. Les scènes et sources existantes ne sont jamais supprimées
automatiquement.

## Transport

Le transport recommandé est un named pipe Windows local, privé à la session
utilisateur. Il évite d'ouvrir un port réseau et ne requiert pas obs-websocket.
Un fichier d'état atomique peut servir de solution provisoire pendant le
développement, mais il n'est pas le transport final.

## Évolutions DOSOFT prévues

Le changement DOSOFT sera minimal : un adaptateur optionnel, désactivé par
défaut, appelé immédiatement après chaque `focus_window` réussi. Le plugin OBS
reste entièrement fonctionnel en mode `foreground` si DOSOFT est absent.
# Contrat DOSOFT ↔ OBS

Le connecteur local utilise désormais le protocole **v3**. La négociation
`hello` annonce la version du plugin, la plage de protocole acceptée, un
identifiant de session OBS et les capacités disponibles. DOSOFT 1.3.8 reste
compatible avec le plugin v2 (0.2.0) pendant la migration.

Le pipe est limité à la machine locale (`PIPE_REJECT_REMOTE_CLIENTS`). Chaque
message doit contenir un `request_id`, un événement et une version de protocole
comprise entre 2 et 3. Une réponse doit reprendre le même `request_id`.
