# Compiler et installer pour OBS 32 sous Windows

OBS installé depuis son installeur ne contient pas les en-têtes et bibliothèques
de développement nécessaires à un plugin C++. Il faut donc un environnement de
compilation séparé : Visual Studio 2022 avec **Desktop development with C++**,
CMake 3.28+ et le SDK de développement d'OBS 32 (avec `include/` et `lib/`).

Définir `OBS_SDK_DIR` sur la racine de ce SDK, puis configurer avec CMake et
construire la cible `dofus-scene-guard`. L'installation place le fichier DLL
dans le dossier de plugins 64 bits d'OBS.

```powershell
$env:OBS_SDK_DIR = 'C:\dev\obs-studio-sdk-32'
cmake -S . -B build -G 'Visual Studio 17 2022' -A x64
cmake --build build --config Release
cmake --install build --config Release --prefix 'C:\Program Files\obs-studio'
```

Fermer OBS avant l'installation, puis le relancer. Le journal OBS doit contenir
`[Dofus Scene Guard] loaded`.

Le plugin communique uniquement via le named pipe Windows local
`\\.\pipe\DofusSceneGuard`; il n'ouvre aucun port réseau.
