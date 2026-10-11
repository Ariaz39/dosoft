# DOSOFT 1.3.8 bêta — Notice utilisateur complète

> Guide global au format interview
>
> Plateforme : Windows 10/11
>
> Jeux pris en charge : Dofus Unity, Dofus Rétro et Wakfu
> Extension facultative : Dofus Scene Guard pour OBS Studio 32.x 64 bits

Cette notice explique comment utiliser DOSOFT, mais aussi pourquoi chaque
fonction existe. Elle s'adresse autant à une personne qui découvre les
gestionnaires multicompte qu'à un streamer qui souhaite relier DOSOFT à OBS.

DOSOFT 1.3.8 est une version bêta. Il est recommandé de tester les raccourcis,
l'Auto-Focus et la scène de secours OBS hors stream avant une utilisation en
direct.

---

## 1. Comprendre DOSOFT

### Intervieweur — DOSOFT, c'est quoi exactement ?

**Équipe DOSOFT —** DOSOFT est un gestionnaire de fenêtres pour les joueurs
multicomptes. Il détecte les clients de jeu ouverts, leur associe un personnage,
une classe, une équipe et une position, puis permet de passer rapidement de
l'un à l'autre.

Son objectif n'est pas d'automatiser le jeu. DOSOFT organise les fenêtres et
leur donne le focus lorsque l'utilisateur le demande. Une action de changement
de personnage correspond donc toujours à une demande de l'utilisateur ou à un
événement explicitement autorisé, comme une notification Dofus Rétro.

### Intervieweur — Pourquoi avoir séparé Unity, Rétro et Wakfu ?

**Équipe DOSOFT —** Les trois jeux n'exposent pas leurs fenêtres de la même
manière :

- Dofus Unity utilise des fenêtres Unity et fournit généralement le personnage
  et sa classe dans le titre ;
- Dofus Rétro utilise un format de titre différent et son Auto-Focus repose sur
  les notifications Windows ;
- Wakfu tourne dans une fenêtre Java et nécessite une détection propre à son
  processus et à son titre.

Le moteur choisi indique donc à DOSOFT quelles fenêtres rechercher. Il change
aussi le thème visuel, les portraits et les outils propres au jeu sélectionné.

### Intervieweur — DOSOFT joue-t-il à ma place ?

**Équipe DOSOFT —** Non. Il ne clique pas dans le jeu, ne lance pas de sorts et
ne saisit pas de commandes à votre place. Il sélectionne une fenêtre existante,
range les fenêtres ou copie une commande que vous décidez ensuite d'utiliser.

---

## 2. Installation et premier démarrage

### Intervieweur — Quel fichier dois-je télécharger ?

**Équipe DOSOFT —** Utilisez de préférence
`Dosoft_BETA_Setup_v1.3.8.exe`. Le setup installe l'application et peut aussi
installer le connecteur OBS. `Dosoft_BETA.exe` est une version autonome surtout
utile pour le dépannage.

L'installeur bêta n'est pas signé numériquement. Windows SmartScreen peut donc
afficher un avertissement. Téléchargez uniquement les fichiers publiés sur le
dépôt officiel et comparez leur empreinte avec `SHA256SUMS.txt`.

### Intervieweur — Comment effectuer une installation propre ?

**Équipe DOSOFT —**

1. Fermez complètement DOSOFT.
2. Fermez OBS Studio si vous installez ou remplacez le connecteur.
3. Pour un test sensible, copiez le dossier `%APPDATA%\DOSOFT` dans un endroit
   sûr.
4. Lancez le setup et choisissez les composants souhaités.
5. Relancez OBS en premier si vous utilisez l'extension.
6. Lancez ensuite DOSOFT.
7. Ouvrez au moins une fenêtre du jeu choisi, puis cliquez sur **Rafraîchir**.

### Intervieweur — Mes réglages disparaissent-ils lors d'une mise à jour ?

**Équipe DOSOFT —** Non. Le setup utilise un identifiant d'application stable
et les données sont stockées dans le profil Windows, hors du dossier du
programme. Une mise à niveau conserve normalement les raccourcis, équipes,
thèmes et réglages OBS.

Au premier lancement d'une nouvelle version, DOSOFT crée également une
sauvegarde de migration des fichiers importants.

### Intervieweur — Où sont enregistrés mes réglages ?

**Équipe DOSOFT —** Les principaux fichiers se trouvent dans
`%APPDATA%\DOSOFT` :

- `settings.json` : réglages généraux, raccourcis, équipes et préférences ;
- `settings.backup.json` : dernière sauvegarde valide des réglages ;
- `obs_profile.json` : profil de l'extension OBS ;
- `obs_profile.backup.json` : sauvegarde du profil OBS ;
- `dofus-display` : profils et sauvegardes de l'affichage Dofus ;
- `backups` : sauvegardes de migration entre versions ;
- journaux de diagnostic, lorsqu'ils sont nécessaires ou activés.

Si un fichier JSON devient illisible, DOSOFT tente d'abord de restaurer sa
dernière sauvegarde valide et conserve une copie datée du fichier endommagé.

---

## 3. Visite guidée de la fenêtre principale

### Intervieweur — À quoi servent les boutons **Paramètres** et **OFF** ?

**Équipe DOSOFT —**

- **Paramètres** ouvre tous les réglages de DOSOFT et les extensions
  facultatives.
- **OFF** ferme réellement l'application et arrête ses raccourcis.

Il ne faut pas confondre **OFF** avec **Cacher l'UI** ou le raccourci F12.
Masquer l'interface laisse DOSOFT actif en arrière-plan ; **OFF** l'arrête.

