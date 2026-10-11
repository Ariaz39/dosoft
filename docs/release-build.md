# Construire une release DOSOFT

La release est produite à partir de `Dosoft_BETA.spec`. Le script vérifie les
versions, les cinq catalogues de traduction, les ressources obligatoires, les
tests et la présence du connecteur OBS avant de compiler.

## Commande complète

Depuis PowerShell, à la racine du projet :

```powershell
.\build_release.ps1 -PythonExe "C:\chemin\vers\python.exe"
```

La sortie finale est créée dans `release_output\vX.Y.Z`. Elle contient le
setup, l'exécutable autonome, la DLL OBS, les mentions légales et les empreintes
SHA-256.

## Validation sans Inno Setup

```powershell
.\build_release.ps1 -PythonExe "C:\chemin\vers\python.exe" -SkipInstaller
```

Cette commande compile et contrôle l'exécutable, mais ne produit pas le setup.
Elle est utile sur une machine où Inno Setup 6 n'est pas installé.

## Règles de version

- `version.json`, `app_version.py` et `resources\compatibility.json` doivent
  annoncer la même version DOSOFT.
- `version.json` et `resources\compatibility.json` doivent recommander la même
  version du connecteur OBS.
- Le setup est une mise à niveau sur place : le même `AppId` conserve le profil
  de l'utilisateur. Les réglages sont stockés hors du dossier d'installation et
  ne sont pas supprimés par une mise à jour.
- Les mises à jour restent manuelles : aucun téléchargement ni remplacement
  automatique n'est effectué par DOSOFT.
