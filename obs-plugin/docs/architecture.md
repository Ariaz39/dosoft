# Architecture

## Règle de confidentialité

Une scène OBS ne change que si une instance Dofus connue est sélectionnée.
Une fenêtre de navigateur, le bureau, OBS, DOSOFT ou une boîte de dialogue
Windows ne peut donc jamais déclencher une scène de diffusion.

```text
Windows foreground HWND ─┐
                         ├─> Resolver ─> Scene controller OBS
DOSOFT active account ───┘          │
                                   └─> `FULL_CAM` seulement si toutes les fenêtres Dofus ferment
```

## Composants

| Dossier | Rôle |
| --- | --- |
| `src/core` | règles de résolution, correspondances fenêtre/source et état de sécurité |
| `src/platform` | lecture Windows du premier plan, PID, titre et classe de fenêtre |
| `src/adapters` | source d'événements DOSOFT et façade de l'API OBS |
| `src` | point d'entrée du module OBS et panneau de configuration |
| `data` | exemple de configuration utilisable sans modifier le code |
| `tests` | tests des règles sans nécessiter OBS ou Dofus |

## Décision de scène

1. Une notification DOSOFT valide est utilisée si le mode le permet.
2. Sinon, le `HWND` en premier plan est comparé aux instances Dofus détectées.
3. Si l'instance correspond à une règle configurée, seule sa capture est
   rendue visible dans `Jeu_Dofus` ; `Stream` reste la scène de programme.
4. Lors d'un Alt-Tab ou d'une fenêtre non-Dofus, aucune commande OBS n'est
   envoyée : la dernière capture Dofus reste à l'antenne.
5. Si toutes les fenêtres Dofus synchronisées disparaissent, OBS passe à
   `FULL_CAM`. Lorsqu'une fenêtre revient, `Stream` est restaurée.