### Intervieweur — Que signifie le sélecteur **Contrôler : ALL / Team 1 / Team 2** ?

**Équipe DOSOFT —** Il détermine les personnages inclus dans la boucle de
changement de fenêtre :

- **ALL** utilise tous les comptes actifs ;
- **Team 1** limite la boucle aux personnages de la première équipe ;
- **Team 2** limite la boucle à la seconde équipe.

Le filtre n'efface aucun personnage. Il modifie uniquement la liste que les
raccourcis **Précédent**, **Suivant**, les binds avancés et la barre de
personnages peuvent parcourir.

### Intervieweur — À quoi servent les trois logos de jeu ?

**Équipe DOSOFT —** Ils sélectionnent le moteur de détection :

- logo Dofus Unity : fenêtres Unity ;
- logo Dofus Rétro : fenêtres Rétro et outils de notifications ;
- logo Wakfu : fenêtres Java de Wakfu.

Changer de moteur ne détruit pas les réglages de l'autre jeu. Les équipes,
portraits et scènes OBS sont conservés séparément lorsque cela est nécessaire.

### Intervieweur — Pourquoi existe-t-il un bouton OBS près des moteurs ?

**Équipe DOSOFT —** Lorsque l'extension OBS est activée, ce bouton ouvre
directement l'assistant OBS. Le bouton rouge adjacent est le **redémarrage
d'urgence** des captures : il supprime uniquement les captures gérées par
DOSOFT et les recrée à partir des personnages actuellement détectés.

Le redémarrage d'urgence ne doit pas devenir une action habituelle. Il sert
lorsqu'un changement de personnage, un redémarrage d'OBS ou une fenêtre
renommée a laissé une capture dans un état incohérent.

### Intervieweur — Que montre la zone **Comptes actifs** ?

**Équipe DOSOFT —** Chaque ligne représente une fenêtre détectée. Selon le
moteur et les données disponibles, elle affiche le pseudo, la classe et des
commandes de gestion :

- activer ou retirer le personnage de la boucle ;
- définir le personnage comme **Chef** ;
- l'affecter à **Team 1** ou **Team 2** ;
- le monter ou le descendre dans l'ordre ;
- choisir une position exacte ;
- demander une fermeture propre de sa fenêtre.

La fermeture est envoyée comme une demande Windows normale. DOSOFT ne tue pas
brutalement le processus du jeu, afin de laisser au client le temps
d'enregistrer ses paramètres.

### Intervieweur — Pourquoi les fenêtres sans personnage portent-elles un nom comme `Menu Unity [U1]` ?

**Équipe DOSOFT —** Une page de connexion n'a pas encore de pseudo exploitable.
Sans identifiant stable, plusieurs menus pouvaient permuter à chaque
rafraîchissement et faire boucler la navigation. DOSOFT leur attribue donc un
tag de session (`U1`, `U2`, etc.) fondé sur leur ordre de lancement. Le tag
reste attaché à la fenêtre jusqu'à sa fermeture.

### Intervieweur — À quoi servent **Rafraîchir** et **Trier Barre Windows** ?

**Équipe DOSOFT —**

- **Rafraîchir** rescane les fenêtres et actualise les pseudos, classes,
  équipes et barres flottantes ;
- **Trier Barre Windows** masque puis réaffiche les fenêtres actives dans
  l'ordre DOSOFT afin de remettre de l'ordre dans la barre des tâches.

Après le tri, DOSOFT tente de rendre le focus au Chef.

### Intervieweur — Que contrôle le curseur de volume ?

**Équipe DOSOFT —** Il règle le volume des sons d'interface de la roue radiale
(survol et validation). Il ne modifie ni le volume général de Windows, ni celui
du jeu, ni celui d'OBS.

### Intervieweur — Que fait **Bulles** ?

**Équipe DOSOFT —** Cette option affiche ou masque les infobulles explicatives
au survol des boutons. Elle est utile lors de la découverte du logiciel et peut
être désactivée une fois les commandes mémorisées.

### Intervieweur — Que fait **Cacher l'UI** ?

**Équipe DOSOFT —** Le bouton cache la fenêtre principale dans la zone de
notification, tout en maintenant actifs la détection, les raccourcis, les
barres flottantes autorisées et la liaison OBS. Utilisez l'icône de la zone de
notification ou F12 pour la réafficher.

---

## 4. Raccourcis standards

### Intervieweur — Quels sont les raccourcis principaux ?

**Équipe DOSOFT —** Ils sont modifiables depuis la fenêtre principale :

- **Précédent** : revient au personnage précédent de la boucle active ;
- **Suivant** : passe au personnage suivant ;
- **Chef** : rend immédiatement le focus au personnage défini comme Chef ;
- **Afficher UI** : masque ou réaffiche DOSOFT, F12 par défaut ;
- **Rafraîchir** : relance la détection ;
- **Quitter** : ferme DOSOFT si vous lui attribuez une touche.

Cliquez sur le bouton d'une touche, puis pressez le raccourci voulu. `...`
indique que DOSOFT attend une saisie. Le bouton `✖` efface l'affectation.

### Intervieweur — Pourquoi F12 ne ferme-t-il plus DOSOFT ?

**Équipe DOSOFT —** Parce que l'utilisateur veut souvent cacher l'interface
pendant une session tout en conservant le gestionnaire actif. Fermer le logiciel
rendait les raccourcis et les protections OBS inopérants. F12 sert donc à
masquer/réafficher ; la fermeture reste accessible via **OFF** et l'icône de la
zone de notification.

### Intervieweur — DOSOFT empêche-t-il les doublons de raccourcis ?

**Équipe DOSOFT —** Oui. Avant d'enregistrer, il normalise les variantes de
Ctrl, Alt et Maj puis recherche les conflits entre raccourcis standards, roue
radiale, changement d'équipe et binds avancés. Un conflit est signalé avec les
actions concernées.

---

## 5. Option avancée : **Superposer les raccourcis**

### Intervieweur — À quoi sert exactement cette option ?

**Équipe DOSOFT —** Par défaut, une combinaison doit être entièrement relâchée
avant de pouvoir être déclenchée une seconde fois. Par exemple, après `Alt+A`,
il faut relâcher Alt et A avant un nouveau `Alt+A`. Cette sécurité évite les
répétitions involontaires lors d'un changement de fenêtre.

L'option **Superposer les raccourcis** autorise un autre usage : garder Alt,
Ctrl ou Maj enfoncé, puis presser plusieurs fois la touche principale. Exemple :

1. maintenir Alt ;
2. presser A pour changer de page ;
3. relâcher seulement A ;
4. presser A à nouveau tout en gardant Alt enfoncé.

### Intervieweur — Pourquoi l'option affiche-t-elle un avertissement ?

**Équipe DOSOFT —** Une touche modificatrice maintenue pendant que Windows
change le focus peut être interprétée différemment par le jeu ou une autre
application. Cela peut provoquer des répétitions ou des saisies inattendues.

L'option est donc désactivée par défaut et considérée comme expérimentale. Si
vous l'activez :

- évitez d'utiliser le même combo dans le jeu ;
- testez hors combat et hors stream ;
- relâchez toutes les touches dès qu'un comportement paraît anormal ;
- désactivez l'option avant d'ouvrir un ticket lié à des touches répétées.

### Intervieweur — Dois-je l'activer pour que DOSOFT soit rapide ?

**Équipe DOSOFT —** Non. Elle change uniquement la politique de relâchement des
combinaisons. Les changements de fenêtre standards restent rapides sans elle.

---

## 6. Roue de Focus radiale

### Intervieweur — Pourquoi une roue alors que les touches Suivant/Précédent existent ?

**Équipe DOSOFT —** Suivant/Précédent est idéal pour parcourir une initiative.
La roue est faite pour atteindre directement un personnage sans compter le
nombre de changements nécessaires.

Maintenez son raccourci — `Alt + clic gauche` par défaut — puis déplacez la
souris vers le portrait souhaité. La sélection s'effectue à la fermeture de la
roue.

### Intervieweur — Puis-je la désactiver ?

**Équipe DOSOFT —** Oui. Dans **Paramètres > Roue de Focus**, désactivez la
roue ou changez son raccourci. Une roue désactivée ne réserve plus sa
combinaison.

---

## 7. Barre de personnages et modes Team

### Intervieweur — Qu'est-ce que la **Barre persos** ?

**Équipe DOSOFT —** C'est une petite barre sans titre, toujours au-dessus des
fenêtres, qui affiche les portraits des personnages actifs. Un clic sur un
portrait sélectionne immédiatement sa fenêtre.

La barre est déplaçable et mémorise sa position. Elle peut être horizontale ou
verticale et s'adapte au thème du moteur sélectionné.

### Intervieweur — À quoi sert **Barre perso minimale** ?

**Équipe DOSOFT —** Elle réduit la taille des portraits et compacte la
disposition. Ce mode est utile sur un écran chargé, sur une résolution élevée
ou lorsque la barre doit rester discrète au-dessus du jeu.

Lors de son activation, DOSOFT actualise la liste avant de reconstruire la
barre afin d'éviter qu'une liste ancienne ne la fasse disparaître.

### Intervieweur — Où est passé le **Fast Switch TEAM** ?

**Équipe DOSOFT —** Cette fonction expérimentale est temporairement retirée de
l'interface. Son ancien système de barre fantôme pouvait devenir instable lors
des reconstructions, des changements d'équipe ou selon la mise à l'échelle de
Windows. DOSOFT la force donc désactivée pendant sa refonte.

Les anciens réglages et le raccourci mémorisé ne sont pas effacés, mais ils ne
sont plus exécutés. Le sélecteur normal **ALL / Team 1 / Team 2** reste
disponible et constitue le moyen recommandé de changer d'équipe.

### Intervieweur — Le **Raccourci de changement de TEAM** fonctionne-t-il ?

**Équipe DOSOFT —** Non, il est lui aussi neutralisé tant que le Fast Switch est
en cours de refonte. Utilisez le sélecteur Team 1 / Team 2 de la fenêtre
principale.

---

## 8. Gestionnaire de binds avancés

### Intervieweur — Quelle différence avec Suivant et Précédent ?

**Équipe DOSOFT —** Les binds avancés offrent un accès direct. Deux logiques
sont proposées :

- **cycle** : la touche cible une place de l'ordre actuel. La ligne 1 cible
  toujours le premier personnage, même si le pseudo change ;
- **bind** : la touche reste attachée à un pseudo précis, même si sa position
  change dans l'initiative.

### Intervieweur — À quoi sert le **Préfixe global** ?

**Équipe DOSOFT —** Il ajoute automatiquement `Ctrl`, `Alt`, `Maj` ou aucun
modificateur à toutes les touches du gestionnaire. Cela permet par exemple de
réserver `Ctrl+F1` à `Ctrl+F8` sans saisir Ctrl huit fois.

### Intervieweur — Pourquoi les binds `cycle` affichent-ils huit places ?

**Équipe DOSOFT —** Huit est le format courant d'une équipe Dofus. Une place
vide reste disponible et deviendra fonctionnelle lorsqu'un personnage occupera
cette position.

---

## 9. Auto-Focus Dofus Rétro

### Intervieweur — Pourquoi l'Auto-Focus est-il spécifique à Rétro dans cette bêta ?

**Équipe DOSOFT —** Dofus Rétro publie des notifications Windows suffisamment
structurées pour identifier le personnage concerné et le type d'événement. Le
moteur Wakfu expérimental précédent n'offrait pas une fiabilité suffisante et
n'est donc pas présenté comme fonction stable dans la 1.3.8.

La mécanique Rétro s'inspire de l'approche de Dracoon par Slyss42, créditée dans
le projet, puis ajoute le routage multilingue, les filtres et les sécurités
propres à DOSOFT.

### Intervieweur — Comment l'activer ?

**Équipe DOSOFT —**

1. Sélectionnez le moteur **Rétro**.
2. Vérifiez que les notifications Windows de Dofus Rétro sont autorisées.
3. Activez le bouton Auto-Focus visible à droite des moteurs.
4. Ouvrez son bouton `⚙` pour choisir les événements autorisés.

### Intervieweur — Quels événements peuvent déclencher le focus ?

**Équipe DOSOFT —** Chaque catégorie peut être cochée indépendamment :

- tour de combat ;
- message privé ;
- demande d'échange ;
- invitation de groupe ou de guilde ;
- défi ;
- atelier ou artisanat ;
- attaque de percepteur / événement PvP.

Une catégorie désactivée reste visible dans Windows mais est ignorée par
DOSOFT.

### Intervieweur — Est-ce limité au français ?

**Équipe DOSOFT —** Non. Les catégories enregistrées sont des identifiants
stables (`combat`, `trade`, `group`, etc.) et le moteur reconnaît plusieurs
formulations linguistiques. Changer la langue du jeu ne modifie donc pas la
liste de préférences enregistrée.

### Intervieweur — Que signifie **Moteur Auto-Focus : Automatique / Polling** ?

**Équipe DOSOFT —**

- **Automatique** tente d'abord l'abonnement événementiel Windows et utilise un
  polling réactif comme solution de secours ;
- **Polling** force le mode de dépannage lorsque l'abonnement Windows est
  indisponible ou instable.

Le mode Automatique est recommandé. Un changement de moteur de notifications
nécessite un redémarrage de DOSOFT.

### Intervieweur — Où trouver les informations de diagnostic ?

**Équipe DOSOFT —** Dans **Paramètres > Diagnostic Auto-Focus Rétro > Ouvrir le
journal**. Le fichier `retro-autofocus-debug.log` indique le backend utilisé,
les notifications reconnues ou ignorées et les tentatives de focus.

---

## 10. Outils de fenêtres Dofus Rétro

### Intervieweur — Que fait **Agrandir tout** ?

**Équipe DOSOFT —** Il maximise toutes les fenêtres Rétro actuellement
détectées. Une fenêtre déjà maximisée reste dans cet état.

### Intervieweur — Que fait **Ranger les fenêtres** ?

**Équipe DOSOFT —** Il remplit la zone utilisable de l'écran où se trouve le
Chef — ou la première fenêtre si aucun Chef n'est défini. Avec huit comptes,
la disposition devient une grille de quatre colonnes et deux lignes.

Le calcul prend en compte les bordures invisibles de redimensionnement de
Windows afin de limiter les espaces entre les fenêtres. Les fenêtres sont
restaurées avant d'être placées si elles étaient minimisées ou maximisées.

### Intervieweur — Est-ce que cela fonctionne sur plusieurs écrans ?

**Équipe DOSOFT —** Oui, mais la mosaïque remplit un seul écran à la fois :
celui de la fenêtre Chef, ou celui de la première fenêtre détectée. Déplacez le
Chef sur l'écran souhaité avant de lancer le rangement.

---

## 11. Sauvegarde de l'affichage Dofus : **JEU CLASSIQUE**

### Intervieweur — Quel problème cette fonction résout-elle ?

**Équipe DOSOFT —** Dofus Unity peut perdre ou modifier certaines positions
d'interface et préférences de compte : widgets, barres d'action, chat,
timeline, changement de fenêtre en fin de tour, affichage des informations,
échelle, audio ou paramètres graphiques.

Le profil **JEU CLASSIQUE** permet de préparer une configuration modèle, puis
de la réappliquer à tous les comptes locaux.

### Intervieweur — Est-ce une copie complète de mon compte ?

**Équipe DOSOFT —** Non. DOSOFT copie uniquement une liste contrôlée de
réglages d'affichage, d'interface, d'entrée, d'audio et de combat. Les données
de connexion, historiques, progression et informations sociales ne font pas
partie du profil.

### Intervieweur — Comment créer le profil maître ?

**Équipe DOSOFT —**

1. Ouvrez le compte dont l'interface est votre référence.
2. Configurez parfaitement les interfaces normale et combat.
3. Fermez ce compte en dernier pour que ses fichiers soient les plus récents.
4. Fermez ensuite tous les clients Dofus.
5. Ouvrez **Paramètres > Affichage Dofus**.
6. Cliquez sur **Enregistrer JEU CLASSIQUE**.

DOSOFT utilise comme référence le compte dont les fichiers valides sont les
plus récents.

### Intervieweur — Que fait **Appliquer aux comptes** ?

**Équipe DOSOFT —** DOSOFT crée d'abord une sauvegarde de retour, puis applique
le profil maître aux fichiers d'interface de tous les comptes détectés.

Tous les clients Dofus doivent être fermés. Un client ouvert pourrait réécrire
ses anciens réglages par-dessus les nouveaux au moment de quitter.

### Intervieweur — Quelle différence entre **Enregistrer JEU CLASSIQUE** et **Sauvegarder maintenant** ?

**Équipe DOSOFT —**

- **Enregistrer JEU CLASSIQUE** extrait les réglages autorisés du compte de
  référence pour créer le modèle réutilisable ;
- **Sauvegarder maintenant** archive l'état complet des fichiers ciblés dans
  un ZIP vérifié, sans remplacer le profil maître.

### Intervieweur — Que fait **Restaurer la dernière** ?

**Équipe DOSOFT —** La fonction crée d'abord une sauvegarde de l'état actuel,
puis restaure la dernière archive disponible. Cette étape supplémentaire évite
qu'une restauration mal choisie soit irréversible.

### Intervieweur — Où sont les fichiers Dofus concernés ?

**Équipe DOSOFT —** La 1.3.8 recherche la branche Unity `RELEASE` sous :

`%USERPROFILE%\AppData\LocalLow\Ankama\Dofus\RELEASE`

Les profils et sauvegardes DOSOFT restent, eux, dans
`%APPDATA%\DOSOFT\dofus-display`.

---

## 12. Extension OBS — philosophie et activation

### Intervieweur — L'extension OBS est-elle obligatoire pour utiliser DOSOFT ?

**Équipe DOSOFT —** Non. C'est une extension volontaire. Tant qu'elle n'est
pas activée dans les paramètres, ses boutons, son badge de connexion et son
Streamdeck restent cachés.

### Intervieweur — Quel problème résout Dofus Scene Guard ?

**Équipe DOSOFT —** Pour un streamer multicompte, une capture d'écran ou une
capture de fenêtre mal configurée peut révéler un navigateur, le bureau ou une
autre activité pendant un Alt+Tab. Dofus Scene Guard limite OBS aux fenêtres de
jeu synchronisées et suit le personnage sélectionné par DOSOFT.

### Intervieweur — Quelle est l'architecture recommandée dans OBS ?

**Équipe DOSOFT —**

```text
Scène Stream
└── source de scène → Jeu_Dofus_Unity / Jeu_Dofus_Rétro / Jeu_Wakfu
    └── captures de personnages créées et pilotées par DOSOFT
```

Les scènes de jeu par défaut sont :

- `Jeu_Dofus_Unity` ;
- `Jeu_Dofus_Rétro` ;
- `Jeu_Wakfu`.

La scène `Stream` reste votre composition publique avec overlays, caméra et
alertes. DOSOFT ne force pas le programme OBS à quitter cette scène lorsqu'il
change de personnage : il change les sources à l'intérieur de la scène de jeu
imbriquée.

### Intervieweur — Quel type de capture est utilisé ?

**Équipe DOSOFT —**

- Unity : capture de jeu associée à la fenêtre ciblée ;
- Dofus Rétro : capture de fenêtre via Windows Graphics Capture ;
- Wakfu : capture de fenêtre via Windows Graphics Capture, car le hook de
  capture de jeu Java/OpenGL s'est montré trop saccadé.

La capture du curseur est activée lors de la création des sources.

Pour Unity, une nouvelle capture est automatiquement centrée et ajustée au
canevas vidéo OBS tout en conservant ses proportions. Cela empêche une fenêtre
4K ou un écran avec une forte mise à l'échelle d'apparaître zoomé dans une
scène 1080p. Un cadrage que l'utilisateur a déjà déplacé, rogné ou redimensionné
manuellement n'est pas remplacé.

---

## 13. Assistant OBS en trois étapes

### Intervieweur — Que faut-il préparer avant d'ouvrir l'assistant ?

**Équipe DOSOFT —**

- OBS Studio 32.x en 64 bits ;
- le connecteur installé par le setup ;
- OBS complètement relancé après l'installation ;
- au moins une fenêtre du jeu ouverte ;
- une scène principale de stream existante ou un nom que vous identifiez.

### Intervieweur — Que fait l'étape 1, **Détecter OBS et ses scènes** ?

**Équipe DOSOFT —** Elle vérifie le processus OBS, la communication locale, la
version du plugin et l'inventaire des scènes et sources. Si une des trois scènes
de jeu attendues est absente, l'assistant la crée automatiquement puis contrôle
le résultat.

### Intervieweur — Que dois-je choisir dans les sélecteurs ?

**Équipe DOSOFT —** Les sélecteurs sont en lecture seule pour éviter les fautes
de frappe. Après l'étape 1, choisissez :

- **Scène principale / retour** : votre scène publique, généralement `Stream` ;
- **Scène Dofus gérée par DOSOFT** : la scène du moteur actif ;
- **Scène de secours** : scène affichée en cas de fermeture réelle du jeu ;
- **Scène pause** : cible du bouton Pause du Streamdeck ;
- **Source micro** : source audio à couper/réactiver ;
- **Scène contenant la caméra** : scène dans laquelle chercher la caméra ;
- **Source caméra** : source à masquer/réafficher.

Les valeurs par défaut sont `Stream`, `Pause`, `Mic/Aux`, `CAM` et `Caméra`,
mais elles doivent correspondre aux noms réellement présents dans votre OBS.

### Intervieweur — Que fait l'étape 2, **Créer et relier la scène Dofus** ?

**Équipe DOSOFT —** Elle enregistre les choix, crée la scène de jeu si
nécessaire et ajoute cette scène comme source dans la scène principale. Une
confirmation affiche le nom exact de la nouvelle source liée.

### Intervieweur — Que fait l'étape 3, **Synchroniser les personnages détectés** ?

**Équipe DOSOFT —** Elle commence par actualiser DOSOFT, puis transmet les
fenêtres prêtes au plugin. OBS crée les captures manquantes, les associe aux
bonnes fenêtres et prépare leur première activation.

Une source existante n'est pas dupliquée. Si une même fenêtre change de pseudo
après la connexion d'un nouveau personnage, DOSOFT resynchronise son identité
au lieu de rester bloqué sur l'ancien nom.

### Intervieweur — Que signifie **Enregistrer ces choix sur cet ordinateur** ?

**Équipe DOSOFT —** Ce bouton écrit uniquement le profil local dans
`%APPDATA%\DOSOFT\obs_profile.json`. Il ne crée, ne supprime et ne reconstruit
aucune source dans OBS.

Utilisez-le lorsque vous voulez mémoriser un nom de scène, une option de secours
ou la configuration du Streamdeck sans toucher immédiatement à OBS.

---

## 14. Auto-swap OBS, Alt+Tab et scène de secours

### Intervieweur — Que fait **Auto-swap des clients Dofus** ?

**Équipe DOSOFT —** À chaque changement de personnage confirmé, DOSOFT indique
au plugin quelle capture doit devenir visible. La nouvelle source est affichée
avant de masquer l'ancienne, ce qui évite un écran noir entre deux personnages.

### Intervieweur — Que se passe-t-il si je fais Alt+Tab vers un navigateur ?

**Équipe DOSOFT —** Rien ne change dans OBS. Le plugin conserve la dernière
capture de jeu valide. L'Alt+Tab n'est pas traité comme une erreur et ne doit ni
révéler le bureau, ni envoyer automatiquement la scène de secours.

### Intervieweur — Quand la scène de secours est-elle utilisée ?

**Équipe DOSOFT —** Seulement si l'option est activée et qu'une erreur réelle
est confirmée : fermeture ou disparition des fenêtres de jeu synchronisées,
capture devenue irrécupérable ou état explicitement signalé comme indisponible.

Lorsque le jeu revient et qu'une fenêtre valide est de nouveau synchronisée,
le connecteur reprend la sélection normale.

### Intervieweur — Pourquoi conserver une limite de captures ?

**Équipe DOSOFT —** Les changements fréquents de personnages peuvent laisser
des sources anciennes. La limite — 12 par défaut — permet de nettoyer les
captures gérées par DOSOFT avant que leur accumulation ne ralentisse OBS. Les
autres sources et scènes de l'utilisateur ne sont pas concernées.

### Intervieweur — Que fait **Reconstruire uniquement les captures DOSOFT** ?

**Équipe DOSOFT —** La commande supprime les captures portant les préfixes
gérés par DOSOFT, puis les recrée à partir des fenêtres actuellement détectées.
Elle ne doit pas supprimer vos overlays, alertes, textes ou autres sources OBS.

---

## 15. Streamdeck flottant

### Intervieweur — Pourquoi l'appeler Streamdeck alors qu'il ne s'agit pas d'un appareil physique ?

**Équipe DOSOFT —** Le terme désigne ici un petit panneau logiciel de commandes
rapides. Il reste au-dessus des fenêtres et pilote OBS en un clic. Comme le
connecteur capture uniquement les fenêtres du jeu, ce dock n'apparaît pas dans
les captures gérées par DOSOFT.

### Intervieweur — Quels boutons sont fournis au départ ?

**Équipe DOSOFT —** Trois commandes prédéfinies :

- **Micro** : coupe ou réactive la source audio configurée ;
- **Caméra** : masque ou réaffiche la source caméra dans sa scène ;
- **Pause** : alterne entre la scène Pause et la scène de retour.

Ces boutons peuvent être réordonnés ou retirés du dock. Leur suppression les
masque dans le profil utilisateur ; elle ne supprime pas les sources OBS.

### Intervieweur — Pourquoi certains boutons restent-ils colorés après un clic ?

**Équipe DOSOFT —** Une couleur persistante représente un état durable : micro
muet, caméra cachée, pause active, scène temporaire active ou source masquée.
Un second clic revient à l'état précédent.

Une commande momentanée comme **Aller à une scène** ne doit pas rester rouge ou
attendre un second clic. Son retour visuel s'éteint dès que la commande est
confirmée.

### Intervieweur — Quelles commandes personnalisées peut-on créer ?

**Équipe DOSOFT —**

- **Aller à une scène** : changement simple, sans état persistant ;
- **Scène / retour au second clic** : premier clic vers la scène choisie,
  second clic vers la scène de retour ;
- **Montrer / cacher une source** : interrupteur de visibilité ;
- **Couper / activer une source audio** : interrupteur audio.

Chaque bouton reçoit un nom, une icône et une cible choisie dans l'inventaire
OBS.

### Intervieweur — Puis-je changer l'apparence du dock ?

**Équipe DOSOFT —** Oui. **Gérer le Streamdeck** permet de choisir :

- la taille générale du dock ;
- une disposition horizontale ;
- une disposition verticale ;
- une grille de deux colonnes ;
- une grille de trois colonnes ;
- l'ordre des boutons ;
- des icônes simples : micro, caméra, pause, lecture, jeu, web, écran, œil,
  image, discussion, accueil, sécurité, etc.

### Intervieweur — Que signifie un fond rouge sur un bouton ?

**Équipe DOSOFT —** Il indique généralement l'état « coupé », « caché » ou
« pause active » d'une commande persistante. L'état n'est mis à jour qu'après
confirmation par OBS afin d'éviter qu'un bouton affiche une réussite alors que
la commande a échoué.

---

## 16. Extension désactivée, connexion et compatibilité

### Intervieweur — Que se passe-t-il si je n'active pas l'extension ?

**Équipe DOSOFT —** Aucun artefact OBS n'est affiché dans l'interface
principale : pas de badge, pas de bouton rapide, pas de Streamdeck et pas de
connexion locale persistante.

### Intervieweur — Comment lire le badge OBS ?

**Équipe DOSOFT —**

- vert : plugin connecté ;
- orange : connexion à vérifier ou avertissement de compatibilité ;
- rouge : OBS déconnecté ;
- violet : profil à configurer ;
- état incompatible : versions de protocole non compatibles.

Le badge est contrôlé périodiquement et réagit à la fermeture d'OBS sans exiger
un survol de la souris.

### Intervieweur — Que se passe-t-il après une mise à jour d'OBS ou du plugin ?

**Équipe DOSOFT —** Le profil utilisateur est stocké séparément du binaire du
plugin. Remplacer la DLL ou mettre à jour DOSOFT ne doit donc pas effacer les
scènes, noms de sources, boutons personnalisés ou leur ordre.

Le protocole annonce ses capacités. Une fonction trop récente est refusée avec
un message explicite plutôt que d'envoyer une commande inconnue. Une nouvelle
version majeure d'OBS doit toutefois être testée hors stream avant validation.

---

## 17. Langues, clavier et thèmes

### Intervieweur — Quelles langues sont proposées ?

**Équipe DOSOFT —** Français, anglais, espagnol, portugais et allemand. La
langue se choisit dans **Paramètres > Langue**.

### Intervieweur — Pourquoi choisir une disposition clavier ?

**Équipe DOSOFT —** Les noms et positions de certaines touches diffèrent entre
AZERTY et QWERTY. Choisissez `azerty_fr` ou `qwerty_us` pour que la capture et
l'affichage des raccourcis correspondent à votre clavier.

### Intervieweur — Les thèmes changent-ils le fonctionnement ?

**Équipe DOSOFT —** Non. Les thèmes Unity, Rétro et Wakfu modifient la palette,
les textures et certains portraits. Ils ne changent ni la détection, ni les
raccourcis, ni le profil OBS.

---

## 18. Commandes de groupe et sécurité

### Intervieweur — À quoi sert le Chef ?

**Équipe DOSOFT —** Le Chef est le point de retour privilégié :

- le raccourci Chef lui rend le focus ;
- le tri de la barre Windows tente de revenir sur lui ;
- la mosaïque Rétro utilise son écran comme écran cible ;
- certaines commandes de groupe utilisent son pseudo comme référence.

### Intervieweur — Que fait **Fermer Team** ?

**Équipe DOSOFT —** Après confirmation, DOSOFT demande une fermeture propre de
toutes les fenêtres incluses dans la boucle active. En mode Team 1, seule Team 1
est concernée ; en mode ALL, tous les comptes actifs le sont.

### Intervieweur — Que fait **Reset Settings** ?

**Équipe DOSOFT —** La réinitialisation complète remet à zéro les raccourcis,
équipes, thèmes et profil OBS après confirmation. Les archives d'affichage
Dofus ne sont pas supprimées.

Utilisez cette commande uniquement lorsqu'un profil est devenu incohérent et
qu'une correction ciblée ne suffit pas.

---

## 19. Dépannage rapide

### Intervieweur — Un personnage n'apparaît pas. Que faire ?

**Équipe DOSOFT —**

1. Vérifiez le moteur choisi.
2. Vérifiez que la fenêtre du jeu est visible et possède un titre normal.
3. Cliquez sur **Rafraîchir**.
4. Si le personnage vient juste de se connecter dans une ancienne fenêtre,
   changez une fois de fenêtre puis rafraîchissez.
5. Vérifiez qu'il n'a pas été désactivé dans la liste.

### Intervieweur — Suivant/Précédent ne change rien.

**Équipe DOSOFT —** Vérifiez que :

- au moins un compte est actif dans la boucle choisie ;
- le raccourci n'est pas vide ;
- aucune autre fonction n'utilise la même combinaison ;
- le jeu correspond au moteur sélectionné ;
- **Superposer les raccourcis** est désactivé pendant le diagnostic.

### Intervieweur — L'Auto-Focus Rétro voit des notifications mais ne change pas de fenêtre.

**Équipe DOSOFT —** Vérifiez la catégorie d'événement, le pseudo présent dans
la notification, les notifications Windows et le journal Auto-Focus. Essayez
le mode Automatique avant de forcer Polling.

### Intervieweur — OBS est ouvert mais DOSOFT dit que le plugin est introuvable.

**Équipe DOSOFT —**

1. Fermez complètement OBS.
2. Réinstallez le composant OBS depuis le setup.
3. Relancez OBS et attendez la fin de son chargement.
4. Ouvrez l'assistant puis relancez l'étape 1.
5. Si le problème continue, consultez le journal OBS et
   `%APPDATA%\DOSOFT\dosoft-obs-debug.log` lorsque les diagnostics sont activés.

### Intervieweur — Une scène de jeu existe mais les personnages ne se remplacent pas.

**Équipe DOSOFT —** Lancez l'étape 3 de synchronisation. Si l'inventaire est
toujours incohérent, utilisez **Reconstruire uniquement les captures DOSOFT**.
Ne supprimez pas manuellement toutes les scènes pendant qu'une synchronisation
est en cours.

### Intervieweur — La barre de personnages disparaît ou paraît mal dimensionnée.

**Équipe DOSOFT —** Désactivez puis réactivez **Barre persos**, lancez un
rafraîchissement et testez le mode minimal. La barre applique une correction de
mise à l'échelle pour les écrans 125 %, 150 %, 2K et 4K ; un journal
`quickbar-debug.log` est disponible dans le dossier DOSOFT pour un rapport de
bug.

### Intervieweur — Quels fichiers joindre à un rapport de bug ?

**Équipe DOSOFT —** Indiquez d'abord la version de DOSOFT, le moteur, la version
d'OBS et les étapes exactes. Joignez uniquement les journaux utiles :

- `retro-autofocus-debug.log` pour l'Auto-Focus Rétro ;
- `quickbar-debug.log` pour les barres flottantes ;
- `dosoft-obs-debug.log` pour le connecteur DOSOFT → OBS ;
- `%TEMP%\dofus-scene-guard-swap.log` pour les transitions du plugin OBS ;
- `retro-window-layout.log` pour le rangement des fenêtres Rétro ;
- `hotkey-debug.log` si un incident concerne les raccourcis.

Relisez les fichiers avant de les publier et retirez toute information que vous
ne souhaitez pas partager.

---

## 20. Parcours recommandé pour un nouvel utilisateur

### Intervieweur — Quel est le chemin le plus simple pour commencer sans se perdre ?

**Équipe DOSOFT —**

1. Installez DOSOFT sans activer immédiatement toutes les options.
2. Sélectionnez votre moteur de jeu.
3. Ouvrez vos clients et cliquez sur **Rafraîchir**.
4. Affectez un Chef et vérifiez l'ordre des personnages.
5. Testez **Suivant**, **Précédent** et **Chef**.
6. Créez Team 1 et Team 2 uniquement si vous en avez besoin.
7. Activez la barre de personnages, puis le mode minimal si souhaité.
8. Pour Rétro, testez l'Auto-Focus avec une seule catégorie avant de tout
   activer.
9. Préparez ensuite le profil JEU CLASSIQUE, jeux fermés.
10. Activez enfin l'extension OBS et suivez ses trois étapes.
11. Testez Alt+Tab, fermeture du jeu, scène de secours, micro, caméra et pause
    hors stream.
12. N'activez **Superposer les raccourcis** que si votre manière de jouer en a
    réellement besoin.

---

## 21. Checklist avant un stream

- [ ] DOSOFT et OBS affichent les versions attendues.
- [ ] Le bon moteur de jeu est sélectionné.
- [ ] Tous les personnages utiles sont détectés et actifs.
- [ ] Le Chef et l'ordre de boucle sont corrects.
- [ ] Les raccourcis Suivant, Précédent et Chef fonctionnent.
- [ ] Les scènes `Jeu_*` existent dans OBS.
- [ ] L'étape 3 de synchronisation confirme que les captures sont prêtes.
- [ ] La scène principale contient la scène de jeu gérée par DOSOFT.
- [ ] Un Alt+Tab conserve la dernière image de jeu.
- [ ] La fermeture réelle du jeu déclenche la scène de secours si elle est
  activée.
- [ ] Les boutons Micro, Caméra et Pause ciblent les bonnes sources.
- [ ] Les actions momentanées du Streamdeck ne restent pas colorées.
- [ ] Le setup et le plugin ont été testés hors stream.

---

## 22. Résumé des choix importants

| Fonction | Pourquoi elle existe | Recommandation |
|---|---|---|
| Suivant / Précédent | Parcourir rapidement l'ordre actif | À configurer en premier |
| Chef | Revenir à une fenêtre de référence | Définir un Chef par groupe |
| Team 1 / Team 2 | Séparer plusieurs groupes | Facultatif |
| Barre persos | Accès visuel direct aux personnages | Utile sur un second écran |
| Fast Switch TEAM | Fonction expérimentale en cours de refonte | Temporairement indisponible |
| Roue radiale | Sélection directe autour du curseur | Alternative aux binds directs |
| Superposer les raccourcis | Répéter une touche en gardant Alt/Ctrl/Maj | Expérimental, désactivé par défaut |
| Auto-Focus Rétro | Réagir aux notifications autorisées | Tester catégorie par catégorie |
| JEU CLASSIQUE | Répliquer une interface fiable | Toujours fermer Dofus avant usage |
| Extension OBS | Protéger le stream et suivre le personnage | Facultative, test hors stream |
| Scène de secours | Réagir à une fermeture réelle du jeu | Ne se déclenche pas sur Alt+Tab |
| Streamdeck | Piloter OBS sans quitter le jeu | Configurer les cibles dans l'assistant |
| Reconstruction OBS | Réparer les captures gérées | À utiliser seulement en dépannage |

---

## 23. Limites de la bêta 1.3.8

- Windows 10/11 uniquement.
- Connecteur compilé et validé pour OBS Studio 32.x 64 bits.
- Installeur non signé numériquement.
- Mises à jour manuelles : aucune mise à jour automatique n'est appliquée.
- Auto-Focus Wakfu non proposé comme fonction stable.
- Auto-Focus Rétro dépend des notifications Windows du jeu.
- Le profil JEU CLASSIQUE cible la branche Dofus Unity `RELEASE` locale.

Cette notice décrit DOSOFT 1.3.8 bêta et le connecteur Dofus Scene Guard
0.3.1. Les intitulés peuvent légèrement varier selon la langue sélectionnée,
mais les fonctions et les fichiers enregistrés restent les mêmes.
